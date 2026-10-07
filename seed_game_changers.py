"""
Seed Game Changers to MongoDB Atlas & Bracket Validator Service.
Reads game_changers_database_list.JSON (or game_changers.json) and seeds the MongoDB
'game_changers' collection with a unique index on the 'name' field.
Provides check_game_changers_count(deck_cards, target_bracket).
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

# Default MongoDB Configuration
DEFAULT_MONGO_URI = os.getenv("MONGODB_URI", "mongodb+srv://user:12345@registrousuarios.e6jeny6.mongodb.net/")
DB_NAME = os.getenv("MONGODB_DB", "mtg_optimizer")
COLLECTION_NAME = "game_changers"


class GameChangersMongoService:
    """
    MongoDB service to manage and query the 'game_changers' collection with unique indexing
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
        self.cache_dir = cache_dir or (Path(__file__).parent / ".cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "game_changers_mongo_cache.json"

        self.client = None
        self.db = None
        self.collection = None
        self.using_mongodb = False

        self._init_mongo(connect_timeout_ms)

    def _init_mongo(self, timeout_ms: int):
        """Attempts to initialize MongoDB connection with unique index on 'name'."""
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
            # Ensure unique index on 'name'
            self.collection.create_index("name", unique=True)
            self.using_mongodb = True
            logger.info("GameChangersMongoService successfully connected to MongoDB Atlas.")
        except Exception as e:
            self.using_mongodb = False
            logger.warning(f"MongoDB unavailable ({e}). Operating with local JSON cache fallback.")

    def seed_from_json(self, json_filepath: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """
        Reads game_changers_database_list.JSON (or game_changers.json) and inserts
        documents into the MongoDB 'game_changers' collection.
        Uses upsert on the unique 'name' field to avoid duplicate key errors.
        """
        base_dir = Path(__file__).parent
        candidate_paths = [
            json_filepath,
            base_dir / "game_changers_database_list.JSON",
            base_dir / "game_changers_database_list.json",
            base_dir / "game_changers.json",
            base_dir / "game_changers.JSON",
        ]

        target_path: Optional[Path] = None
        for p in candidate_paths:
            if p and Path(p).exists():
                target_path = Path(p)
                break

        if not target_path:
            raise FileNotFoundError(
                "Could not find 'game_changers_database_list.JSON' or 'game_changers.json' in project directory."
            )

        with open(target_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        if not isinstance(raw_data, list):
            raise ValueError(f"Expected JSON list in {target_path}, got {type(raw_data)}")

        inserted_count = 0
        updated_count = 0

        # Also update local fallback cache
        try:
            with open(self.cache_file, "w", encoding="utf-8") as cf:
                json.dump(raw_data, cf, indent=2)
        except Exception as ce:
            logger.warning(f"Could not save local cache: {ce}")

        if self.using_mongodb and self.collection is not None:
            for item in raw_data:
                name = item.get("name")
                if not name:
                    continue
                result = self.collection.update_one(
                    {"name": name},
                    {"$set": item},
                    upsert=True,
                )
                if result.upserted_id is not None:
                    inserted_count += 1
                elif result.modified_count > 0:
                    updated_count += 1
            logger.info(
                f"Seeding completed in MongoDB '{self.db_name}.{self.collection_name}': "
                f"{inserted_count} new inserted, {updated_count} updated."
            )
        else:
            inserted_count = len(raw_data)
            logger.info(f"Seeding completed in local cache fallback: {inserted_count} cards stored.")

        return {
            "source_file": str(target_path),
            "total_records_processed": len(raw_data),
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "using_mongodb": self.using_mongodb,
        }

    def get_all_game_changers(self) -> List[Dict[str, Any]]:
        """Retrieves all Game Changers documents from MongoDB or local cache."""
        if self.using_mongodb and self.collection is not None:
            try:
                cursor = self.collection.find({}, {"_id": 0})
                return list(cursor)
            except Exception as e:
                logger.warning(f"Error reading from MongoDB ({e}), falling back to cache.")

        # Fallback to local cache
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as cf:
                    return json.load(cf)
            except Exception as ce:
                logger.error(f"Error reading local cache: {ce}")

        # Fallback to root JSON file if cache empty
        root_json = Path(__file__).parent / "game_changers_database_list.JSON"
        if root_json.exists():
            with open(root_json, "r", encoding="utf-8") as rf:
                return json.load(rf)

        return []

    def get_game_changer_names_set(self) -> Set[str]:
        """Returns lowercase set of all Game Changer names."""
        docs = self.get_all_game_changers()
        names = set()
        for doc in docs:
            n = doc.get("name")
            if n:
                names.add(n.strip().lower())
        return names


# Global Singleton Service Instance
_mongo_service_instance: Optional[GameChangersMongoService] = None


def get_game_changers_service() -> GameChangersMongoService:
    global _mongo_service_instance
    if _mongo_service_instance is None:
        _mongo_service_instance = GameChangersMongoService()
    return _mongo_service_instance


def check_game_changers_count(
    deck_cards: Union[List[str], List[Any], Any],
    target_bracket: int,
    mongo_service: Optional[GameChangersMongoService] = None,
) -> Dict[str, Any]:
    """
    Validador de Bracket por Game Changers:
    Consulta MongoDB (o caché resiliente) y evalúa el mazo ingresado contra las reglas oficiales del Bracket:
    - Bracket 1: EXACTAMENTE 0 Game Changers
    - Bracket 2: EXACTAMENTE 0 Game Changers
    - Bracket 3: MÁXIMO 3 Game Changers
    - Bracket 4: ILIMITADO (Sin restricción)
    - Bracket 5: ILIMITADO (Sin restricción)

    Retorna:
    {
        "found_game_changers": List[str],
        "total_count": int,
        "max_allowed": int,
        "is_valid": bool,
        "cards_to_remove": List[str],
        "message": str,
        "target_bracket": int,
    }
    """
    service = mongo_service or get_game_changers_service()
    gc_names_set = service.get_game_changer_names_set()

    # Normalize input deck_cards to list of strings
    raw_card_names: List[str] = []
    if isinstance(deck_cards, str):
        # Raw deck text
        for line in deck_cards.splitlines():
            line_clean = line.strip()
            if line_clean and not line_clean.startswith("//") and not line_clean.startswith("#"):
                # strip quantity prefix (e.g., '1x Sol Ring' -> 'Sol Ring')
                parts = line_clean.split(" ", 1)
                if parts[0].replace("x", "").isdigit() and len(parts) > 1:
                    raw_card_names.append(parts[1].split("(")[0].split("[")[0].strip())
                else:
                    raw_card_names.append(line_clean.split("(")[0].split("[")[0].strip())
    elif hasattr(deck_cards, "items") or hasattr(deck_cards, "maindeck"):
        # Deck object
        items = getattr(deck_cards, "items", getattr(deck_cards, "maindeck", []))
        for it in items:
            name = getattr(it, "effective_name", getattr(it, "name", str(it)))
            raw_card_names.append(name)
    elif isinstance(deck_cards, list):
        for item in deck_cards:
            if isinstance(item, str):
                parts = item.strip().split(" ", 1)
                if parts[0].replace("x", "").isdigit() and len(parts) > 1:
                    raw_card_names.append(parts[1].split("(")[0].split("[")[0].strip())
                else:
                    raw_card_names.append(item.strip().split("(")[0].split("[")[0].strip())
            elif hasattr(item, "effective_name"):
                raw_card_names.append(item.effective_name)
            elif hasattr(item, "name"):
                raw_card_names.append(item.name)
            else:
                raw_card_names.append(str(item))

    # Match Game Changers present in the deck
    found_game_changers: List[str] = []
    seen_found = set()

    for card_name in raw_card_names:
        clean = card_name.lower().strip()
        # Direct match or front face match
        matched_gc_name = None
        for gc_n in gc_names_set:
            if clean == gc_n or (f" // " in clean and clean.split(" // ")[0] == gc_n):
                matched_gc_name = card_name
                break
        
        if matched_gc_name and matched_gc_name.lower() not in seen_found:
            seen_found.add(matched_gc_name.lower())
            found_game_changers.append(matched_gc_name)

    total_count = len(found_game_changers)
    target_b = int(target_bracket)

    # Quotas by Bracket
    max_allowed = {
        1: 0,
        2: 0,
        3: 3,
        4: 999,
        5: 999,
    }.get(target_b, 999)

    cards_to_remove: List[str] = []
    is_valid = False
    message = ""

    if target_b in (1, 2):
        if total_count == 0:
            is_valid = True
            message = f"✅ El mazo cumple con las reglas de Bracket {target_b}: 0 Game Changers presentes."
        else:
            is_valid = False
            cards_to_remove = list(found_game_changers)
            cards_str = ", ".join(f"'{c}'" for c in cards_to_remove)
            message = (
                f"❌ INFRACCIÓN DE BRACKET {target_b}: El mazo contiene {total_count} Game Changer(s) "
                f"({cards_str}), pero Bracket {target_b} permite exactamente 0. "
                f"Cartas a retirar obligatoriamente antes del análisis de IA: {cards_str}."
            )
    elif target_b == 3:
        if total_count <= 3:
            is_valid = True
            message = (
                f"✅ El mazo cumple con las reglas de Bracket 3: {total_count}/3 Game Changers presentes "
                f"({', '.join(found_game_changers) if found_game_changers else 'Ninguno'})."
            )
        else:
            is_valid = False
            excess_count = total_count - 3
            cards_to_remove = found_game_changers[3:]
            cards_to_remove_str = ", ".join(f"'{c}'" for c in cards_to_remove)
            all_gc_str = ", ".join(f"'{c}'" for c in found_game_changers)
            message = (
                f"❌ INFRACCIÓN DE BRACKET 3: El mazo contiene {total_count} Game Changers ({all_gc_str}), "
                f"excediendo el límite máximo oficial de 3. "
                f"Debes retirar obligatoriamente {excess_count} carta(s) antes del análisis de IA: {cards_to_remove_str}."
            )
    else:
        # Bracket 4 & 5
        is_valid = True
        message = (
            f"✅ Bracket {target_b} permite Game Changers ilimitados. "
            f"Total detectados en el mazo: {total_count} ({', '.join(found_game_changers) if found_game_changers else 'Ninguno'})."
        )

    return {
        "found_game_changers": found_game_changers,
        "total_count": total_count,
        "max_allowed": max_allowed,
        "is_valid": is_valid,
        "cards_to_remove": cards_to_remove,
        "message": message,
        "target_bracket": target_b,
    }


def main():
    """CLI execution for seed_game_changers.py"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("\n" + "=" * 65)
    print(" MTG GAME CHANGERS MONGODB SEEDER & VALIDATOR SERVICE")
    print("=" * 65)

    service = GameChangersMongoService()
    try:
        result = service.seed_from_json()
        print("\n[OK] Ingesta de Game Changers completada:")
        print(f"  - Archivo origen: {result['source_file']}")
        print(f"  - Total registros procesados: {result['total_records_processed']}")
        print(f"  - Nuevos insertados: {result['inserted_count']}")
        print(f"  - Actualizados: {result['updated_count']}")
        print(f"  - Conexión a MongoDB activa: {result['using_mongodb']}")
    except Exception as e:
        print(f"\n[ERROR] Error durante el seed: {e}")
        sys.exit(1)

    # Quick demo verification
    print("\n" + "-" * 65)
    print("Verificacion de Consulta y Validacion de Brackets:")
    sample_deck = [
        "1 Sol Ring",
        "1 Mana Crypt",
        "1 Rhystic Study",
        "1 Cyclonic Rift",
        "1 Fierce Guardianship",
        "1 Island",
        "1 Counterspell",
    ]
    print(f"Mazo de prueba: {sample_deck[:5]}...")

    # Test Bracket 1
    res_b1 = check_game_changers_count(sample_deck, target_bracket=1, mongo_service=service)
    print(f"\n[Test Bracket 1] Cumple: {res_b1['is_valid']}")
    print(f"Mensaje: {res_b1['message']}")

    # Test Bracket 3
    res_b3 = check_game_changers_count(sample_deck, target_bracket=3, mongo_service=service)
    print(f"\n[Test Bracket 3] Cumple: {res_b3['is_valid']}")
    print(f"Mensaje: {res_b3['message']}")

    # Test Bracket 4
    res_b4 = check_game_changers_count(sample_deck, target_bracket=4, mongo_service=service)
    print(f"\n[Test Bracket 4] Cumple: {res_b4['is_valid']}")
    print(f"Mensaje: {res_b4['message']}")

    print("\n" + "=" * 65)
    print(" Servicio MongoDB y Validador listos para produccion!")
    print("=" * 65)


if __name__ == "__main__":
    main()
