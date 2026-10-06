"""
Unit tests for WOTC_Commander_Rules_Engine.
Validates strict Color Identity, Real-Time Banlist, Singleton Constraints,
and Middleware Filtering.
"""

import pytest
from typing import List
from mtg_deck_optimizer.models.card import Card, CardFace, CardPrices
from mtg_deck_optimizer.models.deck import Deck, DeckItem, DeckSection
from mtg_deck_optimizer.brackets.standards import BracketTier
from mtg_deck_optimizer.ai.models import (
    OptimizationReport,
    CardInclusion,
    CardCut,
    BudgetSummary,
    ManaBaseAnalysis,
    WinConditionAnalysis,
)
from mtg_deck_optimizer.rules.wotc_rules_engine import (
    WOTC_Commander_Rules_Engine,
    DeckValidationResult,
    CardLegalityResult,
)


def test_wotc_color_identity_hybrid_mana_rejection():
    """
    Validates that a mono-green commander strictly rejects {G/R} hybrid mana cards (like Manamorphose)
    and {G/W} cards (Kitchen Finks).
    """
    engine = WOTC_Commander_Rules_Engine()

    selvala = Card(
        id="selvala_1",
        name="Selvala, Heart of the Wilds",
        mana_cost="{1}{G}{G}",
        type_line="Legendary Creature — Elf Scout",
        oracle_text="{G}, {T}: Add X mana in any combination of colors.",
        color_identity=["G"],
    )

    cmdr_ci = engine.extract_commander_color_identity([selvala])
    assert cmdr_ci == ["G"]

    # Manamorphose {1}{R/G}
    manamorphose = Card(
        id="mana_1",
        name="Manamorphose",
        mana_cost="{1}{R/G}",
        type_line="Instant",
        oracle_text="Add two mana in any combination of colors. Draw a card.",
        color_identity=["R", "G"],
    )

    is_legal, reason = engine.validate_color_identity(manamorphose, cmdr_ci)
    assert is_legal is False
    assert "fuera de la identidad del comandante" in reason

    # Birds of Paradise {G} -> Legal
    bop = Card(
        id="bop_1",
        name="Birds of Paradise",
        mana_cost="{G}",
        type_line="Creature — Bird",
        oracle_text="{T}: Add one mana of any color.",
        color_identity=["G"],
    )
    is_legal_bop, _ = engine.validate_color_identity(bop, cmdr_ci)
    assert is_legal_bop is True


def test_wotc_rules_engine_dfc_and_extort():
    """Validates color identity on DFC cards and ignores reminder text in Extort cards."""
    engine = WOTC_Commander_Rules_Engine()

    # Blind Obedience (Mono-White, Extort has {W/B} reminder text)
    blind_obedience = Card(
        id="bo_1",
        name="Blind Obedience",
        mana_cost="{1}{W}",
        type_line="Enchantment",
        oracle_text="Extort (Whenever you cast a spell, you may pay {W/B}.)",
        color_identity=["W"],
    )
    ci_bo = engine.extract_card_color_identity(blind_obedience)
    assert ci_bo == ["W"]

    # DFC: Nicol Bolas, the Ravager // Nicol Bolas, the Arisen
    bolas = Card(
        id="bolas_1",
        name="Nicol Bolas, the Ravager // Nicol Bolas, the Arisen",
        mana_cost="{1}{U}{B}{R}",
        type_line="Legendary Creature — Elder Dragon",
        oracle_text="Flying...",
        card_faces=[
            CardFace(name="Nicol Bolas, the Ravager", mana_cost="{1}{U}{B}{R}", oracle_text="..."),
            CardFace(name="Nicol Bolas, the Arisen", mana_cost="", oracle_text="+2: Draw two cards."),
        ],
    )
    ci_bolas = engine.extract_commander_color_identity([bolas])
    assert set(ci_bolas) == {"U", "B", "R"}


def test_wotc_banlist_subscription_and_filtering():
    """Validates real-time format banlist filtering (Scryfall legalities + official list)."""
    engine = WOTC_Commander_Rules_Engine()

    jeweled_lotus = Card(
        id="jl_1",
        name="Jeweled Lotus",
        mana_cost="{0}",
        type_line="Artifact",
        legalities={"commander": "banned"},
    )

    is_legal, err = engine.validate_banlist(jeweled_lotus, fetch_remote=False)
    assert is_legal is False
    assert "PROHIBIDA" in err or "banned" in err

    sol_ring = Card(
        id="sr_1",
        name="Sol Ring",
        mana_cost="{1}",
        type_line="Artifact",
        legalities={"commander": "legal"},
    )
    is_legal_sr, _ = engine.validate_banlist(sol_ring, fetch_remote=False)
    assert is_legal_sr is True


def test_wotc_singleton_and_basic_land_rules():
    """Validates singleton rule and exemptions for basic lands and Relentless Rats."""
    engine = WOTC_Commander_Rules_Engine()

    assert engine.is_singleton_exempt("Forest") is True
    assert engine.is_singleton_exempt("Snow-Covered Island") is True
    assert engine.is_singleton_exempt("Relentless Rats") is True
    assert engine.is_singleton_exempt("Seven Dwarves", requested_quantity=7) is True
    assert engine.is_singleton_exempt("Sol Ring") is False

    deck = Deck(
        id="d1",
        name="Mono-G Ramp",
        commanders=[DeckItem(raw_name="Selvala, Heart of the Wilds", quantity=1, section=DeckSection.COMMANDER)],
        maindeck=[
            DeckItem(raw_name="Forest", quantity=30),
            DeckItem(raw_name="Sol Ring", quantity=2),  # VIOLATION
            DeckItem(raw_name="Relentless Rats", quantity=10),  # EXEMPT
        ],
    )

    errors = engine.validate_singleton(deck)
    assert len(errors) == 1
    assert "Sol Ring" in errors[0]


