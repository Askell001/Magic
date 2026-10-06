"""
Unit tests for Color Identity rules, Hybrid Mana enforcement, Singleton, Banlist,
and the Post-AI Integrity Middleware.
"""

from mtg_deck_optimizer.models.card import Card, CardPrices, CardFace
from mtg_deck_optimizer.models.deck import Deck, DeckItem, DeckSection
from mtg_deck_optimizer.brackets.standards import BracketTier
from mtg_deck_optimizer.scryfall.client import ScryfallClient
from mtg_deck_optimizer.rules.color_identity import ColorIdentityExtractor
from mtg_deck_optimizer.rules.legality import SingletonValidator, BanlistValidator
from mtg_deck_optimizer.rules.middleware import validate_recommendations
from mtg_deck_optimizer.ai.models import (
    OptimizationReport,
    CardCut,
    CardInclusion,
    ManaBaseAnalysis,
    WinConditionAnalysis,
    BudgetSummary,
)


def make_card(name: str, mana_cost: str = "{G}", cmc: float = 1.0, type_line: str = "Creature", oracle: str = "", colors: list = None, ci: list = None) -> Card:
    return Card(
        id=f"id_{name.lower().replace(' ', '_')}",
        name=name,
        mana_cost=mana_cost,
        cmc=cmc,
        type_line=type_line,
        oracle_text=oracle,
        colors=colors or ["G"],
        color_identity=ci or ["G"],
    )


def test_color_identity_rules_text_and_extort():
    # Kenrith: Casting cost {4}{W}, but rules text has {R}, {1}{G}, {2}{W}, {3}{U}, {4}{B}
    kenrith = Card(
        id="ken1",
        name="Kenrith, the Returned King",
        mana_cost="{4}{W}",
        cmc=5.0,
        type_line="Legendary Creature — Human Noble",
        oracle_text="{R}: All creatures gain trample and haste.\n{1}{G}: Put a +1/+1 counter...\n{2}{W}: Target player gains 5 life.\n{3}{U}: Target player draws a card.\n{4}{B}: Put target creature card...",
        colors=["W"],
        color_identity=["W", "U", "B", "R", "G"],
    )
    ci = ColorIdentityExtractor.compute_card_color_identity(kenrith)
    assert ci == ["W", "U", "B", "R", "G"]

    # Blind Obedience: Casting cost {1}{W}, Extort reminder text "( {W/B} )"
    # Extort reminder text must NOT add Black to Color Identity
    blind_obedience = Card(
        id="bo1",
        name="Blind Obedience",
        mana_cost="{1}{W}",
        cmc=2.0,
        type_line="Enchantment",
        oracle_text="Extort (Whenever you cast a spell, you may pay {W/B}. If you do, each opponent loses 1 life...)\nArtifacts and creatures your opponents control enter the battlefield tapped.",
        colors=["W"],
        color_identity=["W"],
    )
    ci_bo = ColorIdentityExtractor.compute_card_color_identity(blind_obedience)
    assert ci_bo == ["W"]


def test_color_identity_dfc_faces():
    # Archangel Avacyn: Front is {3}{W}{W} (White), Back face is Red
    avacyn = Card(
        id="ava1",
        name="Archangel Avacyn // Avacyn, the Purifier",
        mana_cost="{3}{W}{W}",
        cmc=5.0,
        type_line="Legendary Creature — Angel // Legendary Creature — Angel",
        colors=["W"],
        color_identity=["W", "R"],
        card_faces=[
            CardFace(name="Archangel Avacyn", mana_cost="{3}{W}{W}", type_line="Legendary Creature — Angel", colors=["W"]),
            CardFace(name="Avacyn, the Purifier", mana_cost=None, type_line="Legendary Creature — Angel", colors=["R"]),
        ],
    )
    ci = ColorIdentityExtractor.compute_card_color_identity(avacyn)
    assert "W" in ci
    assert "R" in ci


