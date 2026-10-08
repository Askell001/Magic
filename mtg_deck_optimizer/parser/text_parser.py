"""
Universal plain-text MTG deck parser for Moxfield, Archidekt, DeckStats, TCGplayer, MTGA, and MTGO.
"""

import re
from typing import List, Tuple, Optional, Dict, Any

from ..models.deck import Deck, DeckItem, DeckSection
from .patterns import (
    identify_section_header,
    LINE_CARD_REGEX,
    SET_COLLECTOR_REGEX,
    COMMANDER_TAG_REGEX,
    COMPANION_TAG_REGEX,
    FOIL_REGEX,
    ETCHED_REGEX,
    MOXFIELD_TAG_REGEX,
    TAG_REGEX,
)


class MTGDeckTextParser:
    """
    Parses unformatted or structured text lists from Moxfield, Archidekt, DeckStats,
    TCGplayer, MTG Arena, and Magic Online into a structured Deck model.
    """

    @classmethod
    def parse(cls, raw_text: str, deck_name: str = "Imported Deck", default_format: str = "commander") -> Deck:
        deck = Deck(name=deck_name, format=default_format)
        current_section = DeckSection.MAINDECK

        lines = raw_text.splitlines()

        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            # Check if this line is a section header (e.g., "// Commander", "Mainboard:", "Sideboard:", "Deck")
            detected_section = identify_section_header(trimmed)
            if detected_section is not None:
                current_section = detected_section
                continue

            # Skip comments that are not card lines (e.g. "// Just some notes", "---")
            if (trimmed.startswith("//") or trimmed.startswith("#") or trimmed.startswith("--")) and not any(
                c.isdigit() for c in trimmed[:4]
            ):
                continue

            # Parse the card line
            item, inline_override_section = cls._parse_card_line(trimmed, current_section)
            if item is None or not item.raw_name:
                continue

            target_section = inline_override_section or current_section

            if target_section == DeckSection.COMMANDER:
                item.section = DeckSection.COMMANDER
                deck.commanders.append(item)
            elif target_section == DeckSection.SIDEBOARD:
                item.section = DeckSection.SIDEBOARD
                deck.sideboard.append(item)
            elif target_section == DeckSection.MAYBEBOARD:
                item.section = DeckSection.MAYBEBOARD
                deck.maybeboard.append(item)
            else:
                item.section = DeckSection.MAINDECK
                deck.maindeck.append(item)

        return deck

    @classmethod
    def _parse_card_line(cls, line: str, current_section: DeckSection) -> Tuple[Optional[DeckItem], Optional[DeckSection]]:
        match = LINE_CARD_REGEX.match(line)
        if not match:
            return None, None

        count_str = match.group("count")
        quantity = int(count_str) if count_str else 1
        card_body = match.group("card_body").strip()

        if not card_body:
            return None, None

        # Check for Moxfield inline commander & companion markers first
        inline_override_section: Optional[DeckSection] = None
        if COMMANDER_TAG_REGEX.search(card_body):
            inline_override_section = DeckSection.COMMANDER
        elif COMPANION_TAG_REGEX.search(card_body):
            inline_override_section = DeckSection.SIDEBOARD

        # Extract foil/etched flags
        is_etched = bool(ETCHED_REGEX.search(card_body))
        is_foil = is_etched or bool(FOIL_REGEX.search(card_body))

        # Strip all Moxfield asterisk markers (*CMDR*, *F*, *E*, *foil*, etc.)
        card_body = COMMANDER_TAG_REGEX.sub("", card_body)
        card_body = COMPANION_TAG_REGEX.sub("", card_body)
        card_body = ETCHED_REGEX.sub("", card_body)
        card_body = FOIL_REGEX.sub("", card_body)
        card_body = MOXFIELD_TAG_REGEX.sub("", card_body)

        # Check for DeckStats prefix set notation: `[LEA] Sol Ring`
        prefix_set_match = re.match(r"^\[([a-zA-Z0-9]{3,6})\]\s+(.*)$", card_body)
        set_code: Optional[str] = None
        collector_number: Optional[str] = None

        if prefix_set_match:
            set_code = prefix_set_match.group(1).lower()
            card_body = prefix_set_match.group(2).strip()

        # Extract inline tags (e.g., #!Commander, # Ramp, [Draw])
        tags: List[str] = []

        for tag_match in TAG_REGEX.finditer(card_body):
            raw_tag = tag_match.group(1) or tag_match.group(2) or tag_match.group(3)
            if raw_tag:
                clean_tag = raw_tag.strip()
                tags.append(clean_tag)
                lower_tag = clean_tag.lower()
                if lower_tag in ("commander", "!commander", "general", "featured"):
                    inline_override_section = DeckSection.COMMANDER
                elif lower_tag in ("sideboard", "sb"):
                    inline_override_section = DeckSection.SIDEBOARD
                elif lower_tag in ("maybeboard", "considering", "wishlist", "tokens"):
                    inline_override_section = DeckSection.MAYBEBOARD

        # Remove all tag substrings from card_body
        card_body = re.sub(r"#\s*\!?([a-zA-Z0-9_\-]+)", "", card_body)

        # Check for suffix set/collector notation: `(LEA) 270`, `(cmm:123)`, `[SLD]`, `(DOM) 168`
        set_match = SET_COLLECTOR_REGEX.search(card_body)
        if set_match:
            potential_set = set_match.group("set")
            if not set_code and potential_set:
                set_code = potential_set.lower()
                collector_number = set_match.group("num_colon") or set_match.group("num_space")

            # Remove the set substring from card_body
            start, end = set_match.span()
            card_body = (card_body[:start] + card_body[end:]).strip()

        # Remove leftover brackets e.g. [Category] or (Foil) that were tags
        card_body = re.sub(r"\[[^\]]*\]|\([^\)]*\)", "", card_body)

        # Clean card name
        # Remove trailing/leading special symbols except valid card characters (like apostrophes, commas, slashes for DFCs)
        clean_name = card_body.strip(" \t\r\n-*#")
        # Normalize double-slash spacing for split/DFC cards (e.g., "Fire//Ice" -> "Fire // Ice")
        clean_name = re.sub(r"\s*//\s*", " // ", clean_name)
        # Collapse multiple spaces
        clean_name = re.sub(r"\s+", " ", clean_name).strip()

        if not clean_name:
            return None, None

        item = DeckItem(
            quantity=quantity,
            raw_name=clean_name,
            set_code=set_code,
            collector_number=collector_number,
            is_foil=is_foil,
            is_etched=is_etched,
            section=current_section,
            custom_tags=tags,
        )

        return item, inline_override_section
