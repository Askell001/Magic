"""
Official 5-Bracket Definitions, Benchmark Targets, Game Changers Quotas,
and Reference Constants for MTG Commander (WotC 5-Bracket System).
"""

from enum import IntEnum
from typing import Dict, List, Set, Any
from pydantic import BaseModel, Field


class BracketTier(IntEnum):
    BRACKET_1_EXHIBITION = 1   # Bracket 1: Exhibition (Ultra-Casual / Temático)
    BRACKET_2_CORE = 2         # Bracket 2: Core (Nivel Preconstruido Promedio)
    BRACKET_3_UPGRADED = 3     # Bracket 3: Upgraded (Preconstruido Mejorado / Optimizado Medio)
    BRACKET_4_OPTIMIZED = 4    # Bracket 4: Optimized (Alta Potencia sin Meta de Torneo)
    BRACKET_5_CEDH = 5         # Bracket 5: cEDH (Competitive Commander / Tournament Meta)

    # Backwards Compatibility Aliases
    BRACKET_1_CASUAL = 1
    BRACKET_2_MID_POWER = 2
    BRACKET_3_HIGH_POWER = 3
    BRACKET_4_CEDH = 4  # Legacy alias

    @property
    def label(self) -> str:
        labels = {
            BracketTier.BRACKET_1_EXHIBITION: "Bracket 1: Exhibition (Ultra-Casual / Temático)",
            BracketTier.BRACKET_2_CORE: "Bracket 2: Core (Nivel Preconstruido Promedio)",
            BracketTier.BRACKET_3_UPGRADED: "Bracket 3: Upgraded (Preconstruido Mejorado / Optimizado Medio)",
            BracketTier.BRACKET_4_OPTIMIZED: "Bracket 4: Optimized (Alta Potencia)",
            BracketTier.BRACKET_5_CEDH: "Bracket 5: cEDH (Competitive Commander / Tournament Meta)",
        }
        return labels.get(self, f"Bracket {self.value}")

    @property
    def experience_description(self) -> str:
        descriptions = {
            BracketTier.BRACKET_1_EXHIBITION: "Mazos hipertemáticos o con restricciones creativas (jank, arte coincidente, etc.). Partidas largas (10+ turnos).",
            BracketTier.BRACKET_2_CORE: "Nivel equivalente a un mazo preconstruido comercial promedio. Motores sólidos, partidas de 9+ turnos con algunas cartas seleccionadas por temática/sabor personal.",
            BracketTier.BRACKET_3_UPGRADED: "Cartas seleccionadas minuciosamente slot por slot. Partidas más rápidas (7-8 turnos).",
            BracketTier.BRACKET_4_OPTIMIZED: "Salidas explosivas, interacción rápida, combos de bajo coste, MLD y sin limitaciones creativas. La mejor versión posible de la noción/tema de tu mazo.",
            BracketTier.BRACKET_5_CEDH: "Enfocado 100% en ganar y responder al metajuego de torneo actual. Eficiencia absoluta donde las cartas favoritas o temáticas (pet cards) son reemplazadas por las mejores respuestas del formato.",
        }
        return descriptions.get(self, "")

    @property
    def deckbuilding_rules(self) -> str:
        rules = {
            BracketTier.BRACKET_1_EXHIBITION: "0 cartas 'Game Changers'. PROHIBIDO: combos infinitos de 2 cartas, destrucción masiva de tierras (MLD) y turnos extra. Tutores extremadamente escasos o nulos.",
            BracketTier.BRACKET_2_CORE: "0 cartas 'Game Changers'. PROHIBIDO: combos infinitos de 2 cartas y MLD. Turnos extra y tutores permitidos en cantidades muy bajas (sin loops ni encadenamientos).",
            BracketTier.BRACKET_3_UPGRADED: "MÁXIMO 3 cartas 'Game Changers'. PROHIBIDO: MLD y combos infinitos de 2 cartas en los primeros 6 turnos. Turnos extra permitidos solo en bajas cantidades y sin loops.",
            BracketTier.BRACKET_4_OPTIMIZED: "Sin restricciones adicionales fuera de la Banlist oficial de Commander. Máximo acceso a 'Game Changers', combos y MLD.",
            BracketTier.BRACKET_5_CEDH: "Sin restricciones adicionales fuera de la Banlist. Priorización estricta de eficiencia de maná (CMC promedio 1.5 - 2.2), fast mana máximo, tutores óptimos y wincons de turnos 1-3.",
        }
        return rules.get(self, "")

    @property
    def description(self) -> str:
        return f"{self.experience_description} | Reglas: {self.deckbuilding_rules}"

    @property
    def max_game_changers(self) -> int:
        quotas = {1: 0, 2: 0, 3: 3, 4: 999, 5: 999}
        return quotas.get(self.value, 999)


