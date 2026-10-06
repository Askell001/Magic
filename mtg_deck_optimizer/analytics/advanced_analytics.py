"""
Advanced_Deck_Analytics Master Façade:
Integrates Mana Pip Density Balancing, Monte Carlo Mulligan Simulations,
Anti-Synergy-Trap Filtering, and Card-by-Card Trade-off Justifications.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple

from ..models.deck import Deck
from ..ai.models import CardCut, CardInclusion
from ..brackets.standards import BracketTier
from .mana_pip_analyzer import ManaPipAnalyzer, ManaPipReport, ColorPipBalance
from .mulligan_simulator import MulliganSimulator, MulliganSimulationReport
from .tradeoff_engine import TradeoffEngine, CardTradeoff, BudgetAlternatives, BudgetTierOption

logger = logging.getLogger(__name__)


class Advanced_Deck_Analytics:
    """
    Advanced Deck Analytics Suite for MTG Commander.
    """

    @classmethod
    def analyze_mana_pips(cls, deck: Deck) -> ManaPipReport:
        """Calculates Mana Pip Density vs Colored Sources Produced and flags imbalances."""
        return ManaPipAnalyzer.analyze(deck)

    @classmethod
    def analyze_mana_pip_balance(cls, deck: Deck) -> ManaPipReport:
        """Alias for analyze_mana_pips."""
        return ManaPipAnalyzer.analyze(deck)

    @classmethod
    def simulate_opening_hands(
        cls,
        deck: Deck,
        num_simulations: int = 1000,
        seed: Optional[int] = 42,
    ) -> MulliganSimulationReport:
        """Runs 1,000 Monte Carlo virtual draws to compute opening hand playability & interaction."""
        return MulliganSimulator.simulate_opening_hands(deck, num_simulations=num_simulations, seed=seed)

    @classmethod
    def build_tradeoffs(
        cls,
        cuts: List[CardCut],
        inclusions: List[CardInclusion],
        target_bracket: BracketTier,
    ) -> List[CardTradeoff]:
        """Builds pairwise Causa-Efecto justifications with 3-tier budget choices."""
        return TradeoffEngine.build_pairwise_tradeoffs(cuts, inclusions, target_bracket)

    @classmethod
    def evaluate_anti_synergy_trap(cls, card_name: str, cmc: float, role: str) -> Tuple[bool, Optional[str]]:
        """Filters high-CMC slow cards in favor of mana efficiency and real meta power."""
        return TradeoffEngine.evaluate_anti_synergy_trap(card_name, cmc, role)


# Convenient Alias
AdvancedDeckAnalytics = Advanced_Deck_Analytics
