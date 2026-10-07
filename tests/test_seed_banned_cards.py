"""
Unit tests for seed_banned_cards.py, BannedCardsMongoService, and validate_banned_cards.
"""

import pytest
from seed_banned_cards import (
    BannedCardsMongoService,
    validate_banned_cards,
    get_banned_cards_service,
)
from mtg_deck_optimizer.models.deck import Deck, DeckItem, DeckSection


def test_banned_cards_mongo_service_seeding_and_retrieval(tmp_path):
    service = BannedCardsMongoService(cache_dir=tmp_path)
    result = service.seed_from_json()
    assert result["total_records_processed"] >= 40

    all_banned = service.get_all_banned_cards()
    assert len(all_banned) >= 40

    b_map = service.get_banned_cards_map()
    assert "mana crypt" in b_map
    assert "jeweled lotus" in b_map
    assert "dockside extortionist" in b_map
    assert "nadu, winged wisdom" in b_map
    assert "lutri, the spellchaser" in b_map


def test_validate_banned_cards_critical_violations():
    # Deck with banned format staples
    banned_deck = [
        "1 Mana Crypt",
        "1 Jeweled Lotus",
        "1 Dockside Extortionist",
        "1 Nadu, Winged Wisdom",
        "1 Sol Ring",
        "1 Counterspell",
    ]

    res = validate_banned_cards(banned_deck)
    assert res["is_legal"] is False
    assert res["has_critical_violation"] is True
    assert len(res["banned_names"]) == 4
    assert "Mana Crypt" in res["banned_names"]
    assert "Jeweled Lotus" in res["banned_names"]
    assert "Dockside Extortionist" in res["banned_names"]
    assert "Nadu, Winged Wisdom" in res["banned_names"]
    assert "BLOQUEO PRE-PROCESAMIENTO" in res["error_message"]
    assert len(res["details"]) == 4


def test_validate_banned_cards_lutri_special_companion_rule():
    # 1. Lutri as companion -> BANNED
    lutri_companion_text = """// Companion
1 Lutri, the Spellchaser
// Maindeck
1 Sol Ring
1 Island"""

    res_comp = validate_banned_cards(lutri_companion_text)
    assert res_comp["is_legal"] is False
    assert res_comp["has_critical_violation"] is True
    assert res_comp["lutri_companion_violation"] is True
    assert "Lutri, the Spellchaser" in res_comp["banned_names"]

    # 2. Lutri in Maindeck -> LEGAL
    lutri_maindeck_text = """1 Lutri, the Spellchaser
1 Sol Ring
1 Island"""

    res_main = validate_banned_cards(lutri_maindeck_text)
    assert res_main["is_legal"] is True
    assert res_main["has_critical_violation"] is False
    assert len(res_main["banned_names"]) == 0

    # 3. Lutri as Commander -> LEGAL
    lutri_cmdr_text = """// Commander
1 Lutri, the Spellchaser
// Maindeck
1 Sol Ring
1 Island"""

    res_cmdr = validate_banned_cards(lutri_cmdr_text)
    assert res_cmdr["is_legal"] is True
    assert res_cmdr["has_critical_violation"] is False


def test_validate_banned_cards_clean_legal_deck():
    clean_deck = [
        "1 Sol Ring",
        "1 Arcane Signet",
        "1 Rhystic Study",
        "1 Swords to Plowshares",
        "1 Command Tower",
        "1 Plains",
        "1 Island",
    ]

    res = validate_banned_cards(clean_deck)
    assert res["is_legal"] is True
    assert res["has_critical_violation"] is False
    assert len(res["banned_names"]) == 0
    assert res["error_message"] == ""


def test_validate_banned_cards_deck_model_support():
    deck_obj = Deck(
        name="Test Deck",
        commanders=[DeckItem(raw_name="Golos, Tireless Pilgrim")],  # Golos is Banned
        maindeck=[DeckItem(raw_name="Sol Ring"), DeckItem(raw_name="Island")],
    )

    res = validate_banned_cards(deck_obj)
    assert res["is_legal"] is False
    assert res["has_critical_violation"] is True
    assert "Golos, Tireless Pilgrim" in res["banned_names"]
