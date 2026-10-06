"""
Card role classifier and current deck power bracket evaluator for MTG Commander.
"""

import re
from typing import List, Dict, Set, Tuple, Optional
from pydantic import BaseModel, Field

from ..models.card import Card
from ..models.deck import Deck, DeckItem
from .standards import (
    BracketTier,
    BRACKET_BENCHMARKS,
    FAST_MANA_CARDS,
    PREMIUM_TUTORS,
    FREE_OR_CHEAP_INTERACTION,
    MASS_REMOVAL,
    KNOWN_COMBO_PACKAGES,
)


class DeckClassification(BaseModel):
    lands_count: int = Field(default=0, description="Total number of land cards")
    ramp_count: int = Field(default=0, description="Total ramp spells/dorks/rocks")
    fast_mana_count: int = Field(default=0, description="Fast mana cards (Crypt, Moxen, Petal, etc.)")
    tutor_count: int = Field(default=0, description="Tutor cards")
    interaction_count: int = Field(default=0, description="Single-target removal and counterspells")
    free_or_cheap_interaction_count: int = Field(default=0, description="0-1 CMC or free high-power interaction")
    board_wipes_count: int = Field(default=0, description="Board wipes and mass removal")
    card_draw_count: int = Field(default=0, description="Card draw and card advantage engines")
    combos_detected: List[List[str]] = Field(default_factory=list, description="Known infinite/game-winning combo packages present")
    
    avg_cmc_without_lands: float = Field(default=0.0, description="Average CMC of non-land cards")
    detected_bracket_score: float = Field(default=1.0, description="Continuous estimated power score (1.0 - 4.0)")
    detected_bracket: BracketTier = Field(default=BracketTier.BRACKET_1_CASUAL, description="Discrete power bracket tier")
    diagnosis_reasons: List[str] = Field(default_factory=list, description="Key factors determining the bracket classification")