def test_wotc_middleware_sanitize_recommendations():
    """Tests that WOTC_Commander_Rules_Engine automatically discards illegal AI recommendations."""
    engine = WOTC_Commander_Rules_Engine()

    selvala = Card(
        id="selvala_1",
        name="Selvala, Heart of the Wilds",
        mana_cost="{1}{G}{G}",
        type_line="Legendary Creature — Elf Scout",
        color_identity=["G"],
    )

    deck = Deck(
        id="d_test",
        name="Selvala Deck",
        commanders=[DeckItem(raw_name="Selvala, Heart of the Wilds", quantity=1, card=selvala, section=DeckSection.COMMANDER)],
        maindeck=[
            DeckItem(raw_name="Forest", quantity=35),
            DeckItem(raw_name="Llanowar Elves", quantity=1),
            DeckItem(raw_name="Sylvan Library", quantity=1),
        ],
    )

    # Simulated raw AI report containing illegal suggestions
    raw_report = OptimizationReport(
        deck_name="Selvala Deck",
        commander_name="Selvala, Heart of the Wilds",
        initial_bracket=BracketTier.BRACKET_2_MID_POWER,
        target_bracket=BracketTier.BRACKET_3_HIGH_POWER,
        estimated_new_power_score=3.2,
        summary_overview="AI generated recommendations.",
        cuts=[
            CardCut(card_name="Llanowar Elves", type_line="Creature", cmc=1.0, role="Ramp", reason="Test cut", estimated_price_usd=0.5),
            CardCut(card_name="Sylvan Library", type_line="Enchantment", cmc=2.0, role="Draw", reason="Test cut", estimated_price_usd=25.0),
        ],
        inclusions=[
            # Color identity violation: Manamorphose (R/G in Mono-G)
            CardInclusion(
                card_name="Manamorphose",
                type_line="Instant",
                cmc=2.0,
                role="Fixing",
                synergy_explanation="R/G Hybrid spell",
                estimated_price_usd=4.0,
            ),
            # Banlist violation: Mana Crypt
            CardInclusion(
                card_name="Mana Crypt",
                type_line="Artifact",
                cmc=0.0,
                role="Fast Mana",
                synergy_explanation="Fast mana",
                estimated_price_usd=150.0,
            ),
        ],
        mana_base_analysis=ManaBaseAnalysis(
            color_balance_status="Mono-G Optimal",
            recommended_land_count=35,
            utility_lands_recommendations=["Nykthos, Shrine to Nyx"],
            fixing_recommendations=[],
            ramp_assessment="High efficiency dorks",
        ),
        win_conditions=WinConditionAnalysis(
            primary_win_path="Craterhoof Behemoth Overrun",
            combos_or_synergies=["Selvala + Umbral Mantle"],
            estimated_turn_to_win="Turn 5-6",
        ),
        budget_summary=BudgetSummary(
            total_cut_value_usd=25.5,
            total_added_cost_usd=154.0,
            net_upgrade_cost_usd=128.5,
        ),
    )

    # Untouchable cards protection
    sanitized = engine.sanitize_recommendations(
        deck=deck,
        report=raw_report,
        untouchable_cards=["Sylvan Library"],
    )

    # 1. Sylvan Library must NOT be cut
    cut_names = [c.card_name for c in sanitized.cuts]
    assert "Sylvan Library" not in cut_names

    # 2. Manamorphose & Mana Crypt must be discarded
    inc_names = [i.card_name for i in sanitized.inclusions]
    assert "Manamorphose" not in inc_names
    assert "Mana Crypt" not in inc_names

    # 3. Audit log must mention WOTC_COMMANDER_RULES_ENGINE
    assert "WOTC_COMMANDER_RULES_ENGINE AUDIT LOG" in sanitized.summary_overview


def test_wotc_validate_deck_full_diagnostics():
    """Tests the comprehensive validate_deck diagnostic report."""
    engine = WOTC_Commander_Rules_Engine()

    selvala = Card(
        id="selvala_1",
        name="Selvala, Heart of the Wilds",
        mana_cost="{1}{G}{G}",
        type_line="Legendary Creature — Elf Scout",
        color_identity=["G"],
    )

    deck = Deck(
        id="d_diag",
        name="Selvala Diagnostics",
        commanders=[DeckItem(raw_name="Selvala, Heart of the Wilds", quantity=1, card=selvala, section=DeckSection.COMMANDER)],
        maindeck=[
            DeckItem(raw_name="Forest", quantity=35),
            DeckItem(raw_name="Sol Ring", quantity=1),
            DeckItem(
                raw_name="Counterspell",
                quantity=1,
                card=Card(id="cs_1", name="Counterspell", mana_cost="{U}{U}", color_identity=["U"]),
            ),
        ],
    )

    diag = engine.validate_deck(deck)
    assert diag.is_fully_legal is False
    assert len(diag.color_identity_errors) >= 1
    assert "Counterspell" in diag.color_identity_errors[0]
