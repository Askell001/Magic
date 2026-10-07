"""
Comprehensive unit tests for the official WOTC_Bracket_Engine (5 Brackets System).
"""

import pytest
from mtg_deck_optimizer.models.card import Card, CardPrices
from mtg_deck_optimizer.models.deck import Deck, DeckItem, DeckSection
from mtg_deck_optimizer.brackets.standards import (
    BracketTier,
    GAME_CHANGERS_MAX_ALLOWED,
)
from mtg_deck_optimizer.brackets.wotc_bracket_engine import (
    WOTC_Bracket_Engine,
    ViolationCategory,
)


def make_test_card(name: str, cmc: float = 2.0, type_line: str = "Sorcery") -> Card:
    return Card(
        id=f"id_{name.lower().replace(' ', '_').replace(',', '')}",
        name=name,
        cmc=cmc,
        type_line=type_line,
        colors=["U"],
        color_identity=["U"],
        prices=CardPrices(usd=2.0),
    )


def test_bracket_matrix_metadata():
    matrix = WOTC_Bracket_Engine.get_bracket_matrix()
    assert len(matrix) == 5
    assert matrix[1]["max_game_changers"] == 0
    assert matrix[2]["max_game_changers"] == 0
    assert matrix[3]["max_game_changers"] == 3
    assert matrix[4]["max_game_changers"] > 100
    assert matrix[5]["max_game_changers"] > 100
    assert "Exhibition" in matrix[1]["label"]
    assert "Core" in matrix[2]["label"]
    assert "Upgraded" in matrix[3]["label"]
    assert "Optimized" in matrix[4]["label"]
    assert "cEDH" in matrix[5]["label"]


def test_bracket_1_rules_violation_game_changers():
    # Deck with Sol Ring (Game Changer) in Bracket 1
    deck = Deck(
        name="Casual Deck",
        commanders=[DeckItem(raw_name="Talrand, Sky Summoner", card=make_test_card("Talrand, Sky Summoner", 4.0, "Legendary Creature"))],
        maindeck=[
            DeckItem(raw_name="Sol Ring", card=make_test_card("Sol Ring", 1.0, "Artifact")),
            DeckItem(raw_name="Opt", card=make_test_card("Opt", 1.0, "Instant")),
            DeckItem(raw_name="Ponder", card=make_test_card("Ponder", 1.0, "Sorcery")),
            DeckItem(raw_name="Island", quantity=35, card=make_test_card("Island", 0.0, "Basic Land")),
        ],
    )

    report_b1 = WOTC_Bracket_Engine.audit_deck(deck, target_bracket=1)
    assert report_b1.is_legal_for_bracket is False
    assert any(v.category == ViolationCategory.GAME_CHANGER_QUOTA for v in report_b1.violations)
    assert any(r.card_name == "Sol Ring" for r in report_b1.cards_to_remove)


def test_bracket_1_rules_violation_extra_turns_and_mld():
    # Deck with Time Warp (Extra turn) and Armageddon (MLD) in Bracket 1
    deck = Deck(
        name="Jank Deck",
        commanders=[DeckItem(raw_name="Talrand, Sky Summoner", card=make_test_card("Talrand, Sky Summoner", 4.0))],
        maindeck=[
            DeckItem(raw_name="Time Warp", card=make_test_card("Time Warp", 5.0, "Sorcery")),
            DeckItem(raw_name="Armageddon", card=make_test_card("Armageddon", 4.0, "Sorcery")),
            DeckItem(raw_name="Island", quantity=35, card=make_test_card("Island", 0.0, "Basic Land")),
        ],
    )

    report_b1 = WOTC_Bracket_Engine.audit_deck(deck, target_bracket=1)
    assert report_b1.is_legal_for_bracket is False
    assert any(v.category == ViolationCategory.EXTRA_TURNS for v in report_b1.violations)
    assert any(v.category == ViolationCategory.MASS_LAND_DENIAL for v in report_b1.violations)


def test_bracket_2_combos_and_mld_prohibited():
    # Deck with 2-Card Combo (Heliod + Ballista) in Bracket 2
    deck = Deck(
        name="Precon Heliod",
        commanders=[DeckItem(raw_name="Heliod, Sun-Crowned", card=make_test_card("Heliod, Sun-Crowned", 3.0, "Legendary Enchantment Creature"))],
        maindeck=[
            DeckItem(raw_name="Walking Ballista", card=make_test_card("Walking Ballista", 0.0, "Artifact Creature")),
            DeckItem(raw_name="Plains", quantity=36, card=make_test_card("Plains", 0.0, "Basic Land")),
        ],
    )

    report_b2 = WOTC_Bracket_Engine.audit_deck(deck, target_bracket=2)
    assert report_b2.is_legal_for_bracket is False
    assert any(v.category == ViolationCategory.PROHIBITED_COMBO for v in report_b2.violations)
    assert any(r.card_name == "Walking Ballista" for r in report_b2.cards_to_remove)


