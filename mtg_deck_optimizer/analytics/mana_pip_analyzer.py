"""
Mana Pip Density & Color Balance Calculator.
Analyzes required color pips across spells vs colored mana sources produced by lands & ramp.
"""

import re
import logging
from typing import Dict, List, Set, Tuple, Optional
from pydantic import BaseModel, Field

from ..models.card import Card
from ..models.deck import Deck
from ..rules.color_identity import WUBRG_ORDER

logger = logging.getLogger(__name__)

MANA_SYMBOL_REGEX = re.compile(r"\{([0-9A-Z/]+)\}", re.IGNORECASE)


class ColorPipBalance(BaseModel):
    """Detailed balance metrics for an individual color."""
    color: str
    color_name: str
    pips_required_count: int
    pips_required_percentage: float
    sources_produced_count: int
    sources_produced_percentage: float
    deficit_or_surplus_percentage: float
    is_deficient: bool
    status_summary: str


class ManaPipReport(BaseModel):
    """Full mana density and color balance diagnostic report."""
    total_spells_analyzed: int
    total_pips_count: int
    total_mana_sources_count: int
    color_breakdowns: Dict[str, ColorPipBalance]
    is_balanced: bool
    discrepancies: Dict[str, float] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class ManaPipAnalyzer:
    """
    Mathematical engine calculating color pip demands vs mana source supplies.
    """

    COLOR_NAMES = {
        "W": "Blanco {W}",
        "U": "Azul {U}",
        "B": "Negro {B}",
        "R": "Rojo {R}",
        "G": "Verde {G}",
        "C": "Incoloro {C}",
    }

    @classmethod
    def count_card_pips(cls, card: Card) -> Dict[str, float]:
        """Counts mana color pips in the casting cost of a card."""
        counts = {c: 0.0 for c in WUBRG_ORDER}
        if not card.mana_cost:
            return counts

        for match in MANA_SYMBOL_REGEX.finditer(card.mana_cost):
            inner = match.group(1).upper()
            parts = inner.split("/")
            if len(parts) == 1 and parts[0] in counts:
                counts[parts[0]] += 1.0
            elif len(parts) == 2:
                # Hybrid mana symbol like {W/U} or {2/B}
                valid_colors = [p for p in parts if p in counts]
                if valid_colors:
                    split_val = 1.0 / len(valid_colors)
                    for c in valid_colors:
                        counts[c] += split_val

        return counts

    @classmethod
    def determine_produced_colors(cls, card: Card, commander_colors: List[str]) -> Set[str]:
        """Infers the colors of mana a land or mana rock produces."""
        produced: Set[str] = set()
        name_lower = card.name.lower()
        type_lower = card.type_line.lower() if card.type_line else ""
        oracle_lower = card.oracle_text.lower() if card.oracle_text else ""

        # Basic lands
        if "plains" in name_lower or "plains" in type_lower:
            produced.add("W")
        if "island" in name_lower or "island" in type_lower:
            produced.add("U")
        if "swamp" in name_lower or "swamp" in type_lower:
            produced.add("B")
        if "mountain" in name_lower or "mountain" in type_lower:
            produced.add("R")
        if "forest" in name_lower or "forest" in type_lower:
            produced.add("G")

        # Any-color lands / rocks (Command Tower, City of Brass, Arcane Signet, Birds of Paradise, etc.)
        any_color_keywords = ["any color", "of any type", "combination of colors", "commander's color identity"]
        if any(kw in oracle_lower for kw in any_color_keywords) or name_lower in (
            "command tower", "exotic orchard", "city of brass", "mana confluence", "reflecting pool", "path of ancestry", "arcane signet", "fellwar stone", "birds of paradise"
        ):
            for c in commander_colors:
                if c in WUBRG_ORDER:
                    produced.add(c)

        # Scryfall colors or color identity
        if card.color_identity:
            for c in card.color_identity:
                if c.upper() in WUBRG_ORDER and ("add" in oracle_lower or "land" in type_lower or "artifact" in type_lower):
                    produced.add(c.upper())

        # Check explicit symbol additions like "{T}: Add {U} or {B}"
        for c in WUBRG_ORDER:
            if f"add {{{c}}}" in oracle_lower or f"add {{{c.lower()}}}" in oracle_lower:
                produced.add(c)

        return produced

    @classmethod
    def analyze(cls, deck: Deck) -> ManaPipReport:
        """
        Executes complete mathematical analysis of color pip balance across the deck.
        """
        commander_cards = [it.card for it in deck.commanders if it.card]
        cmdr_ci = [c.upper() for c in (deck.color_identity or []) if c.upper() in WUBRG_ORDER]
        if not cmdr_ci:
            cmdr_ci = ["W", "U", "B", "R", "G"]

        pip_totals: Dict[str, float] = {c: 0.0 for c in WUBRG_ORDER}
        source_totals: Dict[str, float] = {c: 0.0 for c in WUBRG_ORDER}
        total_spells = 0

        # 1. Count Pips across non-land spells
        all_items = deck.commanders + deck.maindeck
        for it in all_items:
            card = it.card
            if not card:
                continue
            is_land = "Land" in (card.type_line or "")
            if not is_land:
                total_spells += it.quantity
                pips = cls.count_card_pips(card)
                for c, count in pips.items():
                    pip_totals[c] += count * it.quantity
            else:
                # Count sources from lands
                produced = cls.determine_produced_colors(card, cmdr_ci)
                for p in produced:
                    source_totals[p] += it.quantity

        # Count sources from mana rocks / dorks
        for it in deck.maindeck:
            card = it.card
            if not card or "Land" in (card.type_line or ""):
                continue
            type_l = (card.type_line or "").lower()
            if "artifact" in type_l or "creature" in type_l:
                produced = cls.determine_produced_colors(card, cmdr_ci)
                for p in produced:
                    source_totals[p] += (0.8 * it.quantity)  # Weight rocks at 0.8 source

        total_pips = sum(pip_totals.values())
        total_sources = sum(source_totals.values())

        color_breakdowns: Dict[str, ColorPipBalance] = {}
        discrepancies: Dict[str, float] = {}
        warnings: List[str] = []
        recommendations: List[str] = []
        is_balanced = True

        for c in cmdr_ci:
            pips_c = pip_totals[c]
            sources_c = source_totals[c]

            p_pct = (pips_c / total_pips * 100.0) if total_pips > 0 else 0.0
            s_pct = (sources_c / total_sources * 100.0) if total_sources > 0 else 0.0
            delta = round(s_pct - p_pct, 1)
            discrepancies[c] = delta

            # A deficit of > 12% indicates severe mana base skew
            is_def = (delta < -12.0) and (p_pct > 15.0)
            if is_def:
                is_balanced = False
                c_name = cls.COLOR_NAMES.get(c, c)
                warn_msg = (
                    f"⚠️ Desbalance Crítico en {c_name}: El mazo requiere {p_pct:.1f}% de símbolos {c}, "
                    f"pero tus fuentes de maná solo aportan {s_pct:.1f}% (Déficit de {delta:.1f}%)."
                )
                warnings.append(warn_msg)
                recommendations.append(
                    f"Aumenta tierras duales o básicas de color {c_name} (+{int(abs(delta)//3)+1} fuentes) y reduce colores excedentarios."
                )

            status = "Óptimo" if not is_def else "Déficit de Fuentes"

            color_breakdowns[c] = ColorPipBalance(
                color=c,
                color_name=cls.COLOR_NAMES.get(c, c),
                pips_required_count=int(pips_c),
                pips_required_percentage=round(p_pct, 1),
                sources_produced_count=int(sources_c),
                sources_produced_percentage=round(s_pct, 1),
                deficit_or_surplus_percentage=delta,
                is_deficient=is_def,
                status_summary=status,
            )

        return ManaPipReport(
            total_spells_analyzed=total_spells,
            total_pips_count=int(total_pips),
            total_mana_sources_count=int(total_sources),
            color_breakdowns=color_breakdowns,
            is_balanced=is_balanced,
            discrepancies=discrepancies,
            warnings=warnings,
            recommendations=recommendations,
        )
