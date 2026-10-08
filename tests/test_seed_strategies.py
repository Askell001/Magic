"""
Unit tests for Strategy Seeding, MongoDB Service, Dynamic Bracket Filtering,
Dynamic Tribal Subtype Replacement, and AI Prompt Injection.
"""

import pytest
from pathlib import Path
from mtg_deck_optimizer.deckbuilder.strategy_service import (
    StrategyMongoService,
    get_strategies_by_bracket,
    resolve_dynamic_strategy,
    COMMON_CREATURE_SUBTYPES,
)
from seed_strategies import seed_strategies
from mtg_deck_optimizer.models.deck import Deck, DeckItem
from mtg_deck_optimizer.models.card import Card
from mtg_deck_optimizer.intent.models import UserIntent
from mtg_deck_optimizer.intent.questionnaire import build_user_intent
from mtg_deck_optimizer.brackets.standards import BracketTier
from mtg_deck_optimizer.ai.prompt_builder import AIPromptBuilder


@pytest.fixture
def strategy_service(tmp_path):
    cache_dir = tmp_path / ".cache"
    # Use offline service with temporary cache directory
    service = StrategyMongoService(cache_dir=cache_dir, connect_timeout_ms=500)
    service.seed_from_json()
    return service


def test_seed_strategies_execution():
    res = seed_strategies()
    assert res["total_read"] >= 20
    assert res["cached_locally"] >= 20


def test_bracket_filtering_bracket_1(strategy_service):
    """Bracket 1 (Exhibition / Ultra-Casual) must NOT include MLD or cEDH combo."""
    b1_strats = strategy_service.get_strategies_by_bracket(1)
    assert len(b1_strats) > 0

    ids = [s["id"] for s in b1_strats]
    assert "mass_land_destruction" not in ids
    assert "cedh_fast_combo" not in ids
    assert "stompy" in ids or "voltron" in ids


def test_bracket_filtering_bracket_5(strategy_service):
    """Bracket 5 (cEDH) must include high-efficiency / competitive archetypes."""
    b5_strats = strategy_service.get_strategies_by_bracket(5)
    assert len(b5_strats) > 0

    ids = [s["id"] for s in b5_strats]
    assert "cedh_fast_combo" in ids or "mass_land_destruction" in ids


def test_dynamic_tribal_subtype_extraction(strategy_service):
    """Tests creature subtype extraction from type line and card objects."""
    # From string with type line
    subtype_dragon = strategy_service.extract_commander_subtype("Legendary Creature — Dragon Avatar")
    assert subtype_dragon == "Dragon"

    subtype_elf = strategy_service.extract_commander_subtype("Legendary Creature — Elf Noble")
    assert subtype_elf == "Elf"

    subtype_sliver = strategy_service.extract_commander_subtype("Legendary Creature — Sliver Hivelord")
    assert subtype_sliver == "Sliver"

    # From Card object
    card_obj = Card(
        id="lathril-1",
        name="Lathril, Blade of the Elves",
        type_line="Legendary Creature — Elf Noble",
        cmc=4.0,
    )
    subtype_card = strategy_service.extract_commander_subtype(card_obj)
    assert subtype_card == "Elf"


def test_dynamic_tribal_tag_replacement(strategy_service):
    """Tests <COMMANDER_SUBTYPE> substitution across description, key_elements, and win_conditions."""
    tribal_raw = strategy_service.get_strategy_by_id("tribal_kindred")
    assert tribal_raw is not None

    # Resolve for Dragon
    dragon_strat = strategy_service.resolve_dynamic_strategy(tribal_raw, "Legendary Creature — Dragon Avatar")
    assert dragon_strat["detected_commander_subtype"] == "Dragon"
    assert "Dragon" in dragon_strat["key_elements"][0]
    assert "<COMMANDER_SUBTYPE>" not in dragon_strat["key_elements"][0]

    # Resolve for Elf
    elf_strat = strategy_service.resolve_dynamic_strategy(tribal_raw, "Legendary Creature — Elf Noble")
    assert elf_strat["detected_commander_subtype"] == "Elf"
    assert "Elf" in elf_strat["key_elements"][0]
    assert "<COMMANDER_SUBTYPE>" not in elf_strat["key_elements"][0]

    # Fallback when no commander provided
    fallback_strat = strategy_service.resolve_dynamic_strategy(tribal_raw, None)
    assert fallback_strat["active_subtype_label"] == "Criaturas de la Tribu"
    assert "Criaturas de la Tribu" in fallback_strat["key_elements"][0]


def test_ai_prompt_builder_strategy_injection():
    """Tests that the full strategy theoretical profile is injected into the LLM prompt."""
    commander = Card(
        id="ur-dragon-1",
        name="The Ur-Dragon",
        type_line="Legendary Creature — Dragon Avatar",
        cmc=9.0,
        mana_cost="{4}{W}{U}{B}{R}{G}",
        colors=["W", "U", "B", "R", "G"],
        color_identity=["W", "U", "B", "R", "G"],
    )
    deck = Deck(
        name="Ur-Dragon Tribal",
        commanders=[DeckItem(raw_name="The Ur-Dragon", card=commander, quantity=1, is_commander=True)],
        maindeck=[DeckItem(raw_name="Forest", card=Card(id="forest-1", name="Forest", type_line="Basic Land — Forest", cmc=0.0), quantity=99)],
    )

    sample_strategy = {
        "id": "tribal_kindred",
        "name": "Kindred / Tribal (Dragon)",
        "category": "Tribal / Synergy",
        "description": "Estrategia de sinergia absoluta para la tribu Dragon.",
        "key_elements": [
            "Lords de la tribu Dragon",
            "Reductores de coste de dragones",
        ],
        "win_conditions": [
            "Enjambre tribal potenciado",
            "Ataques aéreos devastadores",
        ],
    }

    intent = build_user_intent(
        target_bracket=3,
        strategy_profile=sample_strategy,
    )

    prompts = AIPromptBuilder.build_prompt(deck, intent)
    user_prompt = prompts["user"]
    system_prompt = prompts["system"]

    assert "=== SELECTED STRATEGY & THEORETICAL GUIDE ===" in user_prompt
    assert "Kindred / Tribal (Dragon)" in user_prompt
    assert "Estrategia de sinergia absoluta para la tribu Dragon." in user_prompt
    assert "Lords de la tribu Dragon" in user_prompt
    assert "Ataques aéreos devastadores" in user_prompt
    assert "STRATEGY SYNERGY ALIGNMENT" in system_prompt
