"""
Deck analysis models for computing mana curves, color distributions, type breakdowns, and deck diagnostics.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from .deck import Deck, DeckItem


class DeckAnalysis(BaseModel):
    total_cards: int = Field(default=0, description="Total cards analyzed")
    mana_curve: Dict[int, int] = Field(default_factory=dict, description="Non-land CMC distribution, e.g. {1: 10, 2: 15}")
    avg_cmc_with_lands: float = Field(default=0.0, description="Average CMC including lands")
    avg_cmc_without_lands: float = Field(default=0.0, description="Average CMC excluding lands (true curve)")
    color_distribution: Dict[str, int] = Field(default_factory=dict, description="Count of cards containing each color")
    type_distribution: Dict[str, int] = Field(default_factory=dict, description="Count of cards per primary card type")
    rarity_distribution: Dict[str, int] = Field(default_factory=dict, description="Count of cards per rarity tier")
    estimated_total_usd: Optional[float] = Field(default=None, description="Estimated total cost in USD")
    estimated_total_eur: Optional[float] = Field(default=None, description="Estimated total cost in EUR")
    unresolved_cards: List[str] = Field(default_factory=list, description="Card names that could not be resolved from Scryfall")
    warnings: List[str] = Field(default_factory=list, description="Format legality and consistency warnings")

    @classmethod
    def from_deck(cls, deck: Deck) -> "DeckAnalysis":
        """Generates a complete DeckAnalysis from an enriched Deck."""
        active_items: List[DeckItem] = deck.commanders + deck.maindeck
        total_cards = sum(item.quantity for item in active_items)

        mana_curve: Dict[int, int] = {}
        type_distribution: Dict[str, int] = {}
        color_distribution: Dict[str, int] = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0, "C": 0}
        rarity_distribution: Dict[str, int] = {}
        unresolved: List[str] = []
        warnings: List[str] = []

        total_cmc_all = 0.0
        total_cmc_non_land = 0.0
        non_land_count = 0

        total_usd = 0.0
        total_eur = 0.0
        has_usd = False
        has_eur = False

        deck_ci = set(deck.color_identity)

        for item in active_items:
            card = item.card
            if not card:
                unresolved.append(item.raw_name)
                continue

            qty = item.quantity
            primary_t = card.primary_type
            type_distribution[primary_t] = type_distribution.get(primary_t, 0) + qty

            # Rarity
            rarity = card.rarity or "unknown"
            rarity_distribution[rarity] = rarity_distribution.get(rarity, 0) + qty

            # Colors
            if not card.colors:
                color_distribution["C"] += qty
            else:
                for c in card.colors:
                    if c in color_distribution:
                        color_distribution[c] += qty

            # Color identity check for Commander format
            if deck.format.lower() == "commander" and deck.commanders:
                card_ci = set(card.color_identity)
                if not card_ci.issubset(deck_ci):
                    diff = card_ci - deck_ci
                    warnings.append(
                        f"Card '{card.name}' contains color identity symbols {list(diff)} outside commander identity {deck.color_identity}."
                    )

            # Pricing
            if card.prices:
                unit_usd = card.prices.usd_foil if item.is_foil and card.prices.usd_foil is not None else card.prices.usd
                if unit_usd is not None:
                    total_usd += unit_usd * qty
                    has_usd = True
                unit_eur = card.prices.eur_foil if item.is_foil and card.prices.eur_foil is not None else card.prices.eur
                if unit_eur is not None:
                    total_eur += unit_eur * qty
                    has_eur = True

            # CMC & Curve
            is_land = "Land" in card.type_line
            cmc_int = int(card.cmc)

            total_cmc_all += card.cmc * qty
            if not is_land:
                total_cmc_non_land += card.cmc * qty
                non_land_count += qty
                mana_curve[cmc_int] = mana_curve.get(cmc_int, 0) + qty

        # Commander format specific size checks
        if deck.format.lower() == "commander":
            if total_cards != 100:
                warnings.append(f"Commander deck size is {total_cards} cards (should be exactly 100).")
            if not deck.commanders:
                warnings.append("Commander deck has no Commander specified.")

        # Sort mana curve keys
        sorted_curve = {k: mana_curve[k] for k in sorted(mana_curve.keys())}

        avg_all = round(total_cmc_all / total_cards, 2) if total_cards > 0 else 0.0
        avg_non_land = round(total_cmc_non_land / non_land_count, 2) if non_land_count > 0 else 0.0

        return cls(
            total_cards=total_cards,
            mana_curve=sorted_curve,
            avg_cmc_with_lands=avg_all,
            avg_cmc_without_lands=avg_non_land,
            color_distribution=color_distribution,
            type_distribution=type_distribution,
            rarity_distribution=rarity_distribution,
            estimated_total_usd=round(total_usd, 2) if has_usd else None,
            estimated_total_eur=round(total_eur, 2) if has_eur else None,
            unresolved_cards=unresolved,
            warnings=warnings,
        )
