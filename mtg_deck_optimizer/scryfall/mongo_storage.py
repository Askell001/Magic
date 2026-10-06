"""
Storage repository for Recent and Spoiled MTG Cards with MongoDB Atlas support
and an automatic local disk cache fallback.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import os
from typing import List, Dict, Any, Optional, Set

logger = logging.getLogger(__name__)

DEFAULT_MONGO_URI = os.getenv("MONGODB_URI", "mongodb+srv://user:12345@registrousuarios.e6jeny6.mongodb.net/")
DB_NAME = os.getenv("MONGODB_DB", "mtg_optimizer")
COLLECTION_NAME = "recent_cards"


class RecentCardsRepository:
    """
    Manages persistence of recently spoiled and newly released cards.
    Attempts MongoDB connection first; seamlessly falls back to a persistent local JSON cache
    if network or credentials fail.
    """

    def __init__(
        self,
        mongo_uri: str = DEFAULT_MONGO_URI,
        cache_dir: Optional[Path] = None,
        connect_timeout_ms: int = 4000,
    ):
        self.mongo_uri = mongo_uri
        self.cache_dir = cache_dir or (Path(__file__).parent.parent.parent / ".cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "recent_cards_cache.json"

        self.client = None
        self.db = None
        self.collection = None
        self.using_mongodb = False

        self._init_mongo(connect_timeout_ms)

    def _init_mongo(self, timeout_ms: int):
        """Attempts to initialize MongoDB client and verify connectivity."""
        try:
            import pymongo
            self.client = pymongo.MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=timeout_ms,
                connectTimeoutMS=timeout_ms,
            )
            # Trigger server selection check
            self.client.admin.command("ping")
            self.db = self.client[DB_NAME]
            self.collection = self.db[COLLECTION_NAME]
            # Create indexes
            self.collection.create_index("name", unique=True)
            self.collection.create_index("color_identity")
            self.collection.create_index("released_at")
            self.using_mongodb = True
            logger.info("Connected successfully to MongoDB Atlas for Recent Cards.")
        except Exception as e:
            logger.warning(f"MongoDB connection unavailable ({e}). Using persistent local disk cache: {self.cache_file}")
            self.using_mongodb = False

    def upsert_cards(self, cards_data: List[Dict[str, Any]]) -> int:
        """
        Inserts or updates cards incrementally.
        """
        if not cards_data:
            return 0

        now_str = datetime.now(timezone.utc).isoformat()
        for c in cards_data:
            c["last_updated_at"] = now_str

        # 1. Update local cache always for fast offline reads
        local_cards = self._read_local_cache()
        by_name = {c["name"].lower(): c for c in local_cards}
        for c in cards_data:
            by_name[c["name"].lower()] = c
        updated_list = list(by_name.values())
        self._write_local_cache(updated_list)

        # 2. Update MongoDB if connected
        if self.using_mongodb and self.collection is not None:
            try:
                import pymongo
                operations = []
                for c in cards_data:
                    operations.append(
                        pymongo.UpdateOne(
                            {"name": c["name"]},
                            {"$set": c},
                            upsert=True,
                        )
                    )
                result = self.collection.bulk_write(operations)
                return result.upserted_count + result.modified_count
            except Exception as e:
                logger.error(f"MongoDB bulk write error: {e}. Local cache updated.")

        return len(cards_data)

    def get_recent_cards_by_color(self, color_identity: List[str], limit: int = 15) -> List[Dict[str, Any]]:
        """
        Retrieves recent/spoiled cards matching the given color identity (subset).
        """
        allowed_colors = set(c.upper() for c in color_identity)

        # Query MongoDB if available
        if self.using_mongodb and self.collection is not None:
            try:
                cursor = self.collection.find(
                    {"color_identity": {"$not": {"$elemMatch": {"$nin": list(allowed_colors)}}}}
                ).sort("released_at", -1).limit(limit)
                results = list(cursor)
                if results:
                    # Remove Mongo _id from output
                    for r in results:
                        r.pop("_id", None)
                    return results
            except Exception as e:
                logger.warning(f"MongoDB query failed ({e}), reading from local cache.")

        # Fallback to local cache filtering
        local_cards = self._read_local_cache()
        filtered = []
        for card in local_cards:
            card_ci = set(c.upper() for c in card.get("color_identity", []))
            if card_ci.issubset(allowed_colors):
                filtered.append(card)

        # Sort by released_at descending
        filtered.sort(key=lambda x: str(x.get("released_at", "")), reverse=True)
        return filtered[:limit]

    def get_all_recent_cards(self) -> List[Dict[str, Any]]:
        """Returns all cached recent and spoiled cards."""
        if self.using_mongodb and self.collection is not None:
            try:
                cursor = self.collection.find({}).sort("released_at", -1)
                results = list(cursor)
                for r in results:
                    r.pop("_id", None)
                return results
            except Exception:
                pass
        return self._read_local_cache()

    def count_recent_cards(self) -> int:
        if self.using_mongodb and self.collection is not None:
            try:
                return self.collection.count_documents({})
            except Exception:
                pass
        return len(self._read_local_cache())

    def get_status(self) -> Dict[str, Any]:
        count = self.count_recent_cards()
        return {
            "backend": "MongoDB Atlas" if self.using_mongodb else "Local JSON Cache",
            "total_cards": count,
            "cache_file": str(self.cache_file),
            "status": "Online" if self.using_mongodb else "Local Fallback Active",
        }

    def _read_local_cache(self) -> List[Dict[str, Any]]:
        if not self.cache_file.exists():
            return []
        try:
            return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write_local_cache(self, cards: List[Dict[str, Any]]):
        try:
            self.cache_file.write_text(json.dumps(cards, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write local recent cards cache: {e}")
