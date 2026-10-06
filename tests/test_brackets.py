"""
Unit tests for CardRoleClassifier, Bracket definitions, and DeckGapAnalyzer.
"""

import pytest
from mtg_deck_optimizer.models.card import Card, CardPrices
from mtg_deck_optimizer.models.deck import Deck, DeckItem, DeckSection
from mtg_deck_optimizer.brackets.standards import BracketTier, FAST_MANA_CARDS, PREMIUM_TUTORS
from mtg_deck_optimizer.brackets.classifier import CardRoleClassifier
from mtg_deck_optimizer.brackets.gap_analyzer import DeckGapAnalyzer
from mtg_deck_optimizer.intent.models import UserIntent


def make_card(name: str, cmc: float = 1.0, type_line: str = "Instant", oracle: str = "", usd: float = 1.0) -> Card:
    return Card(
        id=f"id_{name.lower().replace(' ', '_')}",
        name=name,
        cmc=cmc,
        type_line=type_line,
        oracle_text=oracle,
        prices=CardPrices(usd=usd),
    )


def test_card_role_classification():
    crypt = make_card("Mana Crypt", cmc=0.0, type_line="Artifact", oracle="{T}: Add {C}{C}.")
    sol = make_card("Sol Ring", cmc=1.0, type_line="Artifact", oracle="{T}: Add {C}{C}.")
    dork = make_card("Birds of Paradise", cmc=1.0, type_line="Creature — Bird", oracle="{T}: Add one mana of any color.")
    tutor = make_card("Demonic Tutor", cmc=2.0, type_line="Sorcery", oracle="Search your library for a card...")
    fow = make_card("Force of Will", cmc=5.0, type_line="Instant", oracle="You may exile a blue card...")
    wipe = make_card("Toxic Deluge", cmc=3.0, type_line="Sorcery", oracle="Each creature gets -X/-X...")

    assert CardRoleClassifier.is_fast_mana(crypt) is True
    assert CardRoleClassifier.is_ramp(crypt) is True
    assert CardRoleClassifier.is_ramp(sol) is True
    assert CardRoleClassifier.is_ramp(dork) is True
    assert CardRoleClassifier.is_tutor(tutor) is True
    assert CardRoleClassifier.is_interaction(fow) is True
    assert CardRoleClassifier.is_board_wipe(wipe) is True


def test_combo_detection():
    thoracle = make_card("Thassa's Oracle", cmc=2.0, type_line="Creature — Merfolk Wizard")
    consult = make_card("Demonic Consultation", cmc=1.0, type_line="Instant")
    other = make_card("Island", cmc=0.0, type_line="Basic Land — Island")

    items = [
        DeckItem(raw_name="Thassa's Oracle", card=thoracle),
        DeckItem(raw_name="Demonic Consultation", card=consult),
        DeckItem(raw_name="Island", card=other),
    ]

    combos = CardRoleClassifier.detect_combos(items)
    assert len(combos) == 1
    assert "thassa's oracle" in combos[0]
    assert "demonic consultation" in combos[0]


def test_deck_classification_and_gap_analysis():
    # Build a Casual deck (High CMC, no fast mana, lots of lands)
    cmdr = make_card("The Ur-Dragon", cmc=9.0, type_line="Legendary Creature — Dragon Avatar", usd=30.0)
    sol = make_card("Sol Ring", cmc=1.0, type_line="Artifact", oracle="{T}: Add {C}{C}.", usd=1.50)
    drag1 = make_card("Dragonlord Atarka", cmc=7.0, type_line="Legendary Creature — Dragon", usd=5.0)
    drag2 = make_card("Drakuseth, Maw of Flames", cmc=7.0, type_line="Legendary Creature — Dragon", usd=2.0)
    land = make_card("Mountain", cmc=0.0, type_line="Basic Land — Mountain", usd=0.10)

    deck = Deck(
        name="Casual Dragons",
        commanders=[DeckItem(quantity=1, raw_name="The Ur-Dragon", card=cmdr, section=DeckSection.COMMANDER)],
        maindeck=[
            DeckItem(quantity=1, raw_name="Sol Ring", card=sol),
            DeckItem(quantity=1, raw_name="Dragonlord Atarka", card=drag1),
            DeckItem(quantity=1, raw_name="Drakuseth, Maw of Flames", card=drag2),
            DeckItem(quantity=38, raw_name="Mountain", card=land),
        ],
    )

    # Analyze against target Bracket 3 (High-Power)
    intent = UserIntent(
        target_bracket=BracketTier.BRACKET_3_HIGH_POWER,
        max_budget_usd=100.0,
        untouchable_cards=["The Ur-Dragon"],
    )

    gap_report = DeckGapAnalyzer.analyze(deck, intent)

    assert gap_report.current_bracket in (BracketTier.BRACKET_1_CASUAL, BracketTier.BRACKET_2_MID_POWER)
    assert gap_report.target_bracket == BracketTier.BRACKET_3_HIGH_POWER
    assert gap_report.overall_deviation_score > 0.0
    assert gap_report.cmc_detail.gap > 0.0  # High CMC
    assert gap_report.untouchable_cards_count == 1
    assert len(gap_report.recommendations) > 0
    assert any("intocables" in r.lower() for r in gap_report.recommendations)
