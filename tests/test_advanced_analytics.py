"""
Unit tests for Advanced_Deck_Analytics:
1. Mana Pip Density & Color Balance Calculator
2. Monte Carlo Mulligan Simulator (1,000 virtual draws)
3. Pairwise Card-by-Card Trade-offs & 3-Tier Budget Alternatives
4. Anti-Synergy-Trap Detector
"""

import pytest
from mtg_deck_optimizer.models.card import Card, CardPrices
from mtg_deck_optimizer.models.deck import Deck, DeckItem, DeckSection
from mtg_deck_optimizer.brackets import BracketTier
from mtg_deck_optimizer.ai.models import CardCut, CardInclusion
from mtg_deck_optimizer.analytics import (
    Advanced_Deck_Analytics,
    ManaPipAnalyzer,
    ManaPipReport,
    MulliganSimulator,
    MulliganSimulationReport,
    TradeoffEngine,
    CardTradeoff,
)


def test_mana_pip_density_and_color_balance():
    """Verifies that ManaPipAnalyzer correctly counts color pips and detects source imbalances."""
    deck = Deck(
        id="d_pip_test",
        name="Dimir Control",
        commanders=[DeckItem(raw_name="Wilhelt, the Rotcleaver", quantity=1, section=DeckSection.COMMANDER, card=Card(id="c1", name="Wilhelt, the Rotcleaver", mana_cost="{2}{U}{B}", color_identity=["U", "B"]))],
        maindeck=[
            # Heavy Blue spells (6 Blue pips, 0 Black pips)
            DeckItem(raw_name="Counterspell", quantity=1, card=Card(id="c2", name="Counterspell", mana_cost="{U}{U}", color_identity=["U"])),
            DeckItem(raw_name="Cryptic Command", quantity=1, card=Card(id="c3", name="Cryptic Command", mana_cost="{1}{U}{U}{U}", color_identity=["U"])),
            DeckItem(raw_name="Opt", quantity=1, card=Card(id="c4", name="Opt", mana_cost="{U}", color_identity=["U"])),
            # Only Swamps (producing Black mana, 0 Blue sources)
            DeckItem(raw_name="Swamp", quantity=30, card=Card(id="l1", name="Swamp", type_line="Basic Land — Swamp", color_identity=["B"])),
            DeckItem(raw_name="Island", quantity=2, card=Card(id="l2", name="Island", type_line="Basic Land — Island", color_identity=["U"])),
        ],
    )

    report = Advanced_Deck_Analytics.analyze_mana_pips(deck)

    assert isinstance(report, ManaPipReport)
    assert "U" in report.color_breakdowns
    assert "B" in report.color_breakdowns
    assert report.color_breakdowns["U"].pips_required_percentage > 50.0
    # Because there are only 2 Islands vs 30 Swamps, Blue should be severely deficient
    assert report.is_balanced is False
    assert len(report.warnings) > 0
    assert any("Azul" in w or "U" in w for w in report.warnings)


def test_mulligan_monte_carlo_simulator():
    """Verifies that MulliganSimulator executes 1,000 simulations and computes consistent stats."""
    # Build a standard 99-card balanced maindeck
    maindeck_items = []
    # 35 lands
    maindeck_items.append(DeckItem(raw_name="Island", quantity=18, card=Card(id="isl", name="Island", type_line="Basic Land — Island")))
    maindeck_items.append(DeckItem(raw_name="Swamp", quantity=17, card=Card(id="swp", name="Swamp", type_line="Basic Land — Swamp")))
    # 10 ramp pieces
    maindeck_items.append(DeckItem(raw_name="Sol Ring", quantity=1, card=Card(id="sr", name="Sol Ring", mana_cost="{1}", cmc=1.0, type_line="Artifact")))
    maindeck_items.append(DeckItem(raw_name="Arcane Signet", quantity=1, card=Card(id="as", name="Arcane Signet", mana_cost="{2}", cmc=2.0, type_line="Artifact")))
    maindeck_items.append(DeckItem(raw_name="Dimir Signet", quantity=1, card=Card(id="ds", name="Dimir Signet", mana_cost="{2}", cmc=2.0, type_line="Artifact")))
    # 10 low-cost interaction spells
    for i in range(10):
        maindeck_items.append(DeckItem(raw_name=f"Counter_{i}", quantity=1, card=Card(id=f"cnt_{i}", name=f"Counter {i}", mana_cost="{U}{U}", cmc=2.0, type_line="Instant", oracle_text="Counter target spell.")))
    # 44 other spells
    for i in range(44):
        maindeck_items.append(DeckItem(raw_name=f"Spell_{i}", quantity=1, card=Card(id=f"sp_{i}", name=f"Spell {i}", mana_cost="{2}{U}", cmc=3.0, type_line="Sorcery")))

    deck = Deck(
        id="d_sim_test",
        name="Sim Test Deck",
        commanders=[DeckItem(raw_name="Wilhelt, the Rotcleaver", quantity=1, section=DeckSection.COMMANDER, card=Card(id="cmdr", name="Wilhelt, the Rotcleaver", cmc=4.0))],
        maindeck=maindeck_items,
    )

    sim_report = Advanced_Deck_Analytics.simulate_opening_hands(deck, num_simulations=1000, seed=123)

    assert isinstance(sim_report, MulliganSimulationReport)
    assert sim_report.total_simulations == 1000
    assert 40.0 <= sim_report.playable_hand_rate_percent <= 95.0
    assert 0.0 <= sim_report.mana_screw_rate_percent <= 30.0
    assert 0.0 <= sim_report.mana_flood_rate_percent <= 30.0
    assert sim_report.interaction_turn_1_to_3_percent > 30.0
    assert 2.0 <= sim_report.avg_commander_cast_turn <= 5.0
    assert len(sim_report.sample_opening_hands) == 3


