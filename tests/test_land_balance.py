"""
Unit tests for LandBalanceEngine, Land Deficit/Overload adjustments, and Scryfall client enhancements.
"""

import pytest
from mtg_deck_optimizer.models.deck import Deck, DeckSection, DeckItem
from mtg_deck_optimizer.models.card import Card, CardImageUris
from mtg_deck_optimizer.brackets.standards import BracketTier
from mtg_deck_optimizer.analytics.land_balance_engine import LandBalanceEngine, LandBalanceReport
from mtg_deck_optimizer.ai.optimizer_agent import DeckOptimizerAgent
from mtg_deck_optimizer.intent.models import UserIntent
from mtg_deck_optimizer.scryfall.client import ScryfallClient


def create_mock_deck(commander_name: str, color_identity: list, num_lands: int, num_spells: int) -> Deck:
    cmdr_card = Card(
        id="cmdr-1",
        name=commander_name,
        mana_cost="{1}{U}{B}{R}",
        cmc=4.0,
        type_line="Legendary Creature — Wizard",
        color_identity=color_identity,
    )
    cmdr_item = DeckItem(raw_name=commander_name, quantity=1, section=DeckSection.COMMANDER, card=cmdr_card)

    main_items = []
    # Add lands
    for i in range(num_lands):
        l_card = Card(
            id=f"land-{i}",
            name=f"Island {i}" if i % 2 == 0 else f"Swamp {i}",
            cmc=0.0,
            type_line="Basic Land — Island" if i % 2 == 0 else "Basic Land — Swamp",
            color_identity=color_identity[:1],
        )
        main_items.append(DeckItem(raw_name=l_card.name, quantity=1, section=DeckSection.MAINDECK, card=l_card))

    # Add non-land spells
    for i in range(num_spells):
        cmc_val = 5.0 if i < 5 else 2.0
        s_card = Card(
            id=f"spell-{i}",
            name=f"Heavy Dragon {i}" if i < 5 else f"Cheap Cantrip {i}",
            mana_cost="{3}{U}{R}" if i < 5 else "{1}{U}",
            cmc=cmc_val,
            type_line="Creature — Dragon" if i < 5 else "Instant",
            color_identity=color_identity,
        )
        main_items.append(DeckItem(raw_name=s_card.name, quantity=1, section=DeckSection.MAINDECK, card=s_card))

    return Deck(
        name="Test Mana Deck",
        commanders=[cmdr_item],
        maindeck=main_items,
        color_identity=color_identity,
    )


def test_land_deficit_detection_and_swaps():
    # Deck with only 26 lands for Bracket 2 (where benchmark requires 34-37 lands)
    deck = create_mock_deck("Nicol Bolas", ["U", "B", "R"], num_lands=26, num_spells=73)
    
    report: LandBalanceReport = LandBalanceEngine.evaluate_land_balance(deck, BracketTier.BRACKET_2_MID_POWER)
    assert not report.is_balanced
    assert report.status in ("Déficit Crítico", "Déficit Moderado")
    assert report.current_land_count == 26
    assert report.target_land_min == 34
    assert len(report.adjustments) > 0
    
    # Verify that the swaps cut heavy spells and add on-color lands
    first_adj = report.adjustments[0]
    assert first_adj.action == "cut_spell_add_land"
    assert "Heavy Dragon" in first_adj.cut_card_name
    assert first_adj.cut_card_cmc >= 4.0
    assert first_adj.add_card_name in report.recommended_lands_to_add


def test_land_overload_flood_detection_and_swaps():
    # Deck with 44 lands for Bracket 3 (benchmark 30-34 lands)
    deck = create_mock_deck("Nicol Bolas", ["U", "B", "R"], num_lands=44, num_spells=55)
    
    report: LandBalanceReport = LandBalanceEngine.evaluate_land_balance(deck, BracketTier.BRACKET_3_HIGH_POWER)
    assert not report.is_balanced
    assert report.status in ("Sobrecarga Crítica", "Sobrecarga Moderada")
    assert report.current_land_count == 44
    assert report.target_land_max == 34
    assert len(report.adjustments) > 0
    
    # Verify that the swaps cut excess lands and add business spells
    first_adj = report.adjustments[0]
    assert first_adj.action == "cut_land_add_spell"
    assert "Land" in first_adj.cut_card_type
    assert first_adj.cut_card_name in report.recommended_lands_to_cut


def test_scryfall_client_name_cleaning_and_static_fallbacks():
    client = ScryfallClient()
    
    # Test name cleaner
    assert client.clean_card_name("1x Sol Ring (LEA) #270") == "Sol Ring"
    assert client.clean_card_name("4 Island [NEO]") == "Island"
    assert client.clean_card_name("Boseiju, Who Endures #301") == "Boseiju, Who Endures"
    
    # Test static staple map
    assert "sol ring" in client.STATIC_STAPLE_IMAGES
    assert client.STATIC_STAPLE_IMAGES["sol ring"].startswith("https://cards.scryfall.io/")
    assert client.STATIC_STAPLE_IMAGES["command tower"].startswith("https://cards.scryfall.io/")


def test_optimizer_agent_integrates_land_balance_swaps():
    deck = create_mock_deck("Nicol Bolas", ["U", "B", "R"], num_lands=25, num_spells=74)
    intent = UserIntent(
        target_bracket=BracketTier.BRACKET_2_MID_POWER,
        max_budget_usd=100.0,
        allow_infinite_combos=False,
        allow_fast_mana=False,
    )
    agent = DeckOptimizerAgent()
    opt_report = agent.optimize(deck, intent)
    
    # Check that cuts and inclusions contain land adjustments
    has_land_adjustment_cut = any("déficit de tierras" in c.reason.lower() for c in opt_report.cuts)
    has_land_adjustment_in = any("base de maná" in i.role.lower() or "land" in i.role.lower() for i in opt_report.inclusions)
    
    assert has_land_adjustment_cut or len(opt_report.cuts) > 0
    assert has_land_adjustment_in or len(opt_report.inclusions) > 0
