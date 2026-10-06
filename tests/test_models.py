"""
Unit tests for Card, Deck, and DeckAnalysis Pydantic data models.
"""

import json
from mtg_deck_optimizer.models.card import Card, CardPrices, CardImageUris
from mtg_deck_optimizer.models.deck import Deck, DeckItem, DeckSection
from mtg_deck_optimizer.models.analysis import DeckAnalysis


def test_card_model_creation_and_computed_properties():
    card = Card(
        id="f34614ff-2e6f-4d9a-a289-58b6b08197e9",
        name="Atraxa, Praetors' Voice",
        mana_cost="{G}{W}{U}{B}",
        cmc=4.0,
        type_line="Legendary Creature — Phyrexian Angel Horror",
        oracle_text="Flying, vigilance, deathtouch, lifelink\nAt the beginning of your end step, proliferate.",
        colors=["G", "W", "U", "B"],
        color_identity=["G", "W", "U", "B"],
        keywords=["Flying", "Vigilance", "Deathtouch", "Lifelink", "Proliferate"],
        prices=CardPrices(usd=18.50, usd_foil=25.00),
    )

    assert card.primary_type == "Creature"
    assert card.is_commander_eligible is True
    assert card.prices.usd == 18.50


def test_deck_model_totals_and_json_serialization():
    card_cmdr = Card(
        id="c1",
        name="The Ur-Dragon",
        mana_cost="{4}{W}{U}{B}{R}{G}",
        cmc=9.0,
        type_line="Legendary Creature — Dragon Avatar",
        colors=["W", "U", "B", "R", "G"],
        color_identity=["W", "U", "B", "R", "G"],
        prices=CardPrices(usd=30.00),
    )
    card_sol = Card(
        id="c2",
        name="Sol Ring",
        mana_cost="{1}",
        cmc=1.0,
        type_line="Artifact",
        colors=[],
        color_identity=[],
        prices=CardPrices(usd=1.50),
    )

    deck = Deck(
        name="Dragon's Hoard",
        format="commander",
        commanders=[DeckItem(quantity=1, raw_name="The Ur-Dragon", card=card_cmdr, section=DeckSection.COMMANDER)],
        maindeck=[DeckItem(quantity=1, raw_name="Sol Ring", card=card_sol, section=DeckSection.MAINDECK)],
    )

    assert deck.total_card_count == 2
    assert deck.commander_count == 1
    assert deck.maindeck_count == 1
    assert deck.color_identity == ["W", "U", "B", "R", "G"]
    assert deck.estimated_total_usd == 31.50

    # Test JSON serialization
    json_str = deck.model_dump_json(indent=2)
    parsed_json = json.loads(json_str)
    assert parsed_json["name"] == "Dragon's Hoard"
    assert len(parsed_json["commanders"]) == 1
    assert parsed_json["commanders"][0]["card"]["name"] == "The Ur-Dragon"


def test_deck_analysis_generation():
    card_cmdr = Card(
        id="c1",
        name="The Ur-Dragon",
        mana_cost="{4}{W}{U}{B}{R}{G}",
        cmc=9.0,
        type_line="Legendary Creature — Dragon Avatar",
        colors=["W", "U", "B", "R", "G"],
        color_identity=["W", "U", "B", "R", "G"],
        prices=CardPrices(usd=30.00),
    )
    card_sol = Card(
        id="c2",
        name="Sol Ring",
        mana_cost="{1}",
        cmc=1.0,
        type_line="Artifact",
        colors=[],
        color_identity=[],
        prices=CardPrices(usd=1.50),
    )
    card_land = Card(
        id="c3",
        name="Command Tower",
        cmc=0.0,
        type_line="Land",
        colors=[],
        color_identity=[],
        prices=CardPrices(usd=0.25),
    )

    deck = Deck(
        name="Analysis Test Deck",
        commanders=[DeckItem(quantity=1, raw_name="The Ur-Dragon", card=card_cmdr)],
        maindeck=[
            DeckItem(quantity=1, raw_name="Sol Ring", card=card_sol),
            DeckItem(quantity=1, raw_name="Command Tower", card=card_land),
        ],
    )

    analysis = DeckAnalysis.from_deck(deck)

    assert analysis.total_cards == 3
    assert analysis.mana_curve == {1: 1, 9: 1}  # Lands excluded from curve
    assert analysis.avg_cmc_without_lands == 5.0  # (9 + 1) / 2
    assert analysis.type_distribution["Creature"] == 1
    assert analysis.type_distribution["Artifact"] == 1
    assert analysis.type_distribution["Land"] == 1
    assert analysis.estimated_total_usd == 31.75
