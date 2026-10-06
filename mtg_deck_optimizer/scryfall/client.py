"""
Scryfall Public API Client supporting batch card resolution via /cards/collection,
robust multi-tier single card resolution (exact -> fuzzy -> DFC face -> search),
rate limiting compliance, in-memory & persistent caching, and Card model deserialization.
"""

import time
import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from pathlib import Path
import httpx

from ..models.card import Card
from ..models.deck import Deck, DeckItem

logger = logging.getLogger(__name__)


class ScryfallClient:
    """
    Client for Scryfall REST API compliant with Scryfall rate limits, collection endpoints,
    and bulletproof fallback resolution.
    """

    BASE_URL = "https://api.scryfall.com"
    BATCH_SIZE_LIMIT = 75  # Scryfall maximum per /cards/collection POST request
    DEFAULT_DELAY = 0.08  # 80ms delay between requests (Scryfall requests 50-100ms)
    USER_AGENT = "MTGDeckOptimizer/2.0 (https://github.com/mtg-deck-optimizer)"

    # Direct static CDN fallbacks for staple cards
    STATIC_STAPLE_IMAGES = {
        "sol ring": "https://cards.scryfall.io/normal/front/4/c/4c565076-5db2-47ea-8ee0-4a4fd7bb353d.jpg",
        "arcane signet": "https://cards.scryfall.io/normal/front/2/2/22757544-7709-4b65-94af-bf77694f4c29.jpg",
        "command tower": "https://cards.scryfall.io/normal/front/1/3/13243916-a36c-48be-8f64-4e4b78912e6c.jpg",
        "swords to plowshares": "https://cards.scryfall.io/normal/front/7/c/7c85d402-9988-4f81-a53d-27b91bfad1bb.jpg",
        "counterspell": "https://cards.scryfall.io/normal/front/4/f/4f0aeaf4-6417-4a3d-9867-7248e3bd77ea.jpg",
        "rhystic study": "https://cards.scryfall.io/normal/front/d/6/d6914dba-0d27-4055-ac34-b3ebf5802221.jpg",
        "esper sentinel": "https://cards.scryfall.io/normal/front/f/3/f3537373-ef54-4578-9d05-6216420ee349.jpg",
        "smothering tithe": "https://cards.scryfall.io/normal/front/f/2/f25a4bbc-5b12-4b75-a468-897bb70e7931.jpg",
        "boseiju, who endures": "https://cards.scryfall.io/normal/front/2/1/2135ac5a-187b-4dc9-8f82-34e8d1603416.jpg",
        "otawara, soaring city": "https://cards.scryfall.io/normal/front/4/8/486d7edc-d983-41f0-8b78-c99aecd72996.jpg",
        "takenuma, abandoned mire": "https://cards.scryfall.io/normal/front/4/9/499037cc-a577-41cb-8ca2-5e117945634f.jpg",
        "eiganjo, seat of the empire": "https://cards.scryfall.io/normal/front/c/3/c375a022-5b57-496d-a802-e4ea8376e9e4.jpg",
        "sokenzan, crucible of defiance": "https://cards.scryfall.io/normal/front/5/6/56ea7ea5-91c3-4d4e-bb22-38b47422f27b.jpg",
        "plains": "https://cards.scryfall.io/normal/front/3/9/3932e675-ce90-410d-85aa-d2274477c7c3.jpg",
        "island": "https://cards.scryfall.io/normal/front/f/7/f7e028b1-36c1-4b13-8a30-36a54ad6f592.jpg",
        "swamp": "https://cards.scryfall.io/normal/front/0/b/0b1c97a5-d0ff-4f40-8eb7-9cfc5bfba37e.jpg",
        "mountain": "https://cards.scryfall.io/normal/front/3/a/3a8c1775-6014-4113-9118-e320499cf2ff.jpg",
        "forest": "https://cards.scryfall.io/normal/front/9/1/913cb9be-ec3a-4467-9e79-50c458319f6f.jpg",
        "watery grave": "https://cards.scryfall.io/normal/front/4/5/456ce5d6-a114-445f-be89-7cfc1d43a6d7.jpg",
        "steam vents": "https://cards.scryfall.io/normal/front/6/6/66d618f4-443c-4a6c-8cbd-5d4ea96b2cd4.jpg",
        "blood crypt": "https://cards.scryfall.io/normal/front/8/0/80517865-c052-47df-bb17-8e65e4e7e63b.jpg",
        "overgrown tomb": "https://cards.scryfall.io/normal/front/4/f/4f17f169-b541-4775-802c-7b43c683b51a.jpg",
        "sacred foundry": "https://cards.scryfall.io/normal/front/8/0/8076f8c5-7a05-4721-badd-a25223cdc04c.jpg",
        "breeding pool": "https://cards.scryfall.io/normal/front/b/b/bb54233c-0844-4965-9cde-e8a4ef3e11b8.jpg",
        "hallowed fountain": "https://cards.scryfall.io/normal/front/f/9/f97a6d34-03ab-49f1-b02e-405b733f8843.jpg",
        "godless shrine": "https://cards.scryfall.io/normal/front/c/e/ced4c824-2dfc-42ae-84e6-09f8e3f51b5b.jpg",
        "stomping ground": "https://cards.scryfall.io/normal/front/d/c/dcaa1ea6-304e-44e0-a40c-fb453880fe45.jpg",
        "temple garden": "https://cards.scryfall.io/normal/front/5/1/511790dd-b949-4969-9ed7-5fc54907fb77.jpg",
        "polluted delta": "https://cards.scryfall.io/normal/front/b/8/b854e460-a2e6-4277-bf30-4e3a9686000c.jpg",
        "flooded strand": "https://cards.scryfall.io/normal/front/8/f/8fa2a6cb-996b-4e08-9df2-5d4681615d86.jpg",
        "bloodstained mire": "https://cards.scryfall.io/normal/front/3/a/3a1050e0-c9a9-4675-b82b-8a8f152d1948.jpg",
        "wooded foothills": "https://cards.scryfall.io/normal/front/e/6/e6d42e05-9e67-4228-b0a3-ee108865675e.jpg",
        "windswept heath": "https://cards.scryfall.io/normal/front/b/d/bd1d13f7-fb3e-4f52-a7cf-1ea3d185f424.jpg",
    }

    def __init__(self, request_delay: float = DEFAULT_DELAY, timeout: float = 15.0):
        self.request_delay = request_delay
        self.timeout = timeout
        self.last_request_time: float = 0.0
        self._cache_by_name: Dict[str, Card] = {}
        self._cache_by_set_num: Dict[Tuple[str, str], Card] = {}
        # Load verified CDN card images
        json_file = Path(__file__).parent / "verified_card_images.json"
        if json_file.exists():
            try:
                with open(json_file, "r", encoding="utf-8") as jf:
                    loaded_imgs = json.load(jf)
                    self.STATIC_STAPLE_IMAGES.update(loaded_imgs)
            except Exception:
                pass

    def _rate_limit(self):
        """Enforces polite rate limiting compliant with Scryfall API."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self.last_request_time = time.time()

    @classmethod
    def clean_card_name(cls, raw_name: str) -> str:
        """Strips quantities (1x, 4), collector numbers, set codes, and brackets from card name."""
        clean = raw_name.split("(")[0].split("[")[0].split("#")[0].strip()
        clean = re.sub(r"^\d+\s*x?\s*", "", clean, flags=re.IGNORECASE).strip()
        return clean

    def get_card_by_name(self, name: str, set_code: Optional[str] = None, fuzzy: bool = True) -> Optional[Card]:
        """
        Fetches a single card by exact or fuzzy name with multi-tier fallback resolution.
        """
        clean_name = self.clean_card_name(name)
        cache_key = clean_name.lower()

        if cache_key in self._cache_by_name and not set_code:
            return self._cache_by_name[cache_key]

        # Check front face if DFC
        if " // " in cache_key:
            front = cache_key.split(" // ")[0].strip()
            if front in self._cache_by_name:
                return self._cache_by_name[front]

        headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}

        # Attempt 1: Exact search
        self._rate_limit()
        exact_params = {"set": set_code} if set_code else {}
        exact_params["exact"] = clean_name
        url_named = f"{self.BASE_URL}/cards/named"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url_named, params=exact_params, headers=headers)
                if resp.status_code == 200:
                    card = Card.from_scryfall_dict(resp.json())
                    self._cache_card(card)
                    return card

                # Attempt 2: Fuzzy search
                if fuzzy or resp.status_code == 404:
                    self._rate_limit()
                    fuzzy_params = {"set": set_code} if set_code else {}
                    fuzzy_params["fuzzy"] = clean_name
                    resp_f = client.get(url_named, params=fuzzy_params, headers=headers)
                    if resp_f.status_code == 200:
                        card = Card.from_scryfall_dict(resp_f.json())
                        self._cache_card(card)
                        return card

                # Attempt 3: Front face search if name contains ' // '
                if " // " in clean_name:
                    front_name = clean_name.split(" // ")[0].strip()
                    self._rate_limit()
                    resp_dfc = client.get(url_named, params={"exact": front_name}, headers=headers)
                    if resp_dfc.status_code == 200:
                        card = Card.from_scryfall_dict(resp_dfc.json())
                        self._cache_card(card)
                        return card

                # Attempt 4: General query search /cards/search?q=!"name"
                self._rate_limit()
                search_url = f"{self.BASE_URL}/cards/search"
                resp_s = client.get(search_url, params={"q": f'!"{clean_name}"'}, headers=headers)
                if resp_s.status_code == 200:
                    data = resp_s.json().get("data", [])
                    if data:
                        card = Card.from_scryfall_dict(data[0])
                        self._cache_card(card)
                        return card

        except Exception as e:
            logger.warning(f"Error resolving card '{clean_name}' from Scryfall: {e}")

        return None

    def fetch_cards_collection(self, identifiers: List[Dict[str, Any]]) -> Tuple[List[Card], List[Dict[str, Any]]]:
        """
        Executes Scryfall /cards/collection POST batch lookup.
        Accepts list of identifiers e.g. [{"name": "Sol Ring"}, {"set": "lea", "collector_number": "270"}].
        Returns (resolved_cards, not_found_identifiers).
        """
        if not identifiers:
            return [], []

        resolved_cards: List[Card] = []
        not_found_list: List[Dict[str, Any]] = []

        headers = {
            "User-Agent": self.USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Chunk into slices of up to BATCH_SIZE_LIMIT (75)
        for i in range(0, len(identifiers), self.BATCH_SIZE_LIMIT):
            batch = identifiers[i : i + self.BATCH_SIZE_LIMIT]
            self._rate_limit()

            url = f"{self.BASE_URL}/cards/collection"
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, json={"identifiers": batch}, headers=headers)
                    if resp.status_code == 200:
                        body = resp.json()
                        for card_data in body.get("data", []):
                            card = Card.from_scryfall_dict(card_data)
                            self._cache_card(card)
                            resolved_cards.append(card)
                        for nf in body.get("not_found", []):
                            not_found_list.append(nf)
                    else:
                        logger.error(f"Scryfall batch lookup failed with HTTP {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.error(f"Scryfall batch request exception: {e}")

        return resolved_cards, not_found_list

    def enrich_deck(self, deck: Deck) -> Deck:
        """
        Takes a Deck containing raw parsed items and enriches all items with Scryfall metadata
        using efficient batch requests and local caching.
        """
        all_items: List[DeckItem] = deck.get_all_items()
        if not all_items:
            return deck

        # Build list of unique identifiers needed
        identifiers_to_query: List[Dict[str, Any]] = []
        seen_queries: Set[str] = set()

        # Check in-memory cache first
        for item in all_items:
            cached_card = self._find_in_cache(item.raw_name, item.set_code, item.collector_number)
            if cached_card:
                item.card = cached_card
            else:
                # Prepare identifier for batch request
                clean = self.clean_card_name(item.raw_name)
                query_dict: Dict[str, Any] = {}
                if item.set_code and item.collector_number:
                    query_dict = {"set": item.set_code, "collector_number": item.collector_number}
                    q_key = f"set:{item.set_code}:{item.collector_number}"
                elif item.set_code:
                    query_dict = {"name": clean, "set": item.set_code}
                    q_key = f"name_set:{clean.lower()}:{item.set_code}"
                else:
                    query_dict = {"name": clean}
                    q_key = f"name:{clean.lower()}"

                if q_key not in seen_queries:
                    seen_queries.add(q_key)
                    identifiers_to_query.append(query_dict)

        # Batch query Scryfall for un-cached cards
        if identifiers_to_query:
            resolved_cards, not_found = self.fetch_cards_collection(identifiers_to_query)

            # If some cards failed with set/collector_number, retry fallback by name
            fallback_by_name: List[Dict[str, Any]] = []
            for nf in not_found:
                if "name" in nf:
                    clean_nf = self.clean_card_name(nf["name"])
                    fallback_by_name.append({"name": clean_nf})

            if fallback_by_name:
                retry_cards, _ = self.fetch_cards_collection(fallback_by_name)
                for rc in retry_cards:
                    self._cache_card(rc)

        # Match cards back to deck items
        for item in all_items:
            if not item.card:
                item.card = self._find_in_cache(item.raw_name, item.set_code, item.collector_number)
                if not item.card:
                    # Final single-card resolution fallback
                    item.card = self.get_card_by_name(item.raw_name, fuzzy=True)

        return deck

    def _cache_card(self, card: Card):
        """Indexes card in cache by primary name and set/collector_number."""
        self._cache_by_name[card.name.lower()] = card
        # Also cache front face name for DFCs e.g. "Delver of Secrets"
        if " // " in card.name:
            front = card.name.split(" // ")[0].strip().lower()
            self._cache_by_name[front] = card

        if card.set_code and card.collector_number:
            self._cache_by_set_num[(card.set_code.lower(), card.collector_number.lower())] = card

    def _find_in_cache(self, name: str, set_code: Optional[str], collector_number: Optional[str]) -> Optional[Card]:
        """Looks up a card from in-memory cache."""
        if set_code and collector_number:
            key = (set_code.lower(), collector_number.lower())
            if key in self._cache_by_set_num:
                return self._cache_by_set_num[key]

        clean_lower = self.clean_card_name(name).lower()
        if clean_lower in self._cache_by_name:
            return self._cache_by_name[clean_lower]

        # Check if front name of DFC was passed
        if " // " in clean_lower:
            front = clean_lower.split(" // ")[0].strip()
            if front in self._cache_by_name:
                return self._cache_by_name[front]

        return None

    def get_card_image_url(self, name: str) -> str:
        """
        Returns a high-resolution, dependable Scryfall image URL for any card name.
        Uses verified CDN map first, then cache, then single card lookup, and fallback.
        """
        import urllib.parse
        clean = self.clean_card_name(name)
        clean_l = clean.lower()
        if clean_l in self.STATIC_STAPLE_IMAGES:
            return self.STATIC_STAPLE_IMAGES[clean_l]
        if clean_l in self._cache_by_name:
            c = self._cache_by_name[clean_l]
            if c.image_uris and c.image_uris.normal and "cards.scryfall.io/back.jpg" not in c.image_uris.normal:
                return c.image_uris.normal
        # Attempt to retrieve card metadata and cache image
        scry = self.get_card_by_name(clean, fuzzy=True)
        if scry and scry.image_uris and scry.image_uris.normal:
            img = scry.image_uris.normal
            self.STATIC_STAPLE_IMAGES[clean_l] = img
            return img
        return f"https://api.scryfall.com/cards/named?exact={urllib.parse.quote(clean)}&format=image"

