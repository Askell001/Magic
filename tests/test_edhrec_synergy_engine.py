"""
Unit tests for EDHREC_Synergy_Engine:
Data fetching, slug normalization, MongoDB/local caching, and WotC rules filtering.
"""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from mtg_deck_optimizer.edhrec.synergy_engine import (
    EDHREC_Synergy_Engine,
    EDHRECCacheMongoService,
    EDHRECCommanderData,
    EDHRECCardItem,
    format_commander_slug,
)
from mtg_deck_optimizer.rules.legality import BanlistValidator


def test_format_commander_slug():
    assert format_commander_slug("Yuriko, the Tiger's Shadow") == "yuriko-the-tigers-shadow"
    assert format_commander_slug("The Ur-Dragon") == "the-ur-dragon"
    assert format_commander_slug("Atraxa, Praetors' Voice") == "atraxa-praetors-voice"
    assert format_commander_slug("Krenko, Mob Boss") == "krenko-mob-boss"
    assert format_commander_slug("Lathril, Blade of the Elves") == "lathril-blade-of-the-elves"
    assert format_commander_slug("Omnath, Locus of All") == "omnath-locus-of-all"


def test_edhrec_cache_service_ttl(tmp_path):
    cache_dir = tmp_path / "edhrec_cache"
    cache_service = EDHRECCacheMongoService(cache_dir=cache_dir, connect_timeout_ms=500)

    slug = "test-commander"
    sample_data = {
        "commander_name": "Test Commander",
        "commander_slug": slug,
        "archetype_theme": "Test Theme",
        "total_decks": 1234,
        "high_synergy_cards": [],
        "top_cards": [],
        "new_cards": [],
    }

    # Save data
    cache_service.save_cached_data(slug, "Test Commander", sample_data)

    # Retrieve data within valid TTL (48h)
    cached = cache_service.get_cached_data(slug, max_age_hours=48)
    assert cached is not None
    assert cached["commander_slug"] == slug
    assert cached["total_decks"] == 1234
    assert cached["from_cache"] is True

    # Check expired TTL (0 hours)
    expired = cache_service.get_cached_data(slug, max_age_hours=0)
    assert expired is None


def test_fetch_edhrec_data_curated_or_live():
    engine = EDHREC_Synergy_Engine()
    data = engine.fetch_edhrec_data("The Ur-Dragon")

    assert data.commander_slug == "the-ur-dragon"
    assert len(data.high_synergy_cards) > 0 or len(data.top_cards) > 0


def test_wotc_rules_middleware_filtering():
    """Validates color identity, banlist, and bracket engine filtering."""
    engine = EDHREC_Synergy_Engine()

    raw_data = EDHRECCommanderData(
        commander_name="Yuriko, the Tiger's Shadow",
        commander_slug="yuriko-the-tigers-shadow",
        archetype_theme="Ninja Tribal",
        total_decks=30000,
        high_synergy_cards=[
            EDHRECCardItem(name="Changeling Outcast", synergy=71.8, inclusion_percent=89.5, cmc=1.0, type_line="Creature — Shapeshifter"),
            EDHRECCardItem(name="Birds of Paradise", synergy=25.0, inclusion_percent=50.0, cmc=1.0, type_line="Creature — Bird"),  # Off-color (Green)
            EDHRECCardItem(name="Mana Crypt", synergy=35.0, inclusion_percent=40.0, cmc=0.0, type_line="Artifact"),  # Banned
        ],
        top_cards=[
            EDHRECCardItem(name="Brainstorm", synergy=15.0, inclusion_percent=82.9, cmc=1.0, type_line="Instant"),
            EDHRECCardItem(name="Sol Ring", synergy=10.0, inclusion_percent=95.0, cmc=1.0, type_line="Artifact"),  # Game Changer
        ],
    )

    # Filter for Dimir (U, B), Bracket 2 (0 Game Changers)
    filtered_b2 = engine.filter_by_wotc_rules(raw_data, commander_color_identity=["U", "B"], target_bracket=2)

    syn_names_b2 = [c.name for c in filtered_b2.high_synergy_cards]
    assert "Changeling Outcast" in syn_names_b2
    assert "Birds of Paradise" not in syn_names_b2  # Excluded: Green pip
    assert "Mana Crypt" not in syn_names_b2        # Excluded: Banned

    top_names_b2 = [c.name for c in filtered_b2.top_cards]
    assert "Brainstorm" in top_names_b2
    
    # Check Game Changer flags
    sol_ring_item = next((c for c in filtered_b2.top_cards if c.name == "Sol Ring"), None)
    if sol_ring_item:
        assert sol_ring_item.is_game_changer is True
        assert sol_ring_item.is_bracket_allowed is False  # Bracket 2 does not allow Sol Ring
