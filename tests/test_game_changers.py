"""
Unit tests for Game Changers Database and Bracket Compliance Evaluator.
"""

from mtg_deck_optimizer.models.deck import Deck, DeckItem, DeckSection
from mtg_deck_optimizer.brackets.standards import BracketTier
from mtg_deck_optimizer.brackets.game_changers import (
    GAME_CHANGERS_DATABASE,
    GameChangersEvaluator,
    GameChangerViolation,
)
from mtg_deck_optimizer.intent import build_user_intent
from mtg_deck_optimizer.ai.optimizer_agent import DeckOptimizerAgent


def test_game_changers_database_structure():
    assert "Thassa's Oracle" in GAME_CHANGERS_DATABASE
    assert "Mana Crypt" in GAME_CHANGERS_DATABASE
    assert "Winter Orb" in GAME_CHANGERS_DATABASE
    assert "Rhystic Study" in GAME_CHANGERS_DATABASE

    thoracle = GAME_CHANGERS_DATABASE["Thassa's Oracle"]
    assert 4 in thoracle.allowed_in_brackets
    assert 5 in thoracle.allowed_in_brackets
    assert "Laboratory Maniac" in thoracle.suggested_replacements_by_bracket[3]


def test_game_changers_downshift_detection():
    # Deck with Bracket 4 cards (Thoracle + Consultation + Mana Crypt)
    deck = Deck(
        name="cEDH Inalla",
        format="commander",
        commanders=[DeckItem(raw_name="Inalla, Archmage Ritualist", section=DeckSection.COMMANDER)],
        maindeck=[
            DeckItem(raw_name="Thassa's Oracle", section=DeckSection.MAINDECK),
            DeckItem(raw_name="Demonic Consultation", section=DeckSection.MAINDECK),
            DeckItem(raw_name="Mana Crypt", section=DeckSection.MAINDECK),
            DeckItem(raw_name="Sol Ring", section=DeckSection.MAINDECK),
            DeckItem(raw_name="Counterspell", section=DeckSection.MAINDECK),
        ],
    )

    # Downshifting to Bracket 3
    violations_b3 = GameChangersEvaluator.evaluate_bracket_compliance(deck, target_bracket=3)
    violated_names = [v.card_name for v in violations_b3]

    assert "Thassa's Oracle" in violated_names
    assert "Demonic Consultation" in violated_names
    assert "Mana Crypt" in violated_names
    assert "Sol Ring" not in violated_names  # Sol Ring is legal in Bracket 3

    # Downshifting to Bracket 2
    violations_b2 = GameChangersEvaluator.evaluate_bracket_compliance(deck, target_bracket=2)
    assert len(violations_b2) >= 3


def test_optimizer_agent_downshift_cuts_and_inclusions():
    deck = Deck(
        name="High-Power Turbo",
        format="commander",
        commanders=[DeckItem(raw_name="Kess, Dissident Mage", section=DeckSection.COMMANDER)],
        maindeck=[
            DeckItem(raw_name="Thassa's Oracle", section=DeckSection.MAINDECK),
            DeckItem(raw_name="Demonic Consultation", section=DeckSection.MAINDECK),
            DeckItem(raw_name="Winter Orb", section=DeckSection.MAINDECK),
            DeckItem(raw_name="Sol Ring", section=DeckSection.MAINDECK),
            DeckItem(raw_name="Island", quantity=30, section=DeckSection.MAINDECK),
        ],
    )

    intent = build_user_intent(target_bracket=3)
    agent = DeckOptimizerAgent()
    report = agent.optimize(deck, intent)

    cut_names = [c.card_name for c in report.cuts]
    assert "Thassa's Oracle" in cut_names
    assert "Demonic Consultation" in cut_names
    assert "Winter Orb" in cut_names

    # Check that in-bracket replacements are included
    inc_names = [i.card_name for i in report.inclusions]
    assert len(inc_names) >= 3


def test_game_changers_individual_audit():
    deck = Deck(
        name="Urza Stax Engine",
        format="commander",
        commanders=[DeckItem(raw_name="Urza, Lord High Artificer", section=DeckSection.COMMANDER)],
        maindeck=[
            DeckItem(raw_name="Mana Crypt", section=DeckSection.MAINDECK),
            DeckItem(raw_name="Winter Orb", section=DeckSection.MAINDECK),
            DeckItem(raw_name="Rhystic Study", section=DeckSection.MAINDECK),
            DeckItem(raw_name="Force of Will", section=DeckSection.MAINDECK),
            DeckItem(raw_name="Island", quantity=30, section=DeckSection.MAINDECK),
        ],
    )

    # Audit for Bracket 3
    audit_b3 = GameChangersEvaluator.audit_deck_game_changers(deck, target_bracket=3)
    assert len(audit_b3) == 4
    
    # Mana Crypt and Winter Orb are only allowed in Bracket 4 -> is_allowed is False
    crypt_audit = next(a for a in audit_b3 if a.card_name == "Mana Crypt")
    assert crypt_audit.is_allowed is False
    assert "DEBE SALIR" in crypt_audit.status_label
    assert "S-Tier" in crypt_audit.efficiency_tier
    assert len(crypt_audit.suggested_in_bracket_replacements) > 0

    # Rhystic Study and Force of Will are allowed in Bracket 3 & 4 -> is_allowed is True
    rhystic_audit = next(a for a in audit_b3 if a.card_name == "Rhystic Study")
    assert rhystic_audit.is_allowed is True
    assert "PERMANECE" in rhystic_audit.status_label
    assert "S-Tier" in rhystic_audit.efficiency_tier

