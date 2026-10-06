"""
Regular expression patterns and normalization helpers for MTG decklist parsing.
"""

import re
from typing import Dict, Optional, Tuple, List
from ..models.deck import DeckSection


# Section Header Matchers
SECTION_PATTERNS: Dict[DeckSection, re.Pattern] = {
    DeckSection.COMMANDER: re.compile(
        r"^(?://\s*|#\s*|--\s*)?(?:commander(?:s)?|command\s*zone|commander\s*\(s\)|general|featured|oathbreaker)\b.*$",
        re.IGNORECASE,
    ),
    DeckSection.SIDEBOARD: re.compile(
        r"^(?://\s*|#\s*|--\s*)?(?:sideboard|side\s*board|side\s*deck|sb)\b.*$",
        re.IGNORECASE,
    ),
    DeckSection.MAYBEBOARD: re.compile(
        r"^(?://\s*|#\s*|--\s*)?(?:maybeboard|maybe\s*board|maybe\s*deck|considering|consider|wishlist|acquired|tokens?)\b.*$",
        re.IGNORECASE,
    ),
    DeckSection.MAINDECK: re.compile(
        r"^(?://\s*|#\s*|--\s*)?(?:deck|maindeck|main\s*deck|mainboard|main\s*board|main|library|creatures?|instants?|sorcer(?:y|ies)|artifacts?|enchantments?|planeswalkers?|battles?|lands?|spells?)\b.*$",
        re.IGNORECASE,
    ),
}

# Individual Card Line Matcher
LINE_CARD_REGEX = re.compile(
    r"""
    ^\s*
    (?:(?P<count>\d+)\s*x?\s+)?               # Optional quantity, e.g. "1 ", "1x ", "4x "
    (?P<card_body>.*?)                        # Card name and trailing tags/sets
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Pattern to extract set code and collector number from parentheses or brackets
# e.g., "(LEA) 270", "(CMM:123)", "[SLD:456]", "[LEA]", "(dom) 168", "[NEO] 285a"
SET_COLLECTOR_REGEX = re.compile(
    r"""
    (?:[\(\[](?P<set>[a-zA-Z0-9]{3,6})(?::(?P<num_colon>[a-zA-Z0-9\-\*\+]+))?[\)\]]) # (SET) or [SET] or (SET:NUM)
    (?:\s+(?P<num_space>[a-zA-Z0-9\-\*\+]+))?                                          # space followed by collector number
    """,
    re.VERBOSE,
)

# Foil marker patterns
FOIL_REGEX = re.compile(r"(\*F(?:oil)?\*|\((?:foil|etched|f)\)|\[(?:foil|etched)\])", re.IGNORECASE)
ETCHED_REGEX = re.compile(r"(\*E(?:tched)?\*|\(etched\)|\[etched\])", re.IGNORECASE)

# Inline tag patterns: #tag, # tag, #!Commander, [Tag], {Tag}
TAG_REGEX = re.compile(r"(?:#\s*\!?([a-zA-Z0-9_\-]+)|\[([a-zA-Z0-9_\-\s]+)\]|\{([a-zA-Z0-9_\-\s]+)\})")


def identify_section_header(line: str) -> Optional[DeckSection]:
    """Checks if a stripped line represents a deck section header."""
    clean = line.strip()
    if not clean:
        return None

    # Check for Commander headers first
    if SECTION_PATTERNS[DeckSection.COMMANDER].match(clean):
        return DeckSection.COMMANDER
    if SECTION_PATTERNS[DeckSection.SIDEBOARD].match(clean):
        return DeckSection.SIDEBOARD
    if SECTION_PATTERNS[DeckSection.MAYBEBOARD].match(clean):
        return DeckSection.MAYBEBOARD
    if SECTION_PATTERNS[DeckSection.MAINDECK].match(clean):
        return DeckSection.MAINDECK

    return None