def test_strict_hybrid_mana_rule():
    # Mono-Green Commander (e.g. Selvala)
    mono_green_ci = ["G"]

    # Manamorphose: {1}{R/G} contains Red and Green -> ILLEGAL in Mono-Green
    manamorphose = make_card("Manamorphose", mana_cost="{1}{R/G}", cmc=2.0, type_line="Instant", oracle="Add two mana in any combination of colors. Draw a card.", ci=["R", "G"])
    is_legal_mana, err_mana = ColorIdentityExtractor.validate_color_identity(manamorphose, mono_green_ci)
    assert is_legal_mana is False
    assert "fuera de la identidad" in err_mana

    # Kitchen Finks: {1}{G/W}{G/W} contains White and Green -> ILLEGAL in Mono-Green
    finks = make_card("Kitchen Finks", mana_cost="{1}{G/W}{G/W}", cmc=3.0, type_line="Creature — Ouphe", ci=["W", "G"])
    is_legal_finks, _ = ColorIdentityExtractor.validate_color_identity(finks, mono_green_ci)
    assert is_legal_finks is False

    # Llanowar Elves: {G} -> LEGAL in Mono-Green
    llanowar = make_card("Llanowar Elves", mana_cost="{G}", cmc=1.0, type_line="Creature — Elf", ci=["G"])
    is_legal_ll, _ = ColorIdentityExtractor.validate_color_identity(llanowar, mono_green_ci)
    assert is_legal_ll is True


def test_singleton_validator():
    basic_forest = make_card("Forest", type_line="Basic Land — Forest")
    special_rats = make_card("Relentless Rats", type_line="Creature — Rat")
    regular_spell = make_card("Sol Ring", type_line="Artifact")

    # Valid deck with multiple basics and special rats
    deck_valid = Deck(
        name="Valid Deck",
        maindeck=[
            DeckItem(quantity=30, raw_name="Forest", card=basic_forest),
            DeckItem(quantity=20, raw_name="Relentless Rats", card=special_rats),
            DeckItem(quantity=1, raw_name="Sol Ring", card=regular_spell),
        ],
    )
    errors_valid = SingletonValidator.validate_deck_singleton(deck_valid)
    assert len(errors_valid) == 0

    # Invalid deck with duplicate non-basic
    deck_invalid = Deck(
        name="Invalid Deck",
        maindeck=[
            DeckItem(quantity=2, raw_name="Sol Ring", card=regular_spell),
        ],
    )
    errors_invalid = SingletonValidator.validate_deck_singleton(deck_invalid)
    assert len(errors_invalid) == 1
    assert "Violación de Singleton" in errors_invalid[0]


def test_banlist_validator():
    dockside = make_card("Dockside Extortionist", mana_cost="{1}{R}", type_line="Creature — Goblin Pirate")
    is_banned, ban_reason = BanlistValidator.is_banned_in_commander(dockside)
    assert is_banned is True
    assert "PROHIBIDA" in ban_reason

    sol_ring = make_card("Sol Ring", mana_cost="{1}", type_line="Artifact")
    is_banned_sol, _ = BanlistValidator.is_banned_in_commander(sol_ring)
    assert is_banned_sol is False


