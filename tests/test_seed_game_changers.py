"""
Unit tests for seed_game_changers.py, GameChangersMongoService, and check_game_changers_count validator.
"""

import pytest
from seed_game_changers import (
    GameChangersMongoService,
    check_game_changers_count,
    get_game_changers_service,
)


def test_game_changers_service_seeding_and_retrieval(tmp_path):
    service = GameChangersMongoService(cache_dir=tmp_path)
    result = service.seed_from_json()
    assert result["total_records_processed"] >= 40

    all_gc = service.get_all_game_changers()
    assert len(all_gc) >= 40
    names_set = service.get_game_changer_names_set()
    assert "rhystic study" in names_set
    assert "cyclonic rift" in names_set
    assert "sol ring" in names_set


def test_check_game_changers_count_bracket_1_and_2():
    deck_with_gc = ["1 Sol Ring", "1 Rhystic Study", "1 Island", "1 Plains"]
    res_b1 = check_game_changers_count(deck_with_gc, target_bracket=1)
    assert res_b1["is_valid"] is False
    assert res_b1["total_count"] == 2
    assert "Sol Ring" in res_b1["found_game_changers"]
    assert "Rhystic Study" in res_b1["found_game_changers"]
    assert len(res_b1["cards_to_remove"]) == 2
    assert "INFRACCIÓN DE BRACKET 1" in res_b1["message"]

    res_b2 = check_game_changers_count(deck_with_gc, target_bracket=2)
    assert res_b2["is_valid"] is False
    assert len(res_b2["cards_to_remove"]) == 2

    # Clean casual deck
    clean_deck = ["1 Cultivate", "1 Kodama's Reach", "1 Forest", "1 Llanowar Elves"]
    res_clean_b1 = check_game_changers_count(clean_deck, target_bracket=1)
    assert res_clean_b1["is_valid"] is True
    assert res_clean_b1["total_count"] == 0
    assert len(res_clean_b1["cards_to_remove"]) == 0


def test_check_game_changers_count_bracket_3():
    # 3 Game Changers (Legal in Bracket 3)
    deck_3gc = ["1 Sol Ring", "1 Rhystic Study", "1 Cyclonic Rift", "1 Island", "1 Counterspell"]
    res_b3_legal = check_game_changers_count(deck_3gc, target_bracket=3)
    assert res_b3_legal["is_valid"] is True
    assert res_b3_legal["total_count"] == 3
    assert len(res_b3_legal["cards_to_remove"]) == 0
    assert "cumple con las reglas de Bracket 3" in res_b3_legal["message"]

    # 4 Game Changers (Illegal in Bracket 3)
    deck_4gc = [
        "1 Sol Ring",
        "1 Rhystic Study",
        "1 Cyclonic Rift",
        "1 Fierce Guardianship",
        "1 Island",
    ]
    res_b3_illegal = check_game_changers_count(deck_4gc, target_bracket=3)
    assert res_b3_illegal["is_valid"] is False
    assert res_b3_illegal["total_count"] == 4
    assert len(res_b3_illegal["cards_to_remove"]) == 1  # 4 - 3 = 1 card must be removed
    assert "INFRACCIÓN DE BRACKET 3" in res_b3_illegal["message"]


def test_check_game_changers_count_bracket_4_and_5():
    deck_cedh = [
        "1 Sol Ring",
        "1 Mana Crypt",
        "1 Mox Diamond",
        "1 Lion's Eye Diamond",
        "1 Thassa's Oracle",
        "1 Demonic Consultation",
        "1 Island",
    ]
    res_b4 = check_game_changers_count(deck_cedh, target_bracket=4)
    assert res_b4["is_valid"] is True
    assert res_b4["total_count"] >= 5
    assert len(res_b4["cards_to_remove"]) == 0

    res_b5 = check_game_changers_count(deck_cedh, target_bracket=5)
    assert res_b5["is_valid"] is True
    assert len(res_b5["cards_to_remove"]) == 0
