"""
Rigorous Color Identity Extraction and Hybrid Mana Rule Enforcement for MTG Commander.
"""

import re
from typing import List, Set, Tuple, Optional, Dict, Any
from ..models.card import Card, CardFace

WUBRG_ORDER = ["W", "U", "B", "R", "G"]

# Regex to match mana symbols like {W}, {U}, {B}, {R}, {G}, {W/U}, {B/R}, {2/W}, {G/P}, {W/U/P}, {C}
MANA_SYMBOL_REGEX = re.compile(r"\{([0-9A-Z/]+)\}", re.IGNORECASE)

# Regex to identify reminder text inside parentheses (e.g. "(Extort {W/B})")
REMINDER_TEXT_REGEX = re.compile(r"\([^)]*\)")


class ColorIdentityExtractor:
    """
    Computes exact Color Identity (CR 903.4) by inspecting mana costs,
    rules text (excluding reminder text), color indicators, and DFC back faces.
    """

    @classmethod
    def extract_colors_from_symbol_string(cls, text: str) -> Set[str]:
        """Extracts all WUBRG color characters present in mana symbol brackets."""
        colors: Set[str] = set()
        for match in MANA_SYMBOL_REGEX.finditer(text):
            inner = match.group(1).upper()
            # Split hybrid/split symbols like "W/U", "2/B", "G/P"
            parts = inner.split("/")
            for p in parts:
                if p in ("W", "U", "B", "R", "G"):
                    colors.add(p)
        return colors

    @classmethod
    def clean_oracle_text(cls, oracle_text: Optional[str]) -> str:
        """Removes reminder text in parentheses so Extort and other reminder text doesn't taint color identity."""
        if not oracle_text:
            return ""
        return REMINDER_TEXT_REGEX.sub("", oracle_text)

    @classmethod
    def compute_card_color_identity(cls, card: Card) -> List[str]:
        """
        Computes the complete, verified Color Identity for a card.
        Combines casting cost, cleaned oracle rules text, color indicator, and all card faces.
        """
        # If card already has Scryfall's official color_identity, start with it
        colors: Set[str] = set(c.upper() for c in (card.color_identity or []))

        # Check front face mana cost & rules text
        if card.mana_cost:
            colors.update(cls.extract_colors_from_symbol_string(card.mana_cost))

        cleaned_oracle = cls.clean_oracle_text(card.oracle_text)
        if cleaned_oracle:
            colors.update(cls.extract_colors_from_symbol_string(cleaned_oracle))

        # Check multi-faced cards (DFCs, MDFCs, Transforms)
        if card.card_faces:
            for face in card.card_faces:
                if face.mana_cost:
                    colors.update(cls.extract_colors_from_symbol_string(face.mana_cost))
                face_oracle = cls.clean_oracle_text(face.oracle_text)
                if face_oracle:
                    colors.update(cls.extract_colors_from_symbol_string(face_oracle))
                if face.colors:
                    colors.update(c.upper() for c in face.colors if c in ("W", "U", "B", "R", "G"))

        return [c for c in WUBRG_ORDER if c in colors]

    @classmethod
    def compute_commander_color_identity(cls, commander_cards: List[Card]) -> List[str]:
        """Calculates the aggregate Color Identity of the Commander(s) (including Partners)."""
        combined_colors: Set[str] = set()
        for cmdr in commander_cards:
            ci = cls.compute_card_color_identity(cmdr)
            combined_colors.update(ci)
        return [c for c in WUBRG_ORDER if c in combined_colors]

    @classmethod
    def validate_color_identity(
        cls,
        card: Card,
        commander_identity: List[str],
    ) -> Tuple[bool, Optional[str]]:
        """
        Strictly verifies that a card's color identity is a subset of the Commander's color identity.
        Applies strict Hybrid Mana rules.

        Returns: (is_legal, error_message_if_illegal)
        """
        card_ci = set(cls.compute_card_color_identity(card))
        cmdr_ci = set(c.upper() for c in commander_identity)

        # Check if card has colors not in commander identity
        forbidden_colors = card_ci - cmdr_ci
        if forbidden_colors:
            forbidden_list = [c for c in WUBRG_ORDER if c in forbidden_colors]
            cmdr_list = [c for c in WUBRG_ORDER if c in cmdr_ci] or ["Colorless"]
            return False, (
                f"La carta '{card.name}' contiene símbolos de color {forbidden_list} "
                f"fuera de la identidad del comandante {cmdr_list} (Regla estricta de maná híbrido/identidad)."
            )

        return True, None
