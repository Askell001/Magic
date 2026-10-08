"""
Deck data models for MTG Deck Optimizer.
"""

from enum import Enum
from typing import List, Optional, Dict, Any, Set
from pydantic import BaseModel, Field, computed_field

from .card import Card


class DeckSection(str, Enum):
    COMMANDER = "commander"
    MAINDECK = "maindeck"
    SIDEBOARD = "sideboard"
    MAYBEBOARD = "maybeboard"


class DeckItem(BaseModel):
    quantity: int = Field(default=1, ge=1, description="Quantity of the card in this section")
    raw_name: str = Field(description="Name as originally parsed from the raw list")
    set_code: Optional[str] = Field(default=None, description="Set code if specified in export")
    collector_number: Optional[str] = Field(default=None, description="Collector number if specified")
    is_foil: bool = Field(default=False, description="Whether the card is foil")
    is_etched: bool = Field(default=False, description="Whether the card is etched foil")
    section: DeckSection = Field(default=DeckSection.MAINDECK, description="Target section in deck")
    custom_tags: List[str] = Field(default_factory=list, description="Tags like #Ramp, #Draw, Moxfield tags")
    card: Optional[Card] = Field(default=None, description="Resolved Scryfall card metadata")

    @computed_field
    @property
    def effective_name(self) -> str:
        """Returns resolved card name if available, otherwise raw parsed name."""
        return self.card.name if self.card else self.raw_name

    @computed_field
    @property
    def total_price_usd(self) -> Optional[float]:
        """Calculates total estimated price for this line item in USD."""
        if not self.card or not self.card.prices:
            return None
        unit_price = self.card.prices.usd_foil if self.is_foil and self.card.prices.usd_foil is not None else self.card.prices.usd
        if unit_price is not None:
            return round(unit_price * self.quantity, 2)
        return None


