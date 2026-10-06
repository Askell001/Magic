"""
Singleton Rule Validator and Official Commander Banlist Validator.
"""

from typing import Set, Dict, List, Tuple, Optional
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

# Official Commander Banlist (maintained by Commander Rules Committee / WotC)
OFFICIAL_COMMANDER_BANLIST: Set[str] = {
    "ancestral recall",
    "balance",
    "biorhythm",
    "black lotus",
    "braids, cabal minion",
    "channel",
    "chaos orb",
    "coalition victory",
    "dockside extortionist",
    "emrakul, the aeons torn",
    "erayo, soratami ascendant",
    "falling star",
    "fastbond",
    "flash",
    "gifts ungiven",
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
    "panoptic mirror",
    "paradox engine",
    "primeval titan",
    "prophet of kruphix",
    "recurring nightmare",
    "rofellos, llanowar emissary",
    "shahrazad",
    "sundering titan",
    "sway of the stars",
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
    def is_banned_in_commander(cls, card: Card) -> Tuple[bool, Optional[str]]:
        """
        Checks if a card is banned in Commander.
        Returns: (is_banned, ban_reason)
        """
        name_lower = card.name.strip().lower()

        # Check offline curated banlist
        if name_lower in OFFICIAL_COMMANDER_BANLIST:
            return True, f"La carta '{card.name}' está oficialmente PROHIBIDA (Banned) en Commander."

        # Check faces for DFCs
        if " // " in name_lower:
            front = name_lower.split(" // ")[0].strip()
            if front in OFFICIAL_COMMANDER_BANLIST:
                return True, f"La carta '{card.name}' está oficialmente PROHIBIDA (Banned) en Commander."

        # Check Scryfall legalities dictionary if populated
        if card.legalities:
            cmd_leg = card.legalities.get("commander", "legal").lower()
            if cmd_leg in ("banned", "not_legal", "restricted"):
                return True, f"La carta '{card.name}' no es legal en Commander según Scryfall (Estado: {cmd_leg})."

        # Check Conspiracy card type
        if "Conspiracy" in card.type_line:
            return True, f"Las cartas de tipo Conspiracy ('{card.name}') no son legales en Commander construido."

        return False, None
