"""
Land Balance Engine for Land Deficit & Land Overload (Flood) Diagnostics and Swaps.
Calculates exact land requirements based on curve & bracket benchmarks,
identifying specific cards to cut for lands (Deficit) or specific excess lands to cut for business spells (Surplus).
"""

import re
from typing import List, Dict, Set, Tuple, Optional
from pydantic import BaseModel, Field

from ..models.card import Card
from ..models.deck import Deck, DeckItem
from ..brackets.standards import BracketTier, BracketBenchmark, BRACKET_BENCHMARKS
from ..rules.color_identity import WUBRG_ORDER


class LandAdjustmentSwap(BaseModel):
    """Specific 1-to-1 card swap recommended to fix land balance."""
    action: str = Field(description="'cut_spell_add_land' (for deficit) or 'cut_land_add_spell' (for surplus)")
    cut_card_name: str
    cut_card_type: str
    cut_card_cmc: float
    add_card_name: str
    add_card_type: str
    add_card_cmc: float
    category: str = Field(description="'Déficit de Tierras (Faltan Tierras)' or 'Sobrecarga de Tierras (Exceso de Tierras)'")
    reason: str
    cmc_impact: float


class LandBalanceReport(BaseModel):
    """Diagnostic report for deck land count, deficit/surplus, and actionable swaps."""
    current_land_count: int
    target_land_min: int
    target_land_max: int
    target_land_recommended: int
    status: str  # "Déficit Crítico", "Déficit Moderado", "Sobrecarga Crítica", "Sobrecarga Moderada", "Equilibrado"
    deficit_or_surplus_count: int  # negative for deficit, positive for surplus
    is_balanced: bool
    diagnosis_message: str
    adjustments: List[LandAdjustmentSwap] = Field(default_factory=list)
    recommended_lands_to_add: List[str] = Field(default_factory=list)
    recommended_lands_to_cut: List[str] = Field(default_factory=list)
    fixing_upgrade_suggestions: List[str] = Field(default_factory=list)


