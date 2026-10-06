"""
High-level service orchestrating MTG deck parsing, Scryfall enrichment, analysis, and AI optimization.
"""

from typing import Tuple, Optional, Callable

from .models.deck import Deck, DeckItem, DeckSection
from .models.analysis import DeckAnalysis
from .parser.text_parser import MTGDeckTextParser
from .scryfall.client import ScryfallClient
from .intent.models import UserIntent
from .brackets.gap_analyzer import DeckGapAnalyzer, DeckGapReport
from .ai.models import OptimizationReport
from .ai.optimizer_agent import DeckOptimizerAgent


class DeckIngestionService:
    """
    Main entry point for importing, normalizing, enriching, analyzing, and optimizing MTG decks.
    """

    def __init__(
        self,
        scryfall_client: Optional[ScryfallClient] = None,
        ai_agent: Optional[DeckOptimizerAgent] = None,
    ):
        self.scryfall = scryfall_client or ScryfallClient()
        self.ai_agent = ai_agent or DeckOptimizerAgent()

    def ingest_from_text(
        self,
        raw_text: str,
        deck_name: str = "Imported Deck",
        default_format: str = "commander",
        enrich: bool = True,
        custom_commander: Optional[str] = None,
        commander_override: Optional[str] = None,
        auto_detect_commander_if_empty: bool = True,
    ) -> Tuple[Deck, DeckAnalysis]:
        """
        Parses raw export text, optionally queries Scryfall for metadata, and generates DeckAnalysis.
        Supports automatic 1st-card commander detection or explicit commander override.
        """
        effective_cmdr = commander_override or custom_commander
        deck = MTGDeckTextParser.parse(raw_text=raw_text, deck_name=deck_name, default_format=default_format)

        # Handle explicit custom commander override
        if effective_cmdr and effective_cmdr.strip():
            cmdr_raw = effective_cmdr.strip()
            parsed_cmdr_item, _ = MTGDeckTextParser._parse_card_line(cmdr_raw, DeckSection.COMMANDER)
            if parsed_cmdr_item and parsed_cmdr_item.raw_name:
                cmdr_clean = parsed_cmdr_item.raw_name
                set_code = parsed_cmdr_item.set_code
                collector_number = parsed_cmdr_item.collector_number
                is_foil = parsed_cmdr_item.is_foil
            else:
                cmdr_clean = cmdr_raw
                set_code = None
                collector_number = None
                is_foil = False

            cmdr_lower = cmdr_clean.lower()
            existing_item: Optional[DeckItem] = None

            # Look in existing commanders
            for idx, item in enumerate(deck.commanders):
                if item.effective_name.lower() == cmdr_lower:
                    existing_item = item
                    break

            # Look in maindeck
            if not existing_item:
                for idx, item in enumerate(deck.maindeck):
                    if item.effective_name.lower() == cmdr_lower:
                        existing_item = deck.maindeck.pop(idx)
                        existing_item.section = DeckSection.COMMANDER
                        break

            if existing_item:
                deck.commanders = [existing_item]
            else:
                new_cmdr_item = DeckItem(
                    quantity=1,
                    raw_name=cmdr_clean,
                    set_code=set_code,
                    collector_number=collector_number,
                    is_foil=is_foil,
                    section=DeckSection.COMMANDER,
                )
                deck.commanders = [new_cmdr_item]

        # Auto-detect commander from 1st card in maindeck if format is commander and commanders list is empty
        elif auto_detect_commander_if_empty and not deck.commanders and deck.maindeck and default_format.lower() == "commander":
            first_item = deck.maindeck.pop(0)
            first_item.section = DeckSection.COMMANDER
            deck.commanders.append(first_item)

        if enrich:
            deck = self.scryfall.enrich_deck(deck)

        analysis = DeckAnalysis.from_deck(deck)
        return deck, analysis

    def evaluate_gap(self, deck: Deck, intent: UserIntent) -> DeckGapReport:
        """Evaluates deviation between current deck and target power bracket."""
        return DeckGapAnalyzer.analyze(deck, intent)

    def optimize_deck(
        self,
        deck: Deck,
        intent: UserIntent,
        llm_caller: Optional[Callable[[str, str], str]] = None,
    ) -> OptimizationReport:
        """Runs the AI Optimization Agent to produce cuts, inclusions, mana base and wincon roadmap."""
        return self.ai_agent.optimize(deck=deck, intent=intent, llm_caller=llm_caller)
