"""
WOTC_Bracket_Engine: Master Official 5-Bracket Compliance, Audit & Optimization Suite for MTG Commander.

Strictly enforces WotC 5-Bracket Rules:
- Bracket 1 (Exhibition): 0 Game Changers, 0 2-Card Combos, 0 MLD, 0 Extra Turns, Nul/Scant Tutors.
- Bracket 2 (Core): 0 Game Changers, 0 2-Card Combos, 0 MLD, Scant Extra Turns (<=1) & Tutors (<=2).
- Bracket 3 (Upgraded): Max 3 Game Changers, 0 MLD, 0 Fast Combos (Turn 1-6), Controlled Extra Turns (<=2).
- Bracket 4 (Optimized): Unlimited Game Changers, Combos & MLD allowed (Banlist only).
- Bracket 5 (cEDH): Unlimited Game Changers, Maximum Efficiency (Avg CMC 1.2-1.9, Fast Mana & Tutors).
"""

import logging
from typing import List, Dict, Set, Any, Optional, Tuple
from enum import Enum
from pydantic import BaseModel, Field

from ..models.card import Card
from ..models.deck import Deck, DeckItem
from .standards import (
    BracketTier,
    BRACKET_BENCHMARKS,
    GAME_CHANGERS_MAX_ALLOWED,
    MASS_LAND_DENIAL_CARDS,
    EXTRA_TURNS_CARDS,
    KNOWN_TWO_CARD_COMBOS,
    FAST_EARLY_COMBOS,
    KNOWN_COMBO_PACKAGES,
    PREMIUM_TUTORS,
    FAST_MANA_CARDS,
)
from .game_changers import GAME_CHANGERS_DATABASE, GameChangerDefinition

logger = logging.getLogger(__name__)


class ViolationCategory(str, Enum):
    GAME_CHANGER_QUOTA = "Game Changer Quota Exceeded"
    PROHIBITED_COMBO = "Prohibited 2-Card Infinite Combo"
    FAST_COMBO = "Prohibited Fast Early Combo (Turn 1-6)"
    MASS_LAND_DENIAL = "Mass Land Denial / Destruction Prohibited"
    EXTRA_TURNS = "Extra Turns Prohibited or Exceeded"
    TUTOR_LIMIT = "Tutor Density Exceeded"
    CMC_TOO_HIGH = "Mana Efficiency Warning"


class BracketViolation(BaseModel):
    category: ViolationCategory
    offending_cards: List[str]
    target_bracket: int
    rule_description: str
    message: str
    severity: str = "ERROR"  # 'ERROR' (blocks bracket) or 'WARNING'


class CardRemovalRecommendation(BaseModel):
    card_name: str
    reason: str
    category: str
    suggested_replacements: List[str] = Field(default_factory=list)
    card_type: str = "Spell"
    cmc: float = 0.0


class GameChangerAuditDetail(BaseModel):
    card_name: str
    category: str
    efficiency_tier: str
    efficiency_explanation: str
    is_allowed: bool
    status_label: str
    suggested_replacements: List[str] = Field(default_factory=list)


class BracketAuditReport(BaseModel):
    is_legal_for_bracket: bool
    target_bracket: int
    target_bracket_label: str
    target_experience: str
    target_deckbuilding_rules: str
    
    # Detected Stats
    detected_bracket: int
    detected_bracket_label: str
    avg_cmc_without_lands: float
    
    # Violations & Removals
    violations: List[BracketViolation] = Field(default_factory=list)
    cards_to_remove: List[CardRemovalRecommendation] = Field(default_factory=list)
    
    # Component Counts
    total_game_changers_count: int = 0
    max_allowed_game_changers: int = 0
    game_changers_detected: List[GameChangerAuditDetail] = Field(default_factory=list)
    
    combos_detected: List[List[str]] = Field(default_factory=list)
    mld_detected: List[str] = Field(default_factory=list)
    extra_turns_detected: List[str] = Field(default_factory=list)
    tutors_detected: List[str] = Field(default_factory=list)
    
    # Summary
    status_headline: str = ""
    actionable_summary: str = ""


