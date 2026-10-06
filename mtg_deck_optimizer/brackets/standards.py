"""
Power Bracket definitions, benchmark targets, and MTG reference constants for Commander.
"""

from enum import IntEnum
from typing import Dict, List, Set
from pydantic import BaseModel, Field


class BracketTier(IntEnum):
    BRACKET_1_CASUAL = 1      # Jank / Casual
    BRACKET_2_MID_POWER = 2   # Casual Optimizado / Mid-Power
    BRACKET_3_HIGH_POWER = 3  # High-Power / Optimized
    BRACKET_4_CEDH = 4        # cEDH / Máximo Nivel Competitivo

    @property
    def label(self) -> str:
        labels = {
            BracketTier.BRACKET_1_CASUAL: "Bracket 1: Jank / Casual",
            BracketTier.BRACKET_2_MID_POWER: "Bracket 2: Mid-Power / Casual Optimizado",
            BracketTier.BRACKET_3_HIGH_POWER: "Bracket 3: High-Power / Optimized",
            BracketTier.BRACKET_4_CEDH: "Bracket 4: cEDH / Máximo Nivel",
        }
        return labels.get(self, f"Bracket {self.value}")

    @property
    def description(self) -> str:
        descriptions = {
            BracketTier.BRACKET_1_CASUAL: "Sinergias bajas/temáticas, sin combos infinitos, curvas de maná altas (CMC > 3.5), presupuesto bajo y tierras lentas.",
            BracketTier.BRACKET_2_MID_POWER: "Sinergia clara, wincons definidas, interacción estándar (CMC ~2.8-3.4), sin fast mana abusivo ni combos rápidos.",
            BracketTier.BRACKET_3_HIGH_POWER: "Fast mana permitido, combos eficientes de 2-3 cartas, alta densidad de tutores y respuestas baratas (CMC ~2.0-2.8).",
            BracketTier.BRACKET_4_CEDH: "Eficiencia absoluta, wincons de turno 2-4 (e.g. Thoracle + Consultation), máxima interactividad y coste ultra-bajo (CMC ~1.4-2.0).",
        }
        return descriptions.get(self, "")


class BracketBenchmark(BaseModel):
    tier: BracketTier
    min_avg_cmc: float
    max_avg_cmc: float
    target_lands_min: int
    target_lands_max: int
    target_ramp_min: int
    target_fast_mana_min: int
    target_tutors_min: int
    target_interaction_min: int
    target_board_wipes_min: int
    target_board_wipes_max: int
    allow_infinite_combos: bool
    typical_win_turn: str


BRACKET_BENCHMARKS: Dict[BracketTier, BracketBenchmark] = {
    BracketTier.BRACKET_1_CASUAL: BracketBenchmark(
        tier=BracketTier.BRACKET_1_CASUAL,
        min_avg_cmc=3.4,
        max_avg_cmc=4.5,
        target_lands_min=37,
        target_lands_max=40,
        target_ramp_min=6,
        target_fast_mana_min=0,
        target_tutors_min=0,
        target_interaction_min=5,
        target_board_wipes_min=2,
        target_board_wipes_max=5,
        allow_infinite_combos=False,
        typical_win_turn="Turno 10+",
    ),
    BracketTier.BRACKET_2_MID_POWER: BracketBenchmark(
        tier=BracketTier.BRACKET_2_MID_POWER,
        min_avg_cmc=2.8,
        max_avg_cmc=3.4,
        target_lands_min=34,
        target_lands_max=37,
        target_ramp_min=10,
        target_fast_mana_min=0,
        target_tutors_min=1,
        target_interaction_min=8,
        target_board_wipes_min=2,
        target_board_wipes_max=4,
        allow_infinite_combos=False,
        typical_win_turn="Turno 7-9",
    ),
    BracketTier.BRACKET_3_HIGH_POWER: BracketBenchmark(
        tier=BracketTier.BRACKET_3_HIGH_POWER,
        min_avg_cmc=2.0,
        max_avg_cmc=2.8,
        target_lands_min=30,
        target_lands_max=34,
        target_ramp_min=12,
        target_fast_mana_min=2,
        target_tutors_min=4,
        target_interaction_min=12,
        target_board_wipes_min=1,
        target_board_wipes_max=3,
        allow_infinite_combos=True,
        typical_win_turn="Turno 4-6",
    ),
    BracketTier.BRACKET_4_CEDH: BracketBenchmark(
        tier=BracketTier.BRACKET_4_CEDH,
        min_avg_cmc=1.2,
        max_avg_cmc=2.0,
        target_lands_min=26,
        target_lands_max=29,
        target_ramp_min=14,
        target_fast_mana_min=5,
        target_tutors_min=7,
        target_interaction_min=16,
        target_board_wipes_min=0,
        target_board_wipes_max=2,
        allow_infinite_combos=True,
        typical_win_turn="Turno 2-4",
    ),
}

