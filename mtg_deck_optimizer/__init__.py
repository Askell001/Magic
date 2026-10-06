"""
MTG Deck Optimizer: Ingestion, Normalization, Bracket Classification, User Intent, AI Optimization, and Rules Engine.
"""

from .models import (
    Card,
    CardPrices,
    CardImageUris,
    CardFace,
    Deck,
    DeckItem,
    DeckSection,
    DeckAnalysis,
)
from .parser import MTGDeckTextParser
from .scryfall import ScryfallClient, RecentCardsRepository, RecentCardsService
from .service import DeckIngestionService
from .brackets import (
    BracketTier,
    BracketBenchmark,
    BRACKET_BENCHMARKS,
    CardRoleClassifier,
    DeckClassification,
    DeckGapAnalyzer,
    DeckGapReport,
)
from .intent import (
    UserIntent,
    ask_user_intent_cli,
    build_user_intent,
)
from .ai import (
    CardCut,
    CardInclusion,
    ManaBaseAnalysis,
    WinConditionAnalysis,
    BudgetSummary,
    OptimizationReport,
    CommunityDataService,
    AIPromptBuilder,
    DeckOptimizerAgent,
    RecentCardsContextInjector,
)
from .rules import (
    ColorIdentityExtractor,
    SingletonValidator,
    BanlistValidator,
    validate_recommendations,
    WOTC_Commander_Rules_Engine,
    WotcCommanderRulesEngine,
)
from .analytics import (
    Advanced_Deck_Analytics,
    AdvancedDeckAnalytics,
    ManaPipAnalyzer,
    ManaPipReport,
    ColorPipBalance,
    MulliganSimulator,
    MulliganSimulationReport,
    TradeoffEngine,
    CardTradeoff,
    BudgetAlternatives,
)
from .deckbuilder import (
    MTGDeckbuilderGenerator,
    MTG_Deckbuilder_Generator,
    DeckbuilderParams,
    GeneratedDeckResult,
    CommanderSuggestion,
    DeckRoleBreakdown,
)
from .exporter import DeckExporter

__version__ = "0.6.0"

__all__ = [
    "Card",
    "CardPrices",
    "CardImageUris",
    "CardFace",
    "Deck",
    "DeckItem",
    "DeckSection",
    "DeckAnalysis",
    "MTGDeckTextParser",
    "ScryfallClient",
    "RecentCardsRepository",
    "RecentCardsService",
    "DeckIngestionService",
    "BracketTier",
    "BracketBenchmark",
    "BRACKET_BENCHMARKS",
    "CardRoleClassifier",
    "DeckClassification",
    "DeckGapAnalyzer",
    "DeckGapReport",
    "UserIntent",
    "ask_user_intent_cli",
    "build_user_intent",
    "CardCut",
    "CardInclusion",
    "ManaBaseAnalysis",
    "WinConditionAnalysis",
    "BudgetSummary",
    "OptimizationReport",
    "CommunityDataService",
    "AIPromptBuilder",
    "DeckOptimizerAgent",
    "RecentCardsContextInjector",
    "ColorIdentityExtractor",
    "SingletonValidator",
    "BanlistValidator",
    "validate_recommendations",
    "WOTC_Commander_Rules_Engine",
    "WotcCommanderRulesEngine",
    "Advanced_Deck_Analytics",
    "AdvancedDeckAnalytics",
    "ManaPipAnalyzer",
    "ManaPipReport",
    "ColorPipBalance",
    "MulliganSimulator",
    "MulliganSimulationReport",
    "TradeoffEngine",
    "CardTradeoff",
    "BudgetAlternatives",
    "MTGDeckbuilderGenerator",
    "MTG_Deckbuilder_Generator",
    "DeckbuilderParams",
    "GeneratedDeckResult",
    "CommanderSuggestion",
    "DeckRoleBreakdown",
    "DeckExporter",
]


