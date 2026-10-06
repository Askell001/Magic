"""
MTG Deck Optimizer - User Intent & Bracket Gap Analysis Demo
Ingests a deck, evaluates its current power bracket, collects user intent,
and computes the Deviation Metric & Optimization Roadmap.
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mtg_deck_optimizer.service import DeckIngestionService
from mtg_deck_optimizer.brackets import (
    BracketTier,
    CardRoleClassifier,
    DeckGapAnalyzer,
)
from mtg_deck_optimizer.intent import ask_user_intent_cli, build_user_intent
from tests.fixtures.sample_decks import MOXFIELD_SAMPLE


def main():
    print("=" * 75)
    print(" MTG DECK OPTIMIZER - INTENT EVALUATION & POWER BRACKET GAP ANALYSIS")
    print("=" * 75)

    # 1. Ingest and enrich deck from Scryfall
    print("\n[1] Ingesting decklist and fetching Scryfall metadata...")
    service = DeckIngestionService()
    deck, _ = service.ingest_from_text(
        raw_text=MOXFIELD_SAMPLE,
        deck_name="The Ur-Dragon's Dominion",
        default_format="commander",
        enrich=True,
    )
    print(f"  [OK] Mazo cargado: '{deck.name}' ({deck.total_card_count} cartas, ${deck.estimated_total_usd} USD)")

    # 2. Evaluate current deck classification
    print("\n[2] Diagnosticando nivel de poder actual del mazo...")
    current_class = CardRoleClassifier.classify_deck(deck)
    print(f"  - Bracket Detectado:     {current_class.detected_bracket.label}")
    print(f"  - Power Score Estimado:  {current_class.detected_bracket_score} / 4.0")
    print(f"  - CMC Medio (s/tierras): {current_class.avg_cmc_without_lands}")
    print(f"  - Tierras:               {current_class.lands_count}")
    print(f"  - Ramp / Fast Mana:      {current_class.ramp_count} (Fast Mana: {current_class.fast_mana_count})")
    print(f"  - Tutores:               {current_class.tutor_count}")
    print(f"  - Interacción:           {current_class.interaction_count} (Free/Cheap: {current_class.free_or_cheap_interaction_count})")
    print(f"  - Factores Clave:")
    for reason in current_class.diagnosis_reasons:
        print(f"    * {reason}")

    # 3. User Intent Questionnaire
    # Support both non-interactive CLI argument/fallback or interactive terminal
    interactive = "--interactive" in sys.argv or "-i" in sys.argv

    if interactive:
        intent = ask_user_intent_cli(default_bracket=BracketTier.BRACKET_3_HIGH_POWER)
    else:
        print("\n[3] Aplicando perfil de intención de usuario de ejemplo (usa '--interactive' para CLI interactivo):")
        intent = build_user_intent(
            target_bracket=3, # Target Bracket 3 (High-Power)
            max_budget_usd=600.0,
            untouchable_cards=["The Ur-Dragon", "Rhystic Study", "Demonic Tutor"],
            allow_infinite_combos=True,
        )
        print(f"  - Bracket Objetivo:      {intent.target_bracket.label}")
        print(f"  - Presupuesto Máximo:    ${intent.max_budget_usd:,.2f} USD")
        print(f"  - Cartas Intocables:     {intent.untouchable_cards}")
        print(f"  - Permitir Combos:       {intent.effective_allow_combos}")

    # 4. Gap Analysis and Deviation Metric
    print("\n[4] Ejecutando Gap Analysis y calculando Métrica de Desviación...")
    gap_report = DeckGapAnalyzer.analyze(deck, intent)

    print("\n" + "=" * 75)
    print(f" REPORTE DE DESVIACION (GAP ANALYSIS) -> Objetivo: {gap_report.target_bracket.label}")
    print("=" * 75)
    print(f"  - Bracket Actual:           {gap_report.current_bracket.label} (Score: {gap_report.current_bracket_score})")
    print(f"  - Metrica de Desviacion:    {gap_report.overall_deviation_score} / 10.0")
    print(f"  - Brecha de Curva (CMC):    Actual {gap_report.cmc_detail.current_value:.2f} vs Target [{gap_report.cmc_detail.target_benchmark_range}] (Gap: {gap_report.cmc_detail.gap:+.2f}) -> {gap_report.cmc_detail.status}")
    print(f"  - Brecha de Tierras:        Actual {int(gap_report.lands_detail.current_value)} vs Target [{gap_report.lands_detail.target_benchmark_range}] -> {gap_report.lands_detail.status}")
    print(f"  - Brecha de Rampa:          Actual {int(gap_report.ramp_detail.current_value)} vs Target [{gap_report.ramp_detail.target_benchmark_range}] -> {gap_report.ramp_detail.status}")
    print(f"  - Brecha de Fast Mana:      Actual {int(gap_report.fast_mana_detail.current_value)} vs Target [{gap_report.fast_mana_detail.target_benchmark_range}] -> {gap_report.fast_mana_detail.status}")
    print(f"  - Brecha de Interaccion:    Actual {int(gap_report.interaction_detail.current_value)} vs Target [{gap_report.interaction_detail.target_benchmark_range}] -> {gap_report.interaction_detail.status}")
    print(f"  - Brecha de Tutores:        Actual {int(gap_report.tutors_detail.current_value)} vs Target [{gap_report.tutors_detail.target_benchmark_range}] -> {gap_report.tutors_detail.status}")
    print(f"  - Estado de Presupuesto:    {gap_report.budget_detail.message}")

    print("\n[-] RECOMENDACIONES ACCIONABLES DE OPTIMIZACION:")
    for idx, rec in enumerate(gap_report.recommendations, 1):
        print(f"  {idx}. {rec}")

    # 5. Save structured report to JSON
    output_path = Path("gap_analysis_report.json")
    output_path.write_text(gap_report.model_dump_json(indent=2), encoding="utf-8")
    print(f"\n[OK] Reporte completo guardado en: {output_path.resolve()}")
    print("=" * 75)


if __name__ == "__main__":
    main()
