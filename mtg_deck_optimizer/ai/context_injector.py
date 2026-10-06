"""
Context Injection module formatting recent expansions and spoiled cards
to enrich LLM prompts with the latest competitive MTG meta innovations.
"""

from typing import List, Optional
from ..models.card import Card
from ..scryfall.recent_cards_service import RecentCardsService


class RecentCardsContextInjector:
    """
    Filters and formats recently spoiled and newly printed cards
    matching the commander's color identity for prompt injection.
    """

    def __init__(self, recent_service: Optional[RecentCardsService] = None):
        self.recent_service = recent_service or RecentCardsService()

    def get_recent_cards_for_color(self, color_identity: List[str], limit: int = 8) -> List[Card]:
        """Fetches recent cards from catalog; seeds if catalog is empty."""
        cards = self.recent_service.get_innovations_for_commander(color_identity=color_identity, limit=limit)
        if not cards:
            # Trigger quick initial sync
            self.recent_service.sync_recent_and_spoiled_cards(max_pages=1)
            cards = self.recent_service.get_innovations_for_commander(color_identity=color_identity, limit=limit)
        return cards

    def format_recent_innovations_block(
        self,
        color_identity: List[str],
        limit: int = 8,
    ) -> str:
        """
        Builds a markdown context block detailing latest cards and tech for the LLM prompt.
        """
        cards = self.get_recent_cards_for_color(color_identity=color_identity, limit=limit)

        if not cards:
            return "No recent spoilers found for this color identity."

        lines: List[str] = []
        lines.append("=== CARTAS E INNOVACIONES RECIENTES RELEVANTES (2025-2026 / SPOILERS) ===")
        lines.append("Considera incorporar estas opciones recién reveladas o lanzadas si aumentan la sinergia y velocidad del mazo:")

        for c in cards:
            price_str = f"${c.prices.usd:.2f} USD" if c.prices and c.prices.usd is not None else "N/A"
            spoiler_tag = " [SPOILER / RECIENTE]"
            oracle_summary = (c.oracle_text or "").replace("\n", " ")[:90]
            if len(c.oracle_text or "") > 90:
                oracle_summary += "..."
            set_str = f"Set: {c.set_code.upper()}" if c.set_code else "Set: Reciente"
            lines.append(f"- {c.name} ({c.type_line}, {c.cmc:.0f} CMC) | {set_str}{spoiler_tag} | Efecto: \"{oracle_summary}\" | Precio: {price_str}")

        return "\n".join(lines)
