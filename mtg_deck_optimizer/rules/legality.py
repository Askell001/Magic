"""
Singleton Rule Validator and Official Commander Banlist Validator.
"""

from typing import Set, Dict, List, Tuple, Optional, Union
from ..models.card import Card
from ..models.deck import Deck, DeckItem


# Basic land names that can be repeated indefinitely in Commander
BASIC_LANDS: Set[str] = {
    "plains",
    "island",
    "swamp",
    "mountain",
    "forest",
    "wastes",
    "snow-covered plains",
    "snow-covered island",
    "snow-covered swamp",
    "snow-covered mountain",
    "snow-covered forest",
    "snow-covered wastes",
}

# Cards with explicit rules text bypassing the Singleton rule (CR 100.2a)
UNLIMITED_COPY_CARDS: Set[str] = {
    "relentless rats",
    "shadowborn apostle",
    "rat colony",
    "persistent petitioners",
    "dragon's approach",
    "hare apparent",
    "slime against humanity",
}

# Official Commander Banlist loaded from banned_cards.json (curated format banlist)
OFFICIAL_COMMANDER_BANLIST: Set[str] = {
    "ancestral recall",
    "balance",
    "black lotus",
    "chaos orb",
    "channel",
    "dockside extortionist",
    "emrakul, the aeons torn",
    "erayo, soratami ascendant",
    "falling star",
    "fastbond",
    "flash",
    "golos, tireless pilgrim",
    "griselbrand",
    "hullbreacher",
    "iona, shield of emeria",
    "jeweled lotus",
    "karakas",
    "leovold, emissary of trest",
    "library of alexandria",
    "limited resources",
    "lutri, the spellchaser",
    "mana crypt",
    "mox emerald",
    "mox jet",
    "mox pearl",
    "mox ruby",
    "mox sapphire",
    "nadu, winged wisdom",
    "paradox engine",
    "primeval titan",
    "prophet of kruphix",
    "recurring nightmare",
    "rofellos, llanowar emissary",
    "shahrazad",
    "sundering titan",
    "sylvan primordial",
    "time vault",
    "time walk",
    "tinker",
    "tolarian academy",
    "trade secrets",
    "upheaval",
    "yawgmoth's bargain",
}


class SingletonValidator:
    """Validates the 1-copy Singleton rule for Commander decks with official exceptions."""

    @classmethod
    def is_singleton_exempt(cls, card_name: str, requested_quantity: int = 1) -> bool:
        name_lower = card_name.strip().lower()
        if name_lower in BASIC_LANDS:
            return True
        if name_lower in UNLIMITED_COPY_CARDS:
            return True
        if name_lower == "seven dwarves" and requested_quantity <= 7:
            return True
        return False

    @classmethod
    def validate_deck_singleton(cls, deck: Deck) -> List[str]:
        """Scans the deck for Singleton violations and returns error messages."""
        counts: Dict[str, int] = {}
        errors: List[str] = []

        for item in deck.commanders + deck.maindeck:
            name_clean = item.effective_name.strip().lower()
            counts[name_clean] = counts.get(name_clean, 0) + item.quantity

        for name, qty in counts.items():
            if qty > 1 and not cls.is_singleton_exempt(name, qty):
                errors.append(
                    f"Violación de Singleton: '{name.title()}' tiene {qty} copias en el mazo (máx. 1 permitido en Commander)."
                )

        return errors


class BanlistValidator:
    """Validates format legality against Scryfall legality metadata and the official banlist."""

    @classmethod
    def is_banned(cls, card_name_or_card: Union[str, Card]) -> bool:
        """Convenience method checking whether a card name or Card object is banned."""
        if isinstance(card_name_or_card, str):
            name_lower = card_name_or_card.strip().lower()
            if name_lower in OFFICIAL_COMMANDER_BANLIST:
                return True
            if " // " in name_lower and name_lower.split(" // ")[0].strip() in OFFICIAL_COMMANDER_BANLIST:
                return True
            return False
        banned, _ = cls.is_banned_in_commander(card_name_or_card)
        return banned

    @classmethod
    def is_banned_in_commander(cls, card: Card, is_companion: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Checks if a card is banned in Commander against the official banned_cards catalog.
        Returns: (is_banned, ban_reason)
        """
        name_lower = card.name.strip().lower()

        # Special Lutri Companion Rule
        if "lutri, the spellchaser" in name_lower:
            if is_companion:
                return True, "La carta 'Lutri, the Spellchaser' está PROHIBIDA únicamente como Compañero (Companion)."
            return False, None

        # Check curated format banlist (banned_cards.json / MongoDB)
        if name_lower in OFFICIAL_COMMANDER_BANLIST:
            return True, f"La carta '{card.name}' está oficialmente PROHIBIDA (Banned) en Commander."

        # Check faces for DFCs
        if " // " in name_lower:
            front = name_lower.split(" // ")[0].strip()
            if front in OFFICIAL_COMMANDER_BANLIST:
                return True, f"La carta '{card.name}' está oficialmente PROHIBIDA (Banned) en Commander."

        # Check Conspiracy card type
        if "Conspiracy" in card.type_line:
            return True, f"Las cartas de tipo Conspiracy ('{card.name}') no son legales en Commander construido."

        return False, None
