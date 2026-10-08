"""
EDHREC Synergy Engine: Real-Time Community Data Extraction, MongoDB Caching & WOTC Rules Middleware.
Fetches public EDHREC JSON endpoints (https://json.edhrec.com/pages/commanders/{slug}.json),
caches data in MongoDB 'edhrec_cache' with 24-48h TTL, and filters recommendations
through WOTC Color Identity, Banlist, and 5-Bracket Game Changer limits.
"""

import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple, Union
import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Default MongoDB Configuration
DEFAULT_MONGO_URI = os.getenv("MONGODB_URI", "mongodb+srv://user:12345@registrousuarios.e6jeny6.mongodb.net/")
DB_NAME = os.getenv("MONGODB_DB", "mtg_optimizer")
COLLECTION_NAME = "edhrec_cache"
DEFAULT_CACHE_TTL_HOURS = 48  # 48-hour cache freshness window


class EDHRECCardItem(BaseModel):
    """Normalized card representation from EDHREC community dataset."""
    name: str
    sanitized: str = ""
    synergy: float = Field(default=0.0, description="Synergy percentage against the average of the color identity")
    num_decks: int = Field(default=0, description="Number of decks including this card")
    potential_decks: int = Field(default=0, description="Total potential decks analyzed")
    inclusion_percent: float = Field(default=0.0, description="Inclusion rate (num_decks / potential_decks * 100)")
    cmc: float = 0.0
    type_line: str = "Card"
    primary_type: str = "Other"
    primary_role: str = "General"
    price_usd: Optional[float] = None
    image_url: Optional[str] = None
    tag: str = "general"
    is_game_changer: bool = False
    game_changer_category: Optional[str] = None
    is_banned: bool = False
    is_color_legal: bool = True
    is_bracket_allowed: bool = True


class EDHRECCommanderData(BaseModel):
    """Complete community profile extracted from EDHREC for a specific Commander."""
    commander_name: str
    commander_slug: str
    archetype_theme: str = "Commander Archetype"
    total_decks: int = 0
    description: str = ""
    high_synergy_cards: List[EDHRECCardItem] = Field(default_factory=list)
    top_cards: List[EDHRECCardItem] = Field(default_factory=list)
    new_cards: List[EDHRECCardItem] = Field(default_factory=list)
    creatures: List[EDHRECCardItem] = Field(default_factory=list)
    instants: List[EDHRECCardItem] = Field(default_factory=list)
    sorceries: List[EDHRECCardItem] = Field(default_factory=list)
    utility_artifacts: List[EDHRECCardItem] = Field(default_factory=list)
    enchantments: List[EDHRECCardItem] = Field(default_factory=list)
    lands: List[EDHRECCardItem] = Field(default_factory=list)
    planeswalkers: List[EDHRECCardItem] = Field(default_factory=list)
    battles: List[EDHRECCardItem] = Field(default_factory=list)
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    from_cache: bool = False


def format_commander_slug(commander_name: str) -> str:
    """
    Normalizes Commander name to EDHREC slug format.
    Example: 'Yuriko, the Tiger\'s Shadow' -> 'yuriko-the-tigers-shadow'
             'The Ur-Dragon' -> 'the-ur-dragon'
             'Atraxa, Praetors\' Voice' -> 'atraxa-praetors-voice'
    """
    if not commander_name:
        return ""
    clean = commander_name.lower().strip()
    # Strip apostrophes and special quotes
    clean = re.sub(r"[\'\’\`]", "", clean)
    # Convert non-alphanumeric to hyphens
    clean = re.sub(r"[^a-z0-9]+", "-", clean)
    clean = clean.strip("-")
    return clean