def test_pairwise_card_tradeoffs_and_budget_tiers():
    """Verifies that pairwise trade-offs generate causal rationale, mana delta, and 3-tier budget alternatives."""
    cuts = [
        CardCut(card_name="Cultivate", type_line="Sorcery", cmc=3.0, role="Ramp", reason="Slow 3 CMC ramp", estimated_price_usd=0.50),
        CardCut(card_name="Diabolic Tutor", type_line="Sorcery", cmc=4.0, role="Tutor", reason="Expensive 4 CMC tutor", estimated_price_usd=1.00),
    ]
    inclusions = [
        CardInclusion(card_name="Delighted Halfling", type_line="Creature — Halfling", cmc=1.0, role="Ramp", synergy_explanation="Acelera comandante y evita counters", estimated_price_usd=12.00),
        CardInclusion(card_name="Demonic Tutor", type_line="Sorcery", cmc=2.0, role="Tutor", synergy_explanation="Tutor universal de 2 CMC", estimated_price_usd=35.00),
    ]

    tradeoffs = Advanced_Deck_Analytics.build_tradeoffs(cuts, inclusions, target_bracket=BracketTier.BRACKET_3_HIGH_POWER)

    assert len(tradeoffs) == 2
    t1 = tradeoffs[0]
    assert t1.card_cut_name == "Cultivate"
    assert t1.card_in_name == "Delighted Halfling"
    assert t1.cmc_delta == -2.0
    assert "reduce la curva" in t1.technical_justification
    assert t1.budget_tiers.recommended.name == "Delighted Halfling"
    assert t1.budget_tiers.budget_sidegrade is not None

    t2 = tradeoffs[1]
    assert t2.card_cut_name == "Diabolic Tutor"
    assert t2.card_in_name == "Demonic Tutor"
    assert t2.cmc_delta == -2.0
    assert t2.budget_tiers.budget_sidegrade.name == "Diabolic Intent"
    assert t2.budget_tiers.premium_staple.name == "Imperial Seal"


def test_anti_synergy_trap_detector():
    """Verifies that high CMC cards (>4) that are not wincons are flagged as synergy traps."""
    # Slow 6 CMC value engine -> TRAP
    is_trap, msg = Advanced_Deck_Analytics.evaluate_anti_synergy_trap("Sunbird's Invocation", cmc=6.0, role="Value Engine")
    assert is_trap is True
    assert "trampa de sinergia" in msg

    # High CMC Wincon (e.g. Craterhoof Behemoth) -> NOT TRAP
    is_trap_wincon, _ = Advanced_Deck_Analytics.evaluate_anti_synergy_trap("Craterhoof Behemoth", cmc=8.0, role="Wincon")
    assert is_trap_wincon is False

    # Low CMC Spell (e.g. Sol Ring 1 CMC) -> NOT TRAP
    is_trap_low, _ = Advanced_Deck_Analytics.evaluate_anti_synergy_trap("Sol Ring", cmc=1.0, role="Ramp")
    assert is_trap_low is False
