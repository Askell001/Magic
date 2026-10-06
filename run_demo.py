"""
MTG Deck Optimizer - Demo Script
Ingests a sample Commander decklist (Moxfield/Archidekt format),
queries Scryfall for live card metadata & pricing,
and exports the fully validated Deck + DeckAnalysis to structured JSON.
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from mtg_deck_optimizer.service import DeckIngestionService
from tests.fixtures.sample_decks import MOXFIELD_SAMPLE, ARCHIDEKT_SAMPLE


def main():
    print("=" * 70)
    print(" MTG DECK OPTIMIZER - INGESTION & SCRYFALL NORMALIZATION DEMO")
    print("=" * 70)

    raw_deck_text = """
// Commander
1 The Ur-Dragon (C17) 48 *F* #!Commander

// Mainboard
1 Sol Ring (LEA) 270
1 Arcane Signet (C20) 247
1 Command Tower (ELD) 333
1 Birds of Paradise (RAV) 153
1 Rhystic Study (JMP) 169 *F*
1 Smothering Tithe (RNA) 22
1 Cyclonic Rift (RTR) 35
1 Demonic Tutor (UMA) 93
1 Teferi's Protection (C17) 8
1 Cultivate (M21) 177
1 Farseek (M13) 170
1 Nature's Lore (EMA) 178
1 Chaos Warp (C18) 122
1 Swords to Plowshares (A25) 35
1 Counterspell (EMA) 43
1 Scalding Tarn (MH2) 254
1 Misty Rainforest (MH2) 250
1 Verdant Catacombs (MH2) 260
1 Arid Mesa (MH2) 244

// Sideboard
1 Relic of Progenitus (EMA) 231
1 Red Elemental Blast (4ED) 218

// Considering
1 Doubling Season (2XM) 164
1 Mana Crypt (2XM) 225
"""

    print("\n[1] Ingesting decklist and fetching Scryfall metadata in batches...")
    service = DeckIngestionService()
    deck, analysis = service.ingest_from_text(
        raw_text=raw_deck_text,
        deck_name="The Ur-Dragon's Dominion",
        default_format="commander",
        enrich=True,
    )

    print("\n[2] Ingestion Summary:")
    print(f"  - Deck Name:       {deck.name}")
    print(f"  - Format:          {deck.format}")
    print(f"  - Commanders:      {deck.commander_count} ({[c.effective_name for c in deck.commanders]})")
    print(f"  - Maindeck:        {deck.maindeck_count} cards")
    print(f"  - Sideboard:       {deck.sideboard_count} cards")
    print(f"  - Maybeboard:      {deck.maybeboard_count} cards")
    print(f"  - Color Identity:  {''.join(deck.color_identity)}")
    print(f"  - Estimated Value: ${deck.estimated_total_usd} USD")

    print("\n[3] Deck Analysis Summary:")
    print(f"  - Avg CMC (w/o lands): {analysis.avg_cmc_without_lands}")
    print(f"  - Mana Curve:          {analysis.mana_curve}")
    print(f"  - Type Breakdown:      {analysis.type_distribution}")
    print(f"  - Color Breakdown:     {analysis.color_distribution}")
    print(f"  - Warnings:            {analysis.warnings if analysis.warnings else 'None'}")

    print("\n[4] Exporting full Deck JSON (Pydantic model_dump_json)...")
    deck_json = deck.model_dump_json(indent=2)
    
    # Save output to file for easy inspection
    output_path = Path("demo_output_deck.json")
    output_path.write_text(deck_json, encoding="utf-8")
    print(f"  -> Saved full structured JSON to: {output_path.resolve()}")

    # Print first 50 lines snippet of JSON
    json_lines = deck_json.splitlines()[:45]
    print("\n[5] JSON Output Preview (First 45 lines):")
    print("\n".join(json_lines))
    print("    ... [truncated for console display] ...")


if __name__ == "__main__":
    main()
