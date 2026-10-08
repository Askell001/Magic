"""
Strategy Management & Dynamic Tribal Resolver Service for MTG Commander Optimization.
Reads commander_strategies.json and interacts with MongoDB collection 'strategies'
with unique indexing, dynamic bracket filtering, and subtype replacement.
"""

import os
import sys
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

# Default MongoDB Configuration
DEFAULT_MONGO_URI = os.getenv("MONGODB_URI", "mongodb+srv://user:12345@registrousuarios.e6jeny6.mongodb.net/")
DB_NAME = os.getenv("MONGODB_DB", "mtg_optimizer")
COLLECTION_NAME = "strategies"

# Known MTG Creature Subtypes for robust extraction from type line
COMMON_CREATURE_SUBTYPES = {
    "Advisor", "Aetherborn", "Alien", "Ally", "Angel", "Antelope", "Ape", "Archer", "Archon",
    "Armadillo", "Army", "Artificer", "Assassin", "Assembly-Worker", "Atog", "Aurochs", "Avatar",
    "Azra", "Badger", "Barbarian", "Bard", "Basilisk", "Bat", "Bear", "Beast", "Beeble",
    "Beholder", "Berserker", "Bird", "Blinkmoth", "Boar", "Bringer", "Brushwagg", "Camarid",
    "Camel", "Capybara", "Caribou", "Carrier", "Cat", "Centaur", "Cephalid", "Chimera", "Citizen",
    "Cleric", "Clown", "Cockatrice", "Construct", "Coward", "Crab", "Crocodile", "Cyborg",
    "Cyclops", "Dauthi", "Demigod", "Demon", "Deserter", "Detective", "Devil", "Dinosaur",
    "Djinn", "Dog", "Dragon", "Drake", "Dreadnought", "Drone", "Druid", "Dryad", "Dwarf",
    "Efreet", "Egg", "Elder", "Eldrazi", "Elemental", "Elephant", "Elf", "Elk", "Eye",
    "Faerie", "Ferret", "Fish", "Flagbearer", "Fox", "Fractal", "Frog", "Fungus", "Gargoyle",
    "Germ", "Giant", "Gith", "Gnome", "Goat", "Goblin", "God", "Golem", "Gorgon", "Graveborn",
    "Gremlin", "Griffin", "Hag", "Halfling", "Hamster", "Harpy", "Hellion", "Hippo", "Hippogriff",
    "Homarid", "Homunculus", "Horror", "Horse", "Human", "Hydra", "Hyena", "Illusion", "Imp",
    "Incarnation", "Inkling", "Inquisitor", "Insect", "Jackal", "Jellyfish", "Juggernaut",
    "Kavu", "Kirin", "Kithkin", "Knight", "Kobold", "Kor", "Kraken", "Lamia", "Lammasu",
    "Leech", "Leviathan", "Lhurgoyf", "Licid", "Lizard", "Manticore", "Masticore", "Mercenary",
    "Merfolk", "Metathran", "Minion", "Minotaur", "Mole", "Monger", "Mongoose", "Monk",
    "Monkey", "Moonfolk", "Mount", "Mouse", "Mutant", "Myr", "Mystic", "Naga", "Nautilus",
    "Necron", "Nephilim", "Nightmare", "Nightstalker", "Ninja", "Noble", "Noggle", "Nomad",
    "Nymph", "Octopus", "Ogre", "Ooze", "Orb", "Orc", "Orgg", "Otter", "Ouphe", "Ox",
    "Oyster", "Pangolin", "Peasant", "Pegasus", "Pentavite", "Pest", "Phelddagrif", "Phoenix",
    "Phyrexian", "Pilot", "Pincher", "Pirate", "Plant", "Praetor", "Primarch", "Prism",
    "Processor", "Rabbit", "Raccoon", "Ranger", "Rat", "Rebel", "Reflection", "Rhino",
    "Rigger", "Robot", "Rogue", "Sable", "Salamander", "Samurai", "Sand", "Saproling",
    "Satyr", "Scarecrow", "Scion", "Scorpion", "Scout", "Sculpture", "Serf", "Serpent",
    "Servo", "Shade", "Shaman", "Shapeshifter", "Shark", "Sheep", "Siren", "Skeleton",
    "Slith", "Sliver", "Slug", "Snail", "Snake", "Soldier", "Soltari", "Spawn", "Specter",
    "Spellshaper", "Sphinx", "Spider", "Spike", "Spirit", "Splinter", "Sponge", "Squid",
    "Squirrel", "Starfish", "Surrakar", "Survivor", "Tentacle", "Tetravite", "Thalakos",
    "Thopter", "Thrull", "Tiefling", "Treefolk", "Trilobite", "Triskelavite", "Troll",
    "Turtle", "Tyranid", "Unicorn", "Umpire", "Urchin", "Ur-Dragon", "Vampire", "Vampyre",
    "Vedalken", "Vehicle", "Viashino", "Volver", "Wall", "Walrus", "Warlock", "Warrior",
    "Weasel", "Weird", "Werewolf", "Whale", "Wizard", "Wolf", "Wolverine", "Wombat",
    "Worm", "Wraith", "Wurm", "Yeti", "Zombie", "Zubera"
}


