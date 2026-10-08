"""
Seed MTG Commander Strategies to MongoDB Atlas & Bracket Filter/Resolver Service.
Reads commander_strategies.json and seeds the MongoDB 'strategies' collection with a unique index on 'id' and 'name'.
Provides dynamic bracket filtering and <COMMANDER_SUBTYPE> substitution.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

# Add project root to sys.path
BASE_DIR = Path(__file__).parent.resolve()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from mtg_deck_optimizer.deckbuilder.strategy_service import (
    StrategyMongoService,
    get_strategies_by_bracket,
    resolve_dynamic_strategy,
    get_strategy_service,
    DEFAULT_MONGO_URI,
    DB_NAME,
    COLLECTION_NAME,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_strategies")


def seed_strategies(
    json_filepath: Optional[Union[str, Path]] = None,
    mongo_uri: str = DEFAULT_MONGO_URI,
    db_name: str = DB_NAME,
) -> Dict[str, Any]:
    """
    Ingests commander_strategies.json into MongoDB collection 'strategies' with unique indexing.
    """
    service = StrategyMongoService(mongo_uri=mongo_uri, db_name=db_name)
    result = service.seed_from_json(json_filepath)
    return result


if __name__ == "__main__":
    print("=" * 70)
    print(" MTG COMMANDER STRATEGIES SEED & VALIDATION UTILITY")
    print("=" * 70)

    try:
        res = seed_strategies()
        print(f"✅ Total Strategies read from JSON: {res['total_read']}")
        print(f"📊 Connected to MongoDB: {res['using_mongodb']}")
        print(f"📥 Upserted to MongoDB 'strategies' collection: {res['upserted_to_mongo']}")
        print(f"💾 Cached locally for offline resilience: {res['cached_locally']} entries")
        print("-" * 70)

        # Test Bracket Filtering
        service = get_strategy_service()
        for b in [1, 2, 3, 4, 5]:
            strat_b = service.get_strategies_by_bracket(b)
            print(f"🎯 Bracket {b} Compatible Strategies ({len(strat_b)}):")
            names = [s['name'] for s in strat_b[:4]]
            if len(strat_b) > 4:
                names.append(f"... (+{len(strat_b)-4} more)")
            print(f"   -> {', '.join(names)}")

        # Test Dynamic Tribal Subtype Replacement
        print("-" * 70)
        print("🐉 Testing Dynamic Tribal Subtype Replacement for 'The Ur-Dragon' (Dragon Avatar):")
        tribal_raw = service.get_strategy_by_id("tribal_kindred")
        if tribal_raw:
            resolved = resolve_dynamic_strategy(tribal_raw, "The Ur-Dragon")
            print(f"   Detected Subtype: {resolved.get('detected_commander_subtype')}")
            print(f"   Sample Key Element: {resolved['key_elements'][0]}")

        print("=" * 70)
        print("🎉 Strategies seeding and verification completed successfully!")
    except Exception as e:
        print(f"❌ Error during strategies seed: {e}")
        sys.exit(1)