class Deck(BaseModel):
    name: str = Field(default="Untitled Deck", description="Deck name")
    format: str = Field(default="commander", description="Target MTG format (commander, standard, modern, etc.)")
    commanders: List[DeckItem] = Field(default_factory=list, description="Commander(s) / Oathbreaker / Companion")
    maindeck: List[DeckItem] = Field(default_factory=list, description="Main deck cards")
    sideboard: List[DeckItem] = Field(default_factory=list, description="Sideboard cards")
    maybeboard: List[DeckItem] = Field(default_factory=list, description="Maybeboard / Considering / Wishlist")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata / source info")

    @computed_field
    @property
    def total_card_count(self) -> int:
        """Total number of physical cards in commanders + maindeck."""
        return sum(item.quantity for item in self.commanders) + sum(item.quantity for item in self.maindeck)

    @computed_field
    @property
    def total_cards(self) -> int:
        """Alias for total_card_count."""
        return self.total_card_count

    @computed_field
    @property
    def commander_count(self) -> int:
        return sum(item.quantity for item in self.commanders)

    @computed_field
    @property
    def maindeck_count(self) -> int:
        return sum(item.quantity for item in self.maindeck)

    @computed_field
    @property
    def sideboard_count(self) -> int:
        return sum(item.quantity for item in self.sideboard)

    @computed_field
    @property
    def maybeboard_count(self) -> int:
        return sum(item.quantity for item in self.maybeboard)

    @computed_field
    @property
    def color_identity(self) -> List[str]:
        """Deck color identity based on commanders, or union of colored cards if commander identity unresolved."""
        colors: Set[str] = set()
        
        # 1. Primary: Evaluate all commanders
        if self.commanders:
            for item in self.commanders:
                if item.card and item.card.color_identity:
                    colors.update(item.card.color_identity)
                elif item.card and item.card.colors:
                    colors.update(item.card.colors)
                elif item.card and item.card.card_faces:
                    for f in item.card.card_faces:
                        if f.colors:
                            colors.update(f.colors)
                else:
                    # Check Archetype Registry as safe zero-network fallback
                    clean_name = item.effective_name.lower().strip()
                    # Also check front face if DFC
                    front_name = clean_name.split(" // ")[0].split(" / ")[0].strip()
                    try:
                        from ..deckbuilder.archetype_database import CARD_METADATA_REGISTRY
                        for reg_k, reg_v in CARD_METADATA_REGISTRY.items():
                            reg_lower = reg_k.lower()
                            if reg_lower == clean_name or reg_lower == front_name:
                                colors.update(reg_v[1])
                                break
                    except Exception:
                        pass
        
        # 2. Fallback: If no commander or commander colors couldn't be resolved, infer from colored non-land cards in maindeck
        if not colors and self.maindeck:
            for item in self.maindeck:
                if item.card and item.card.color_identity and "Land" not in item.card.type_line:
                    colors.update(item.card.color_identity)
                elif item.card and item.card.colors and "Land" not in item.card.type_line:
                    colors.update(item.card.colors)

        # Standard WUBRG sort order
        wubrg = ["W", "U", "B", "R", "G"]
        return [c for c in wubrg if c in colors]

    @computed_field
    @property
    def estimated_total_usd(self) -> Optional[float]:
        """Calculates total estimated cost for Maindeck + Commanders in USD."""
        total = 0.0
        has_prices = False
        for item in self.commanders + self.maindeck:
            p = item.total_price_usd
            if p is not None:
                total += p
                has_prices = True
        return round(total, 2) if has_prices else None


    @computed_field
    @property
    def commander_name(self) -> Optional[str]:
        """Returns the primary commander name if present."""
        if self.commanders:
            return self.commanders[0].effective_name
        return None

    @computed_field
    @property
    def average_cmc_without_lands(self) -> float:
        """Calculates average CMC of non-land cards."""
        non_lands = [it for it in self.commanders + self.maindeck if not (it.card and "Land" in it.card.type_line)]
        if not non_lands:
            return 0.0
        total_cmc = sum((it.card.cmc if it.card else 0.0) * it.quantity for it in non_lands)
        total_qty = sum(it.quantity for it in non_lands)
        return round(total_cmc / total_qty, 2) if total_qty > 0 else 0.0

    @computed_field
    @property
    def total_price_usd(self) -> Optional[float]:
        return self.estimated_total_usd

    def get_items_by_section(self, section: DeckSection) -> List[DeckItem]:
        if section == DeckSection.COMMANDER:
            return self.commanders
        elif section == DeckSection.MAINDECK:
            return self.maindeck
        elif section == DeckSection.SIDEBOARD:
            return self.sideboard
        elif section == DeckSection.MAYBEBOARD:
            return self.maybeboard
        return []

    def get_all_items(self) -> List[DeckItem]:
        return self.commanders + self.maindeck + self.sideboard + self.maybeboard

    @property
    def items(self) -> List[DeckItem]:
        """Convenient accessor for all deck items across sections."""
        return self.get_all_items()

    def get_moxfield_categorized_items(self) -> Dict[str, List[DeckItem]]:
        """
        Groups all maindeck and commander items into standard MTG/Moxfield categories:
        Commander, Planeswalkers, Creatures, Instants, Sorceries, Artifacts, Enchantments, Battles, Lands.
        Guarantees accurate categorization even if card metadata is not pre-enriched or for DFCs.
        """
        cats = {
            "Commander": list(self.commanders),
            "Planeswalkers": [],
            "Creatures": [],
            "Instants": [],
            "Sorceries": [],
            "Artifacts": [],
            "Enchantments": [],
            "Battles": [],
            "Lands": [],
        }

        # Lazy load registry for zero-network type resolution fallback
        reg_map = {}
        try:
            from ..deckbuilder.archetype_database import CARD_METADATA_REGISTRY
            reg_map = {k.lower(): v[2] for k, v in CARD_METADATA_REGISTRY.items()}
        except Exception:
            pass

        for item in self.maindeck:
            tl = ""
            if item.card and item.card.type_line and item.card.type_line.strip() not in ("", "Card", "Magic Card", "Magic: The Gathering Card"):
                tl = item.card.type_line.lower()
            elif item.card and item.card.card_faces:
                tl = " // ".join(f.type_line or "" for f in item.card.card_faces).lower()

            if not tl or tl.strip() in ("", "card"):
                # 1. Lookup in metadata registry
                clean_n = item.effective_name.strip().lower()
                front_n = clean_n.split(" // ")[0].split(" / ")[0].strip()
                if clean_n in reg_map:
                    tl = reg_map[clean_n].lower()
                elif front_n in reg_map:
                    tl = reg_map[front_n].lower()

            if not tl or tl.strip() in ("", "card"):
                # 2. Try Scryfall client cache
                try:
                    from ..scryfall.client import ScryfallClient
                    scry = ScryfallClient()
                    c_obj = scry._cache_by_name.get(item.effective_name.lower()) or scry._find_in_cache(item.effective_name, None, None)
                    if c_obj and c_obj.type_line:
                        tl = c_obj.type_line.lower()
                except Exception:
                    pass

            if not tl or tl.strip() in ("", "card"):
                # 3. Intelligent Name Heuristics Fallback
                n_low = item.effective_name.lower()
                if any(w in n_low for w in ["island", "plains", "swamp", "mountain", "forest", "wastes", "land", "sanctuary", "grove", "tomb", "shrine", "foundry", "pool", "delta", "mire", "tarn", "strand", "mesa", "catacombs", "foothills", "heath", "tower", "orchard", "confluence", "city", "springs", "ridge", "estate", "village"]):
                    tl = "land"
                elif any(w in n_low for w in ["sol ring", "arcane signet", "fellwar stone", "thought vessel", "talisman", "mox", "lotus", "boots", "greaves", "skullclamp", "monolith", "crypt", "vault", "bauble", "stone", "chalice", "lens", "sphere", "lantern", "reservoir", "ring", "altar", "statuary", "banner", "horn"]):
                    tl = "artifact"
                elif any(w in n_low for w in ["counterspell", "drain", "swords", "path", "gift", "protection", "silence", "bolt", "warp", "pongify", "hybridization", "resculpt", "flusterstorm", "denial", "song", "intervention", "charm", "veto", "command", "instant"]):
                    tl = "instant"
                elif any(w in n_low for w in ["study", "remora", "tithe", "library", "arena", "connections", "project", "breach", "season", "tax", "dreams", "caress", "enchantment"]):
                    tl = "enchantment"
                elif any(w in n_low for w in ["jace", "teferi", "liliana", "chandra", "nissa", "ajani", "karn", "ugin", "bolas", "tamiyo", "narset", "oko", "planeswalker"]):
                    tl = "planeswalker"
                elif any(w in n_low for w in ["tutor", "wrath", "damnation", "act", "farewell", "windfall", "wheel", "ponder", "preordain", "reanimate", "loot", "spiral", "cultivate", "reach", "lore", "visits", "zenith", "finale", "sorcery"]):
                    tl = "sorcery"
                else:
                    tl = "creature"

            # MTG / Moxfield Category Assignment Hierarchy:
            # 1. Lands (Basic, Dual, Fetch, Artifact Land)
            if "land" in tl:
                cats["Lands"].append(item)
            # 2. Creatures (Creature, Artifact Creature, Enchantment Creature)
            elif "creature" in tl:
                cats["Creatures"].append(item)
            # 3. Planeswalkers
            elif "planeswalker" in tl:
                cats["Planeswalkers"].append(item)
            # 4. Battles
            elif "battle" in tl:
                cats["Battles"].append(item)
            # 5. Instants
            elif "instant" in tl:
                cats["Instants"].append(item)
            # 6. Sorceries
            elif "sorcery" in tl:
                cats["Sorceries"].append(item)
            # 7. Artifacts (Non-creature)
            elif "artifact" in tl:
                cats["Artifacts"].append(item)
            # 8. Enchantments (Non-creature)
            elif "enchantment" in tl:
                cats["Enchantments"].append(item)
            else:
                cats["Sorceries"].append(item)

        # Return only non-empty categories preserving standard Moxfield sort order
        return {k: v for k, v in cats.items() if v}
