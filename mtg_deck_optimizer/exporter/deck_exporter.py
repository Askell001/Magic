"""
Deck Exporter & Modifier applying optimization recommendations and formatting standard MTG exports.
"""

from typing import List, Dict, Tuple, Optional
from copy import deepcopy

from ..models.deck import Deck, DeckItem, DeckSection
from ..models.card import Card, CardPrices
from ..ai.models import OptimizationReport, CardCut, CardInclusion


class DeckExporter:
    """Applies optimization changes to create an upgraded Deck and exports standard text lists."""

    @classmethod
    def apply_optimization(cls, original_deck: Deck, report: OptimizationReport) -> Tuple[Deck, Dict[int, int], float]:
        """
        Applies cuts and inclusions from the OptimizationReport to produce a new optimized Deck object.
        Returns: (optimized_deck, post_mana_curve, post_avg_cmc_without_lands)
        """
        new_deck = deepcopy(original_deck)
        new_deck.name = f"{original_deck.name} (Optimized - Bracket {report.target_bracket.value})"

        # Build set of card names to cut
        cut_names_to_remove = {cut.card_name.lower(): cut for cut in report.cuts}

        # 1. Apply cuts from maindeck
        filtered_maindeck: List[DeckItem] = []
        for item in new_deck.maindeck:
            name_lower = item.effective_name.lower()
            if name_lower in cut_names_to_remove:
                # Remove this instance
                del cut_names_to_remove[name_lower]
            else:
                filtered_maindeck.append(item)

        new_deck.maindeck = filtered_maindeck

        # 2. Apply inclusions
        for inc in report.inclusions:
            # Create Card model for inclusion
            inc_card = Card(
                id=f"opt_{inc.card_name.lower().replace(' ', '_')}",
                name=inc.card_name,
                cmc=inc.cmc,
                type_line=inc.type_line,
                prices=CardPrices(usd=inc.estimated_price_usd),
            )
            new_item = DeckItem(
                quantity=1,
                raw_name=inc.card_name,
                section=DeckSection.MAINDECK,
                card=inc_card,
            )
            new_deck.maindeck.append(new_item)

        # 3. Compute post-optimization mana curve and avg CMC
        curve: Dict[int, int] = {}
        non_land_cmcs: List[float] = []

        for it in new_deck.commanders + new_deck.maindeck:
            c = it.card
            if c:
                if "Land" not in c.type_line:
                    cmc_int = int(c.cmc)
                    curve[cmc_int] = curve.get(cmc_int, 0) + it.quantity
                    non_land_cmcs.extend([c.cmc] * it.quantity)
            else:
                non_land_cmcs.extend([3.0] * it.quantity)

        sorted_curve = {k: curve[k] for k in sorted(curve.keys())}
        post_avg_cmc = round(sum(non_land_cmcs) / len(non_land_cmcs), 2) if non_land_cmcs else 0.0

        return new_deck, sorted_curve, post_avg_cmc

    @classmethod
    def export_to_moxfield_text(cls, deck: Deck) -> str:
        """
        Formats the deck into standard plain text ready for 1-click import into Moxfield or Archidekt.
        """
        lines: List[str] = []

        # Commanders
        if deck.commanders:
            lines.append("// Commander")
            for it in deck.commanders:
                set_part = f" ({it.set_code.upper()})" if it.set_code else ""
                num_part = f" {it.collector_number}" if it.collector_number else ""
                foil_part = " *F*" if it.is_foil else ""
                lines.append(f"{it.quantity} {it.effective_name}{set_part}{num_part}{foil_part}")
            lines.append("")

        # Maindeck
        if deck.maindeck:
            lines.append("// Mainboard")
            for it in deck.maindeck:
                set_part = f" ({it.set_code.upper()})" if it.set_code else ""
                num_part = f" {it.collector_number}" if it.collector_number else ""
                foil_part = " *F*" if it.is_foil else ""
                lines.append(f"{it.quantity} {it.effective_name}{set_part}{num_part}{foil_part}")
            lines.append("")

        # Sideboard
        if deck.sideboard:
            lines.append("// Sideboard")
            for it in deck.sideboard:
                set_part = f" ({it.set_code.upper()})" if it.set_code else ""
                num_part = f" {it.collector_number}" if it.collector_number else ""
                foil_part = " *F*" if it.is_foil else ""
                lines.append(f"{it.quantity} {it.effective_name}{set_part}{num_part}{foil_part}")
            lines.append("")

        # Maybeboard / Considering
        if deck.maybeboard:
            lines.append("// Considering")
            for it in deck.maybeboard:
                set_part = f" ({it.set_code.upper()})" if it.set_code else ""
                num_part = f" {it.collector_number}" if it.collector_number else ""
                foil_part = " *F*" if it.is_foil else ""
                lines.append(f"{it.quantity} {it.effective_name}{set_part}{num_part}{foil_part}")
            lines.append("")

        return "\n".join(lines).strip()

    @classmethod
    def export_to_text(cls, deck: Deck) -> str:
        """Alias for export_to_moxfield_text."""
        return cls.export_to_moxfield_text(deck)

