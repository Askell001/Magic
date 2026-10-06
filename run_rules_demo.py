"""
MTG Deck Optimizer - Color Identity & Commander Rules Enforcement Demo
Demonstrates:
1. Rigorous Color Identity extraction (mana costs, rules text, DFC back faces, Extort reminder text).
2. Strict Hybrid Mana Rule enforcement (e.g. banning {R/G} Manamorphose in Mono-Green decks).
3. Singleton and Official Commander Banlist validation.
4. Post-AI Integrity Middleware discarding illegal LLM suggestions and providing compliant substitutes.
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mtg_deck_optimizer.models.card import Card, CardPrices, CardFace
from mtg_deck_optimizer.models.deck import Deck, DeckItem, DeckSection
from mtg_deck_optimizer.brackets.standards import BracketTier
from mtg_deck_optimizer.rules import (
    ColorIdentityExtractor,
    SingletonValidator,
    BanlistValidator,
    validate_recommendations,
)
from mtg_deck_optimizer.ai.models import (
    OptimizationReport,
    CardCut,
    CardInclusion,
    ManaBaseAnalysis,
    WinConditionAnalysis,
    BudgetSummary,
)


def main():
    print("=" * 80)
    print(" MTG DECK OPTIMIZER - STRICT COLOR IDENTITY & COMMANDER RULES ENFORCEMENT")
    print("=" * 80)

    # 1. Color Identity Demonstrations
    print("\n[1] Extracción Rigurosa de Color Identity (Reglas, DFCs y Texto de Recordatorio):")

    # Kenrith test
    kenrith = Card(
        id="ken",
        name="Kenrith, the Returned King",
        mana_cost="{4}{W}",
        cmc=5.0,
        type_line="Legendary Creature — Human Noble",
        oracle_text="{R}: Trample/Haste\n{1}{G}: +1/+1 counter\n{2}{W}: 5 life\n{3}{U}: Draw card\n{4}{B}: Reanimate",
        colors=["W"],
        color_identity=["W", "U", "B", "R", "G"],
    )
    ci_ken = ColorIdentityExtractor.compute_card_color_identity(kenrith)
    print(f"  - Kenrith, the Returned King (Coste: {kenrith.mana_cost}) -> Color Identity Real: {''.join(ci_ken)} (5 Colores)")

    # Blind obedience test
    blind_obed = Card(
        id="bo",
        name="Blind Obedience",
        mana_cost="{1}{W}",
        cmc=2.0,
        type_line="Enchantment",
        oracle_text="Extort (Whenever you cast a spell, you may pay {W/B}...)\nOpponents' artifacts/creatures enter tapped.",
        colors=["W"],
        color_identity=["W"],
    )
    ci_bo = ColorIdentityExtractor.compute_card_color_identity(blind_obed)
    print(f"  - Blind Obedience (Extort {{W/B}} en texto recordatorio) -> Color Identity: {''.join(ci_bo)} (Mono-Blanco)")

    # 2. Strict Hybrid Mana Rule Demonstration
    print("\n[2] Regla Estricta de Maná Híbrido en Commander:")
    mono_green_ci = ["G"]
    print(f"  * Comandante Objetivo: Selvala, Heart of the Wilds (Identidad: {mono_green_ci})")

    cards_to_test = [
        Card(id="t1", name="Manamorphose", mana_cost="{1}{R/G}", cmc=2.0, type_line="Instant", color_identity=["R", "G"]),
        Card(id="t2", name="Kitchen Finks", mana_cost="{1}{G/W}{G/W}", cmc=3.0, type_line="Creature — Ouphe", color_identity=["G", "W"]),
        Card(id="t3", name="Birds of Paradise", mana_cost="{G}", cmc=1.0, type_line="Creature — Bird", color_identity=["G"]),
    ]

    for c in cards_to_test:
        is_legal, err = ColorIdentityExtractor.validate_color_identity(c, mono_green_ci)
        status_str = "[LEGAL]" if is_legal else "[ILEGAL / RECHAZADO]"
        print(f"    {status_str:20} -> {c.name:18} (Coste: {c.mana_cost:12}) | {err or 'Válido'}")

    # 3. Post-AI Integrity Middleware Simulation
    print("\n[3] Ejecutando Middleware Post-IA 'validate_recommendations':")
    deck = Deck(
        name="Selvala Mono-Green Stompy",
        commanders=[DeckItem(raw_name="Selvala, Heart of the Wilds", card=Card(id="sel", name="Selvala, Heart of the Wilds", cmc=3.0, type_line="Legendary Creature", color_identity=["G"]), section=DeckSection.COMMANDER)],
        maindeck=[DeckItem(raw_name="Sol Ring", card=Card(id="sr", name="Sol Ring", cmc=1.0, type_line="Artifact", color_identity=[]))],
    )

    # Simulated AI report with violations
    simulated_raw_ai_report = OptimizationReport(
        deck_name="Selvala Mono-Green Stompy",
        commander_name="Selvala, Heart of the Wilds",
        initial_bracket=BracketTier.BRACKET_2_MID_POWER,
        target_bracket=BracketTier.BRACKET_3_HIGH_POWER,
        estimated_new_power_score=3.1,
        summary_overview="Sugerencias iniciales generadas por el modelo de IA.",
        cuts=[
            CardCut(card_name="Selvala, Heart of the Wilds", type_line="Legendary Creature", cmc=3.0, reason="Corte erróneo del comandante.")
        ],
        inclusions=[
            CardInclusion(card_name="Manamorphose", type_line="Instant", cmc=2.0, role="Ramp", synergy_explanation="Sugerencia híbrida.", estimated_price_usd=4.0),
            CardInclusion(card_name="Fastbond", type_line="Enchantment", cmc=1.0, role="Ramp", synergy_explanation="Carta prohibida en Commander.", estimated_price_usd=25.0),
            CardInclusion(card_name="Sol Ring", type_line="Artifact", cmc=1.0, role="Ramp", synergy_explanation="Duplicado ya en mazo.", estimated_price_usd=1.5),
            CardInclusion(card_name="Heroic Intervention", type_line="Instant", cmc=2.0, role="Protection", synergy_explanation="Protección verde legal.", estimated_price_usd=8.5),
        ],
        mana_base_analysis=ManaBaseAnalysis(color_balance_status="Mono-G", recommended_land_count=33, utility_lands_recommendations=[], fixing_recommendations=[], ramp_assessment="OK"),
        win_conditions=WinConditionAnalysis(primary_win_path="Combat", combos_or_synergies=[], estimated_turn_to_win="Turn 5"),
        budget_summary=BudgetSummary(),
    )

    print("  * Evaluando y sanitizando reporte de IA...")
    clean_report = validate_recommendations(
        deck=deck,
        report=simulated_raw_ai_report,
        untouchable_cards=["Selvala, Heart of the Wilds"],
    )

    print("\n" + "-" * 80)
    print("INCLUSIONES FINALES DESPUÉS DEL FILTRO DE INTEGRIDAD:")
    for idx, inc in enumerate(clean_report.inclusions, 1):
        print(f"  {idx}. [IN] {inc.card_name} ({inc.type_line}) | Rol: {inc.role} | Precio: ${inc.estimated_price_usd:.2f}")

    print("\n" + "-" * 80)
    print("BITÁCORA DE AUDITORÍA REGISTRADA EN EL REPORTE:")
    print(clean_report.summary_overview)
    print("-" * 80)

    print("\n[OK] Demostración del Módulo de Reglas y Color Identity completada con éxito.")
    print("=" * 80)


if __name__ == "__main__":
    main()