class StrategyMongoService:
    """
    MongoDB service to manage and query the 'strategies' collection with unique indexing
    and local JSON cache resilience.
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
        self.cache_dir = cache_dir or (Path(__file__).parent.parent.parent / ".cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "strategies_mongo_cache.json"

        self.client = None
        self.db = None
        self.collection = None
        self.using_mongodb = False

        self._init_mongo(connect_timeout_ms)

    def _init_mongo(self, timeout_ms: int):
        """Attempts to initialize MongoDB connection with unique index on 'id' and 'name'."""
        try:
            import pymongo
            self.client = pymongo.MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=timeout_ms,
                connectTimeoutMS=timeout_ms,
            )
            # Test connectivity
            self.client.admin.command("ping")
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            # Ensure unique index on 'id' and 'name'
            self.collection.create_index("id", unique=True)
            self.collection.create_index("name", unique=True)
            self.using_mongodb = True
            logger.info("StrategyMongoService successfully connected to MongoDB Atlas.")
        except Exception as e:
            self.using_mongodb = False
            logger.warning(f"MongoDB unavailable ({e}). Operating with local JSON cache fallback.")

    def seed_from_json(self, json_filepath: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """
        Reads commander_strategies.json and upserts all documents into MongoDB 'strategies'.
        Creates local cache copy for offline resilience.
        """
        base_dir = Path(__file__).parent.parent.parent
        candidate_paths = [
            json_filepath,
            base_dir / "commander_strategies.json",
            base_dir / "commander_strategies.JSON",
        ]

        target_path: Optional[Path] = None
        for p in candidate_paths:
            if p and Path(p).exists():
                target_path = Path(p)
                break

        if not target_path:
            raise FileNotFoundError("Could not find 'commander_strategies.json' in project directory.")

        with open(target_path, "r", encoding="utf-8") as f:
            raw_content = json.load(f)

        if isinstance(raw_content, dict) and "strategies" in raw_content:
            raw_data = raw_content["strategies"]
        elif isinstance(raw_content, list):
            raw_data = raw_content
        else:
            raise ValueError(f"Unexpected JSON format in {target_path}")

        inserted_count = 0
        updated_count = 0
        all_docs = []

        for item in raw_data:
            doc_id = item.get("id")
            doc_name = item.get("name")
            if not doc_id or not doc_name:
                continue

            doc = {
                "id": str(doc_id).strip(),
                "name": str(doc_name).strip(),
                "category": str(item.get("category", "General")).strip(),
                "description": str(item.get("description", "")).strip(),
                "key_elements": item.get("key_elements", []),
                "win_conditions": item.get("win_conditions", []),
                "brackets_compatible": item.get("brackets_compatible", [1, 2, 3, 4, 5]),
                "is_dynamic_tribal": bool(item.get("is_dynamic_tribal", False)),
                "generic_tribal_staples": item.get("generic_tribal_staples", []),
            }
            all_docs.append(doc)

            if self.using_mongodb and self.collection is not None:
                try:
                    res = self.collection.update_one(
                        {"id": doc["id"]},
                        {"$set": doc},
                        upsert=True,
                    )
                    if res.upserted_id is not None:
                        inserted_count += 1
                    else:
                        updated_count += 1
                except Exception as ex:
                    logger.error(f"Error upserting strategy '{doc['name']}': {ex}")

        # Update local JSON cache
        try:
            with open(self.cache_file, "w", encoding="utf-8") as cf:
                json.dump(all_docs, cf, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not write strategies cache: {e}")

        return {
            "total_read": len(raw_data),
            "upserted_to_mongo": inserted_count + updated_count if self.using_mongodb else 0,
            "inserted": inserted_count,
            "updated": updated_count,
            "using_mongodb": self.using_mongodb,
            "cached_locally": len(all_docs),
        }

    def get_all_strategies(self) -> List[Dict[str, Any]]:
        """Retrieves all strategies from MongoDB or local cache."""
        if self.using_mongodb and self.collection is not None:
            try:
                docs = list(self.collection.find({}, {"_id": 0}))
                if docs:
                    return docs
            except Exception as e:
                logger.warning(f"MongoDB query failed: {e}. Falling back to cache.")

        # Fallback to local cache
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        # Fallback to raw JSON file
        base_dir = Path(__file__).parent.parent.parent
        json_p = base_dir / "commander_strategies.json"
        if json_p.exists():
            try:
                with open(json_p, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    return raw.get("strategies", []) if isinstance(raw, dict) else raw
            except Exception:
                pass

        return []

    def get_strategies_by_bracket(self, bracket: int) -> List[Dict[str, Any]]:
        """
        Filters strategies compatible with the given Bracket (1 to 5).
        Returns strategies where `bracket in strategy.brackets_compatible`.
        """
        all_strat = self.get_all_strategies()
        filtered = [
            s for s in all_strat
            if bracket in s.get("brackets_compatible", [1, 2, 3, 4, 5])
        ]
        return filtered

    def get_strategy_by_id(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Finds a strategy by its unique identifier."""
        target_id = strategy_id.strip().lower()
        if self.using_mongodb and self.collection is not None:
            try:
                doc = self.collection.find_one({"id": target_id}, {"_id": 0})
                if doc:
                    return doc
            except Exception:
                pass

        for s in self.get_all_strategies():
            if s.get("id", "").strip().lower() == target_id:
                return s
        return None

    def get_strategy_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Finds a strategy by its display name (case-insensitive)."""
        target_name = name.strip().lower()
        if self.using_mongodb and self.collection is not None:
            try:
                doc = self.collection.find_one({"name": {"$regex": f"^{re.escape(target_name)}$", "$options": "i"}}, {"_id": 0})
                if doc:
                    return doc
            except Exception:
                pass

        for s in self.get_all_strategies():
            if s.get("name", "").strip().lower() == target_name:
                return s
        return None

    @classmethod
    def extract_commander_subtype(cls, commander_card_or_name: Union[str, Any, None]) -> Optional[str]:
        """
        Extracts primary creature subtype from a Commander Card object or card name
        via type line parsing or Scryfall lookup.
        """
        if not commander_card_or_name:
            return None

        type_line: Optional[str] = None

        # If it's a Card or DeckItem object
        if hasattr(commander_card_or_name, "type_line"):
            type_line = commander_card_or_name.type_line
        elif hasattr(commander_card_or_name, "card") and commander_card_or_name.card:
            type_line = commander_card_or_name.card.type_line

        # If string passed, could be a name or type line
        if isinstance(commander_card_or_name, str):
            if "—" in commander_card_or_name or "-" in commander_card_or_name:
                type_line = commander_card_or_name
            else:
                # Query ScryfallClient for card metadata
                try:
                    from ..scryfall.client import ScryfallClient
                    client = ScryfallClient()
                    card_obj = client.get_card_by_name(commander_card_or_name)
                    if card_obj and card_obj.type_line:
                        type_line = card_obj.type_line
                except Exception as e:
                    logger.debug(f"Scryfall subtype lookup fallback: {e}")

        if not type_line:
            return None

        # Parse subtypes after dash (— or -)
        parts = re.split(r"[—\-]", type_line)
        if len(parts) < 2:
            return None

        subtypes_str = parts[1].strip()
        # Split tokens (e.g. "Dragon Avatar", "Elf Druid", "Vampire Noble")
        tokens = [t.strip() for t in subtypes_str.split() if t.strip()]

        # Find known creature subtypes in tokens
        found_subtypes = [t for t in tokens if t in COMMON_CREATURE_SUBTYPES]
        if found_subtypes:
            # Return primary creature subtype (e.g. "Dragon")
            return found_subtypes[0]

        # If tokens exist after dash on a Creature, return the first token
        if "Creature" in parts[0] and tokens:
            return tokens[0]

        return None

    @classmethod
    def resolve_dynamic_strategy(
        cls,
        strategy: Dict[str, Any],
        commander_card_or_name: Union[str, Any, None] = None,
    ) -> Dict[str, Any]:
        """
        Replaces dynamic tags like <COMMANDER_SUBTYPE> in description, key elements,
        and win conditions using the Commander's creature subtype.
        """
        if not strategy:
            return {}

        import copy
        resolved = copy.deepcopy(strategy)

        # Detect subtype
        detected_subtype = cls.extract_commander_subtype(commander_card_or_name)
        subtype_label = detected_subtype if detected_subtype else "Criaturas de la Tribu"

        def _sub(text: str) -> str:
            if not isinstance(text, str):
                return text
            return text.replace("<COMMANDER_SUBTYPE>", subtype_label)

        if "name" in resolved:
            resolved["name"] = _sub(resolved["name"])
        if "description" in resolved:
            resolved["description"] = _sub(resolved["description"])
        if "key_elements" in resolved and isinstance(resolved["key_elements"], list):
            resolved["key_elements"] = [_sub(el) for el in resolved["key_elements"]]
        if "win_conditions" in resolved and isinstance(resolved["win_conditions"], list):
            resolved["win_conditions"] = [_sub(wc) for wc in resolved["win_conditions"]]

        resolved["detected_commander_subtype"] = detected_subtype
        resolved["active_subtype_label"] = subtype_label
        return resolved


# Singleton & helper functions
_default_service: Optional[StrategyMongoService] = None


def get_strategy_service() -> StrategyMongoService:
    global _default_service
    if _default_service is None:
        _default_service = StrategyMongoService()
    return _default_service


def get_strategies_by_bracket(bracket: int, mongo_service: Optional[StrategyMongoService] = None) -> List[Dict[str, Any]]:
    """Convenience helper to retrieve bracket-filtered strategies."""
    service = mongo_service or get_strategy_service()
    return service.get_strategies_by_bracket(bracket)


def resolve_dynamic_strategy(
    strategy: Dict[str, Any],
    commander_card_or_name: Union[str, Any, None] = None,
) -> Dict[str, Any]:
    """Convenience helper to resolve dynamic tags in a strategy."""
    return StrategyMongoService.resolve_dynamic_strategy(strategy, commander_card_or_name)
