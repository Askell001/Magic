"""
Unit tests for Community Data Service, AI Prompt Builder, DeckOptimizerAgent, and OptimizationReport models.
"""

import json
from unittest.mock import MagicMock

from mtg_deck_optimizer.models.card import Card, CardPrices
from mtg_deck_optimizer.models.deck import Deck, DeckItem, DeckSection
from mtg_deck_optimizer.brackets.standards import BracketTier
from mtg_deck_optimizer.intent.models import UserIntent
from mtg_deck_optimizer.ai.community_data import CommunityDataService
from mtg_deck_optimizer.ai.prompt_builder import AIPromptBuilder
from mtg_deck_optimizer.ai.optimizer_agent import DeckOptimizerAgent
from mtg_deck_optimizer.ai.models import OptimizationReport


def make_card(name: str, cmc: float = 1.0, type_line: str = "Instant", oracle: str = "", usd: float = 1.0, ci: list = None) -> Card:
    return Card(
        id=f"id_{name.lower().replace(' ', '_')}",
        name=name,
        cmc=cmc,
        type_line=type_line,
        oracle_text=oracle,
        color_identity=ci if ci is not None else (["W", "U", "B", "R", "G"] if "Ur-Dragon" in name else ["G"]),
        prices=CardPrices(usd=usd),
    )


def test_community_data_service():
    service = CommunityDataService()
    ur_dragon_data = service.get_commander_data("The Ur-Dragon", color_identity=["W", "U", "B", "R", "G"])
    assert ur_dragon_data.commander_name == "The Ur-Dragon"
    assert len(ur_dragon_data.top_synergy_cards) > 0
    assert any(c.name == "Miirym, Sentinel Wyrm" for c in ur_dragon_data.top_synergy_cards)

    fallback_data = service.get_commander_data("Random New Commander", color_identity=["U", "B"])
    assert fallback_data.commander_name == "Random New Commander"
    assert len(fallback_data.top_staples) > 0


def test_ai_prompt_builder():
    cmdr = make_card("The Ur-Dragon", cmc=9.0, type_line="Legendary Creature — Dragon Avatar", usd=30.0)
    sol = make_card("Sol Ring", cmc=1.0, type_line="Artifact", oracle="{T}: Add {C}{C}.", usd=1.50)

    deck = Deck(
        name="Ur-Dragon High Power",
        commanders=[DeckItem(raw_name="The Ur-Dragon", card=cmdr, section=DeckSection.COMMANDER)],
        maindeck=[DeckItem(raw_name="Sol Ring", card=sol, section=DeckSection.MAINDECK)],
    )

    intent = UserIntent(
        target_bracket=BracketTier.BRACKET_3_HIGH_POWER,
        max_budget_usd=350.0,
        untouchable_cards=["The Ur-Dragon"],
    )

    prompts = AIPromptBuilder.build_prompt(deck, intent)

    assert "system" in prompts
    assert "user" in prompts
    assert "The Ur-Dragon" in prompts["user"]
    assert "$350.00 USD" in prompts["user"]
    assert "Bracket 3" in prompts["user"]
    assert "cuts" in prompts["user"]
    assert "inclusions" in prompts["user"]