# Quota Map per Bracket Tier
GAME_CHANGERS_MAX_ALLOWED: Dict[int, int] = {
    1: 0,
    2: 0,
    3: 3,
    4: 999,
    5: 999,
}


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
    allow_mld: bool = False
    allow_extra_turns: bool = False
    typical_win_turn: str


BRACKET_BENCHMARKS: Dict[BracketTier, BracketBenchmark] = {
    BracketTier.BRACKET_1_EXHIBITION: BracketBenchmark(
        tier=BracketTier.BRACKET_1_EXHIBITION,
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
        allow_mld=False,
        allow_extra_turns=False,
        typical_win_turn="Turno 10+",
    ),
    BracketTier.BRACKET_2_CORE: BracketBenchmark(
        tier=BracketTier.BRACKET_2_CORE,
        min_avg_cmc=2.8,
        max_avg_cmc=3.4,
        target_lands_min=34,
        target_lands_max=37,
        target_ramp_min=9,
        target_fast_mana_min=0,
        target_tutors_min=1,
        target_interaction_min=8,
        target_board_wipes_min=2,
        target_board_wipes_max=4,
        allow_infinite_combos=False,
        allow_mld=False,
        allow_extra_turns=True,  # Low quantities only, no loops
        typical_win_turn="Turno 9+",
    ),
    BracketTier.BRACKET_3_UPGRADED: BracketBenchmark(
        tier=BracketTier.BRACKET_3_UPGRADED,
        min_avg_cmc=2.2,
        max_avg_cmc=2.8,
        target_lands_min=31,
        target_lands_max=34,
        target_ramp_min=11,
        target_fast_mana_min=1,
        target_tutors_min=3,
        target_interaction_min=12,
        target_board_wipes_min=1,
        target_board_wipes_max=3,
        allow_infinite_combos=True,  # Mid-to-late game combos (Turn 7+)
        allow_mld=False,
        allow_extra_turns=True,
        typical_win_turn="Turno 7-8",
    ),
    BracketTier.BRACKET_4_OPTIMIZED: BracketBenchmark(
        tier=BracketTier.BRACKET_4_OPTIMIZED,
        min_avg_cmc=1.8,
        max_avg_cmc=2.4,
        target_lands_min=28,
        target_lands_max=31,
        target_ramp_min=13,
        target_fast_mana_min=3,
        target_tutors_min=5,
        target_interaction_min=15,
        target_board_wipes_min=0,
        target_board_wipes_max=2,
        allow_infinite_combos=True,
        allow_mld=True,
        allow_extra_turns=True,
        typical_win_turn="Turno 4-6",
    ),
    BracketTier.BRACKET_5_CEDH: BracketBenchmark(
        tier=BracketTier.BRACKET_5_CEDH,
        min_avg_cmc=1.2,
        max_avg_cmc=1.9,
        target_lands_min=25,
        target_lands_max=28,
        target_ramp_min=15,
        target_fast_mana_min=6,
        target_tutors_min=8,
        target_interaction_min=18,
        target_board_wipes_min=0,
        target_board_wipes_max=1,
        allow_infinite_combos=True,
        allow_mld=True,
        allow_extra_turns=True,
        typical_win_turn="Turno 1-3",
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

# Mass Land Denial / Mass Land Destruction (MLD) Cards
MASS_LAND_DENIAL_CARDS: Set[str] = {
    "armageddon",
    "ravages of war",
    "winter orb",
    "static orb",
    "stasis",
    "jokulhaups",
    "obliterate",
    "cataclysm",
    "decree of annihilation",
    "sunder",
    "fall of the thran",
    "ruination",
    "blood moon",
    "back to basics",
    "rising waters",
    "hokori, dust drinker",
    "apocalypse",
    "wildfire",
    "destructive force",
    "epicenter",
    "tectonic break",
    "thoughts of ruin",
    "global ruin",
    "kormus bell",
    "tsunami",
    "flashfires",
    "boil",
    "boiling seas",
    "choke",
    "contamination",
    "infernal darkness",
    "mana vortex",
    "desolation",
    "nether void",
}

# Extra Turns Cards
EXTRA_TURNS_CARDS: Set[str] = {
    "time warp",
    "temporal manipulation",
    "capture of jingzhou",
    "time stretch",
    "expropriate",
    "nexus of fate",
    "beacon of tomorrows",
    "karn's temporal sundering",
    "alrund's epiphany",
    "part the waterveil",
    "walk the aeons",
    "temporal trespass",
    "temporal mastery",
    "notorious throng",
    "plea for power",
    "stitch in time",
    "gonti's aether heart",
    "magosi, the waterveil",
    "ugin's nexus",
    "medomai the ageless",
    "sage of hours",
}

# Known 2-Card Infinite Combos
KNOWN_TWO_CARD_COMBOS: List[Set[str]] = [
    {"thassa's oracle", "demonic consultation"},
    {"thassa's oracle", "tainted pact"},
    {"isochron scepter", "dramatic reversal"},
    {"heliod, sun-crowned", "walking ballista"},
    {"dualcaster mage", "twinflame"},
    {"dualcaster mage", "molten duplication"},
    {"dualcaster mage", "saw in half"},
    {"kiki-jiki, mirror breaker", "felidar guardian"},
    {"kiki-jiki, mirror breaker", "village bell-ringer"},
    {"kiki-jiki, mirror breaker", "zealous conscripts"},
    {"kiki-jiki, mirror breaker", "corridor monitor"},
    {"godo, bandit warlord", "helm of the host"},
    {"sanguine bond", "exquisite blood"},
    {"mikaeus, the unhallowed", "triskelion"},
    {"karmic guide", "reveillark"},
    {"painter's servant", "grindstone"},
    {"mindcrank", "bloodchief ascension"},
    {"mindcrank", "duskmantle guildmage"},
    {"professor onyx", "chain of smog"},
    {"witherbloom apprentice", "chain of smog"},
    {"niv-mizzet, parun", "curiosity"},
    {"niv-mizzet, the firemind", "curiosity"},
    {"niv-mizzet, parun", "ophidian eye"},
    {"niv-mizzet, the firemind", "ophidian eye"},
    {"niv-mizzet, parun", "tandem lookout"},
    {"niv-mizzet, the firemind", "tandem lookout"},
    {"worldgorger dragon", "animate dead"},
    {"abdel adrian, gorion's ward", "animate dead"},
    {"naru meha, master wizard", "ghostly flicker"},
]

# Fast / early combo packages (Turn 1-6 wincons prohibited in Bracket 3 and below)
FAST_EARLY_COMBOS: List[Set[str]] = [
    {"thassa's oracle", "demonic consultation"},
    {"thassa's oracle", "tainted pact"},
    {"underworld breach", "brain freeze", "lion's eye diamond"},
    {"underworld breach", "grinding station"},
    {"isochron scepter", "dramatic reversal"},
    {"heliod, sun-crowned", "walking ballista"},
    {"dualcaster mage", "twinflame"},
    {"dualcaster mage", "molten duplication"},
    {"professor onyx", "chain of smog"},
    {"witherbloom apprentice", "chain of smog"},
    {"worldgorger dragon", "animate dead"},
]

# All known combo packages (including 3-card packages)
KNOWN_COMBO_PACKAGES: List[Set[str]] = [
    *KNOWN_TWO_CARD_COMBOS,
    {"underworld breach", "brain freeze", "lion's eye diamond"},
    {"underworld breach", "grinding station"},
]