class EDHRECCacheMongoService:
    """
    MongoDB service for caching EDHREC JSON payloads with unique index and TTL policy.
    """

    def __init__(
        self,
        mongo_uri: str = DEFAULT_MONGO_URI,
        db_name: str = DB_NAME,
        cache_dir: Optional[Path] = None,
        connect_timeout_ms: int = 4000,
    ):
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.collection_name = COLLECTION_NAME
        self.cache_dir = cache_dir or (Path(__file__).parent.parent.parent / ".cache" / "edhrec")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.client = None
        self.db = None
        self.collection = None
        self.using_mongodb = False

        self._init_mongo(connect_timeout_ms)

    def _init_mongo(self, timeout_ms: int):
        """Attempts to initialize MongoDB connection with unique index on 'commander_slug'."""
        try:
            import pymongo
            self.client = pymongo.MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=timeout_ms,
                connectTimeoutMS=timeout_ms,
            )
            self.client.admin.command("ping")
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            # Ensure unique index on commander_slug
            self.collection.create_index("commander_slug", unique=True)
            self.using_mongodb = True
            logger.info("EDHRECCacheMongoService successfully connected to MongoDB Atlas.")
        except Exception as e:
            self.using_mongodb = False
            logger.warning(f"MongoDB unavailable for EDHREC cache ({e}). Operating with local JSON cache.")

    def get_cached_data(self, slug: str, max_age_hours: int = DEFAULT_CACHE_TTL_HOURS) -> Optional[Dict[str, Any]]:
        """
        Retrieves cached EDHREC data if updated within max_age_hours.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=max_age_hours)

        # 1. Check MongoDB
        if self.using_mongodb and self.collection is not None:
            try:
                doc = self.collection.find_one({"commander_slug": slug})
                if doc and "updated_at" in doc and "data" in doc:
                    try:
                        updated_at = datetime.fromisoformat(doc["updated_at"])
                        if updated_at.tzinfo is None:
                            updated_at = updated_at.replace(tzinfo=timezone.utc)
                        if updated_at >= cutoff:
                            logger.info(f"EDHREC Cache HIT (MongoDB) for '{slug}' (Age: {now - updated_at}).")
                            data = doc["data"]
                            data["from_cache"] = True
                            data["updated_at"] = doc["updated_at"]
                            return data
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"MongoDB EDHREC cache lookup error: {e}")

        # 2. Check Local File Cache
        local_file = self.cache_dir / f"{slug}.json"
        if local_file.exists():
            try:
                with open(local_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                if "updated_at" in cached and "data" in cached:
                    updated_at = datetime.fromisoformat(cached["updated_at"])
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=timezone.utc)
                    if updated_at >= cutoff:
                        logger.info(f"EDHREC Cache HIT (Local JSON) for '{slug}'.")
                        data = cached["data"]
                        data["from_cache"] = True
                        data["updated_at"] = cached["updated_at"]
                        return data
            except Exception as e:
                logger.debug(f"Local EDHREC cache read error: {e}")

        return None

    def save_cached_data(self, slug: str, commander_name: str, data: Dict[str, Any]):
        """
        Stores extracted EDHREC data in MongoDB and local cache.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        doc = {
            "commander_slug": slug,
            "commander_name": commander_name,
            "updated_at": now_str,
            "data": data,
        }

        # 1. Store in MongoDB
        if self.using_mongodb and self.collection is not None:
            try:
                self.collection.update_one(
                    {"commander_slug": slug},
                    {"$set": doc},
                    upsert=True,
                )
                logger.info(f"EDHREC data cached in MongoDB for '{slug}'.")
            except Exception as e:
                logger.warning(f"Failed to cache EDHREC data in MongoDB: {e}")

        # 2. Store in Local File Cache
        try:
            local_file = self.cache_dir / f"{slug}.json"
            with open(local_file, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to write local EDHREC cache file: {e}")


class EDHREC_Synergy_Engine:
    """
    Engine for fetching, normalizing, caching, and validating EDHREC community data.
    """

    EDHREC_BASE_URL = "https://json.edhrec.com/pages/commanders"
    USER_AGENT = "MTGDeckOptimizer/2.0 (https://github.com/mtg-deck-optimizer)"

    def __init__(self, cache_service: Optional[EDHRECCacheMongoService] = None):
        self.cache_service = cache_service or EDHRECCacheMongoService()

    @classmethod
    def _parse_cardview(cls, cv: Dict[str, Any], tag: str = "general") -> EDHRECCardItem:
        """Parses a single raw cardview dictionary from EDHREC JSON."""
        name = cv.get("name", "").strip()
        sanitized = cv.get("sanitized", "") or cv.get("slug", "")
        synergy_raw = cv.get("synergy", 0.0) or 0.0
        synergy_pct = round(float(synergy_raw) * 100.0, 1)

        num_decks = int(cv.get("num_decks", 0) or 0)
        potential_decks = int(cv.get("potential_decks", 0) or 0)
        inclusion_pct = round((num_decks / potential_decks * 100.0), 1) if potential_decks > 0 else (
            round(float(cv.get("inclusion", 0.0) or 0.0) * 100.0, 1)
        )

        cmc = float(cv.get("cmc", 0.0) or 0.0)
        type_line = cv.get("primary_type", "") or cv.get("type", "") or "Card"
        primary_type = cv.get("primary_type", "") or "Card"

        # Prices
        prices = cv.get("prices", {}) or {}
        price_usd = None
        if isinstance(prices, dict):
            p_val = prices.get("tcgplayer", {}).get("price") or prices.get("cardmarket", {}).get("price")
            if p_val is not None:
                try:
                    price_usd = float(p_val)
                except Exception:
                    pass

        # Images
        image_url = None
        img_uris = cv.get("image_uris")
        if isinstance(img_uris, list) and img_uris:
            first_img = img_uris[0]
            if isinstance(first_img, dict):
                image_url = first_img.get("normal") or first_img.get("large") or first_img.get("small")
            elif isinstance(first_img, str):
                image_url = first_img
        elif isinstance(img_uris, dict):
            image_url = img_uris.get("normal") or img_uris.get("large") or img_uris.get("small")

        # Fallback image direct endpoint from Scryfall
        if not image_url and sanitized:
            image_url = f"https://api.scryfall.com/cards/named?exact={sanitized}&format=image"

        return EDHRECCardItem(
            name=name,
            sanitized=sanitized,
            synergy=synergy_pct,
            num_decks=num_decks,
            potential_decks=potential_decks,
            inclusion_percent=inclusion_pct,
            cmc=cmc,
            type_line=type_line,
            primary_type=primary_type,
            price_usd=price_usd,
            image_url=image_url,
            tag=tag,
        )

    def fetch_edhrec_data(
        self,
        commander_name: str,
        max_age_hours: int = DEFAULT_CACHE_TTL_HOURS,
        force_refresh: bool = False,
    ) -> EDHRECCommanderData:
        """
        Fetches EDHREC JSON data for the given commander, using 24-48h MongoDB/local cache.
        """
        slug = format_commander_slug(commander_name)
        if not slug:
            return EDHRECCommanderData(commander_name=commander_name, commander_slug="")

        # 1. Check Cache unless forced
        if not force_refresh:
            cached = self.cache_service.get_cached_data(slug, max_age_hours=max_age_hours)
            if cached:
                try:
                    return EDHRECCommanderData(**cached)
                except Exception as e:
                    logger.warning(f"Error deserializing cached EDHREC data: {e}")

        # 2. Fetch from Live EDHREC JSON Endpoint
        url = f"{self.EDHREC_BASE_URL}/{slug}.json"
        headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}

        raw_json = None
        try:
            with httpx.Client(timeout=3.5, follow_redirects=True) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    raw_json = resp.json()
                else:
                    logger.debug(f"EDHREC returned HTTP {resp.status_code} for '{url}'")
        except Exception as ex:
            logger.debug(f"Failed to fetch EDHREC data from '{url}': {ex}")

        if not raw_json:
            # Fallback to curated community database if present
            from ..ai.community_data import COMMUNITY_COMMANDER_DATABASE
            key = commander_name.strip().lower()
            if key in COMMUNITY_COMMANDER_DATABASE:
                curated = COMMUNITY_COMMANDER_DATABASE[key]
                high_syn = [
                    EDHRECCardItem(
                        name=s.name,
                        synergy=s.synergy_score,
                        inclusion_percent=s.inclusion_percent,
                        cmc=s.cmc,
                        type_line=s.type_line,
                        price_usd=s.estimated_price_usd,
                        primary_role=s.primary_role,
                        tag="highsynergycards",
                    )
                    for s in curated.top_synergy_cards
                ]
                top_st = [
                    EDHRECCardItem(
                        name=s.name,
                        synergy=s.synergy_score,
                        inclusion_percent=s.inclusion_percent,
                        cmc=s.cmc,
                        type_line=s.type_line,
                        price_usd=s.estimated_price_usd,
                        primary_role=s.primary_role,
                        tag="topcards",
                    )
                    for s in curated.top_staples
                ]
                return EDHRECCommanderData(
                    commander_name=commander_name,
                    commander_slug=slug,
                    archetype_theme=curated.archetype_theme,
                    total_decks=curated.total_decks_analyzed,
                    high_synergy_cards=high_syn,
                    top_cards=top_st,
                    from_cache=False,
                )

            # Return empty structure for generic color fallback
            return EDHRECCommanderData(
                commander_name=commander_name,
                commander_slug=slug,
                archetype_theme="Commander Archetype",
                total_decks=0,
                from_cache=False,
            )

        # 3. Parse JSON Structure
        container = raw_json.get("container", {})
        json_dict = container.get("json_dict", {})
        cardlists = json_dict.get("cardlists", [])

        # Calculate max potential decks from cardlists (usually in topcards or creatures)
        max_decks = 0
        for cl in cardlists:
            for cv in cl.get("cardviews", []):
                p_decks = int(cv.get("potential_decks", 0) or 0)
                if p_decks > max_decks:
                    max_decks = p_decks

        archetype_theme = raw_json.get("description", "") or container.get("theme", "Commander Deck")
        description = raw_json.get("header", "") or f"EDHREC community recommendations for {commander_name}"

        parsed_data = {
            "commander_name": commander_name,
            "commander_slug": slug,
            "archetype_theme": str(archetype_theme).strip() if archetype_theme else "Commander Deck",
            "total_decks": max_decks,
            "description": str(description).strip(),
            "high_synergy_cards": [],
            "top_cards": [],
            "new_cards": [],
            "creatures": [],
            "instants": [],
            "sorceries": [],
            "utility_artifacts": [],
            "enchantments": [],
            "lands": [],
            "planeswalkers": [],
            "battles": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "from_cache": False,
        }

        tag_map = {
            "highsynergycards": "high_synergy_cards",
            "highliftcards": "high_synergy_cards",
            "topcards": "top_cards",
            "newcards": "new_cards",
            "creatures": "creatures",
            "instants": "instants",
            "sorceries": "sorceries",
            "utilityartifacts": "utility_artifacts",
            "manaartifacts": "utility_artifacts",
            "artifacts": "utility_artifacts",
            "enchantments": "enchantments",
            "lands": "lands",
            "utilitylands": "lands",
            "planeswalkers": "planeswalkers",
            "battles": "battles",
        }

        for cl in cardlists:
            tag = str(cl.get("tag", "")).lower().strip()
            dest_key = tag_map.get(tag)
            cardviews = cl.get("cardviews", [])
            for cv in cardviews:
                card_item = self._parse_cardview(cv, tag=tag)
                if dest_key and dest_key in parsed_data:
                    parsed_data[dest_key].append(card_item.model_dump())

        # Save to Cache
        self.cache_service.save_cached_data(slug, commander_name, parsed_data)
        return EDHRECCommanderData(**parsed_data)

    @classmethod
    def filter_by_wotc_rules(
        cls,
        edhrec_data: EDHRECCommanderData,
        commander_color_identity: List[str],
        target_bracket: int = 3,
    ) -> EDHRECCommanderData:
        """
        Mandatory Middleware Filter:
        Validates all EDHREC suggested cards against:
        1. Color Identity (CR 903.4)
        2. Official Commander Banlist
        3. WOTC 5-Bracket Game Changers quota
        """
        from ..rules.wotc_rules_engine import WOTC_Commander_Rules_Engine
        from ..rules.color_identity import ColorIdentityExtractor
        from ..rules.legality import BanlistValidator
        from ..brackets.game_changers import GAME_CHANGERS_DATABASE
        from ..brackets.standards import GAME_CHANGERS_MAX_ALLOWED
        from ..deckbuilder.archetype_database import CARD_METADATA_REGISTRY
        from ..scryfall.client import ScryfallClient

        scryfall = ScryfallClient()
        cmdr_ci_set = {c.upper() for c in commander_color_identity}
        max_gc_allowed = GAME_CHANGERS_MAX_ALLOWED.get(target_bracket, 999)

        # Pre-populate registry lookup & case-insensitive GC lookup
        reg_lookup = {k.lower(): (k, v) for k, v in CARD_METADATA_REGISTRY.items()}
        gc_lookup = {k.lower(): (k, v) for k, v in GAME_CHANGERS_DATABASE.items()}

        def _evaluate_card(card_item: EDHRECCardItem) -> EDHRECCardItem:
            name_clean = scryfall.clean_card_name(card_item.name)
            name_lower = name_clean.lower()

            # 1. Banlist Check
            is_banned = BanlistValidator.is_banned(name_clean)
            card_item.is_banned = is_banned

            # 2. Color Identity Check (In-memory fast registry first)
            if name_lower in reg_lookup:
                orig_name, (cmc, colors, type_line, price) = reg_lookup[name_lower]
                card_ci = {c.upper() for c in colors}
                card_item.is_color_legal = card_ci.issubset(cmdr_ci_set)
                if card_item.cmc == 0.0:
                    card_item.cmc = cmc
                if card_item.type_line == "Card":
                    card_item.type_line = type_line
                if card_item.price_usd is None or card_item.price_usd == 0.0:
                    card_item.price_usd = price
            else:
                card_obj = scryfall._cache_by_name.get(name_lower)
                if card_obj:
                    card_ci = {c.upper() for c in card_obj.color_identity}
                    card_item.is_color_legal = card_ci.issubset(cmdr_ci_set)
                    if card_item.cmc == 0.0 and card_obj.cmc:
                        card_item.cmc = card_obj.cmc
                    if card_item.type_line == "Card" and card_obj.type_line:
                        card_item.type_line = card_obj.type_line
                else:
                    card_item.is_color_legal = True

            # 3. Game Changer Check
            if name_lower in gc_lookup:
                orig_gc_name, gc_def = gc_lookup[name_lower]
                card_item.is_game_changer = True
                card_item.game_changer_category = gc_def.category
                card_item.is_bracket_allowed = (target_bracket in gc_def.allowed_in_brackets)
            else:
                card_item.is_game_changer = False
                card_item.is_bracket_allowed = True

            return card_item

        def _filter_list(card_list: List[EDHRECCardItem]) -> List[EDHRECCardItem]:
            filtered = []
            for item in card_list:
                evaluated = _evaluate_card(item)
                # Exclude strictly banned cards and illegal colors
                if not evaluated.is_banned and evaluated.is_color_legal:
                    filtered.append(evaluated)
            return filtered

        import copy
        sanitized = copy.deepcopy(edhrec_data)
        sanitized.high_synergy_cards = _filter_list(sanitized.high_synergy_cards)
        sanitized.top_cards = _filter_list(sanitized.top_cards)
        sanitized.new_cards = _filter_list(sanitized.new_cards)
        sanitized.creatures = _filter_list(sanitized.creatures)
        sanitized.instants = _filter_list(sanitized.instants)
        sanitized.sorceries = _filter_list(sanitized.sorceries)
        sanitized.utility_artifacts = _filter_list(sanitized.utility_artifacts)
        sanitized.enchantments = _filter_list(sanitized.enchantments)
        sanitized.lands = _filter_list(sanitized.lands)
        sanitized.planeswalkers = _filter_list(sanitized.planeswalkers)
        sanitized.battles = _filter_list(sanitized.battles)

        return sanitized


# Global Engine Instance & Helper Functions
_default_engine: Optional[EDHREC_Synergy_Engine] = None


def get_edhrec_engine() -> EDHREC_Synergy_Engine:
    global _default_engine
    if _default_engine is None:
        _default_engine = EDHREC_Synergy_Engine()
    return _default_engine


def fetch_edhrec_data(
    commander_name: str,
    max_age_hours: int = DEFAULT_CACHE_TTL_HOURS,
    force_refresh: bool = False,
) -> EDHRECCommanderData:
    """Convenience helper to fetch EDHREC community data."""
    engine = get_edhrec_engine()
    return engine.fetch_edhrec_data(commander_name, max_age_hours=max_age_hours, force_refresh=force_refresh)