def test_bracket_3_max_3_game_changers_quota():
    # Deck with 4 Game Changers in Bracket 3 (Sol Ring, Rhystic Study, Cyclonic Rift, Fierce Guardianship)
    deck = Deck(
        name="High Power Blue",
        commanders=[DeckItem(raw_name="Urza, Lord High Artificer", card=make_test_card("Urza, Lord High Artificer", 4.0))],
        maindeck=[
            DeckItem(raw_name="Sol Ring", card=make_test_card("Sol Ring", 1.0, "Artifact")),
            DeckItem(raw_name="Rhystic Study", card=make_test_card("Rhystic Study", 3.0, "Enchantment")),
            DeckItem(raw_name="Cyclonic Rift", card=make_test_card("Cyclonic Rift", 2.0, "Instant")),
            DeckItem(raw_name="Fierce Guardianship", card=make_test_card("Fierce Guardianship", 3.0, "Instant")),
            DeckItem(raw_name="Island", quantity=34, card=make_test_card("Island", 0.0, "Basic Land")),
        ],
    )

    report_b3 = WOTC_Bracket_Engine.audit_deck(deck, target_bracket=3)
    assert report_b3.is_legal_for_bracket is False
    assert report_b3.total_game_changers_count == 4
    assert report_b3.max_allowed_game_changers == 3
    assert any(v.category == ViolationCategory.GAME_CHANGER_QUOTA for v in report_b3.violations)
    assert len(report_b3.cards_to_remove) == 1  # 4 - 3 = 1 card must be removed

    # Deck with 3 Game Changers in Bracket 3 (Legal)
    deck_3gc = Deck(
        name="High Power Blue Legal",
        commanders=[DeckItem(raw_name="Urza, Lord High Artificer", card=make_test_card("Urza, Lord High Artificer", 4.0))],
        maindeck=[
            DeckItem(raw_name="Sol Ring", card=make_test_card("Sol Ring", 1.0, "Artifact")),
            DeckItem(raw_name="Rhystic Study", card=make_test_card("Rhystic Study", 3.0, "Enchantment")),
            DeckItem(raw_name="Cyclonic Rift", card=make_test_card("Cyclonic Rift", 2.0, "Instant")),
            DeckItem(raw_name="Island", quantity=34, card=make_test_card("Island", 0.0, "Basic Land")),
        ],
    )

    report_legal_b3 = WOTC_Bracket_Engine.audit_deck(deck_3gc, target_bracket=3)
    assert report_legal_b3.is_legal_for_bracket is True
    assert len(report_legal_b3.violations) == 0


def test_bracket_4_and_5_unlimited_game_changers():
    # cEDH Deck with multiple Game Changers, combos and fast mana
    deck_cedh = Deck(
        name="cEDH Rog/Silas",
        commanders=[DeckItem(raw_name="Rograkh, Son of Rohgahh", card=make_test_card("Rograkh, Son of Rohgahh", 0.0))],
        maindeck=[
            DeckItem(raw_name="Thassa's Oracle", card=make_test_card("Thassa's Oracle", 2.0)),
            DeckItem(raw_name="Demonic Consultation", card=make_test_card("Demonic Consultation", 1.0)),
            DeckItem(raw_name="Mana Crypt", card=make_test_card("Mana Crypt", 0.0)),
            DeckItem(raw_name="Mox Diamond", card=make_test_card("Mox Diamond", 0.0)),
            DeckItem(raw_name="Lion's Eye Diamond", card=make_test_card("Lion's Eye Diamond", 0.0)),
            DeckItem(raw_name="Force of Will", card=make_test_card("Force of Will", 5.0)),
            DeckItem(raw_name="Underworld Breach", card=make_test_card("Underworld Breach", 2.0)),
            DeckItem(raw_name="Brain Freeze", card=make_test_card("Brain Freeze", 2.0)),
            DeckItem(raw_name="Island", quantity=25, card=make_test_card("Island", 0.0, "Basic Land")),
        ],
    )

    report_b4 = WOTC_Bracket_Engine.audit_deck(deck_cedh, target_bracket=4)
    assert report_b4.is_legal_for_bracket is True

    report_b5 = WOTC_Bracket_Engine.audit_deck(deck_cedh, target_bracket=5)
    assert report_b5.is_legal_for_bracket is True