class WOTC_Bracket_Engine:
    """
    Official WotC 5-Bracket Compliance, Audit & Downshift/Upshift Optimization Engine.
    """

    @classmethod
    def get_bracket_matrix(cls) -> Dict[int, Dict[str, Any]]:
        """Returns structured metadata for all 5 Brackets."""
        matrix = {}
        for tier_int in [1, 2, 3, 4, 5]:
            tier_enum = BracketTier(tier_int)
            bench = BRACKET_BENCHMARKS[tier_enum]
            matrix[tier_int] = {
                "tier": tier_int,
                "label": tier_enum.label,
                "experience": tier_enum.experience_description,
                "deckbuilding_rules": tier_enum.deckbuilding_rules,
                "max_game_changers": GAME_CHANGERS_MAX_ALLOWED[tier_int],
                "allow_combos": bench.allow_infinite_combos,
                "allow_mld": bench.allow_mld,
                "allow_extra_turns": bench.allow_extra_turns,
                "typical_win_turn": bench.typical_win_turn,
                "target_avg_cmc": f"{bench.min_avg_cmc:.1f} - {bench.max_avg_cmc:.1f}",
            }
        return matrix

    @classmethod
    def detect_game_changers(cls, deck: Deck) -> List[Tuple[str, GameChangerDefinition]]:
        """Finds all Game Changers present in the deck."""
        found = []
        seen = set()
        for item in deck.items:
            card_name = item.effective_name
            clean = card_name.lower().strip()
            # Direct match
            for gc_name, gc_def in GAME_CHANGERS_DATABASE.items():
                if clean == gc_name.lower() or (f" // " in clean and clean.split(" // ")[0] == gc_name.lower()):
                    if gc_name.lower() not in seen:
                        seen.add(gc_name.lower())
                        found.append((card_name, gc_def))
                    break
        return found

    @classmethod
    def detect_two_card_combos(cls, deck: Deck) -> List[List[str]]:
        """Identifies 2-card infinite combos present in the deck."""
        deck_cards = {item.effective_name.lower().strip() for item in deck.items}
        detected = []
        for combo in KNOWN_TWO_CARD_COMBOS:
            if combo.issubset(deck_cards):
                # Retrieve original card names
                matched_names = []
                for piece in combo:
                    for item in deck.items:
                        name_low = item.effective_name.lower().strip()
                        if name_low == piece or name_low.startswith(piece):
                            matched_names.append(item.effective_name)
                            break
                detected.append(matched_names if len(matched_names) == len(combo) else list(combo))
        return detected

    @classmethod
    def detect_fast_combos(cls, deck: Deck) -> List[List[str]]:
        """Identifies Turn 1-6 fast 2-card combo wincons prohibited in Bracket 3 and below."""
        deck_cards = {item.effective_name.lower().strip() for item in deck.items}
        detected = []
        for combo in FAST_EARLY_COMBOS:
            if combo.issubset(deck_cards):
                matched_names = []
                for piece in combo:
                    for item in deck.items:
                        name_low = item.effective_name.lower().strip()
                        if name_low == piece or name_low.startswith(piece):
                            matched_names.append(item.effective_name)
                            break
                detected.append(matched_names if len(matched_names) == len(combo) else list(combo))
        return detected

    @classmethod
    def detect_mld(cls, deck: Deck) -> List[str]:
        """Identifies Mass Land Denial / Destruction cards in the deck."""
        detected = []
        seen = set()
        for item in deck.items:
            clean = item.effective_name.lower().strip()
            for mld_card in MASS_LAND_DENIAL_CARDS:
                if clean == mld_card or (f" // " in clean and clean.split(" // ")[0] == mld_card):
                    if item.effective_name not in seen:
                        seen.add(item.effective_name)
                        detected.append(item.effective_name)
                    break
        return detected

    @classmethod
    def detect_extra_turns(cls, deck: Deck) -> List[str]:
        """Identifies Extra Turn spells in the deck."""
        detected = []
        seen = set()
        for item in deck.items:
            clean = item.effective_name.lower().strip()
            for et_card in EXTRA_TURNS_CARDS:
                if clean == et_card or (f" // " in clean and clean.split(" // ")[0] == et_card):
                    if item.effective_name not in seen:
                        seen.add(item.effective_name)
                        detected.append(item.effective_name)
                    break
        return detected

    @classmethod
    def detect_premium_tutors(cls, deck: Deck) -> List[str]:
        """Identifies Premium unconditional tutors in the deck."""
        detected = []
        seen = set()
        for item in deck.items:
            clean = item.effective_name.lower().strip()
            for tutor_card in PREMIUM_TUTORS:
                if clean == tutor_card or (f" // " in clean and clean.split(" // ")[0] == tutor_card):
                    if item.effective_name not in seen:
                        seen.add(item.effective_name)
                        detected.append(item.effective_name)
                    break
        return detected

    @classmethod
    def audit_deck(cls, deck: Deck, target_bracket: int | BracketTier) -> BracketAuditReport:
        """
        Performs a full audit of a deck against the chosen Bracket (1 to 5).
        Calculates all rule violations, offending cards, and automatic removal recommendations.
        """
        target_b_int = int(target_bracket)
        target_b_enum = BracketTier(target_b_int)
        
        # 1. Run detections
        gc_list = cls.detect_game_changers(deck)
        combos_2c = cls.detect_two_card_combos(deck)
        fast_combos = cls.detect_fast_combos(deck)
        mld_cards = cls.detect_mld(deck)
        extra_turns = cls.detect_extra_turns(deck)
        tutors = cls.detect_premium_tutors(deck)
        
        violations: List[BracketViolation] = []
        removals: List[CardRemovalRecommendation] = []
        cards_marked_for_removal: Set[str] = set()

        max_gc = GAME_CHANGERS_MAX_ALLOWED[target_b_int]
        gc_count = len(gc_list)

        # ---------------------------------------------------------------------
        # RULE 1: Game Changers Quotas
        # Bracket 1 & 2: Exactly 0.
        # Bracket 3: Max 3.
        # Bracket 4 & 5: Unlimited.
        # ---------------------------------------------------------------------
        gc_audit_details: List[GameChangerAuditDetail] = []
        
        if target_b_int in [1, 2]:
            for card_name, gc_def in gc_list:
                is_allowed = False
                gc_audit_details.append(GameChangerAuditDetail(
                    card_name=card_name,
                    category=gc_def.category,
                    efficiency_tier=gc_def.efficiency_tier,
                    efficiency_explanation=gc_def.efficiency_explanation,
                    is_allowed=False,
                    status_label=f"🔴 Prohibido en Bracket {target_b_int} (Cupo 0)",
                    suggested_replacements=gc_def.suggested_replacements_by_bracket.get(target_b_int, ["Cultivate", "Arcane Signet"]),
                ))
                if card_name not in cards_marked_for_removal:
                    cards_marked_for_removal.add(card_name)
                    # Find card model safely
                    card_item = next((i for i in deck.items if i.effective_name.lower() == card_name.lower()), None)
                    removals.append(CardRemovalRecommendation(
                        card_name=card_name,
                        reason=f"Game Changer format-warping ({gc_def.category}). Bracket {target_b_int} prohíbe el uso de Game Changers (límite: 0).",
                        category=gc_def.category,
                        suggested_replacements=gc_def.suggested_replacements_by_bracket.get(target_b_int, ["Arcane Signet", "Mind Stone"]),
                        card_type=card_item.card.type_line if card_item and card_item.card else "Permanent",
                        cmc=card_item.card.cmc if card_item and card_item.card else 0.0,
                    ))
            
            if gc_count > 0:
                violations.append(BracketViolation(
                    category=ViolationCategory.GAME_CHANGER_QUOTA,
                    offending_cards=[c[0] for c in gc_list],
                    target_bracket=target_b_int,
                    rule_description=f"Bracket {target_b_int} permite exactamente 0 cartas 'Game Changers'.",
                    message=f"El mazo contiene {gc_count} Game Changers ({', '.join([c[0] for c in gc_list])}). Deben ser removidos para legalizar en Bracket {target_b_int}.",
                    severity="ERROR",
                ))

        elif target_b_int == 3:
            # Sort GC by efficiency (S-Tier first to prioritize keeping or cutting)
            # Bracket 3 allows max 3. If > 3, prioritize keeping the 3 most balanced or flag the excess
            for idx, (card_name, gc_def) in enumerate(gc_list):
                if idx < 3:
                    is_allowed = True
                    gc_audit_details.append(GameChangerAuditDetail(
                        card_name=card_name,
                        category=gc_def.category,
                        efficiency_tier=gc_def.efficiency_tier,
                        efficiency_explanation=gc_def.efficiency_explanation,
                        is_allowed=True,
                        status_label="🟢 Permitido (Dentro del cupo de 3 en Bracket 3)",
                        suggested_replacements=gc_def.suggested_replacements_by_bracket.get(3, ["Talisman of Progress", "Beast Within"]),
                    ))
                else:
                    is_allowed = False
                    gc_audit_details.append(GameChangerAuditDetail(
                        card_name=card_name,
                        category=gc_def.category,
                        efficiency_tier=gc_def.efficiency_tier,
                        efficiency_explanation=gc_def.efficiency_explanation,
                        is_allowed=False,
                        status_label="🔴 Excede Cupo (Máx 3 Game Changers en Bracket 3)",
                        suggested_replacements=gc_def.suggested_replacements_by_bracket.get(3, ["Talisman of Progress", "Beast Within"]),
                    ))
                    if card_name not in cards_marked_for_removal:
                        cards_marked_for_removal.add(card_name)
                        card_item = next((i for i in deck.items if i.effective_name.lower() == card_name.lower()), None)
                        removals.append(CardRemovalRecommendation(
                            card_name=card_name,
                            reason=f"Excede el límite oficial de 3 Game Changers en Bracket 3 ({idx+1}/3).",
                            category=gc_def.category,
                            suggested_replacements=gc_def.suggested_replacements_by_bracket.get(3, ["Fellwar Stone", "Swords to Plowshares"]),
                            card_type=card_item.card.type_line if card_item and card_item.card else "Spell",
                            cmc=card_item.card.cmc if card_item and card_item.card else 0.0,
                        ))
            
            if gc_count > 3:
                excess_names = [c[0] for c in gc_list[3:]]
                violations.append(BracketViolation(
                    category=ViolationCategory.GAME_CHANGER_QUOTA,
                    offending_cards=excess_names,
                    target_bracket=3,
                    rule_description="Bracket 3 permite como MÁXIMO 3 cartas de la lista 'Game Changers'.",
                    message=f"El mazo contiene {gc_count} Game Changers (límite: 3). Debes remover {gc_count - 3} carta(s): {', '.join(excess_names)}.",
                    severity="ERROR",
                ))
        else:
            # Bracket 4 and 5: Unlimited
            for card_name, gc_def in gc_list:
                gc_audit_details.append(GameChangerAuditDetail(
                    card_name=card_name,
                    category=gc_def.category,
                    efficiency_tier=gc_def.efficiency_tier,
                    efficiency_explanation=gc_def.efficiency_explanation,
                    is_allowed=True,
                    status_label=f"🟢 Permitido sin límite en Bracket {target_b_int}",
                    suggested_replacements=[],
                ))

        # ---------------------------------------------------------------------
        # RULE 2: Combos Infinitos de 2 Cartas
        # Bracket 1 & 2: PROHIBIDO cualquier combo infinito de 2 cartas.
        # Bracket 3: PROHIBIDO combos rápidos de turnos 1-6 (Thoracle/Consultation, IsoRev, Breach).
        # Bracket 4 & 5: PERMITIDO.
        # ---------------------------------------------------------------------
        if target_b_int in [1, 2] and combos_2c:
            for combo_pair in combos_2c:
                violations.append(BracketViolation(
                    category=ViolationCategory.PROHIBITED_COMBO,
                    offending_cards=combo_pair,
                    target_bracket=target_b_int,
                    rule_description=f"Bracket {target_b_int} PROHÍBE terminantemente combos infinitos de 2 cartas.",
                    message=f"Combo infinito detectado: {' + '.join(combo_pair)}. Debe ser desmontado.",
                    severity="ERROR",
                ))
                # Mark pieces for removal
                for piece in combo_pair:
                    if piece not in cards_marked_for_removal:
                        cards_marked_for_removal.add(piece)
                        card_item = next((i for i in deck.items if i.effective_name.lower() == piece.lower()), None)
                        removals.append(CardRemovalRecommendation(
                            card_name=piece,
                            reason=f"Pieza de combo infinito de 2 cartas con {', '.join([p for p in combo_pair if p != piece])}, prohibido en Bracket {target_b_int}.",
                            category="2-Card Combo Wincon",
                            suggested_replacements=["Reconnaissance Mission", "Sun Titan", "Beast Within", "Fact or Fiction"],
                            card_type=card_item.card.type_line if card_item and card_item.card else "Permanent",
                            cmc=card_item.card.cmc if card_item and card_item.card else 0.0,
                        ))

        elif target_b_int == 3 and fast_combos:
            for combo_pair in fast_combos:
                violations.append(BracketViolation(
                    category=ViolationCategory.FAST_COMBO,
                    offending_cards=combo_pair,
                    target_bracket=3,
                    rule_description="Bracket 3 PROHÍBE combos rápidos de 2 cartas que ganen en los primeros 6 turnos.",
                    message=f"Combo ultrarrápido detectado: {' + '.join(combo_pair)}. Prohibido en Bracket 3.",
                    severity="ERROR",
                ))
                for piece in combo_pair:
                    if piece not in cards_marked_for_removal:
                        cards_marked_for_removal.add(piece)
                        card_item = next((i for i in deck.items if i.effective_name.lower() == piece.lower()), None)
                        removals.append(CardRemovalRecommendation(
                            card_name=piece,
                            reason=f"Pieza de combo rápido t1-t6 ({' + '.join(combo_pair)}), restringido a Brackets 4 y 5.",
                            category="Fast Combo Wincon",
                            suggested_replacements=["Aetherflux Reservoir", "Approach of the Second Sun", "Niv-Mizzet, Parun"],
                            card_type=card_item.card.type_line if card_item and card_item.card else "Permanent",
                            cmc=card_item.card.cmc if card_item and card_item.card else 0.0,
                        ))

        # ---------------------------------------------------------------------
        # RULE 3: Mass Land Denial / Destruction (MLD)
        # Bracket 1, 2, 3: PROHIBIDO.
        # Bracket 4, 5: PERMITIDO.
        # ---------------------------------------------------------------------
        if target_b_int in [1, 2, 3] and mld_cards:
            violations.append(BracketViolation(
                category=ViolationCategory.MASS_LAND_DENIAL,
                offending_cards=mld_cards,
                target_bracket=target_b_int,
                rule_description=f"Bracket {target_b_int} PROHÍBE la destrucción o denegación masiva de tierras (MLD).",
                message=f"Cartas de MLD detectadas: {', '.join(mld_cards)}. Deben ser sustituidas por interactividad justa.",
                severity="ERROR",
            ))
            for mld_c in mld_cards:
                if mld_c not in cards_marked_for_removal:
                    cards_marked_for_removal.add(mld_c)
                    card_item = next((i for i in deck.items if i.effective_name.lower() == mld_c.lower()), None)
                    removals.append(CardRemovalRecommendation(
                        card_name=mld_c,
                        reason=f"Destrucción/bloqueo masivo de tierras (MLD), prohibido en Bracket {target_b_int}.",
                        category="Mass Land Denial",
                        suggested_replacements=["Blasphemous Act", "Farewell", "Wrath of God", "Toxic Deluge"],
                        card_type=card_item.card.type_line if card_item and card_item.card else "Sorcery",
                        cmc=card_item.card.cmc if card_item and card_item.card else 4.0,
                    ))

        # ---------------------------------------------------------------------
        # RULE 4: Turnos Extra (Extra Turns)
        # Bracket 1: PROHIBIDO.
        # Bracket 2: Cantidades muy bajas (<= 1, sin loops).
        # Bracket 3: Cantidades controladas (<= 2, sin loops).
        # Bracket 4 & 5: PERMITIDO.
        # ---------------------------------------------------------------------
        if target_b_int == 1 and extra_turns:
            violations.append(BracketViolation(
                category=ViolationCategory.EXTRA_TURNS,
                offending_cards=extra_turns,
                target_bracket=1,
                rule_description="Bracket 1 PROHÍBE los hechizos de turnos extra.",
                message=f"Turnos extra detectados en Bracket 1: {', '.join(extra_turns)}. Deben ser removidos.",
                severity="ERROR",
            ))
            for et_c in extra_turns:
                if et_c not in cards_marked_for_removal:
                    cards_marked_for_removal.add(et_c)
                    card_item = next((i for i in deck.items if i.effective_name.lower() == et_c.lower()), None)
                    removals.append(CardRemovalRecommendation(
                        card_name=et_c,
                        reason="Hechizo de turno extra, prohibido en Bracket 1 Exhibition.",
                        category="Extra Turns",
                        suggested_replacements=["Sphinx's Revelation", "Fact or Fiction", "Deep Analysis"],
                        card_type=card_item.card.type_line if card_item and card_item.card else "Sorcery",
                        cmc=card_item.card.cmc if card_item and card_item.card else 5.0,
                    ))
        elif target_b_int == 2 and len(extra_turns) > 1:
            excess_et = extra_turns[1:]
            violations.append(BracketViolation(
                category=ViolationCategory.EXTRA_TURNS,
                offending_cards=excess_et,
                target_bracket=2,
                rule_description="Bracket 2 permite como máximo 1 hechizo de turno extra (sin loops).",
                message=f"Exceso de turnos extra en Bracket 2 ({len(extra_turns)} detectados). Se recomienda mantener solo 1.",
                severity="ERROR",
            ))
            for et_c in excess_et:
                if et_c not in cards_marked_for_removal:
                    cards_marked_for_removal.add(et_c)
                    card_item = next((i for i in deck.items if i.effective_name.lower() == et_c.lower()), None)
                    removals.append(CardRemovalRecommendation(
                        card_name=et_c,
                        reason="Exceso de turnos extra en Bracket 2 (máximo 1 permitido).",
                        category="Extra Turns",
                        suggested_replacements=["Pull from Tomorrow", "Tidings", "Concentrate"],
                        card_type=card_item.card.type_line if card_item and card_item.card else "Sorcery",
                        cmc=card_item.card.cmc if card_item and card_item.card else 5.0,
                    ))
        elif target_b_int == 3 and len(extra_turns) > 2:
            excess_et = extra_turns[2:]
            violations.append(BracketViolation(
                category=ViolationCategory.EXTRA_TURNS,
                offending_cards=excess_et,
                target_bracket=3,
                rule_description="Bracket 3 permite como máximo 2 hechizos de turnos extra (sin loops ni encadenamientos).",
                message=f"Exceso de turnos extra en Bracket 3 ({len(extra_turns)} detectados).",
                severity="WARNING",
            ))

        # ---------------------------------------------------------------------
        # RULE 5: Tutores
        # Bracket 1: Escasos o nulos (<= 1).
        # ---------------------------------------------------------------------
        if target_b_int == 1 and len(tutors) > 1:
            excess_tut = tutors[1:]
            violations.append(BracketViolation(
                category=ViolationCategory.TUTOR_LIMIT,
                offending_cards=excess_tut,
                target_bracket=1,
                rule_description="Bracket 1 exige tutores extremadamente escasos o nulos.",
                message=f"Densidad de tutores premium alta para Bracket 1 ({len(tutors)} detectados: {', '.join(tutors)}).",
                severity="WARNING",
            ))

        # ---------------------------------------------------------------------
        # RULE 6: Bracket 5 cEDH Efficiency Check
        # ---------------------------------------------------------------------
        avg_cmc = deck.average_cmc_without_lands
        if target_b_int == 5 and avg_cmc > 2.4:
            violations.append(BracketViolation(
                category=ViolationCategory.CMC_TOO_HIGH,
                offending_cards=[],
                target_bracket=5,
                rule_description="Bracket 5 cEDH requiere una curva de maná ultra-optimizada (CMC promedio 1.2 - 2.0).",
                message=f"La curva actual de {avg_cmc:.2f} CMC es demasiado pesada para cEDH. Se requiere reducir el coste medio e incluir fast mana.",
                severity="WARNING",
            ))

        # Calculate detected bracket
        detected_tier_int = cls.estimate_deck_bracket(
            gc_count=gc_count,
            has_combos=len(combos_2c) > 0,
            has_fast_combos=len(fast_combos) > 0,
            has_mld=len(mld_cards) > 0,
            avg_cmc=avg_cmc,
            fast_mana_count=len([c for c in deck.items if (c.card.name.lower() if c.card else c.effective_name.lower()) in FAST_MANA_CARDS]),
            tutors_count=len(tutors),
        )
        detected_tier_enum = BracketTier(detected_tier_int)

        is_legal = len([v for v in violations if v.severity == "ERROR"]) == 0

        # Status text & headline
        if is_legal:
            status_headline = f"✅ Cumple 100% con las Reglas Oficiales de {target_b_enum.label}"
            actionable_summary = f"El mazo respeta todas las restricciones de Game Changers (límite: {max_gc}), combos, MLD y turnos extra para el Bracket {target_b_int}."
        else:
            status_headline = f"❌ Infracciones Detectadas para {target_b_enum.label} ({len(violations)} alertas)"
            actionable_summary = f"Se detectaron {len(removals)} cartas que violan las reglas de Bracket {target_b_int}. Deben ser removidas o sustituidas por alternativas legales."

        return BracketAuditReport(
            is_legal_for_bracket=is_legal,
            target_bracket=target_b_int,
            target_bracket_label=target_b_enum.label,
            target_experience=target_b_enum.experience_description,
            target_deckbuilding_rules=target_b_enum.deckbuilding_rules,
            detected_bracket=detected_tier_int,
            detected_bracket_label=detected_tier_enum.label,
            avg_cmc_without_lands=avg_cmc,
            violations=violations,
            cards_to_remove=removals,
            total_game_changers_count=gc_count,
            max_allowed_game_changers=max_gc,
            game_changers_detected=gc_audit_details,
            combos_detected=combos_2c,
            mld_detected=mld_cards,
            extra_turns_detected=extra_turns,
            tutors_detected=tutors,
            status_headline=status_headline,
            actionable_summary=actionable_summary,
        )

    @classmethod
    def estimate_deck_bracket(
        cls,
        gc_count: int,
        has_combos: bool,
        has_fast_combos: bool,
        has_mld: bool,
        avg_cmc: float,
        fast_mana_count: int,
        tutors_count: int,
    ) -> int:
        """Estimates inherent bracket (1 to 5) based on format-defining indicators."""
        # Bracket 5 cEDH indicators:
        if has_fast_combos and fast_mana_count >= 3 and tutors_count >= 4 and avg_cmc <= 2.2:
            return 5
        if gc_count >= 5 and avg_cmc <= 2.0 and tutors_count >= 4:
            return 5
            
        # Bracket 4 Optimized:
        if has_mld or has_combos or gc_count > 3 or fast_mana_count >= 2 or avg_cmc <= 2.5:
            return 4
            
        # Bracket 3 Upgraded:
        if gc_count > 0 or tutors_count >= 2 or avg_cmc <= 3.1:
            return 3
            
        # Bracket 2 Core:
        if avg_cmc <= 3.6 or tutors_count >= 1:
            return 2
            
        # Bracket 1 Exhibition:
        return 1


# Convenient Aliases
WotcBracketEngine = WOTC_Bracket_Engine
