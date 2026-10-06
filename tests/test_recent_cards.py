"""
Unit tests for RecentCardsRepository, RecentCardsService, and RecentCardsContextInjector.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

from mtg_deck_optimizer.scryfall.mongo_storage import RecentCardsRepository
from mtg_deck_optimizer.scryfall.recent_cards_service import RecentCardsService
from mtg_deck_optimizer.ai.context_injector import RecentCardsContextInjector


def test_recent_cards_repository_local_cache(tmp_path):
    repo = RecentCardsRepository(mongo_uri="mongodb://invalid:27017/", cache_dir=tmp_path, connect_timeout_ms=500)
    assert repo.using_mongodb is False  # Correctly fell back to local cache

    sample_cards = [
        {
            "id": "c1",
            "name": "Kaito, Bane of Nightmares",
            "mana_cost": "{1}{U}{B}",
            "cmc": 3.0,
            "type_line": "Legendary Planeswalker — Kaito",
            "colors": ["U", "B"],
            "color_identity": ["U", "B"],
            "set": "dsk",
            "released_at": "2024-09-27",
            "prices": {"usd": "18.50"},
            "oracle_text": "Ninjutsu {1}{U}{B}...",
        },
        {
            "id": "c2",
            "name": "Valgavoth, Terror Eater",
            "mana_cost": "{6}{B}{B}{B}",
            "cmc": 9.0,
            "type_line": "Legendary Creature — Elder Demon",
            "colors": ["B"],
            "color_identity": ["B"],
            "set": "dsk",
            "released_at": "2024-09-27",
            "prices": {"usd": "24.00"},
            "oracle_text": "Flying, lifelink, ward...",
        },
        {
            "id": "c3",
            "name": "Overlord of the Hauntwoods",
            "mana_cost": "{3}{G}{G}",
            "cmc": 5.0,
            "type_line": "Enchantment Creature — Avatar Horror",
            "colors": ["G"],
            "color_identity": ["G"],
            "set": "dsk",
            "released_at": "2024-09-27",
            "prices": {"usd": "15.00"},
            "oracle_text": "Impending 4...",
        },
    ]

    count = repo.upsert_cards(sample_cards)
    assert count == 3
    assert repo.count_recent_cards() == 3

    # Test color filtering: Esper ["W", "U", "B"] should match Kaito and Valgavoth, but not Overlord (Green)
    esper_cards = repo.get_recent_cards_by_color(color_identity=["W", "U", "B"])
    names = [c["name"] for c in esper_cards]
    assert "Kaito, Bane of Nightmares" in names
    assert "Valgavoth, Terror Eater" in names
    assert "Overlord of the Hauntwoods" not in names


def test_recent_cards_service_sync_mocked(tmp_path):
    repo = RecentCardsRepository(mongo_uri="mongodb://invalid:27017/", cache_dir=tmp_path, connect_timeout_ms=500)
    service = RecentCardsService(repository=repo)

    mock_scryfall_search_response = {
        "data": [
            {
                "id": "s1",
                "name": "Screaming Nemesis",
                "mana_cost": "{2}{R}",
                "cmc": 3.0,
                "type_line": "Creature — Spirit Nemesis",
                "colors": ["R"],
                "color_identity": ["R"],
                "set": "dsk",
                "set_name": "Duskmourn: House of Horror",
                "collector_number": "157",
                "rarity": "rare",
                "released_at": "2024-09-27",
                "oracle_text": "Haste\nWhenever Screaming Nemesis is dealt damage...",
                "prices": {"usd": "12.00"},
                "preview": {"previewed_at": "2024-08-30"},
            }
        ],
        "has_more": False,
    }

    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_scryfall_search_response
        mock_get.return_value = mock_resp

        result = service.sync_recent_and_spoiled_cards()
        assert result["success"] is True
        assert result["cards_fetched"] == 1
        assert repo.count_recent_cards() == 1


def test_context_injector_formatting(tmp_path):
    repo = RecentCardsRepository(mongo_uri="mongodb://invalid:27017/", cache_dir=tmp_path, connect_timeout_ms=500)
    repo.upsert_cards([
        {
            "id": "s1",
            "name": "Kona, Rescue Beastie",
            "mana_cost": "{3}{G}",
            "cmc": 4.0,
            "type_line": "Legendary Creature — Beast Survivor",
            "colors": ["G"],
            "color_identity": ["G"],
            "set": "dsk",
            "released_at": "2024-09-27",
            "oracle_text": "Survival — Whenever Kona becomes tapped...",
            "prices": {"usd": "6.50"},
            "is_spoiler": False,
        }
    ])

    service = RecentCardsService(repository=repo)
    injector = RecentCardsContextInjector(recent_service=service)

    block = injector.format_recent_innovations_block(color_identity=["G", "R", "W"])
    assert "Kona, Rescue Beastie" in block
    assert "CARTAS E INNOVACIONES RECIENTES" in block
    assert "$6.50 USD" in block