def test_validate_recommendations_middleware():
    # Mono-Green deck: Commander is Selvala
    selvala = make_card("Selvala, Heart of the Wilds", mana_cost="{1}{G}{G}", cmc=3.0, type_line="Legendary Creature — Elf Scout", ci=["G"])
    sol_ring = make_card("Sol Ring", mana_cost="{1}", cmc=1.0, type_line="Artifact", ci=[])

    deck = Deck(
        name="Mono Green Selvala",
        commanders=[DeckItem(raw_name="Selvala, Heart of the Wilds", card=selvala, section=DeckSection.COMMANDER)],
        maindeck=[DeckItem(raw_name="Sol Ring", card=sol_ring, section=DeckSection.MAINDECK)],
    )

    # Simulated AI report containing:
    # 1. Illegal Hybrid Mana: Manamorphose {1}{R/G} (contains Red in Mono-Green)
    # 2. Banned card: Fastbond
    # 3. Duplicate: Sol Ring (already in deck)
    # 4. Valid legal card: Birds of Paradise {G}
    # 5. Cut targeting Selvala (which is untouchable)
    report = OptimizationReport(
        deck_name="Mono Green Selvala",
        commander_name="Selvala, Heart of the Wilds",
        initial_bracket=BracketTier.BRACKET_2_MID_POWER,
        target_bracket=BracketTier.BRACKET_3_HIGH_POWER,
        estimated_new_power_score=3.0,
        summary_overview="AI generated recommendations.",
        cuts=[
            CardCut(card_name="Selvala, Heart of the Wilds", type_line="Legendary Creature", cmc=3.0, reason="Cut commander test.")
        ],
        inclusions=[
            CardInclusion(card_name="Manamorphose", type_line="Instant", cmc=2.0, role="Ramp", synergy_explanation="Hybrid test.", estimated_price_usd=4.0),
            CardInclusion(card_name="Fastbond", type_line="Enchantment", cmc=1.0, role="Ramp", synergy_explanation="Banned test.", estimated_price_usd=25.0),
            CardInclusion(card_name="Sol Ring", type_line="Artifact", cmc=1.0, role="Ramp", synergy_explanation="Duplicate test.", estimated_price_usd=1.5),
            CardInclusion(card_name="Birds of Paradise", type_line="Creature — Bird", cmc=1.0, role="Ramp", synergy_explanation="Legal test.", estimated_price_usd=6.5),
        ],
        mana_base_analysis=ManaBaseAnalysis(
            color_balance_status="Mono-G",
            recommended_land_count=33,
            utility_lands_recommendations=["Boseiju"],
            fixing_recommendations=[],
            ramp_assessment="Good",
        ),
        win_conditions=WinConditionAnalysis(
            primary_win_path="Aggro",
            combos_or_synergies=[],
            estimated_turn_to_win="Turn 6",
        ),
        budget_summary=BudgetSummary(),
    )

    mock_client = ScryfallClient()
    mock_client._cache_card(make_card("Manamorphose", mana_cost="{1}{R/G}", ci=["R", "G"]))
    mock_client._cache_card(make_card("Fastbond", mana_cost="{G}", ci=["G"]))
    mock_client._cache_card(make_card("Sol Ring", mana_cost="{1}", ci=[]))
    mock_client._cache_card(make_card("Birds of Paradise", mana_cost="{G}", ci=["G"]))

    cleaned_report = validate_recommendations(
        deck=deck,
        report=report,
        untouchable_cards=["Selvala, Heart of the Wilds"],
        scryfall_client=mock_client,
    )

    # Inclusions audit: Manamorphose, Fastbond, Sol Ring must be discarded
    final_inclusion_names = [i.card_name for i in cleaned_report.inclusions]
    assert "Manamorphose" not in final_inclusion_names
    assert "Fastbond" not in final_inclusion_names
    assert "Sol Ring" not in final_inclusion_names
    assert "Birds of Paradise" in final_inclusion_names

    # Cuts audit: Selvala cut must be cancelled
    final_cut_names = [c.card_name for c in cleaned_report.cuts]
    assert "Selvala, Heart of the Wilds" not in final_cut_names

    # Audit log block must be present in summary
    assert "AUDITORÍA DE REGLAS DE COMMANDER" in cleaned_report.summary_overview
    assert "Rechazado por Identidad de Color" in cleaned_report.summary_overview
    assert "Rechazado por Banlist" in cleaned_report.summary_overview
    assert "Rechazado por Singleton" in cleaned_report.summary_overview
    assert "Corte Anulado" in cleaned_report.summary_overview
