"""
Pydantic data models for the AI Optimization Engine output report.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from ..brackets.standards import BracketTier


class CardCut(BaseModel):
    card_name: str = Field(description="Name of the card recommended to be cut")
    type_line: str = Field(description="Card type, e.g. 'Creature — Dragon'")
    cmc: float = Field(description="Converted mana cost of the card")
    role: str = Field(default="Flex", description="Functional role of the cut card (e.g. 'Ramp', 'High CMC Spells', 'Flex')")
    reason: str = Field(description="Detailed technical/statistical justification for cutting this card")
    estimated_price_usd: Optional[float] = Field(default=None, description="Current market price of the cut card in USD")



class CardInclusion(BaseModel):
    card_name: str = Field(description="Name of the card recommended to be added")
    type_line: str = Field(description="Card type, e.g. 'Instant'")
    cmc: float = Field(description="Converted mana cost of the card")
    role: str = Field(description="Functional role, e.g. 'Ramp', 'Tutor', 'Wincon', 'Interaction', 'Protection'")
    synergy_explanation: str = Field(description="Explanation of why this card accelerates deck consistency towards target bracket")
    estimated_price_usd: Optional[float] = Field(default=None, description="Current market price of the added card in USD")
    synergy_score: Optional[float] = Field(default=None, description="Community synergy percentage (e.g. +45%)")


class ManaBaseAnalysis(BaseModel):
    color_balance_status: str = Field(description="Diagnosis of color requirements vs available mana sources")
    recommended_land_count: int = Field(description="Target land count optimized for target bracket")
    utility_lands_recommendations: List[str] = Field(default_factory=list, description="Recommended utility lands (e.g. Ancient Tomb, Urza's Saga, Boseiju)")
    fixing_recommendations: List[str] = Field(default_factory=list, description="Suggestions for fixing (e.g. Shocklands, Fetchlands, Triomes, Painlands)")
    ramp_assessment: str = Field(description="Assessment of mana rocks, dorks, and fast mana efficiency")


class WinConditionAnalysis(BaseModel):
    primary_win_path: str = Field(description="Primary game-winning strategy (e.g., Dragon Beatdown, Combat Swarm, Infinite Combo)")
    combos_or_synergies: List[str] = Field(default_factory=list, description="Key card combinations, combo lines, or synergy packages")
    estimated_turn_to_win: str = Field(description="Estimated turn window to threaten or execute a win (e.g. Turn 4-6)")


class BudgetSummary(BaseModel):
    total_cut_value_usd: float = Field(default=0.0, description="Total estimated value of cards being cut")
    total_added_cost_usd: float = Field(default=0.0, description="Total cost of recommended inclusions in USD")
    net_upgrade_cost_usd: float = Field(default=0.0, description="Net cost to perform the upgrade (added - cut)")
    is_within_budget: bool = Field(default=True, description="Whether the upgrade fits within user's max budget constraint")
    budget_notes: str = Field(default="", description="Additional comments on budget allocation and high-value staples")


class OptimizationReport(BaseModel):
    deck_name: str = Field(description="Name of the deck being analyzed")
    commander_name: str = Field(description="Name of the primary Commander")
    initial_bracket: BracketTier = Field(description="Initial diagnosed power tier")
    target_bracket: BracketTier = Field(description="Target power tier chosen by user")
    estimated_new_power_score: float = Field(description="Projected power score after applying recommendations (1.0 - 4.0)")
    summary_overview: str = Field(description="Executive summary of the optimization strategy")
    
    cuts: List[CardCut] = Field(default_factory=list, description="List of recommended cuts (Outs)")
    inclusions: List[CardInclusion] = Field(default_factory=list, description="List of recommended additions (Ins)")
    tradeoffs: List[Dict[str, Any]] = Field(default_factory=list, description="Pairwise Card-by-Card Trade-off Causa-Efecto justifications")
    mana_base_analysis: ManaBaseAnalysis = Field(description="In-depth mana base diagnosis and fixing plan")
    win_conditions: WinConditionAnalysis = Field(description="Detailed win conditions and combo lines")
    budget_summary: BudgetSummary = Field(description="Financial summary of the recommended changes")