class LandBalanceEngine:
    """
    Analyzes deck land count vs target bracket benchmarks and curve demands,
    producing actionable card-by-card swaps with technical reasons.
    """

    # High quality lands catalog organized by color identity
    ON_COLOR_LAND_CATALOG = {
        # Rainbow / Any Color
        "ANY": [
            ("Command Tower", "Land", 0.0),
            ("Exotic Orchard", "Land", 0.0),
            ("City of Brass", "Land", 0.0),
            ("Mana Confluence", "Land", 0.0),
            ("Reflecting Pool", "Land", 0.0),
            ("Forbidden Orchard", "Land", 0.0),
            ("Path of Ancestry", "Land", 0.0),
        ],
        # Colorless / Utility
        "C": [
            ("Ancient Tomb", "Land", 0.0),
            ("Urza's Saga", "Land — Urza's Saga", 0.0),
            ("War Room", "Land", 0.0),
            ("Reliquary Tower", "Land", 0.0),
            ("Scavenger Grounds", "Land", 0.0),
            ("Strip Mine", "Land", 0.0),
        ],
        # Monocolor Channel / Utility
        "W": [
            ("Eiganjo, Seat of the Empire", "Legendary Land", 0.0),
            ("Emeria, the Sky Ruin", "Land", 0.0),
            ("Castle Ardenvale", "Land", 0.0),
            ("Plains", "Basic Land — Plains", 0.0),
        ],
        "U": [
            ("Otawara, Soaring City", "Legendary Land", 0.0),
            ("Mystic Sanctuary", "Land — Island", 0.0),
            ("Castle Vantress", "Land", 0.0),
            ("Island", "Basic Land — Island", 0.0),
        ],
        "B": [
            ("Takenuma, Abandoned Mire", "Legendary Land", 0.0),
            ("Cabal Coffers", "Land", 0.0),
            ("Urborg, Tomb of Yawgmoth", "Legendary Land", 0.0),
            ("Castle Locthwain", "Land", 0.0),
            ("Swamp", "Basic Land — Swamp", 0.0),
        ],
        "R": [
            ("Sokenzan, Crucible of Defiance", "Legendary Land", 0.0),
            ("Valakut, the Molten Pinnacle", "Land", 0.0),
            ("Castle Embereth", "Land", 0.0),
            ("Mountain", "Basic Land — Mountain", 0.0),
        ],
        "G": [
            ("Boseiju, Who Endures", "Legendary Land", 0.0),
            ("Yavimaya, Cradle of Growth", "Legendary Land", 0.0),
            ("Castle Garenbrig", "Land", 0.0),
            ("Forest", "Basic Land — Forest", 0.0),
        ],
        # Color pairs: Shocklands & Fetchlands & Bondlands
        ("W", "U"): [
            ("Hallowed Fountain", "Land — Plains Island", 0.0),
            ("Flooded Strand", "Land", 0.0),
            ("Sea of Clouds", "Land", 0.0),
            ("Glacial Fortress", "Land", 0.0),
        ],
        ("U", "B"): [
            ("Watery Grave", "Land — Island Swamp", 0.0),
            ("Polluted Delta", "Land", 0.0),
            ("Morphic Pool", "Land", 0.0),
            ("Drowned Catacomb", "Land", 0.0),
        ],
        ("B", "R"): [
            ("Blood Crypt", "Land — Swamp Mountain", 0.0),
            ("Bloodstained Mire", "Land", 0.0),
            ("Luxury Suite", "Land", 0.0),
            ("Dragonskull Summit", "Land", 0.0),
        ],
        ("R", "G"): [
            ("Stomping Ground", "Land — Mountain Forest", 0.0),
            ("Wooded Foothills", "Land", 0.0),
            ("Spire Garden", "Land", 0.0),
            ("Rootbound Crag", "Land", 0.0),
        ],
        ("G", "W"): [
            ("Temple Garden", "Land — Forest Plains", 0.0),
            ("Windswept Heath", "Land", 0.0),
            ("Bountiful Promenade", "Land", 0.0),
            ("Sunpetal Grove", "Land", 0.0),
        ],
        ("W", "B"): [
            ("Godless Shrine", "Land — Plains Swamp", 0.0),
            ("Marsh Flats", "Land", 0.0),
            ("Vault of Champions", "Land", 0.0),
            ("Isolated Chapel", "Land", 0.0),
        ],
        ("U", "R"): [
            ("Steam Vents", "Land — Island Mountain", 0.0),
            ("Scalding Tarn", "Land", 0.0),
            ("Training Center", "Land", 0.0),
            ("Sulfur Falls", "Land", 0.0),
        ],
        ("B", "G"): [
            ("Overgrown Tomb", "Land — Swamp Forest", 0.0),
            ("Verdant Catacombs", "Land", 0.0),
            ("Undergrowth Stadium", "Land", 0.0),
            ("Woodland Cemetery", "Land", 0.0),
        ],
        ("R", "W"): [
            ("Sacred Foundry", "Land — Mountain Plains", 0.0),
            ("Arid Mesa", "Land", 0.0),
            ("Spectator Seating", "Land", 0.0),
            ("Clifftop Retreat", "Land", 0.0),
        ],
        ("G", "U"): [
            ("Breeding Pool", "Land — Forest Island", 0.0),
            ("Misty Rainforest", "Land", 0.0),
            ("Rejuvenating Springs", "Land", 0.0),
            ("Hinterland Harbor", "Land", 0.0),
        ],
    }

    # Spells to recommend when deck has land overload (excess lands to cut)
    SURPLUS_SPELL_REPLACEMENTS = {
        "W": [
            ("Esper Sentinel", "Creature — Human Soldier", 1.0, "Draw / Advantage"),
            ("Swords to Plowshares", "Instant", 1.0, "Interaction"),
            ("Trouble in Pairs", "Enchantment", 4.0, "Draw / Engine"),
            ("Path to Exile", "Instant", 1.0, "Interaction"),
        ],
        "U": [
            ("Rhystic Study", "Enchantment", 3.0, "Draw / Advantage"),
            ("Mystic Remora", "Enchantment", 1.0, "Draw / Advantage"),
            ("Counterspell", "Instant", 2.0, "Interaction"),
            ("Ponder", "Sorcery", 1.0, "Cantrip / Selection"),
        ],
        "B": [
            ("Demonic Tutor", "Sorcery", 2.0, "Tutor"),
            ("Night's Whisper", "Sorcery", 2.0, "Draw / Advantage"),
            ("Feed the Swarm", "Sorcery", 2.0, "Interaction"),
            ("Dark Ritual", "Instant", 1.0, "Fast Mana / Ramp"),
        ],
        "R": [
            ("Jeska's Will", "Sorcery", 3.0, "Ramp / Advantage"),
            ("Chaos Warp", "Instant", 3.0, "Interaction"),
            ("Lightning Bolt", "Instant", 1.0, "Interaction"),
            ("Faithless Looting", "Sorcery", 1.0, "Card Filtering"),
        ],
        "G": [
            ("Sylvan Library", "Enchantment", 2.0, "Draw / Advantage"),
            ("Nature's Lore", "Sorcery", 2.0, "Ramp"),
            ("Three Visits", "Sorcery", 2.0, "Ramp"),
            ("Beast Within", "Instant", 3.0, "Interaction"),
            ("Birds of Paradise", "Creature — Bird", 1.0, "Ramp"),
        ],
        "COLORLESS": [
            ("Sol Ring", "Artifact", 1.0, "Ramp"),
            ("Arcane Signet", "Artifact", 2.0, "Ramp"),
            ("Fellwar Stone", "Artifact", 2.0, "Ramp"),
            ("Mind Stone", "Artifact", 2.0, "Ramp / Draw"),
            ("Thought Vessel", "Artifact", 2.0, "Ramp"),
        ],
    }

    @classmethod
    def evaluate_land_balance(
        cls,
        deck: Deck,
        target_bracket: BracketTier,
        untouchable_names: Optional[Set[str]] = None,
    ) -> LandBalanceReport:
        """
        Diagnoses land deficits or surpluses, generating exact card-for-land or land-for-card swaps.
        """
        untouchables = {n.lower() for n in (untouchable_names or set())}
        bench: BracketBenchmark = BRACKET_BENCHMARKS[target_bracket]

        # Extract current lands and spells
        current_lands: List[DeckItem] = []
        current_spells: List[DeckItem] = []
        current_card_names: Set[str] = set()

        for it in deck.maindeck:
            name_l = it.effective_name.lower()
            current_card_names.add(name_l)
            card = it.card
            if card and "Land" in (card.type_line or ""):
                current_lands.append(it)
            elif not card and ("land" in name_l or "plains" in name_l or "island" in name_l or "swamp" in name_l or "mountain" in name_l or "forest" in name_l):
                current_lands.append(it)
            else:
                current_spells.append(it)

        total_lands = sum(it.quantity for it in current_lands)
        min_target = bench.target_lands_min
        max_target = bench.target_lands_max
        recommended_target = int((min_target + max_target) / 2)

        # Determine Commander Color Identity
        cmdr_ci = [c.upper() for c in (deck.color_identity or []) if c.upper() in WUBRG_ORDER]
        if not cmdr_ci:
            cmdr_ci = ["W", "U", "B", "R", "G"]

        adjustments: List[LandAdjustmentSwap] = []
        recommended_lands_to_add: List[str] = []
        recommended_lands_to_cut: List[str] = []
        fixing_suggestions: List[str] = []

        # ---------------------------------------------------------------------
        # Case 1: Land Deficit (Current lands < Min Target)
        # ---------------------------------------------------------------------
        if total_lands < min_target:
            deficit_count = recommended_target - total_lands
            if total_lands <= min_target - 4:
                status = "Déficit Crítico"
            else:
                status = "Déficit Moderado"

            diag_msg = (
                f"⚠️ **Déficit de Tierras ({total_lands} actuales vs {min_target}-{max_target} recomendadas para Bracket {target_bracket.value})**: "
                f"El mazo tiene una probabilidad elevada de atasco de maná (mana screw) y no alcanzar los turnos clave de la curva. "
                f"Se requiere incorporar **+{deficit_count} tierras** retirando hechizos pesados o prescindibles."
            )

            # 1. Identify Spells to CUT (Heaviest CMC non-untouchable non-protected spells)
            PROTECTED_STAPLES = {
                "force of will", "force of negation", "fierce guardianship", "pact of negation",
                "deflecting swat", "deadly rollick", "mental misstep", "flusterstorm", "mindbreak trap",
                "submerge", "snuff out", "misdirection", "commandeer", "sol ring", "mana crypt",
                "mana vault", "chrome mox", "mox diamond", "mox opal", "mox amber", "lotus petal",
                "lion's eye diamond", "grim monolith", "dark ritual", "cabal ritual", "simian spirit guide",
                "elvish spirit guide", "dockside extortionist", "ragavan, nimble pilferer", "demonic tutor",
                "vampiric tutor", "imperial seal", "mystical tutor", "worldly tutor", "enlightened tutor",
                "gamble", "tainted pact", "demonic consultation", "entomb", "reanimate", "rhystic study",
                "mystic remora", "the one ring", "necropotence", "necrodominance", "sylvan library",
                "underworld breach", "brain freeze", "thassa's oracle", "ad nauseam", "peer into the abyss",
                "jeska's will", "cyclonic rift", "chain of vapor", "swan song", "an offer you can't refuse",
                "mana drain", "counterspell", "silence", "grand abolisher", "esper sentinel",
                "orcish bowmasters", "opposition agent", "dauthi voidwalker", "drannith magistrate",
            }

            candidate_spell_cuts = []
            for it in current_spells:
                n_low = it.effective_name.lower().strip()
                front_low = n_low.split(" // ")[0].split(" / ")[0].strip()
                if n_low in untouchables or n_low in PROTECTED_STAPLES or front_low in PROTECTED_STAPLES:
                    continue
                candidate_spell_cuts.append(it)

            candidate_spell_cuts.sort(
                key=lambda it: it.card.cmc if it.card else 4.0,
                reverse=True
            )

            # 2. Identify Lands to ADD
            lands_pool: List[Tuple[str, str, float]] = []
            
            # Add Commander Tower / Any-color lands if missing
            for name, tl, cmc in cls.ON_COLOR_LAND_CATALOG["ANY"]:
                if name.lower() not in current_card_names and name.lower() not in [p[0].lower() for p in lands_pool]:
                    lands_pool.append((name, tl, cmc))

            # Add Channel / Utility lands for colors
            for c in cmdr_ci:
                if c in cls.ON_COLOR_LAND_CATALOG:
                    for name, tl, cmc in cls.ON_COLOR_LAND_CATALOG[c]:
                        if name.lower() not in current_card_names and name.lower() not in [p[0].lower() for p in lands_pool]:
                            lands_pool.append((name, tl, cmc))

            # Add Color pair duals (Shocklands, Fetchlands, Bondlands)
            if len(cmdr_ci) >= 2:
                for i in range(len(cmdr_ci)):
                    for j in range(i + 1, len(cmdr_ci)):
                        pair = (cmdr_ci[i], cmdr_ci[j])
                        pair_rev = (cmdr_ci[j], cmdr_ci[i])
                        dual_list = cls.ON_COLOR_LAND_CATALOG.get(pair) or cls.ON_COLOR_LAND_CATALOG.get(pair_rev) or []
                        for name, tl, cmc in dual_list:
                            if name.lower() not in current_card_names and name.lower() not in [p[0].lower() for p in lands_pool]:
                                lands_pool.append((name, tl, cmc))

            # Fallback basic lands if pool is small
            basic_names = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
            for c in cmdr_ci:
                b_name = basic_names.get(c, "Island")
                lands_pool.append((b_name, f"Basic Land — {b_name}", 0.0))

            num_swaps = min(deficit_count, len(candidate_spell_cuts), len(lands_pool))
            for k in range(num_swaps):
                cut_it = candidate_spell_cuts[k]
                add_land_info = lands_pool[k]

                cut_name = cut_it.effective_name
                cut_cmc = cut_it.card.cmc if cut_it.card else 5.0
                cut_type = cut_it.card.type_line if cut_it.card else "Spell"

                land_name, land_type, land_cmc = add_land_info
                recommended_lands_to_add.append(land_name)

                delta = round(land_cmc - cut_cmc, 1)
                reason = (
                    f"Corregir déficit de tierras: Retirar hechizo pesado '{cut_name}' ({cut_cmc:.0f} CMC) "
                    f"para incorporar '{land_name}' ({land_type}), garantizando curvas de maná estables y bajadas de turno 1-4."
                )

                adjustments.append(
                    LandAdjustmentSwap(
                        action="cut_spell_add_land",
                        cut_card_name=cut_name,
                        cut_card_type=cut_type,
                        cut_card_cmc=cut_cmc,
                        add_card_name=land_name,
                        add_card_type=land_type,
                        add_card_cmc=land_cmc,
                        category="Déficit de Tierras (Faltan Tierras)",
                        reason=reason,
                        cmc_impact=delta,
                    )
                )

            is_balanced = False

        # ---------------------------------------------------------------------
        # Case 2: Land Overload (Current lands > Max Target)
        # ---------------------------------------------------------------------
        elif total_lands > max_target:
            surplus_count = total_lands - recommended_target
            if total_lands >= max_target + 4:
                status = "Sobrecarga Crítica"
            else:
                status = "Sobrecarga Moderada"

            diag_msg = (
                f"🌊 **Sobrecarga de Tierras / Flood ({total_lands} actuales vs {min_target}-{max_target} recomendadas para Bracket {target_bracket.value})**: "
                f"El mazo sufre de exceso de fuentes pasivas que provocan manos muertas por robo de tierras en mid/late game. "
                f"Se recomienda retirar **-{surplus_count} tierras excedentarias o lentas** e incorporar motores de robo, rampa o interacción."
            )

            # 1. Identify Lands to CUT (Prefer taplands, guildgates, slow lands, or basic duplicates)
            candidate_land_cuts = [
                it for it in current_lands
                if it.effective_name.lower() not in untouchables
            ]

            def land_cut_priority(it: DeckItem) -> int:
                name_l = it.effective_name.lower()
                card = it.card
                oracle_l = (card.oracle_text or "").lower() if card else ""
                # Priority 1: Guildgates, Taplands, Gainlands
                if "enters the battlefield tapped" in oracle_l and "unless" not in oracle_l:
                    return 1
                if "guildgate" in name_l or "temple of" in name_l or "campus" in name_l or "tapland" in name_l:
                    return 2
                # Priority 2: High count basic lands
                if "basic land" in (card.type_line.lower() if card else "") or name_l in ("plains", "island", "swamp", "mountain", "forest"):
                    return 3
                return 4

            candidate_land_cuts.sort(key=land_cut_priority)

            # 2. Identify Spells to ADD (Ramp rocks, Card Advantage, Removal matching colors)
            spells_pool: List[Tuple[str, str, float, str]] = []

            # Always add colorless staples (Sol Ring, Arcane Signet, Fellwar Stone) if missing
            for name, tl, cmc, role in cls.SURPLUS_SPELL_REPLACEMENTS["COLORLESS"]:
                if name.lower() not in current_card_names and name.lower() not in [p[0].lower() for p in spells_pool]:
                    spells_pool.append((name, tl, cmc, role))

            # Add color-specific high synergy staples
            for c in cmdr_ci:
                if c in cls.SURPLUS_SPELL_REPLACEMENTS:
                    for name, tl, cmc, role in cls.SURPLUS_SPELL_REPLACEMENTS[c]:
                        if name.lower() not in current_card_names and name.lower() not in [p[0].lower() for p in spells_pool]:
                            spells_pool.append((name, tl, cmc, role))

            num_swaps = min(surplus_count, len(candidate_land_cuts), len(spells_pool))
            for k in range(num_swaps):
                cut_it = candidate_land_cuts[k]
                add_spell_info = spells_pool[k]

                cut_name = cut_it.effective_name
                cut_cmc = 0.0
                cut_type = cut_it.card.type_line if cut_it.card else "Land"
                recommended_lands_to_cut.append(cut_name)

                spell_name, spell_type, spell_cmc, spell_role = add_spell_info
                delta = round(spell_cmc - cut_cmc, 1)

                reason = (
                    f"Corregir sobrecarga de tierras (Flood): Retirar tierra '{cut_name}' ({cut_type}) "
                    f"para incorporar '{spell_name}' ({spell_role}, {spell_cmc:.0f} CMC), maximizando la densidad de juego y velocidad del mazo."
                )

                adjustments.append(
                    LandAdjustmentSwap(
                        action="cut_land_add_spell",
                        cut_card_name=cut_name,
                        cut_card_type=cut_type,
                        cut_card_cmc=cut_cmc,
                        add_card_name=spell_name,
                        add_card_type=spell_type,
                        add_card_cmc=spell_cmc,
                        category="Sobrecarga de Tierras (Exceso de Tierras)",
                        reason=reason,
                        cmc_impact=delta,
                    )
                )

            is_balanced = False

        # ---------------------------------------------------------------------
        # Case 3: Balanced
        # ---------------------------------------------------------------------
        else:
            status = "Equilibrado"
            diag_msg = (
                f"✅ **Base de Tierras Equilibrada ({total_lands} tierras)**: "
                f"La cantidad total de tierras está dentro del rango óptimo ({min_target}-{max_target}) para Bracket {target_bracket.value}."
            )
            is_balanced = True

        # Generate fixing upgrade recommendations (e.g. swap taplands for shocklands)
        if len(cmdr_ci) >= 2:
            fixing_suggestions.append("Sustituir tierras que entran giradas incondicionales (taplands/guildgates) por Shocklands y Fetchlands.")
            fixing_suggestions.append("Incorporar Battlebond Duals (ej. Morphic Pool, Sea of Clouds) para garantizar maná enderezado en multijugador.")
        if any(c in cmdr_ci for c in ["G", "U", "B", "W", "R"]):
            fixing_suggestions.append("Añadir Channel Lands (ej. Boseiju, Who Endures / Otawara, Soaring City) para aportar versatilidad e interactuar sin ocupar espacios de hechizos.")

        return LandBalanceReport(
            current_land_count=total_lands,
            target_land_min=min_target,
            target_land_max=max_target,
            target_land_recommended=recommended_target,
            status=status,
            deficit_or_surplus_count=(total_lands - recommended_target),
            is_balanced=is_balanced,
            diagnosis_message=diag_msg,
            adjustments=adjustments,
            recommended_lands_to_add=recommended_lands_to_add,
            recommended_lands_to_cut=recommended_lands_to_cut,
            fixing_upgrade_suggestions=fixing_suggestions,
        )
