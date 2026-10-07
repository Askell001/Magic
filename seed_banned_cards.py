"""
Seed Official Banned Cards to MongoDB Atlas & Absolute Banlist Validator Middleware.
Reads banned_cards.json and seeds the MongoDB 'banned_cards' collection with a unique index on 'name'.
Provides validate_banned_cards(deck_cards) with special Lutri companion rule and pre-processing blocking.
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
COLLECTION_NAME = "banned_cards"


class BannedCardsMongoService:
    """
    MongoDB service to manage and query the 'banned_cards' collection with unique indexing
    and local JSON cache fallback resilience.
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
        self.cache_file = self.cache_dir / "banned_cards_mongo_cache.json"

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
            self.client.admin.command("ping")
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            # Ensure unique index on 'name'
            self.collection.create_index("name", unique=True)
            self.using_mongodb = True
            logger.info("BannedCardsMongoService successfully connected to MongoDB Atlas.")
        except Exception as e:
            self.using_mongodb = False
            logger.warning(f"MongoDB unavailable ({e}). Operating with local JSON cache fallback.")

    def seed_from_json(self, json_filepath: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """
        Reads banned_cards.json and upserts all documents into MongoDB 'banned_cards'.
        """
        base_dir = Path(__file__).parent
        candidate_paths = [
            json_filepath,
            base_dir / "banned_cards.json",
            base_dir / "banned_cards.JSON",
        ]

        target_path: Optional[Path] = None
        for p in candidate_paths:
            if p and Path(p).exists():
                target_path = Path(p)
                break

        if not target_path:
            raise FileNotFoundError("Could not find 'banned_cards.json' in project directory.")

        with open(target_path, "r", encoding="utf-8") as f:
            raw_content = json.load(f)

        # Support both {"banned_cards": [...]} and [...] list format
        if isinstance(raw_content, dict) and "banned_cards" in raw_content:
            raw_data = raw_content["banned_cards"]
        elif isinstance(raw_content, list):
            raw_data = raw_content
        else:
            raise ValueError(f"Unexpected JSON format in {target_path}")

        inserted_count = 0
        updated_count = 0

        # Update local fallback cache
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

    def get_all_banned_cards(self) -> List[Dict[str, Any]]:
        """Retrieves all banned cards from MongoDB or fallback cache."""
        if self.using_mongodb and self.collection is not None:
            try:
                cursor = self.collection.find({}, {"_id": 0})
                return list(cursor)
            except Exception as e:
                logger.warning(f"Error reading from MongoDB ({e}), falling back to cache.")

        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as cf:
                    return json.load(cf)
            except Exception as ce:
                logger.error(f"Error reading local cache: {ce}")

        root_json = Path(__file__).parent / "banned_cards.json"
        if root_json.exists():
            with open(root_json, "r", encoding="utf-8") as rf:
                data = json.load(rf)
                return data.get("banned_cards", data) if isinstance(data, dict) else data

        return []

    def get_banned_cards_map(self) -> Dict[str, Dict[str, Any]]:
        """Returns map of lowercase card name -> card document."""
        docs = self.get_all_banned_cards()
        b_map = {}
        for doc in docs:
            n = doc.get("name")
            if n:
                b_map[n.strip().lower()] = doc
        return b_map


# Global Singleton Service Instance
_banned_service_instance: Optional[BannedCardsMongoService] = None


def get_banned_cards_service() -> BannedCardsMongoService:
    global _banned_service_instance
    if _banned_service_instance is None:
        _banned_service_instance = BannedCardsMongoService()
    return _banned_service_instance


def validate_banned_cards(
    deck_cards: Union[List[str], List[Any], Any],
    mongo_service: Optional[BannedCardsMongoService] = None,
) -> Dict[str, Any]:
    """
    Validador Absoluto de Banlist WOTC Commander:
    Consulta la colección MongoDB 'banned_cards' y verifica la lista del mazo ingresado.

    Reglas aplicadas:
    1. Si detecta cartas prohibidas (ej. Mana Crypt, Jeweled Lotus, Dockside Extortionist, Nadu, Winged Wisdom),
       las marca como 'Violación Crítica de Reglas'.
    2. Regla Especial Lutri: 'Lutri, the Spellchaser' únicamente está prohibida como Compañero (Companion).
       Es legal si está en el mazo principal (99) o en la zona de mando como Comandante.
    3. Bloqueo Pre-Procesamiento: Si el mazo contiene alguna carta no legal, genera un reporte detallado
       para detener el flujo antes de permitir consultas o inferencias de IA.

    Retorna:
    {
        "is_legal": bool,
        "has_critical_violation": bool,
        "banned_cards_found": List[Dict[str, Any]],
        "banned_names": List[str],
        "lutri_companion_violation": bool,
        "error_message": str,
        "details": List[str],
    }
    """
    service = mongo_service or get_banned_cards_service()
    banned_map = service.get_banned_cards_map()

    # Normalize input into tuples of (raw_name, section, is_companion)
    parsed_entries: List[Tuple[str, str, bool]] = []

    if isinstance(deck_cards, str):
        current_section = "maindeck"
        for line in deck_cards.splitlines():
            line_clean = line.strip()
            if not line_clean:
                continue
            if line_clean.lower().startswith("// companion") or line_clean.lower().startswith("# companion"):
                current_section = "companion"
                continue
            elif line_clean.lower().startswith("// commander") or line_clean.lower().startswith("# commander"):
                current_section = "commander"
                continue
            elif line_clean.lower().startswith("// sideboard") or line_clean.lower().startswith("# sideboard"):
                current_section = "sideboard"
                continue
            elif line_clean.startswith("//") or line_clean.startswith("#"):
                continue

            # Strip quantity
            parts = line_clean.split(" ", 1)
            if parts[0].replace("x", "").isdigit() and len(parts) > 1:
                clean_name = parts[1].split("(")[0].split("[")[0].strip()
            else:
                clean_name = line_clean.split("(")[0].split("[")[0].strip()

            is_comp = current_section == "companion" or "companion" in line_clean.lower()
            parsed_entries.append((clean_name, current_section, is_comp))

    elif hasattr(deck_cards, "get_all_items") or hasattr(deck_cards, "commanders"):
        # Deck model object
        commanders = getattr(deck_cards, "commanders", [])
        maindeck = getattr(deck_cards, "maindeck", [])
        sideboard = getattr(deck_cards, "sideboard", [])
        maybeboard = getattr(deck_cards, "maybeboard", [])

        for it in commanders:
            name = getattr(it, "effective_name", getattr(it, "name", str(it)))
            parsed_entries.append((name, "commander", False))
        for it in maindeck:
            name = getattr(it, "effective_name", getattr(it, "name", str(it)))
            parsed_entries.append((name, "maindeck", False))
        for it in sideboard:
            name = getattr(it, "effective_name", getattr(it, "name", str(it)))
            tags = getattr(it, "custom_tags", [])
            is_comp = any("companion" in str(t).lower() for t in tags) or "companion" in getattr(it, "raw_name", "").lower()
            parsed_entries.append((name, "companion" if is_comp else "sideboard", is_comp))
        for it in maybeboard:
            name = getattr(it, "effective_name", getattr(it, "name", str(it)))
            parsed_entries.append((name, "maybeboard", False))

    elif isinstance(deck_cards, list):
        for item in deck_cards:
            if isinstance(item, str):
                parts = item.strip().split(" ", 1)
                if parts[0].replace("x", "").isdigit() and len(parts) > 1:
                    clean_name = parts[1].split("(")[0].split("[")[0].strip()
                else:
                    clean_name = item.strip().split("(")[0].split("[")[0].strip()
                is_comp = "companion" in item.lower()
                parsed_entries.append((clean_name, "maindeck", is_comp))
            elif hasattr(item, "effective_name"):
                name = item.effective_name
                sec = getattr(item, "section", "maindeck")
                sec_str = getattr(sec, "value", str(sec))
                tags = getattr(item, "custom_tags", [])
                is_comp = "companion" in sec_str.lower() or any("companion" in str(t).lower() for t in tags)
                parsed_entries.append((name, sec_str, is_comp))
            elif hasattr(item, "name"):
                parsed_entries.append((item.name, "maindeck", False))
            else:
                parsed_entries.append((str(item), "maindeck", False))

    # Evaluate banlist matching
    banned_found: List[Dict[str, Any]] = []
    banned_names: List[str] = []
    details: List[str] = []
    lutri_violation = False
    seen_violations: Set[str] = set()

    for card_name, section, is_companion in parsed_entries:
        clean = card_name.lower().strip()
        matched_ban_doc = None

        for b_name_lower, doc in banned_map.items():
            if clean == b_name_lower or (f" // " in clean and clean.split(" // ")[0] == b_name_lower):
                matched_ban_doc = doc
                break

        if matched_ban_doc:
            official_name = matched_ban_doc.get("name", card_name)
            notes = matched_ban_doc.get("notes", "")

            # Special Rule for Lutri, the Spellchaser
            if "lutri, the spellchaser" in official_name.lower():
                if is_companion or section == "companion":
                    lutri_violation = True
                    if official_name not in seen_violations:
                        seen_violations.add(official_name)
                        banned_found.append(matched_ban_doc)
                        banned_names.append(official_name)
                        details.append(
                            f"❌ '{official_name}': PROHIBIDA exclusivamente bajo la regla de Compañero (Companion). "
                            f"No puede ser declarada como compañero de inicio."
                        )
                else:
                    # Legal as regular card in the 99 or commander
                    continue
            else:
                if official_name not in seen_violations:
                    seen_violations.add(official_name)
                    banned_found.append(matched_ban_doc)
                    banned_names.append(official_name)
                    notes_str = f" ({notes})" if notes else ""
                    details.append(
                        f"🚨 '{official_name}' [{matched_ban_doc.get('type', 'Spell')}]: "
                        f"VIOLACIÓN CRÍTICA DE REGLAS. Carta oficialmente prohibida (Banned) en MTG Commander{notes_str}."
                    )

    has_critical_violation = len(banned_names) > 0
    is_legal = not has_critical_violation

    if has_critical_violation:
        banned_str = ", ".join(f"'{n}'" for n in banned_names)
        error_message = (
            f"🚨 BLOQUEO PRE-PROCESAMIENTO: El mazo contiene {len(banned_names)} carta(s) PROHIBIDAS "
            f"en Commander oficial ({banned_str}). "
            f"El sistema ha detenido el análisis. Debes retirar estas cartas obligatoriamente antes de proceder con el estudio o sugerencias de IA."
        )
    else:
        error_message = ""

    return {
        "is_legal": is_legal,
        "has_critical_violation": has_critical_violation,
        "banned_cards_found": banned_found,
        "banned_names": banned_names,
        "lutri_companion_violation": lutri_violation,
        "error_message": error_message,
        "details": details,
    }


def main():
    """CLI execution for seed_banned_cards.py"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("\n" + "=" * 65)
    print(" MTG BANNED CARDS MONGODB SEEDER & BANLIST VALIDATOR SERVICE")
    print("=" * 65)

    service = BannedCardsMongoService()
    try:
        result = service.seed_from_json()
        print("\n[OK] Ingesta de Banned Cards completada exitosamente:")
        print(f"  - Archivo origen: {result['source_file']}")
        print(f"  - Total registros procesados: {result['total_records_processed']}")
        print(f"  - Nuevos insertados: {result['inserted_count']}")
        print(f"  - Actualizados: {result['updated_count']}")
        print(f"  - Conexión a MongoDB activa: {result['using_mongodb']}")
    except Exception as e:
        print(f"\n[ERROR] Error durante el seed de banned cards: {e}")
        sys.exit(1)

    print("\n" + "-" * 65)
    print("Verificacion de Banlist Validator:")
    
    # Test 1: Deck with banned staples (Mana Crypt, Jeweled Lotus, Dockside, Nadu)
    banned_deck = [
        "1 Mana Crypt",
        "1 Jeweled Lotus",
        "1 Dockside Extortionist",
        "1 Nadu, Winged Wisdom",
        "1 Sol Ring",
        "1 Counterspell",
    ]
    res_banned = validate_banned_cards(banned_deck, mongo_service=service)
    print(f"\n[Test 1 - Cartas Prohibidas] Legal: {res_banned['is_legal']}")
    print(f"Violación Crítica: {res_banned['has_critical_violation']}")
    print(f"Cartas detectadas: {res_banned['banned_names']}")
    print(f"Mensaje de bloqueo: {res_banned['error_message']}")

    # Test 2: Lutri as companion vs regular deck
    lutri_companion = ["// Companion\n1 Lutri, the Spellchaser\n1 Sol Ring\n1 Island"]
    res_lutri_comp = validate_banned_cards(lutri_companion[0], mongo_service=service)
    print(f"\n[Test 2 - Lutri como Companion] Legal: {res_lutri_comp['is_legal']}")
    print(f"Lutri violation: {res_lutri_comp['lutri_companion_violation']}")

    lutri_in_99 = ["1 Lutri, the Spellchaser", "1 Sol Ring", "1 Island"]
    res_lutri_99 = validate_banned_cards(lutri_in_99, mongo_service=service)
    print(f"\n[Test 3 - Lutri en el 99/Maindeck] Legal: {res_lutri_99['is_legal']}")

    # Test 4: Fully legal deck
    legal_deck = ["1 Sol Ring", "1 Arcane Signet", "1 Rhystic Study", "1 Island"]
    res_legal = validate_banned_cards(legal_deck, mongo_service=service)
    print(f"\n[Test 4 - Mazo 100% Legal] Legal: {res_legal['is_legal']}")

    print("\n" + "=" * 65)
    print(" Servicio Banlist MongoDB y Validador Absoluto listos!")
    print("=" * 65)


if __name__ == "__main__":
    main()
