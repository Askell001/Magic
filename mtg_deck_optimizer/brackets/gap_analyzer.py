"""
Gap Analysis Engine computing deviation metrics and actionable recommendations
between a deck's current state and the user's target power bracket.
"""

from typing import List, Dict, Optional, Any, TYPE_CHECKING
from pydantic import BaseModel, Field

from ..models.deck import Deck
from .standards import BracketTier, BracketBenchmark, BRACKET_BENCHMARKS
from .classifier import CardRoleClassifier, DeckClassification

if TYPE_CHECKING:
    from ..intent.models import UserIntent


class GapMetricDetail(BaseModel):
    current_value: float = Field(description="Actual value in current deck")
    target_benchmark_range: str = Field(description="Target range for target bracket")
    gap: float = Field(description="Calculated deficit (>0) or surplus (<0)")
    status: str = Field(description="Status: 'OK', 'Déficit', 'Exceso'")


class BudgetGapDetail(BaseModel):
    current_deck_usd: Optional[float] = None
    max_budget_usd: Optional[float] = None
    remaining_budget_usd: Optional[float] = None
    is_exceeded: bool = False
    message: str = ""


class DeckGapReport(BaseModel):
    current_bracket: BracketTier
    current_bracket_score: float
    target_bracket: BracketTier
    overall_deviation_score: float = Field(description="Normalized deviation score from 0.0 (aligned) to 10.0 (severe gap)")
    
    # Detailed metric gaps
    cmc_detail: GapMetricDetail
    lands_detail: GapMetricDetail
    ramp_detail: GapMetricDetail
    fast_mana_detail: GapMetricDetail
    interaction_detail: GapMetricDetail
    tutors_detail: GapMetricDetail
    board_wipes_detail: GapMetricDetail
    
    combos_status: str
    budget_detail: BudgetGapDetail
    untouchable_cards_count: int
    
    recommendations: List[str] = Field(default_factory=list, description="Concrete optimization suggestions")
    diagnosis_reasons: List[str] = Field(default_factory=list, description="Reasons behind current power tier")


