"""
MTG Deck Optimizer - Recent Cards & Spoilers Sync Demo
Demonstrates:
1. Connecting to Scryfall API search endpoint for spoilers and recent releases (2025-2026).
2. Persisting catalog into MongoDB / Local Cache.
3. Filtering and formatting Context Injection block for the AI Prompt.
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mtg_deck_optimizer.scryfall.recent_cards_service import RecentCardsService
from mtg_deck_optimizer.ai.context_injector import RecentCardsContextInjector


def main():
    print("=" * 75)
    print(" MTG DECK OPTIMIZER - ACTUALIZACIÓN DIARIA Y SPOILERS SERVICE")
    print("=" * 75)

    # 1. Initialize Service & Storage
    print("\n[1] Inicializando RecentCardsService y verificando repositorio de datos...")
    service = RecentCardsService()
    status = service.repository.get_status()
    print(f"  - Backend de Almacenamiento: {status['backend']}")
    print(f"  - Cartas en Catálogo Local:  {status['total_cards']}")
    print(f"  - Estado de Conexión:        {status['status']}")

    # 2. Sync Spoilers and Recent Releases from Scryfall
    print("\n[2] Consultando Scryfall API (/cards/search?q=is:spoiler+OR+year>=2026)...")
    sync_result = service.sync_recent_and_spoiled_cards(max_pages=2)
    print(f"  [OK] Sincronización exitosa:")
    print(f"       * Páginas Scryfall consultadas: {sync_result['pages_processed']}")
    print(f"       * Cartas obtenidas en lote:     {sync_result['cards_fetched']}")
    print(f"       * Cartas persistidas / actualizadas: {sync_result['cards_persisted']}")
    print(f"       * Total actual en catálogo:     {sync_result['total_in_catalog']}")

    # 3. Context Injection for a Commander (e.g. The Ur-Dragon: WUBRG)
    print("\n[3] Generando Bloque de Context Injection para Comandante WUBRG (The Ur-Dragon)...")
    injector = RecentCardsContextInjector(recent_service=service)
    context_block = injector.format_recent_innovations_block(color_identity=["W", "U", "B", "R", "G"], limit=5)
    
    print("\n" + "-" * 75)
    print(context_block)
    print("-" * 75)

    # 4. Context Injection for a Dimir Commander (e.g. Yuriko: U, B)
    print("\n[4] Generando Bloque de Context Injection para Comandante Dimir (U, B)...")
    dimir_block = injector.format_recent_innovations_block(color_identity=["U", "B"], limit=4)
    print("\n" + "-" * 75)
    print(dimir_block)
    print("-" * 75)

    print("\n[OK] Demostración del servicio de Spoilers y Nuevas Cartas completada exitosamente.")
    print("=" * 75)


if __name__ == "__main__":
    main()
