"""
Service for daily updating, detecting spoiled and recently released cards from Scryfall,
and persisting them into MongoDB / Local Cache.
"""

import time
import logging
from typing import List, Dict, Any, Optional
import httpx

from ..models.card import Card
from .client import ScryfallClient
from .mongo_storage import RecentCardsRepository

logger = logging.getLogger(__name__)


class RecentCardsService:
    """
    Connects to Scryfall API search endpoints to track recently spoiled,
    current-year, and new expansion releases (Foundations, Universes Beyond, Secret Lair).
    """

    BASE_URL = "https://api.scryfall.com"
    SCRYFALL_QUERY = "is:spoiler OR year>=2026 OR (year>=2025 (set:fdn OR set:dft OR set:spg OR set:sld OR set_type:commander))"

    def __init__(
        self,
        repository: Optional[RecentCardsRepository] = None,
        request_delay: float = 0.08,
        timeout: float = 15.0,
    ):
        self.repository = repository or RecentCardsRepository()
        self.request_delay = request_delay
        self.timeout = timeout
        self.last_request_time: float = 0.0

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self.last_request_time = time.time()

    def sync_recent_and_spoiled_cards(
        self,
        custom_query: Optional[str] = None,
        max_pages: int = 2,
    ) -> Dict[str, Any]:
        """
        Executes Scryfall search for spoiled and latest releases, extracting and upserting into database.
        """
        query = custom_query or self.SCRYFALL_QUERY
        url = f"{self.BASE_URL}/cards/search"
        params = {"q": query, "order": "released", "dir": "desc"}
        headers = {
            "User-Agent": ScryfallClient.USER_AGENT,
            "Accept": "application/json",
        }

        fetched_cards: List[Dict[str, Any]] = []
        pages_processed = 0

        try:
            with httpx.Client(timeout=self.timeout) as client:
                while url and pages_processed < max_pages:
                    self._rate_limit()
                    resp = client.get(url, params=params if pages_processed == 0 else None, headers=headers)
                    if resp.status_code == 200:
                        body = resp.json()
                        raw_data = body.get("data", [])
                        for item in raw_data:
                            normalized = self._normalize_scryfall_card(item)
                            fetched_cards.append(normalized)

                        pages_processed += 1
                        has_more = body.get("has_more", False)
                        url = body.get("next_page") if has_more else None
                    elif resp.status_code == 404:
                        # No results for query
                        break
                    else:
                        logger.error(f"Scryfall recent search failed HTTP {resp.status_code}: {resp.text}")
                        break
        except Exception as e:
            logger.error(f"Error syncing recent cards from Scryfall: {e}")

        # Upsert into repository
        upserted_count = 0
        if fetched_cards:
            upserted_count = self.repository.upsert_cards(fetched_cards)

        db_status = self.repository.get_status()
        return {
            "success": True,
            "pages_processed": pages_processed,
            "cards_fetched": len(fetched_cards),
            "cards_persisted": upserted_count,
            "total_in_catalog": db_status["total_cards"],
            "storage_backend": db_status["backend"],
        }

    def get_innovations_for_commander(
        self,
        color_identity: List[str],
        limit: int = 10,
    ) -> List[Card]:
        """
        Retrieves recent/spoiled cards matching the commander's color identity,
        converted to Card models.
        """
        raw_list = self.repository.get_recent_cards_by_color(color_identity=color_identity, limit=limit)
        cards: List[Card] = []
        for r in raw_list:
            try:
                card_obj = Card.from_scryfall_dict(r)
                cards.append(card_obj)
            except Exception:
                # If simplified dict was stored
                pass
        return cards

    def _normalize_scryfall_card(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures key Scryfall attributes and spoiler tags are preserved for persistence."""
        is_spoiler = data.get("preview", {}).get("previewed_at") is not None or "preview" in data
        return {
            "id": data.get("id"),
            "oracle_id": data.get("oracle_id"),
            "name": data.get("name"),
            "mana_cost": data.get("mana_cost"),
            "cmc": float(data.get("cmc", 0.0)),
            "type_line": data.get("type_line", ""),
            "oracle_text": data.get("oracle_text", ""),
            "colors": data.get("colors", []),
            "color_identity": data.get("color_identity", []),
            "keywords": data.get("keywords", []),
            "set": data.get("set"),
            "set_name": data.get("set_name"),
            "collector_number": data.get("collector_number"),
            "rarity": data.get("rarity"),
            "layout": data.get("layout", "normal"),
            "released_at": data.get("released_at"),
            "is_spoiler": is_spoiler,
            "prices": data.get("prices", {}),
            "image_uris": data.get("image_uris", {}),
            "card_faces": data.get("card_faces"),
            "legalities": data.get("legalities", {}),
            "scryfall_uri": data.get("scryfall_uri"),
        }
