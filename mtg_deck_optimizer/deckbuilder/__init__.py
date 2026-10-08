"""
Deckbuilder and Strategy Services module for MTG Commander Optimization.
"""

from .generator import MTGDeckbuilderGenerator, MTG_Deckbuilder_Generator
from .models import (
    DeckbuilderParams,
    CommanderSuggestion,
    GeneratedDeckResult,
    DeckRoleBreakdown,
)
from .archetype_database import (
    ARCHETYPE_DEFINITIONS,
    COLOR_STAPLES,
    CARD_METADATA_REGISTRY,
)
from .strategy_service import (
    StrategyMongoService,
    get_strategies_by_bracket,
    resolve_dynamic_strategy,
    get_strategy_service,
)

__all__ = [
    "MTGDeckbuilderGenerator",
    "MTG_Deckbuilder_Generator",
    "DeckbuilderParams",
    "CommanderSuggestion",
    "GeneratedDeckResult",
    "DeckRoleBreakdown",
    "ARCHETYPE_DEFINITIONS",
    "COLOR_STAPLES",
    "CARD_METADATA_REGISTRY",
    "StrategyMongoService",
    "get_strategies_by_bracket",
    "resolve_dynamic_strategy",
    "get_strategy_service",
]
