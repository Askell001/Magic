"""
Data models for MTG Deckbuilder Generator.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from ..brackets.standards import BracketTier
from ..models.deck import Deck
from ..models.card import Card
from ..rules.wotc_rules_engine import DeckValidationResult


class DeckbuilderParams(BaseModel):
    """Input parameters provided by the user for deck generation."""
    commander_name: Optional[str] = Field(default=None, description="Exact or partial commander name. If None, IA suggests top 3.")
    target_bracket: int = Field(default=3, ge=1, le=5, description="Target Power Bracket (1 to 5)")
    strategy_archetype: str = Field(default="Aristocrats", description="Core strategy or archetype (e.g. Aristocrats, Spellslinger, Landfall, cEDH Combo)")
    max_budget_usd: Optional[float] = Field(default=None, description="Max budget constraint in USD. None means unlimited.")
    include_spoilers: bool = Field(default=True, description="Whether to include recent 2025-2026 cards / spoilers in the deck pool")


class CommanderSuggestion(BaseModel):
    """Recommended commander for a given strategy/bracket."""
    name: str
    color_identity: List[str]
    cmc: float
    type_line: str
    reason: str
    typical_tier: int
    image_url: Optional[str] = None

    @property
    def synergy_reason(self) -> str:
        return self.reason


class DeckRoleBreakdown(BaseModel):
    """Card count breakdown by functional role."""
    lands: int = 0
    ramp_and_mana: int = 0
    card_draw_and_engines: int = 0
    targeted_removal: int = 0
    board_wipes: int = 0
    tutors: int = 0
    synergy_and_wincons: int = 0


class GeneratedDeckResult(BaseModel):
    """Output result produced by MTG Deckbuilder Generator."""
    deck: Deck
    commander: Card
    bracket: BracketTier
    strategy: str
    total_price_usd: float
    average_cmc: float
    role_breakdown: DeckRoleBreakdown
    suggested_commanders: List[CommanderSuggestion] = Field(default_factory=list)
    key_combos_or_synergies: List[str] = Field(default_factory=list)
    validation: DeckValidationResult
    export_text: str
