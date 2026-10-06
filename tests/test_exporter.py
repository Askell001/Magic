"""
Unit tests for DeckExporter.
"""

from mtg_deck_optimizer.models.card import Card, CardPrices
from mtg_deck_optimizer.models.deck import Deck, DeckItem, DeckSection
from mtg_deck_optimizer.brackets.standards import BracketTier
from mtg_deck_optimizer.ai.models import (
    OptimizationReport,
    CardCut,
    CardInclusion,
    ManaBaseAnalysis,
    WinConditionAnalysis,
    BudgetSummary,
)
from mtg_deck_optimizer.exporter.deck_exporter import DeckExporter


def test_deck_exporter_apply_optimization_and_export_text():
    cmdr = Card(id="c1", name="The Ur-Dragon", cmc=9.0, type_line="Legendary Creature — Dragon Avatar", set_code="c17", collector_number="48")
    cut_card = Card(id="c2", name="Bogardan Hellkite", cmc=8.0, type_line="Creature — Dragon", set_code="m10", collector_number="127")
    keep_card = Card(id="c3", name="Sol Ring", cmc=1.0, type_line="Artifact", set_code="lea", collector_number="270")

    deck = Deck(
        name="Test Dragon Deck",
        commanders=[DeckItem(raw_name="The Ur-Dragon", set_code="c17", collector_number="48", card=cmdr, is_foil=True, section=DeckSection.COMMANDER)],
        maindeck=[
            DeckItem(raw_name="Bogardan Hellkite", set_code="m10", collector_number="127", card=cut_card, section=DeckSection.MAINDECK),
            DeckItem(raw_name="Sol Ring", set_code="lea", collector_number="270", card=keep_card, section=DeckSection.MAINDECK),
        ],
    )

    report = OptimizationReport(
        deck_name="Test Dragon Deck",
        commander_name="The Ur-Dragon",
        initial_bracket=BracketTier.BRACKET_2_MID_POWER,
        target_bracket=BracketTier.BRACKET_3_HIGH_POWER,
        estimated_new_power_score=3.1,
        summary_overview="Upgraded deck with Miirym.",
        cuts=[
            CardCut(card_name="Bogardan Hellkite", type_line="Creature — Dragon", cmc=8.0, reason="Too slow.")
        ],
        inclusions=[
            CardInclusion(card_name="Miirym, Sentinel Wyrm", type_line="Legendary Creature — Dragon Spirit", cmc=6.0, role="Engine", synergy_explanation="Doubles dragons.", estimated_price_usd=4.5)
        ],
        mana_base_analysis=ManaBaseAnalysis(
            color_balance_status="WUBRG",
            recommended_land_count=33,
            utility_lands_recommendations=["Boseiju"],
            fixing_recommendations=["Shocklands"],
            ramp_assessment="Good",
        ),
        win_conditions=WinConditionAnalysis(
            primary_win_path="Dragon Beatdown",
            combos_or_synergies=["Miirym + Scourge of Valkas"],
            estimated_turn_to_win="Turn 5",
        ),
        budget_summary=BudgetSummary(
            total_cut_value_usd=1.5,
            total_added_cost_usd=4.5,
            net_upgrade_cost_usd=3.0,
            is_within_budget=True,
        ),
    )

    opt_deck, new_curve, post_cmc = DeckExporter.apply_optimization(deck, report)

    # Check that Bogardan Hellkite was replaced by Miirym
    main_names = [it.effective_name for it in opt_deck.maindeck]
    assert "Bogardan Hellkite" not in main_names
    assert "Miirym, Sentinel Wyrm" in main_names
    assert "Sol Ring" in main_names

    # Check Moxfield export string
    export_text = DeckExporter.export_to_moxfield_text(opt_deck)
    assert "// Commander" in export_text
    assert "1 The Ur-Dragon (C17) 48 *F*" in export_text
    assert "// Mainboard" in export_text
    assert "1 Sol Ring (LEA) 270" in export_text
    assert "1 Miirym, Sentinel Wyrm" in export_text