class CardRoleClassifier:
    """Classifies individual cards and complete decks into functional roles and power tiers."""

    @staticmethod
    def is_land(card: Card) -> bool:
        return "Land" in card.type_line

    @classmethod
    def is_fast_mana(cls, card: Card) -> bool:
        name = card.name.lower()
        if name in FAST_MANA_CARDS:
            return True
        # Check faces for DFCs
        if " // " in name:
            front = name.split(" // ")[0].strip()
            if front in FAST_MANA_CARDS:
                return True
        return False

    @classmethod
    def is_ramp(cls, card: Card) -> bool:
        if cls.is_fast_mana(card):
            return True

        name = card.name.lower()
        oracle = (card.oracle_text or "").lower()
        type_l = card.type_line.lower()

        # Sol Ring is ramp (and fast mana in high brackets)
        if "sol ring" in name or "arcane signet" in name or "fellwar stone" in name:
            return True

        # Talismans & Signets
        if "talisman of " in name or " signet" in name:
            return True

        # Common green land ramp
        ramp_spells = {
            "cultivate", "kodama's reach", "farseek", "nature's lore", "three visits",
            "rampant growth", "skyshroud claim", "explosive vegetation", "circuitous route",
            "sakura-tribe elder", "wood elves", "dryad of the ilysian grove"
        }
        if name in ramp_spells:
            return True

        # Mana Dorks (Creatures with CMC <= 2 that add mana)
        if "creature" in type_l and card.cmc <= 2.0:
            if re.search(r"\{t\}:\s*add\s*\{", oracle) or "add one mana" in oracle:
                return True

        # Mana Rocks (Artifacts with CMC <= 3 that add mana)
        if "artifact" in type_l and card.cmc <= 3.0:
            if re.search(r"\{t\}:\s*add\s*\{", oracle) or "add one mana" in oracle:
                return True

        # Land search ramp
        if "search your library for a" in oracle and "land" in oracle and "onto the battlefield" in oracle:
            return True

        return False

    @classmethod
    def is_tutor(cls, card: Card) -> bool:
        name = card.name.lower()
        if name in PREMIUM_TUTORS:
            return True
        oracle = (card.oracle_text or "").lower()
        if "search your library for a" in oracle:
            # Exclude simple basic land ramp
            if "basic land card" in oracle and "onto the battlefield tapped" in oracle:
                return False
            return True
        return False

    @classmethod
    def is_board_wipe(cls, card: Card) -> bool:
        name = card.name.lower()
        if name in MASS_REMOVAL:
            return True
        oracle = (card.oracle_text or "").lower()
        if "destroy all " in oracle or "exile all " in oracle or "each creature" in oracle or "all creatures get -" in oracle:
            return True
        return False

    @classmethod
    def is_interaction(cls, card: Card) -> bool:
        if cls.is_board_wipe(card):
            return False

        name = card.name.lower()
        if name in FREE_OR_CHEAP_INTERACTION:
            return True

        oracle = (card.oracle_text or "").lower()
        type_l = card.type_line.lower()

        # Counterspells
        if "counter target " in oracle:
            return True

        # Targeted removal
        if ("destroy target " in oracle or "exile target " in oracle or "return target " in oracle) and (
            "instant" in type_l or "sorcery" in type_l
        ):
            return True

        return False

    @classmethod
    def is_card_draw(cls, card: Card) -> bool:
        oracle = (card.oracle_text or "").lower()
        name = card.name.lower()
        if "rhystic study" in name or "mystic remora" in name or "sylvan library" in name or "esika's chariot" in name:
            return True
        if "draw a card" in oracle or "draw two cards" in oracle or "draw three cards" in oracle or "draws a card" in oracle or "draw cards equal" in oracle:
            return True
        return False

    @classmethod
    def detect_combos(cls, active_items: List[DeckItem]) -> List[List[str]]:
        """Scans deck card list for known compact game-winning combos."""
        deck_card_names = {item.effective_name.lower() for item in active_items}
        combos_found: List[List[str]] = []

        for combo_set in KNOWN_COMBO_PACKAGES:
            if combo_set.issubset(deck_card_names):
                combos_found.append(sorted(list(combo_set)))

        return combos_found

    @classmethod
    def classify_deck(cls, deck: Deck) -> DeckClassification:
        """Analyzes a full Deck and returns detailed role counts and Power Bracket evaluation."""
        active_items = deck.commanders + deck.maindeck
        non_land_cmcs: List[float] = []

        lands_count = 0
        ramp_count = 0
        fast_mana_count = 0
        tutor_count = 0
        interaction_count = 0
        free_interaction_count = 0
        board_wipes_count = 0
        card_draw_count = 0

        for item in active_items:
            qty = item.quantity
            card = item.card
            if not card:
                continue

            name_lower = card.name.lower()

            if cls.is_land(card):
                lands_count += qty
            else:
                non_land_cmcs.extend([card.cmc] * qty)

            if cls.is_fast_mana(card):
                fast_mana_count += qty

            if cls.is_ramp(card):
                ramp_count += qty

            if cls.is_tutor(card):
                tutor_count += qty

            if cls.is_board_wipe(card):
                board_wipes_count += qty
            elif cls.is_interaction(card):
                interaction_count += qty

            if name_lower in FREE_OR_CHEAP_INTERACTION:
                free_interaction_count += qty

            if cls.is_card_draw(card):
                card_draw_count += qty

        avg_cmc_nl = sum(non_land_cmcs) / len(non_land_cmcs) if non_land_cmcs else 3.5
        combos = cls.detect_combos(active_items)

        # Compute Continuous Power Score (1.0 to 4.0)
        score = 1.0
        reasons: List[str] = []

        # 1. Base score from Mana Curve (lower CMC = higher score)
        if avg_cmc_nl <= 1.8:
            score += 1.8
            reasons.append(f"Curva de maná ultra-eficiente (Avg CMC {avg_cmc_nl:.2f})")
        elif avg_cmc_nl <= 2.4:
            score += 1.2
            reasons.append(f"Curva de maná baja y optimizada (Avg CMC {avg_cmc_nl:.2f})")
        elif avg_cmc_nl <= 3.0:
            score += 0.7
            reasons.append(f"Curva de maná equilibrada (Avg CMC {avg_cmc_nl:.2f})")
        else:
            reasons.append(f"Curva de maná alta típica de juego casual (Avg CMC {avg_cmc_nl:.2f})")

        # 2. Fast mana contribution
        if fast_mana_count >= 4:
            score += 0.8
            reasons.append(f"Alta presencia de Fast Mana ({fast_mana_count} piezas)")
        elif fast_mana_count >= 1:
            score += 0.4
            reasons.append(f"Presencia moderada de Fast Mana ({fast_mana_count} piezas)")

        # 3. Tutor density contribution
        if tutor_count >= 6:
            score += 0.7
            reasons.append(f"Alta densidad de tutores ({tutor_count} tutores)")
        elif tutor_count >= 3:
            score += 0.4
            reasons.append(f"Tutores clave incluidos ({tutor_count} tutores)")

        # 4. Combos detection
        if combos:
            score += 0.8
            combo_names = [" + ".join(c) for c in combos]
            reasons.append(f"Combos infinitos/compactos detectados: {', '.join(combo_names)}")

        # 5. Free / Cheap interaction
        if free_interaction_count >= 5:
            score += 0.5
            reasons.append(f"Fuerte suite de interacción gratuita/eficiente ({free_interaction_count} cartas)")

        # Clamp score between 1.0 and 4.0
        score = max(1.0, min(4.0, round(score, 2)))

        # Determine discrete bracket tier
        if score >= 3.4 or (combos and fast_mana_count >= 3 and avg_cmc_nl < 2.2):
            tier = BracketTier.BRACKET_4_CEDH
        elif score >= 2.5:
            tier = BracketTier.BRACKET_3_HIGH_POWER
        elif score >= 1.6:
            tier = BracketTier.BRACKET_2_MID_POWER
        else:
            tier = BracketTier.BRACKET_1_CASUAL

        return DeckClassification(
            lands_count=lands_count,
            ramp_count=ramp_count,
            fast_mana_count=fast_mana_count,
            tutor_count=tutor_count,
            interaction_count=interaction_count,
            free_or_cheap_interaction_count=free_interaction_count,
            board_wipes_count=board_wipes_count,
            card_draw_count=card_draw_count,
            combos_detected=combos,
            avg_cmc_without_lands=round(avg_cmc_nl, 2),
            detected_bracket_score=score,
            detected_bracket=tier,
            diagnosis_reasons=reasons,
        )
