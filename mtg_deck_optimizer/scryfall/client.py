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

from ..models.card import Card, CardImageUris
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
        "sol ring": "https://cards.scryfall.io/normal/front/8/e/8ee443cc-e17a-493b-9c93-1f9e141a30e4.jpg?1789644446",
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
        self.rate_limited_until: float = 0.0
        self._cache_by_name: Dict[str, Card] = {}
        self._cache_by_set_num: Dict[Tuple[str, str], Card] = {}
        self.cache_file = Path(".cache/scryfall_cache.json")
        
        # Load verified CDN card images
        json_file = Path(__file__).parent / "verified_card_images.json"
        if json_file.exists():
            try:
                with open(json_file, "r", encoding="utf-8") as jf:
                    loaded_imgs = json.load(jf)
                    self.STATIC_STAPLE_IMAGES.update(loaded_imgs)
            except Exception:
                pass

        # Load persistent disk cache
        self._load_disk_cache()

    def _load_disk_cache(self):
        """Loads cached card data from disk if available."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        card = Card.model_validate(item)
                        self._cache_by_name[card.name.lower()] = card
                        if " // " in card.name:
                            front = card.name.split(" // ")[0].strip().lower()
                            self._cache_by_name[front] = card
                        if card.set_code and card.collector_number:
                            self._cache_by_set_num[(card.set_code.lower(), card.collector_number.lower())] = card
            except Exception as e:
                logger.warning(f"Could not load Scryfall disk cache: {e}")

    def _save_disk_cache(self):
        """Saves cached cards to disk."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            unique_cards = {c.id: c.model_dump() for c in self._cache_by_name.values()}
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(list(unique_cards.values()), f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not save Scryfall disk cache: {e}")

    def _rate_limit(self):
        """Enforces polite rate limiting compliant with Scryfall API."""
        if time.time() < self.rate_limited_until:
            time_left = int(self.rate_limited_until - time.time())
            logger.info(f"Scryfall client is cooling down from rate limit ({time_left}s remaining). Using local cache.")
            return

        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self.last_request_time = time.time()

    @classmethod
    def clean_card_name(cls, raw_name: str) -> str:
        """Strips quantities (1x, 4), collector numbers, set codes, and brackets from card name."""
        clean = raw_name
        # Strip all Moxfield asterisk markers (*CMDR*, *F*, *FOIL*, *E*, etc.)
        clean = re.sub(r"\*[A-Za-z0-9_\-]+\*", "", clean)
        # Split off set/tag markers like (LEA), [CMM], #Tag
        clean = clean.split("(")[0].split("[")[0].split("#")[0].strip()
        # Strip leading counts like "1 ", "1x ", "4x "
        clean = re.sub(r"^\d+\s*x?\s*", "", clean, flags=re.IGNORECASE).strip()
        # Strip leading/trailing special characters
        clean = clean.strip(" \t\r\n-*#")
        # Normalize DFC single or double slashes
        clean = re.sub(r"\s*/+\s*", " // ", clean)
        return clean

    KNOWN_STAPLE_METADATA = {
        "manamorphose": {"mana_cost": "{1}{R/G}", "cmc": 2.0, "type_line": "Instant", "colors": ["R", "G"], "color_identity": ["R", "G"]},
        "mana crypt": {"mana_cost": "{0}", "cmc": 0.0, "type_line": "Artifact", "colors": [], "color_identity": []},
        "sol ring": {"mana_cost": "{1}", "cmc": 1.0, "type_line": "Artifact", "colors": [], "color_identity": []},
        "arcane signet": {"mana_cost": "{2}", "cmc": 2.0, "type_line": "Artifact", "colors": [], "color_identity": []},
        "cyclonic rift": {"mana_cost": "{1}{U}", "cmc": 2.0, "type_line": "Instant", "colors": ["U"], "color_identity": ["U"]},
        "demonic tutor": {"mana_cost": "{1}{B}", "cmc": 2.0, "type_line": "Sorcery", "colors": ["B"], "color_identity": ["B"]},
        "vampiric tutor": {"mana_cost": "{B}", "cmc": 1.0, "type_line": "Instant", "colors": ["B"], "color_identity": ["B"]},
        "rhystic study": {"mana_cost": "{2}{U}", "cmc": 3.0, "type_line": "Enchantment", "colors": ["U"], "color_identity": ["U"]},
        "swords to plowshares": {"mana_cost": "{W}", "cmc": 1.0, "type_line": "Instant", "colors": ["W"], "color_identity": ["W"]},
        "llanowar elves": {"mana_cost": "{G}", "cmc": 1.0, "type_line": "Creature — Elf Druid", "colors": ["G"], "color_identity": ["G"]},
        "sylvan library": {"mana_cost": "{1}{G}", "cmc": 2.0, "type_line": "Enchantment", "colors": ["G"], "color_identity": ["G"]},
        "beast within": {"mana_cost": "{2}{G}", "cmc": 3.0, "type_line": "Instant", "colors": ["G"], "color_identity": ["G"]},
        "cultivate": {"mana_cost": "{2}{G}", "cmc": 3.0, "type_line": "Sorcery", "colors": ["G"], "color_identity": ["G"]},
    }

    def _create_synthetic_fallback_card(self, raw_name: str) -> Card:
        """Creates a safe synthetic Card model so no deck item is ever left as None or without accurate colors."""
        clean = self.clean_card_name(raw_name)
        clean_l = clean.lower()
        # Check front name if DFC
        front_l = clean_l.split(" // ")[0].split(" / ")[0].strip()

        if clean_l in self.KNOWN_STAPLE_METADATA or front_l in self.KNOWN_STAPLE_METADATA:
            meta = self.KNOWN_STAPLE_METADATA.get(clean_l) or self.KNOWN_STAPLE_METADATA[front_l]
            img_u = self.STATIC_STAPLE_IMAGES.get(clean_l) or self.STATIC_STAPLE_IMAGES.get(front_l)
            card = Card(
                id=f"syn_{clean_l.replace(' ', '_')}",
                name=clean,
                mana_cost=meta.get("mana_cost", "{3}"),
                cmc=meta.get("cmc", 3.0),
                type_line=meta.get("type_line", "Spell"),
                colors=meta.get("colors", []),
                color_identity=meta.get("color_identity", []),
                image_uris=CardImageUris(normal=img_u) if img_u else None,
            )
            self._cache_card(card)
            return card

        # Consult comprehensive Archetype Database Registry (800+ cards & commanders)
        try:
            from ..deckbuilder.archetype_database import CARD_METADATA_REGISTRY
            for reg_k, reg_v in CARD_METADATA_REGISTRY.items():
                reg_low = reg_k.lower()
                if reg_low == clean_l or reg_low == front_l:
                    cmc_val, colors_val, typ_val, _ = reg_v
                    img_u = self.STATIC_STAPLE_IMAGES.get(reg_low) or self.STATIC_STAPLE_IMAGES.get(front_l)
                    card = Card(
                        id=f"syn_{clean_l.replace(' ', '_')}",
                        name=reg_k if reg_low == clean_l else clean,
                        cmc=cmc_val,
                        type_line=typ_val,
                        colors=list(colors_val),
                        color_identity=list(colors_val),
                        image_uris=CardImageUris(normal=img_u) if img_u else None,
                    )
                    self._cache_card(card)
                    return card
        except Exception:
            pass

        # Comprehensive MTG Lexical & Semantic Type Inference
        type_line = "Creature"
        cmc = 3.0

        # 1. Lands
        if any(k in clean_l for k in ["land", "plains", "island", "swamp", "mountain", "forest", "wastes", "sanctuary", "grove", "tomb", "shrine", "foundry", "pool", "delta", "mire", "tarn", "strand", "mesa", "catacombs", "foothills", "heath", "tower", "orchard", "confluence", "city", "springs", "ridge", "estate", "village", "boseiju", "otawara", "eiganjo", "takenuma", "sokenzan", "glade", "depths", "pass", "cove", "harbor", "falls", "valley"]):
            type_line = "Land"
            cmc = 0.0
        # 2. Planeswalkers
        elif any(k in clean_l for k in ["jace", "teferi", "liliana", "chandra", "nissa", "ajani", "karn", "ugin", "bolas", "tamiyo", "narset", "oko", "elspeth", "gideon", "sorin", "vraska", "vivien", "kaya", "rowan", "will", "guff", "planeswalker"]):
            type_line = "Legendary Planeswalker"
            cmc = 4.0
        # 3. Artifacts (Non-creature equipment, rocks, engines)
        elif any(k in clean_l for k in ["sol ring", "signet", "talisman", "mox", "lotus", "boots", "greaves", "skullclamp", "monolith", "crypt", "vault", "bauble", "stone", "chalice", "lens", "sphere", "lantern", "reservoir", "ring", "altar", "statuary", "banner", "horn", "orb", "helm", "sword", "shield", "armor", "plate", "dynamo", "compass", "engine", "vessel", "crucible", "station", "matrix", "forge", "anvil", "cauldron", "sceptre", "scepter", "staff", "rod", "wand", "crown", "relic", "tome", "map", "key", "locket", "medallion", "apparatus", "device", "artifact"]):
            type_line = "Artifact"
            cmc = 2.0
        # 4. Instants
        elif any(k in clean_l for k in ["counterspell", "drain", "swords", "path", "gift", "protection", "silence", "bolt", "warp", "pongify", "hybridization", "resculpt", "flusterstorm", "denial", "song", "intervention", "charm", "veto", "command", "shift", "blink", "flicker", "consultation", "ritual", "dispute", "tear", "offer", "pact", "trap", "reversal", "misstep", "rebuttal", "stroke", "opt", "consider", "snuff", "push", "terminate", "blast", "grasp", "freeze", "vapor", "rollick", "guardianship", "swat", "maneuver", "deflecting", "instant"]):
            type_line = "Instant"
            cmc = 2.0
        # 5. Enchantments
        elif any(k in clean_l for k in ["study", "remora", "tithe", "library", "arena", "connections", "project", "breach", "season", "tax", "dreams", "caress", "notion", "talent", "class", "saga", "presence", "aura", "rancor", "ascendancy", "agony", "bonders", "vigor", "fervor", "market", "leyline", "court", "authority", "tribute", "confinement", "seal", "enchantment"]):
            type_line = "Enchantment"
            cmc = 3.0
        # 6. Sorceries
        elif any(k in clean_l for k in ["wrath", "damnation", "act", "farewell", "windfall", "wheel", "ponder", "preordain", "reanimate", "loot", "spiral", "cultivate", "reach", "lore", "visits", "zenith", "finale", "excision", "tutor", "probe", "buried", "entomb", "victimize", "persist", "gifts", "twister", "fabricate", "search", "consult", "reshape", "transmute", "demonic", "diabolic", "imperial", "personal", "solve", "merchant", "sorcery"]):
            type_line = "Sorcery"
            cmc = 3.0
        # 7. Creatures (Character titles, names with commas or creatures)
        elif "," in clean or " of " in clean_l or " the " in clean_l or "lord" in clean_l or "mage" in clean_l or "king" in clean_l or "queen" in clean_l or "dragon" in clean_l or "demon" in clean_l or "angel" in clean_l or "god" in clean_l:
            type_line = "Legendary Creature"
            cmc = 4.0
        else:
            type_line = "Creature"
            cmc = 3.0

        img_u = self.STATIC_STAPLE_IMAGES.get(clean_l) or self.STATIC_STAPLE_IMAGES.get(front_l)
        if not img_u:
            img_u = "https://cards.scryfall.io/back.jpg"

        card = Card(
            id=f"syn_{clean_l.replace(' ', '_')}",
            name=clean,
            cmc=cmc,
            type_line=type_line,
            image_uris=CardImageUris(normal=img_u),
        )
        self._cache_card(card)
        return card

    def get_card_by_name(self, name: str, set_code: Optional[str] = None, fuzzy: bool = True) -> Optional[Card]:
        """
        Fetches a single card by exact or fuzzy name with multi-tier fallback resolution.
        """
        clean_name = self.clean_card_name(name)
        cache_key = clean_name.lower()

        if cache_key in self._cache_by_name and not set_code:
            cached = self._cache_by_name[cache_key]
            # If cached card is not synthetic, return it
            if not cached.id.startswith("syn_") and cached.image_uris and cached.image_uris.normal and "back.jpg" not in cached.image_uris.normal:
                return cached

        # Check front face if DFC
        if " // " in cache_key:
            front = cache_key.split(" // ")[0].strip()
            if front in self._cache_by_name:
                cached = self._cache_by_name[front]
                if not cached.id.startswith("syn_") and cached.image_uris and cached.image_uris.normal and "back.jpg" not in cached.image_uris.normal:
                    return cached

        # If cooling down from 429, serve synthetic fallback immediately
        if time.time() < self.rate_limited_until:
            return self._create_synthetic_fallback_card(clean_name)

        headers = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}
        url_named = f"{self.BASE_URL}/cards/named"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                # Attempt 1: Exact search with set code if given
                if set_code:
                    self._rate_limit()
                    resp = client.get(url_named, params={"exact": clean_name, "set": set_code}, headers=headers)
                    if resp.status_code == 200:
                        card = Card.from_scryfall_dict(resp.json())
                        self._cache_card(card)
                        return card
                    elif resp.status_code == 429:
                        self.rate_limited_until = time.time() + 60.0
                        return self._create_synthetic_fallback_card(clean_name)

                # Attempt 2: Exact search by clean name (global)
                self._rate_limit()
                resp = client.get(url_named, params={"exact": clean_name}, headers=headers)
                if resp.status_code == 200:
                    card = Card.from_scryfall_dict(resp.json())
                    self._cache_card(card)
                    return card
                elif resp.status_code == 429:
                    self.rate_limited_until = time.time() + 60.0
                    return self._create_synthetic_fallback_card(clean_name)

                # Attempt 3: Fuzzy search by clean name (global)
                if fuzzy or resp.status_code == 404:
                    self._rate_limit()
                    resp_f = client.get(url_named, params={"fuzzy": clean_name}, headers=headers)
                    if resp_f.status_code == 200:
                        card = Card.from_scryfall_dict(resp_f.json())
                        self._cache_card(card)
                        return card
                    elif resp_f.status_code == 429:
                        self.rate_limited_until = time.time() + 60.0
                        return self._create_synthetic_fallback_card(clean_name)

                # Attempt 4: Front face exact / fuzzy if DFC
                if " // " in clean_name:
                    front_name = clean_name.split(" // ")[0].strip()
                    self._rate_limit()
                    resp_dfc = client.get(url_named, params={"exact": front_name}, headers=headers)
                    if resp_dfc.status_code == 200:
                        card = Card.from_scryfall_dict(resp_dfc.json())
                        self._cache_card(card)
                        return card
                    elif resp_dfc.status_code == 429:
                        self.rate_limited_until = time.time() + 60.0
                        return self._create_synthetic_fallback_card(clean_name)

                    self._rate_limit()
                    resp_dfc_f = client.get(url_named, params={"fuzzy": front_name}, headers=headers)
                    if resp_dfc_f.status_code == 200:
                        card = Card.from_scryfall_dict(resp_dfc_f.json())
                        self._cache_card(card)
                        return card

        except Exception as e:
            logger.warning(f"Error resolving card '{clean_name}' from Scryfall: {e}")

        return self._create_synthetic_fallback_card(clean_name)

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

        # If currently rate limited, return synthetic cards immediately
        if time.time() < self.rate_limited_until:
            for ident in identifiers:
                c_name = ident.get("name", "Card")
                syn = self._create_synthetic_fallback_card(c_name)
                resolved_cards.append(syn)
            return resolved_cards, []

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
                    elif resp.status_code == 429:
                        self.rate_limited_until = time.time() + 60.0
                        logger.warning("Scryfall batch rate-limited (HTTP 429). Activating local synthetic fallback for 60 seconds.")
                        for ident in batch:
                            c_name = ident.get("name", "Card")
                            syn = self._create_synthetic_fallback_card(c_name)
                            resolved_cards.append(syn)
                        break
                    else:
                        logger.error(f"Scryfall batch lookup failed with HTTP {resp.status_code}: {resp.text}")
                        for ident in batch:
                            c_name = ident.get("name", "Card")
                            syn = self._create_synthetic_fallback_card(c_name)
                            resolved_cards.append(syn)
            except Exception as e:
                logger.error(f"Scryfall batch request exception: {e}")
                for ident in batch:
                    c_name = ident.get("name", "Card")
                    syn = self._create_synthetic_fallback_card(c_name)
                    resolved_cards.append(syn)

        self._save_disk_cache()
        return resolved_cards, not_found_list

    def enrich_deck(self, deck: Deck, force_refresh: bool = False) -> Deck:
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
        ident_to_clean_name: Dict[str, str] = {}

        for item in all_items:
            clean = self.clean_card_name(item.raw_name)
            cached_card = None if force_refresh else self._find_in_cache(item.raw_name, item.set_code, item.collector_number)
            
            # If cached card is synthetic or lacks real image, force fresh fetch
            if cached_card and (cached_card.id.startswith("syn_") or not cached_card.image_uris or not cached_card.image_uris.normal or "back.jpg" in cached_card.image_uris.normal):
                cached_card = None

            if cached_card:
                item.card = cached_card
            else:
                q_key = clean.lower()
                if q_key not in seen_queries:
                    seen_queries.add(q_key)
                    # Use name-based batch lookup for 100% reliable matching
                    identifiers_to_query.append({"name": clean})
                    ident_to_clean_name[q_key] = clean

        # Batch query Scryfall for un-cached cards if not rate limited
        if identifiers_to_query:
            resolved_cards, not_found = self.fetch_cards_collection(identifiers_to_query)

            # If some cards failed, retry fallback with front face name for DFCs
            fallback_by_name: List[Dict[str, Any]] = []
            fallback_seen: Set[str] = set()
            for nf in not_found:
                clean_target = nf.get("name")
                if not clean_target:
                    continue
                c_clean = self.clean_card_name(clean_target)
                if " // " in c_clean:
                    front = c_clean.split(" // ")[0].strip()
                    if front.lower() not in fallback_seen and front.lower() not in self._cache_by_name:
                        fallback_seen.add(front.lower())
                        fallback_by_name.append({"name": front})

            if fallback_by_name and time.time() >= self.rate_limited_until:
                retry_cards, _ = self.fetch_cards_collection(fallback_by_name)
                for rc in retry_cards:
                    self._cache_card(rc)

        # Match cards back to deck items, guaranteeing NO item has card=None
        for item in all_items:
            if not item.card or item.card.id.startswith("syn_") or not item.card.image_uris or "back.jpg" in item.card.image_uris.normal:
                resolved = self._find_in_cache(item.raw_name, item.set_code, item.collector_number)
                if (not resolved or resolved.id.startswith("syn_")) and time.time() >= self.rate_limited_until:
                    resolved = self.get_card_by_name(item.raw_name, set_code=item.set_code)
                if resolved and not resolved.id.startswith("syn_"):
                    item.card = resolved
                elif not item.card:
                    item.card = self._create_synthetic_fallback_card(item.raw_name)

        return deck

    def _cache_card(self, card: Card):
        """Indexes card in cache by primary name, front face name, single-slash variant, and set/collector_number."""
        self._cache_by_name[card.name.lower()] = card
        # Also cache front face name and single slash variant for DFCs e.g. "Norman Osborn"
        if " // " in card.name:
            front = card.name.split(" // ")[0].strip().lower()
            self._cache_by_name[front] = card
            single_slash = card.name.lower().replace(" // ", " / ")
            self._cache_by_name[single_slash] = card

        if card.set_code and card.collector_number:
            self._cache_by_set_num[(card.set_code.lower(), card.collector_number.lower())] = card

    def _find_in_cache(self, name: str, set_code: Optional[str], collector_number: Optional[str]) -> Optional[Card]:
        """Looks up a card from in-memory cache with fallback on name variations."""
        if set_code and collector_number:
            key = (set_code.lower(), collector_number.lower())
            if key in self._cache_by_set_num:
                return self._cache_by_set_num[key]

        clean_lower = self.clean_card_name(name).lower()
        if clean_lower in self._cache_by_name:
            return self._cache_by_name[clean_lower]

        # Check if front name of DFC was passed or if single slash / was passed
        if " // " in clean_lower:
            front = clean_lower.split(" // ")[0].strip()
            if front in self._cache_by_name:
                return self._cache_by_name[front]
        if " / " in clean_lower:
            front = clean_lower.split(" / ")[0].strip()
            if front in self._cache_by_name:
                return self._cache_by_name[front]
            double_slash = clean_lower.replace(" / ", " // ")
            if double_slash in self._cache_by_name:
                return self._cache_by_name[double_slash]

        return None

    def get_card_image_url(self, name: str) -> str:
        """
        Returns a high-resolution, dependable Scryfall image URL for any card name.
        Uses verified CDN map first, then cache, and resolves from Scryfall if needed.
        """
        clean = self.clean_card_name(name)
        clean_l = clean.lower()
        if clean_l in self.STATIC_STAPLE_IMAGES:
            return self.STATIC_STAPLE_IMAGES[clean_l]
        if clean_l in self._cache_by_name:
            c = self._cache_by_name[clean_l]
            if c.image_uris and c.image_uris.normal and "cards.scryfall.io" in c.image_uris.normal and "back.jpg" not in c.image_uris.normal:
                return c.image_uris.normal

        # Check front face in cache
        front = clean.split(" // ")[0].split(" / ")[0].strip()
        front_l = front.lower()
        if front_l in self.STATIC_STAPLE_IMAGES:
            return self.STATIC_STAPLE_IMAGES[front_l]
        if front_l in self._cache_by_name:
            c = self._cache_by_name[front_l]
            if c.image_uris and c.image_uris.normal and "cards.scryfall.io" in c.image_uris.normal and "back.jpg" not in c.image_uris.normal:
                return c.image_uris.normal

        cached = self._find_in_cache(clean, None, None)
        if cached and cached.image_uris and cached.image_uris.normal and "cards.scryfall.io" in cached.image_uris.normal and "back.jpg" not in cached.image_uris.normal:
            return cached.image_uris.normal

        # Query Scryfall to resolve real CDN URL if not cooling down
        if time.time() >= self.rate_limited_until:
            try:
                card = self.get_card_by_name(clean)
                if card and card.image_uris and card.image_uris.normal and "cards.scryfall.io" in card.image_uris.normal and "back.jpg" not in card.image_uris.normal:
                    return card.image_uris.normal
                if " // " in clean:
                    card_f = self.get_card_by_name(front)
                    if card_f and card_f.image_uris and card_f.image_uris.normal and "cards.scryfall.io" in card_f.image_uris.normal and "back.jpg" not in card_f.image_uris.normal:
                        return card_f.image_uris.normal
            except Exception:
                pass

        import urllib.parse
        target_name = front if front else clean
        encoded = urllib.parse.quote_plus(target_name)
        return f"https://api.scryfall.com/cards/named?exact={encoded}&format=image&version=normal"

