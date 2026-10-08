"""
Unit and integration tests for Scryfall API client.
"""

from unittest.mock import patch, MagicMock
from mtg_deck_optimizer.scryfall.client import ScryfallClient
from mtg_deck_optimizer.models.deck import Deck, DeckItem, DeckSection


def test_scryfall_cache_and_enrichment_mocked():
    client = ScryfallClient()

    mock_scryfall_response = {
        "data": [
            {
                "id": "e0d046f4-b91c-4ce1-85e8-5b1eb7d00f7c",
                "name": "The Ur-Dragon",
                "mana_cost": "{4}{W}{U}{B}{R}{G}",
                "cmc": 9.0,
                "type_line": "Legendary Creature — Dragon Avatar",
                "oracle_text": "Flying\nEminence — ...",
                "colors": ["W", "U", "B", "R", "G"],
                "color_identity": ["W", "U", "B", "R", "G"],
                "keywords": ["Flying"],
                "set": "c17",
                "collector_number": "48",
                "rarity": "mythic",
                "prices": {"usd": "28.50", "usd_foil": "55.00"},
            },
            {
                "id": "286bfcce-89fd-4731-8da6-373c829b3e23",
                "name": "Sol Ring",
                "mana_cost": "{1}",
                "cmc": 1.0,
                "type_line": "Artifact",
                "oracle_text": "{T}: Add {C}{C}.",
                "colors": [],
                "color_identity": [],
                "keywords": [],
                "set": "lea",
                "collector_number": "270",
                "rarity": "uncommon",
                "prices": {"usd": "1.50", "usd_foil": None},
            },
        ],
        "not_found": [],
    }

    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_scryfall_response
        mock_post.return_value = mock_resp

        deck = Deck(
            name="Mock Test Deck",
            commanders=[DeckItem(raw_name="The Ur-Dragon", set_code="c17", collector_number="48", section=DeckSection.COMMANDER)],
            maindeck=[DeckItem(raw_name="Sol Ring", set_code="lea", collector_number="270", section=DeckSection.MAINDECK)],
        )

        enriched = client.enrich_deck(deck)

        assert enriched.commanders[0].card is not None
        assert enriched.commanders[0].card.name == "The Ur-Dragon"
        assert enriched.commanders[0].card.cmc == 9.0
        assert enriched.commanders[0].card.prices.usd == 28.50

        assert enriched.maindeck[0].card is not None
        assert enriched.maindeck[0].card.name == "Sol Ring"
        assert enriched.maindeck[0].card.primary_type == "Artifact"


def test_scryfall_rate_limit_429_graceful_fallback():
    client = ScryfallClient()

    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = '{"code": "rate_limited"}'
        mock_post.return_value = mock_resp

        deck = Deck(
            name="Rate Limited Deck",
            commanders=[DeckItem(raw_name="Yuriko, the Tiger's Shadow", section=DeckSection.COMMANDER)],
            maindeck=[
                DeckItem(raw_name="Island", section=DeckSection.MAINDECK),
                DeckItem(raw_name="Mystical Tutor", section=DeckSection.MAINDECK),
            ],
        )

        enriched = client.enrich_deck(deck)

        # None of the cards should be None even during 429
        assert enriched.commanders[0].card is not None
        assert enriched.commanders[0].card.name == "Yuriko, the Tiger's Shadow"
        assert enriched.maindeck[0].card is not None
        assert enriched.maindeck[0].card.name == "Island"
        assert enriched.maindeck[1].card is not None
        assert enriched.maindeck[1].card.name == "Mystical Tutor"