def test_deck_optimizer_heuristic_inference():
    cmdr = make_card("The Ur-Dragon", cmc=9.0, type_line="Legendary Creature — Dragon Avatar", usd=30.0)
    sacred_dragon = make_card("Drakuseth, Maw of Flames", cmc=7.0, type_line="Legendary Creature — Dragon", usd=2.0)
    slow_card = make_card("Bogardan Hellkite", cmc=8.0, type_line="Creature — Dragon", usd=1.5)
    sol = make_card("Sol Ring", cmc=1.0, type_line="Artifact", oracle="{T}: Add {C}{C}.", usd=1.5)
    mountain = make_card("Mountain", cmc=0.0, type_line="Basic Land — Mountain", usd=0.1)

    deck = Deck(
        name="Casual Dragon Beatdown",
        commanders=[DeckItem(raw_name="The Ur-Dragon", card=cmdr, section=DeckSection.COMMANDER)],
        maindeck=[
            DeckItem(raw_name="Drakuseth, Maw of Flames", card=sacred_dragon),
            DeckItem(raw_name="Bogardan Hellkite", card=slow_card),
            DeckItem(raw_name="Sol Ring", card=sol),
            DeckItem(quantity=36, raw_name="Mountain", card=mountain),
        ],
    )

    # User declares Drakuseth as UNTOUCHABLE
    intent = UserIntent(
        target_bracket=BracketTier.BRACKET_3_HIGH_POWER,
        max_budget_usd=100.0,
        untouchable_cards=["The Ur-Dragon", "Drakuseth, Maw of Flames"],
    )

    agent = DeckOptimizerAgent()
    report = agent.optimize(deck=deck, intent=intent)

    assert isinstance(report, OptimizationReport)
    assert report.target_bracket == BracketTier.BRACKET_3_HIGH_POWER
    assert len(report.cuts) > 0
    assert len(report.inclusions) > 0

    # Ensure untouchable cards were NOT cut
    cut_names = [c.card_name.lower() for c in report.cuts]
    assert "the ur-dragon" not in cut_names
    assert "drakuseth, maw of flames" not in cut_names

    # Ensure Bogardan Hellkite was cut due to high CMC
    assert "bogardan hellkite" in cut_names

    # Ensure Mana base & Wincons are populated
    assert report.mana_base_analysis.recommended_land_count > 0
    assert len(report.win_conditions.combos_or_synergies) > 0
    assert report.budget_summary.total_added_cost_usd <= 100.0


def test_deck_optimizer_external_llm_mock():
    cmdr = make_card("The Ur-Dragon", cmc=9.0, type_line="Legendary Creature — Dragon Avatar", usd=30.0)
    deck = Deck(
        name="Mock LLM Test Deck",
        commanders=[DeckItem(raw_name="The Ur-Dragon", card=cmdr, section=DeckSection.COMMANDER)],
    )
    intent = UserIntent(target_bracket=BracketTier.BRACKET_4_CEDH)

    mock_llm_json = {
        "deck_name": "Mock LLM Test Deck",
        "commander_name": "The Ur-Dragon",
        "initial_bracket": 2,
        "target_bracket": 4,
        "estimated_new_power_score": 3.9,
        "summary_overview": "Optimized to cEDH tier with compact wincons.",
        "cuts": [
            {
                "card_name": "Slow Card",
                "type_line": "Creature",
                "cmc": 6.0,
                "reason": "Too slow for cEDH.",
                "estimated_price_usd": 1.0,
            }
        ],
        "inclusions": [
            {
                "card_name": "Thassa's Oracle",
                "type_line": "Creature — Merfolk Wizard",
                "cmc": 2.0,
                "role": "Wincon",
                "synergy_explanation": "Primary compact game-winning combo.",
                "estimated_price_usd": 18.0,
                "synergy_score": 90.0,
            }
        ],
        "mana_base_analysis": {
            "color_balance_status": "Optimal ABUR Duals and Fetches required.",
            "recommended_land_count": 28,
            "utility_lands_recommendations": ["Ancient Tomb", "Gemstone Caverns"],
            "fixing_recommendations": ["Original Duals", "Fetchlands"],
            "ramp_assessment": "Full fast mana suite (Mox Diamond, Chrome Mox, Lotus Petal, Mana Crypt).",
        },
        "win_conditions": {
            "primary_win_path": "Thoracle + Demonic Consultation",
            "combos_or_synergies": ["Thassa's Oracle + Tainted Pact"],
            "estimated_turn_to_win": "Turn 2-3",
        },
        "budget_summary": {
            "total_cut_value_usd": 1.0,
            "total_added_cost_usd": 18.0,
            "net_upgrade_cost_usd": 17.0,
            "is_within_budget": True,
            "budget_notes": "Within limits.",
        },
    }

    # Simulate LLM caller returning markdown-wrapped JSON
    mock_llm_caller = MagicMock(return_value=f"```json\n{json.dumps(mock_llm_json)}\n```")

    agent = DeckOptimizerAgent()
    report = agent.optimize(deck=deck, intent=intent, llm_caller=mock_llm_caller)

    assert report.deck_name == "Mock LLM Test Deck"
    assert report.target_bracket == BracketTier.BRACKET_4_CEDH
    assert report.estimated_new_power_score == 3.9
    assert report.inclusions[0].card_name == "Thassa's Oracle"
    assert mock_llm_caller.called is True
