"""
Unit tests for the universal MTG plain text deck parser.
"""

import pytest
from mtg_deck_optimizer.parser.text_parser import MTGDeckTextParser
from mtg_deck_optimizer.models.deck import DeckSection
from tests.fixtures.sample_decks import (
    MOXFIELD_SAMPLE,
    ARCHIDEKT_SAMPLE,
    DECKSTATS_SAMPLE,
    TCGPLAYER_SAMPLE,
)


def test_parse_moxfield_sample():
    deck = MTGDeckTextParser.parse(MOXFIELD_SAMPLE, deck_name="Ur-Dragon Commander")
    
    # Assert section counts
    assert deck.name == "Ur-Dragon Commander"
    assert deck.format == "commander"
    assert len(deck.commanders) == 1
    assert deck.commanders[0].raw_name == "The Ur-Dragon"
    assert deck.commanders[0].set_code == "c17"
    assert deck.commanders[0].collector_number == "48"
    assert deck.commanders[0].is_foil is True

    # Maindeck checks
    assert len(deck.maindeck) == 20
    names = [item.raw_name for item in deck.maindeck]
    assert "Sol Ring" in names
    assert "Arcane Signet" in names
    assert "Rhystic Study" in names
    assert "Cyclonic Rift" in names

    # Specific item checks
    sol_ring = next(item for item in deck.maindeck if item.raw_name == "Sol Ring")
    assert sol_ring.set_code == "lea"
    assert sol_ring.collector_number == "270"

    rhystic = next(item for item in deck.maindeck if item.raw_name == "Rhystic Study")
    assert rhystic.is_foil is True
    assert rhystic.set_code == "jmp"

    # Sideboard and considering
    assert len(deck.sideboard) == 2
    assert len(deck.maybeboard) == 2
    assert deck.sideboard[0].raw_name == "Relic of Progenitus"
    assert deck.maybeboard[0].raw_name == "Doubling Season"


def test_parse_archidekt_sample():
    deck = MTGDeckTextParser.parse(ARCHIDEKT_SAMPLE, deck_name="Atraxa Superfriends")

    assert len(deck.commanders) == 1
    assert deck.commanders[0].raw_name == "Atraxa, Praetors' Voice"
    assert deck.commanders[0].set_code == "cmm"
    assert deck.commanders[0].collector_number == "123"
    assert deck.commanders[0].is_foil is True

    # Maindeck
    assert len(deck.maindeck) == 10
    main_names = [item.raw_name for item in deck.maindeck]
    assert "Sol Ring" in main_names
    assert "Doubling Season" in main_names
    assert "Deepglow Skate" in main_names

    # Check tags extracted
    sol_ring = next(item for item in deck.maindeck if item.raw_name == "Sol Ring")
    assert sol_ring.is_foil is True
    assert "Ramp" in sol_ring.custom_tags

    # Sideboard & Maybeboard
    assert len(deck.sideboard) == 1
    assert deck.sideboard[0].raw_name == "Heroic Intervention"
    assert len(deck.maybeboard) == 2
    assert deck.maybeboard[0].raw_name == "Vorinclex, Monstrous Raider"


def test_parse_deckstats_sample():
    deck = MTGDeckTextParser.parse(DECKSTATS_SAMPLE)

    assert len(deck.commanders) == 1
    assert deck.commanders[0].raw_name == "The Ur-Dragon"
    assert deck.commanders[0].set_code == "c17"

    assert len(deck.maindeck) == 5
    assert len(deck.sideboard) == 1
    assert len(deck.maybeboard) == 1


def test_parse_tcgplayer_sample():
    deck = MTGDeckTextParser.parse(TCGPLAYER_SAMPLE)

    assert len(deck.maindeck) == 5
    assert len(deck.sideboard) == 1
    assert deck.maindeck[0].raw_name == "The Ur-Dragon"
    assert deck.sideboard[0].raw_name == "Relic of Progenitus"


def test_parse_edge_cases():
    edge_text = """
    4x Lightning Bolt (A25) 141 *F* #Burn
    1 Fire // Ice (UMA) 225
    2x Jace, the Mind Sculptor (WWK)
    1 Delver of Secrets // Insectile Aberration (ISD)
    """
    deck = MTGDeckTextParser.parse(edge_text, default_format="modern")
    assert len(deck.maindeck) == 4

    bolt = deck.maindeck[0]
    assert bolt.quantity == 4
    assert bolt.raw_name == "Lightning Bolt"
    assert bolt.is_foil is True
    assert "Burn" in bolt.custom_tags

    split = deck.maindeck[1]
    assert split.raw_name == "Fire // Ice"

    dfc = deck.maindeck[3]
    assert dfc.raw_name == "Delver of Secrets // Insectile Aberration"


def test_parse_moxfield_inline_cmdr_and_color_identity():
    """Test standard Moxfield text export with inline *CMDR* tags."""
    moxfield_text = """
    1 Atraxa, Praetors' Voice (2X2) 196 *F* *CMDR*
    1 Sol Ring (C21) 263
    1 Arcane Signet (C21) 259
    1 Rhystic Study (WOT) 25
    """
    deck = MTGDeckTextParser.parse(moxfield_text, default_format="commander")
    assert len(deck.commanders) == 1
    assert deck.commanders[0].raw_name == "Atraxa, Praetors' Voice"
    assert deck.commanders[0].set_code == "2x2"
    assert deck.commanders[0].collector_number == "196"
    assert deck.commanders[0].is_foil is True
    assert deck.commander_name == "Atraxa, Praetors' Voice"
    assert deck.color_identity == ["W", "U", "B", "G"]
    assert len(deck.maindeck) == 3


def test_parse_moxfield_partner_commanders():
    """Test Moxfield partner commanders with *CMDR* on multiple cards."""
    partner_text = """
    1 Thrasios, Triton Hero (C16) 46 *CMDR*
    1 Tymna the Weaver (C16) 48 *CMDR*
    1 Sol Ring (C21) 263
    1 Demonic Tutor (STA) 27
    """
    deck = MTGDeckTextParser.parse(partner_text, default_format="commander")
    assert len(deck.commanders) == 2
    cmdr_names = [c.raw_name for c in deck.commanders]
    assert "Thrasios, Triton Hero" in cmdr_names
    assert "Tymna the Weaver" in cmdr_names
    assert deck.color_identity == ["W", "U", "B", "G"]

