"""
EDHREC Synergy Engine CLI & Test Utility.
Fetches and caches EDHREC community data for Commander decks with WotC validation.
"""

import os
import sys
import json
import logging
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).parent.resolve()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from mtg_deck_optimizer.edhrec.synergy_engine import (
    EDHREC_Synergy_Engine,
    EDHRECCacheMongoService,
    EDHRECCommanderData,
    fetch_edhrec_data,
    format_commander_slug,
    get_edhrec_engine,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_edhrec")


if __name__ == "__main__":
    print("=" * 70)
    print(" EDHREC SYNERGY ENGINE - COMMUNITY DATA & MONGODB CACHING")
    print("=" * 70)

    test_commander = "Yuriko, the Tiger's Shadow"
    slug = format_commander_slug(test_commander)
    print(f"👑 Testing Commander: '{test_commander}' (Slug: '{slug}')")

    try:
        engine = get_edhrec_engine()
        print("🌐 Querying EDHREC JSON API / MongoDB Cache...")
        data = engine.fetch_edhrec_data(test_commander)

        print(f"✅ Total Decks Analyzed: {data.total_decks:,}")
        print(f"📊 Archetype / Theme: {data.archetype_theme}")
        print(f"💾 From Cache: {data.from_cache} (Updated: {data.updated_at})")
        print("-" * 70)

        print(f"🔥 Top Synergy Cards ({len(data.high_synergy_cards)}):")
        for card in data.high_synergy_cards[:5]:
            print(f"   - {card.name} | Synergy: +{card.synergy}% | Inclusion: {card.inclusion_percent}% | CMC: {card.cmc}")

        print(f"\n🌟 Top Staples ({len(data.top_cards)}):")
        for card in data.top_cards[:5]:
            print(f"   - {card.name} | Inclusion: {card.inclusion_percent}% | Price: ${card.price_usd if card.price_usd else 0.0:.2f}")

        print(f"\n🚀 New Releases ({len(data.new_cards)}):")
        for card in data.new_cards[:5]:
            print(f"   - {card.name} | Synergy: +{card.synergy}% | Type: {card.type_line}")

        # Test WotC Rules Filtering for Bracket 3
        print("-" * 70)
        print("⚖️ Testing WotC Rules Middleware (Color Identity: U/B, Bracket 3):")
        filtered = engine.filter_by_wotc_rules(data, commander_color_identity=["U", "B"], target_bracket=3)
        print(f"   Filtered High Synergy: {len(filtered.high_synergy_cards)} cards legal")
        print(f"   Filtered Top Staples: {len(filtered.top_cards)} cards legal")
        print(f"   Filtered New Cards: {len(filtered.new_cards)} cards legal")

        print("=" * 70)
        print("🎉 EDHREC Synergy Engine verified successfully!")
    except Exception as e:
        print(f"❌ Error during EDHREC verification: {e}")
        sys.exit(1)
