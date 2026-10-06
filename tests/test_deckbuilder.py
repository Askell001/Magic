"""
Unit tests for MTG Deckbuilder Generator.
Validates 100-card generation, commander suggestions, WotC rules compliance,
budget controls, and export generation.
"""

import pytest
from mtg_deck_optimizer.deckbuilder import (
    MTGDeckbuilderGenerator,
    DeckbuilderParams,
    GeneratedDeckResult,
)
from mtg_deck_optimizer.brackets import BracketTier


def test_deckbuilder_suggest_commanders():
    """Verifies that the deckbuilder returns top commanders for any valid strategy."""
    generator = MTGDeckbuilderGenerator()
    
    suggestions_aristocrats = generator.suggest_commanders("Aristocrats", target_bracket=2)
    assert len(suggestions_aristocrats) >= 3
    names_aristocrats = [s.name for s in suggestions_aristocrats]
    assert "Teysa Karlov" in names_aristocrats or "Korvold, Fae-Cursed King" in names_aristocrats

    suggestions_cedh = generator.suggest_commanders("cEDH Combo", target_bracket=4)
    assert len(suggestions_cedh) >= 3
    names_cedh = [s.name for s in suggestions_cedh]
    assert any("Kinnan" in n or "Stella" in n or "Niv-Mizzet" in n or "Rograkh" in n for n in names_cedh)



def test_deckbuilder_build_deck_from_scratch_100_cards():
    """Verifies that the generated deck contains exactly 1 Commander and 99 Maindeck cards."""
    generator = MTGDeckbuilderGenerator()

    params = DeckbuilderParams(
        commander_name="Teysa Karlov",
        target_bracket=2,
        strategy_archetype="Aristocrats",
        max_budget_usd=200.0,
    )

    result = generator.build_deck(params)

    assert isinstance(result, GeneratedDeckResult)
    assert len(result.deck.commanders) == 1
    assert result.deck.commander_count == 1
    assert result.deck.maindeck_count == 99
    assert result.deck.total_card_count == 100


def test_deckbuilder_wotc_rules_compliance():
    """Verifies that the generated deck is 100% legal under official WotC Commander rules."""
    generator = MTGDeckbuilderGenerator()

    params = DeckbuilderParams(
        commander_name="Stella Lee, Wild Card",
        target_bracket=3,
        strategy_archetype="Spellslinger",
    )

    result = generator.build_deck(params)

    # Validate with rules engine
    assert result.validation.is_fully_legal is True
    assert len(result.validation.color_identity_errors) == 0
    assert len(result.validation.banlist_errors) == 0
    assert len(result.validation.singleton_errors) == 0
    assert set(result.deck.color_identity).issubset({"U", "R"})


def test_deckbuilder_cedh_bracket_4():
    """Verifies that a Bracket 4 deck includes cEDH elements, low curve and fast mana."""
    generator = MTGDeckbuilderGenerator()

    params = DeckbuilderParams(
        commander_name="Kinnan, Bonder Prodigy",
        target_bracket=4,
        strategy_archetype="cEDH Combo",
    )

    result = generator.build_deck(params)

    assert result.deck.total_card_count == 100
    assert result.bracket == BracketTier.BRACKET_4_CEDH
    assert result.average_cmc < 3.0
    assert result.role_breakdown.tutors >= 2 or result.role_breakdown.ramp_and_mana >= 4


def test_deckbuilder_export_text():
    """Verifies that export text contains Commander and Maindeck sections compatible with Moxfield."""
    generator = MTGDeckbuilderGenerator()

    params = DeckbuilderParams(
        commander_name="The Ur-Dragon",
        target_bracket=3,
        strategy_archetype="Dragons Tribal",
    )

    result = generator.build_deck(params)
    export_str = result.export_text

    assert "// Commander" in export_str
    assert "The Ur-Dragon" in export_str
    assert "// Mainboard" in export_str or "// Maindeck" in export_str
    assert result.deck.total_card_count == 100


def test_deckbuilder_game_changer_quotas_by_bracket():
    """Verifies that Bracket 3 never exceeds 3 Game Changers, and Bracket 2 has 0."""
    from mtg_deck_optimizer.brackets.game_changers import GameChangersEvaluator
    generator = MTGDeckbuilderGenerator()

    # Bracket 3 generation
    res_b3 = generator.build_deck(
        DeckbuilderParams(
            commander_name="Stella Lee, Wild Card",
            target_bracket=3,
            strategy_archetype="Spellslinger / Storm",
        )
    )
    audit_b3 = GameChangersEvaluator.audit_deck_game_changers(res_b3.deck, 3)
    # Total Game Changers in deck must not exceed 3
    assert len(audit_b3) <= 3
    # None of them should be marked as "DEBE SALIR"
    assert all(a.is_allowed for a in audit_b3)

    # Bracket 2 generation
    res_b2 = generator.build_deck(
        DeckbuilderParams(
            commander_name="Teysa Karlov",
            target_bracket=2,
            strategy_archetype="Aristocrats / Sacrifice",
        )
    )
    audit_b2 = GameChangersEvaluator.audit_deck_game_changers(res_b2.deck, 2)
    # Bracket 2 must have 0 Game Changers
    assert len(audit_b2) == 0

