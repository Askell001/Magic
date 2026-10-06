"""
Unit tests for UserIntent models and CLI questionnaire.
"""

from mtg_deck_optimizer.intent.models import UserIntent
from mtg_deck_optimizer.intent.questionnaire import ask_user_intent_cli, build_user_intent
from mtg_deck_optimizer.brackets.standards import BracketTier


def test_user_intent_untouchable_logic():
    intent = UserIntent(
        target_bracket=BracketTier.BRACKET_3_HIGH_POWER,
        untouchable_cards=["The Ur-Dragon", "Doubling Season", "Delver of Secrets // Insectile Aberration"],
    )

    assert intent.is_untouchable("the ur-dragon") is True
    assert intent.is_untouchable("The Ur-Dragon") is True
    assert intent.is_untouchable("Doubling Season") is True
    assert intent.is_untouchable("Delver of Secrets") is True
    assert intent.is_untouchable("Sol Ring") is False


def test_build_user_intent_programmatic():
    intent = build_user_intent(
        target_bracket=4,
        max_budget_usd=500.0,
        untouchable_cards=["Thassa's Oracle"],
        allow_infinite_combos=True,
    )

    assert intent.target_bracket == BracketTier.BRACKET_4_CEDH
    assert intent.max_budget_usd == 500.0
    assert intent.effective_allow_combos is True
    assert intent.is_untouchable("Thassa's Oracle") is True


def test_ask_user_intent_cli_simulated():
    # Simulate user entering "3", "250", "The Ur-Dragon, Sol Ring", "s"
    responses = iter(["3", "250", "The Ur-Dragon, Sol Ring", "s"])
    mock_input = lambda prompt="": next(responses)

    intent = ask_user_intent_cli(input_func=mock_input)

    assert intent.target_bracket == BracketTier.BRACKET_3_HIGH_POWER
    assert intent.max_budget_usd == 250.0
    assert "The Ur-Dragon" in intent.untouchable_cards
    assert "Sol Ring" in intent.untouchable_cards
    assert intent.allow_infinite_combos is True