# Curated reference lists of cards for accurate role classification
FAST_MANA_CARDS: Set[str] = {
    "mana crypt",
    "mox diamond",
    "chrome mox",
    "mox opal",
    "mox amber",
    "mana vault",
    "grim monolith",
    "lotus petal",
    "jeweled lotus",
    "lion's eye diamond",
    "dockside extortionist",
    "ancient tomb",
    "dark ritual",
    "cabal ritual",
    "rite of flame",
    "simian spirit guide",
    "elvish spirit guide",
    "treasonous ogre",
}

PREMIUM_TUTORS: Set[str] = {
    "demonic tutor",
    "vampiric tutor",
    "imperial seal",
    "mystical tutor",
    "worldly tutor",
    "enlightened tutor",
    "gamble",
    "tainted pact",
    "demonic consultation",
    "spellseeker",
    "grim tutor",
    "diabolic intent",
    "green sun's zenith",
    "finale of devastation",
    "chord of calling",
    "eldritch evolution",
    "neoform",
    "survival of the fittest",
    "merchant scroll",
    "muddle the mixture",
    "entomb",
    "inventors' fair",
    "urza's saga",
}

FREE_OR_CHEAP_INTERACTION: Set[str] = {
    "force of will",
    "force of negation",
    "pact of negation",
    "fierce guardianship",
    "deflecting swat",
    "deadly rollick",
    "flusterstorm",
    "mental misstep",
    "mindbreak trap",
    "swan song",
    "an offer you can't refuse",
    "mana drain",
    "counterspell",
    "dovin's veto",
    "swords to plowshares",
    "path to exile",
    "rapid hybridization",
    "pongify",
    "snuff out",
    "dismember",
    "lightning bolt",
    "chain of vapor",
    "abrupt decay",
    "assassin's trophy",
    "nature's claim",
    "force of vigor",
}

MASS_REMOVAL: Set[str] = {
    "cyclonic rift",
    "toxic deluge",
    "blasphemous act",
    "wrath of god",
    "damnation",
    "vanquish the horde",
    "supreme verdict",
    "farewell",
    "fire covenant",
    "culling ritual",
    "meathook massacre",
}

# Known compact combo pairs and trios (names lowercase)
KNOWN_COMBO_PACKAGES: List[Set[str]] = [
    {"thassa's oracle", "demonic consultation"},
    {"thassa's oracle", "tainted pact"},
    {"underworld breach", "brain freeze", "lion's eye diamond"},
    {"underworld breach", "grinding station"},
    {"isochron scepter", "dramatic reversal"},
    {"heliod, sun-crowned", "walking ballista"},
    {"dualcaster mage", "twinflame"},
    {"dualcaster mage", "molten duplication"},
    {"kiki-jiki, mirror breaker", "felidar guardian"},
    {"kiki-jiki, mirror breaker", "village bell-ringer"},
    {"kiki-jiki, mirror breaker", "zealous conscripts"},
    {"godo, bandit warlord", "helm of the host"},
    {"sanguine bond", "exquisite blood"},
    {"mikaeus, the unhallowed", "triskelion"},
    {"karmic guide", "reveillark"},
]
