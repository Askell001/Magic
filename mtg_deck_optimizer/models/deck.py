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
        """Deck color identity based on commanders, or union of all cards if no commander."""
        colors: Set[str] = set()
        source_items = self.commanders if self.commanders else self.maindeck
        for item in source_items:
            if item.card:
                colors.update(item.card.color_identity)
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
