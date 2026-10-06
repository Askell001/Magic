"""
User Intent data models capturing optimization goals, budget constraints, and protected cards.
"""

from typing import List, Optional, Set
from pydantic import BaseModel, Field, field_validator

from ..brackets.standards import BracketTier, BRACKET_BENCHMARKS


class UserIntent(BaseModel):
    target_bracket: BracketTier = Field(
        default=BracketTier.BRACKET_2_MID_POWER,
        description="Nivel de poder objetivo para el mazo (Bracket 1 a 4)",
    )
    max_budget_usd: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Presupuesto máximo de optimización en USD (None = sin restricción)",
    )
    untouchable_cards: List[str] = Field(
        default_factory=list,
        description="Lista de cartas icónicas o 'sagradas' que el usuario no desea retirar",
    )
    allow_infinite_combos: Optional[bool] = Field(
        default=None,
        description="Permitir combos infinitos explícitamente (si es None, se usa el estándar del Bracket)",
    )
    allow_fast_mana: Optional[bool] = Field(
        default=None,
        description="Permitir fast mana explícitamente (si es None, se usa el estándar del Bracket)",
    )

    @property
    def effective_allow_combos(self) -> bool:
        if self.allow_infinite_combos is not None:
            return self.allow_infinite_combos
        benchmark = BRACKET_BENCHMARKS.get(self.target_bracket)
        return benchmark.allow_infinite_combos if benchmark else False

    @property
    def effective_allow_fast_mana(self) -> bool:
        if self.allow_fast_mana is not None:
            return self.allow_fast_mana
        return self.target_bracket >= BracketTier.BRACKET_3_HIGH_POWER

    def is_untouchable(self, card_name: str) -> bool:
        """Checks if a given card name is marked as untouchable (case-insensitive)."""
        card_clean = card_name.strip().lower()
        for u in self.untouchable_cards:
            u_clean = u.strip().lower()
            if u_clean == card_clean:
                return True
            if " // " in u_clean and card_clean == u_clean.split(" // ")[0]:
                return True
        return False