class DeckGapAnalyzer:
    """Computes deviations and produces optimization roadmaps based on UserIntent and Bracket benchmarks."""

    @classmethod
    def analyze(cls, deck: Deck, intent: "UserIntent") -> DeckGapReport:
        # Step 1: Classify current deck
        classification = CardRoleClassifier.classify_deck(deck)
        
        target_tier = intent.target_bracket
        bench: BracketBenchmark = BRACKET_BENCHMARKS[target_tier]
        
        # Step 2: Compute individual metric gaps
        # CMC Gap
        target_cmc_mid = (bench.min_avg_cmc + bench.max_avg_cmc) / 2.0
        cmc_diff = round(classification.avg_cmc_without_lands - target_cmc_mid, 2)
        if classification.avg_cmc_without_lands > bench.max_avg_cmc:
            cmc_status = "Déficit de velocidad (Curva alta)"
        elif classification.avg_cmc_without_lands < bench.min_avg_cmc:
            cmc_status = "Curva más baja que el benchmark"
        else:
            cmc_status = "OK"

        cmc_detail = GapMetricDetail(
            current_value=classification.avg_cmc_without_lands,
            target_benchmark_range=f"{bench.min_avg_cmc:.1f} - {bench.max_avg_cmc:.1f}",
            gap=cmc_diff,
            status=cmc_status,
        )

        # Lands Gap
        target_lands_mid = (bench.target_lands_min + bench.target_lands_max) / 2.0
        lands_diff = round(classification.lands_count - target_lands_mid, 1)
        if classification.lands_count > bench.target_lands_max:
            lands_status = "Exceso de tierras"
        elif classification.lands_count < bench.target_lands_min:
            lands_status = "Déficit de tierras"
        else:
            lands_status = "OK"

        lands_detail = GapMetricDetail(
            current_value=float(classification.lands_count),
            target_benchmark_range=f"{bench.target_lands_min} - {bench.target_lands_max}",
            gap=lands_diff,
            status=lands_status,
        )

        # Ramp Gap
        ramp_deficit = max(0, bench.target_ramp_min - classification.ramp_count)
        ramp_detail = GapMetricDetail(
            current_value=float(classification.ramp_count),
            target_benchmark_range=f">={bench.target_ramp_min}",
            gap=float(ramp_deficit),
            status="Déficit de rampa" if ramp_deficit > 0 else "OK",
        )

        # Fast Mana Gap
        fast_mana_deficit = max(0, bench.target_fast_mana_min - classification.fast_mana_count)
        fast_mana_detail = GapMetricDetail(
            current_value=float(classification.fast_mana_count),
            target_benchmark_range=f">={bench.target_fast_mana_min}",
            gap=float(fast_mana_deficit),
            status="Déficit de fast mana" if fast_mana_deficit > 0 else "OK",
        )

        # Interaction Gap
        interaction_deficit = max(0, bench.target_interaction_min - classification.interaction_count)
        interaction_detail = GapMetricDetail(
            current_value=float(classification.interaction_count),
            target_benchmark_range=f">={bench.target_interaction_min}",
            gap=float(interaction_deficit),
            status="Déficit de interacción" if interaction_deficit > 0 else "OK",
        )

        # Tutors Gap
        tutor_deficit = max(0, bench.target_tutors_min - classification.tutor_count)
        tutors_detail = GapMetricDetail(
            current_value=float(classification.tutor_count),
            target_benchmark_range=f">={bench.target_tutors_min}",
            gap=float(tutor_deficit),
            status="Déficit de tutores" if tutor_deficit > 0 else "OK",
        )

        # Board Wipes Gap
        wipes_diff = classification.board_wipes_count - bench.target_board_wipes_max
        if classification.board_wipes_count > bench.target_board_wipes_max:
            wipes_status = "Demasiados wipes (ralentizan el juego)"
        elif classification.board_wipes_count < bench.target_board_wipes_min:
            wipes_status = "Déficit de wipes"
        else:
            wipes_status = "OK"

        board_wipes_detail = GapMetricDetail(
            current_value=float(classification.board_wipes_count),
            target_benchmark_range=f"{bench.target_board_wipes_min} - {bench.target_board_wipes_max}",
            gap=float(wipes_diff),
            status=wipes_status,
        )

        # Combos Status
        combos_status = "Alineado con el Bracket"
        if intent.effective_allow_combos and not classification.combos_detected and target_tier >= BracketTier.BRACKET_3_HIGH_POWER:
            combos_status = "Se sugiere incorporar un combo compacto de 2-3 cartas para cerrar partidas rápidamente."
        elif not intent.effective_allow_combos and classification.combos_detected:
            combos_status = f"El mazo contiene combos ({len(classification.combos_detected)}) no deseados para este nivel casual."

        # Budget Analysis
        current_usd = deck.estimated_total_usd
        budget_msg = "Sin restricción de presupuesto."
        is_exceeded = False
        remaining_usd: Optional[float] = None

        if intent.max_budget_usd is not None and current_usd is not None:
            remaining_usd = round(intent.max_budget_usd - current_usd, 2)
            if remaining_usd < 0:
                is_exceeded = True
                budget_msg = f"El valor actual del mazo (${current_usd:,.2f}) excede el presupuesto límite por ${abs(remaining_usd):,.2f} USD."
            else:
                budget_msg = f"Presupuesto disponible para upgrades: ${remaining_usd:,.2f} USD."

        budget_detail = BudgetGapDetail(
            current_deck_usd=current_usd,
            max_budget_usd=intent.max_budget_usd,
            remaining_budget_usd=remaining_usd,
            is_exceeded=is_exceeded,
            message=budget_msg,
        )

        # Step 3: Compute Overall Deviation Score (0.0 to 10.0)
        tier_diff = abs(int(target_tier) - classification.detected_bracket_score)
        
        raw_score = 0.0
        # Tier gap weight (up to 4.0 points)
        raw_score += tier_diff * 1.5
        
        # CMC gap weight (up to 2.5 points)
        if cmc_diff > 0:
            raw_score += min(2.5, cmc_diff * 1.8)
            
        # Role deficits (up to 3.5 points)
        role_penalties = (
            (ramp_deficit * 0.25)
            + (fast_mana_deficit * 0.5)
            + (interaction_deficit * 0.3)
            + (tutor_deficit * 0.4)
        )
        raw_score += min(3.5, role_penalties)
        
        deviation_score = max(0.0, min(10.0, round(raw_score, 1)))

        # Step 4: Build Actionable Recommendations
        recommendations: List[str] = []

        if classification.detected_bracket < target_tier:
            recommendations.append(
                f"Elevar nivel de poder: El mazo actual está en {classification.detected_bracket.label} y el objetivo es {target_tier.label}."
            )
        elif classification.detected_bracket > target_tier:
            recommendations.append(
                f"Moderar nivel de poder: El mazo actual excede el nivel deseado ({classification.detected_bracket.label} vs {target_tier.label})."
            )

        if cmc_detail.gap > 0.3:
            recommendations.append(
                f"Reducir curva de maná: El CMC medio actual es {classification.avg_cmc_without_lands:.2f}. Bajar a rango [{bench.min_avg_cmc:.1f} - {bench.max_avg_cmc:.1f}] recortando hechizos pesados (>5 CMC)."
            )

        if lands_detail.gap > 2:
            recommendations.append(
                f"Ajustar base de maná: Reducir {int(lands_detail.gap)} tierras (actualmente {classification.lands_count}, sugerido {bench.target_lands_min}-{bench.target_lands_max})."
            )
        elif lands_detail.gap < -2:
            recommendations.append(
                f"Añadir tierras: Faltan aproximadamente {int(abs(lands_detail.gap))} tierras (actualmente {classification.lands_count}, sugerido {bench.target_lands_min}-{bench.target_lands_max})."
            )

        if ramp_deficit > 0:
            recommendations.append(
                f"Añadir rampa eficiente: Incorporar al menos {ramp_deficit} aceleradores de maná de 1-2 CMC (dorks o rocas)."
            )

        if fast_mana_deficit > 0 and intent.effective_allow_fast_mana:
            recommendations.append(
                f"Incorporar Fast Mana: Añadir {fast_mana_deficit} piezas (e.g., Mana Vault, Chrome Mox, Lotus Petal) para acelerar turnos clave."
            )

        if interaction_deficit > 0:
            recommendations.append(
                f"Reforzar interacción: Añadir {interaction_deficit} respuestas instantáneas de bajo coste (<=2 CMC o gratuitas)."
            )

        if tutor_deficit > 0:
            recommendations.append(
                f"Aumentar consistencia: Añadir {tutor_deficit} tutores eficientes para encontrar respuestas y wincons."
            )

        if intent.untouchable_cards:
            recommendations.append(
                f"Cartas intocables respetadas ({len(intent.untouchable_cards)}): No serán sugeridas para sustitución."
            )

        return DeckGapReport(
            current_bracket=classification.detected_bracket,
            current_bracket_score=classification.detected_bracket_score,
            target_bracket=target_tier,
            overall_deviation_score=deviation_score,
            cmc_detail=cmc_detail,
            lands_detail=lands_detail,
            ramp_detail=ramp_detail,
            fast_mana_detail=fast_mana_detail,
            interaction_detail=interaction_detail,
            tutors_detail=tutors_detail,
            board_wipes_detail=board_wipes_detail,
            combos_status=combos_status,
            budget_detail=budget_detail,
            untouchable_cards_count=len(intent.untouchable_cards),
            recommendations=recommendations,
            diagnosis_reasons=classification.diagnosis_reasons,
        )
