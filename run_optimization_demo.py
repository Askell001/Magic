"""
MTG Deck Optimizer - AI Engine & Optimization Report Demo
Demonstrates the full end-to-end pipeline:
1. Ingest deck & fetch Scryfall metadata
2. Diagnose current power bracket & gap analysis
3. Apply user intent (Target Bracket, Budget, Untouchable cards)
4. Consult Community (EDHREC) synergy data
5. Generate AI Optimization Report (Outs, Ins, Mana Base, Wincons, Budget)
6. Export structured JSON response
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
from mtg_deck_optimizer.brackets import BracketTier
from mtg_deck_optimizer.intent import build_user_intent
from tests.fixtures.sample_decks import MOXFIELD_SAMPLE


def main():
    print("=" * 80)
    print(" MTG DECK OPTIMIZER - MOTOR DE OPTIMIZACIÓN E INTELIGENCIA ARTIFICIAL")
    print("=" * 80)

    # 1. Ingest deck
    print("\n[1] Ingestando mazo de prueba (The Ur-Dragon) y sincronizando con Scryfall...")
    service = DeckIngestionService()
    deck, _ = service.ingest_from_text(
        raw_text=MOXFIELD_SAMPLE,
        deck_name="The Ur-Dragon's Hoard",
        default_format="commander",
        enrich=True,
    )
    print(f"  [OK] Mazo cargado: '{deck.name}' ({deck.total_card_count} cartas, ${deck.estimated_total_usd} USD)")

    # 2. Configure user intent
    print("\n[2] Definiendo Perfil de Intención del Usuario:")
    intent = build_user_intent(
        target_bracket=3, # Target Bracket 3 (High-Power)
        max_budget_usd=120.0,
        untouchable_cards=["The Ur-Dragon", "Rhystic Study", "Demonic Tutor"],
        allow_infinite_combos=True,
    )
    print(f"  - Bracket Objetivo:      {intent.target_bracket.label}")
    print(f"  - Presupuesto Máximo:    ${intent.max_budget_usd:,.2f} USD")
    print(f"  - Cartas Intocables:     {intent.untouchable_cards}")
    print(f"  - Permitir Combos:       {intent.effective_allow_combos}")

    # 3. Run AI Optimization Engine
    print("\n[3] Ejecutando el Motor de Inferencia con IA (Prompt Builder + Community Data + Optimization Agent)...")
    report = service.optimize_deck(deck=deck, intent=intent)

    print("\n" + "=" * 80)
    print(" REPORTE DE OPTIMIZACIÓN CON IA (AI OPTIMIZATION REPORT)")
    print("=" * 80)
    print(f"• Mazo:                  {report.deck_name}")
    print(f"• Comandante:            {report.commander_name}")
    print(f"• Nivel Inicial:         {report.initial_bracket.label}")
    print(f"• Nivel Objetivo:        {report.target_bracket.label}")
    print(f"• Power Score Estimado:  {report.estimated_new_power_score} / 4.0")
    print(f"\n[-] Resumen Estratégico:\n  {report.summary_overview}")

    # 4. Detailed Sections
    print("\n" + "-" * 80)
    print(f"✂️ CORTES SUGERIDOS (OUTS - {len(report.cuts)} cartas):")
    print("-" * 80)
    for idx, cut in enumerate(report.cuts, 1):
        price_str = f"${cut.estimated_price_usd:.2f}" if cut.estimated_price_usd else "N/A"
        print(f"  {idx}. [OUT] {cut.card_name} ({cut.type_line}, {cut.cmc:.0f} CMC) | Valor: {price_str}")
        print(f"     -> Justificación: {cut.reason}")

    print("\n" + "-" * 80)
    print(f"✨ INCLUSIONES SUGERIDAS (INS - {len(report.inclusions)} cartas):")
    print("-" * 80)
    for idx, inc in enumerate(report.inclusions, 1):
        price_str = f"${inc.estimated_price_usd:.2f}" if inc.estimated_price_usd else "N/A"
        syn_str = f"+{inc.synergy_score:.0f}%" if inc.synergy_score else "Alta"
        print(f"  {idx}. [IN] {inc.card_name} ({inc.type_line}, {inc.cmc:.0f} CMC) | Rol: {inc.role} | Sinergia: {syn_str} | Precio: {price_str}")
        print(f"     -> Impacto: {inc.synergy_explanation}")

    print("\n" + "-" * 80)
    print("🗺️ ANÁLISIS DE BASE DE MANÁ:")
    print("-" * 80)
    print(f"  - Balance de Color:      {report.mana_base_analysis.color_balance_status}")
    print(f"  - Tierras Recomendadas:  {report.mana_base_analysis.recommended_land_count}")
    print(f"  - Evaluación de Rampa:   {report.mana_base_analysis.ramp_assessment}")
    print("  - Tierras Útiles Sugeridas:")
    for land in report.mana_base_analysis.utility_lands_recommendations:
        print(f"    * {land}")
    print("  - Mejoras de Fijación de Color (Fixing):")
    for fix in report.mana_base_analysis.fixing_recommendations:
        print(f"    * {fix}")

    print("\n" + "-" * 80)
    print("🏆 CONDICIONES DE VICTORIA (WIN CONDITIONS):")
    print("-" * 80)
    print(f"  - Vía Principal:         {report.win_conditions.primary_win_path}")
    print(f"  - Turno Estimado de Win: {report.win_conditions.estimated_turn_to_win}")
    print("  - Líneas de Combos / Sinergias Clave:")
    for combo in report.win_conditions.combos_or_synergies:
        print(f"    * {combo}")

    print("\n" + "-" * 80)
    print("💰 RESUMEN FINANCIERO Y PRESUPUESTO:")
    print("-" * 80)
    print(f"  - Valor Cartas Retiradas:   ${report.budget_summary.total_cut_value_usd:,.2f} USD")
    print(f"  - Coste Cartas Agregadas:   ${report.budget_summary.total_added_cost_usd:,.2f} USD")
    print(f"  - Coste Neto del Upgrade:   ${report.budget_summary.net_upgrade_cost_usd:,.2f} USD")
    print(f"  - Dentro del Presupuesto:   {'SÍ' if report.budget_summary.is_within_budget else 'NO'}")
    print(f"  - Detalle:                  {report.budget_summary.budget_notes}")

    # 5. Export JSON
    output_file = Path("ai_optimization_report.json")
    output_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print("\n" + "=" * 80)
    print(f"[OK] Reporte completo de IA exportado en JSON a: {output_file.resolve()}")
    print("=" * 80)


if __name__ == "__main__":
    main()
