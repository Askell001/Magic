"""
AI Prompt Builder constructing expert LLM prompts for MTG Deck Optimization.
"""

import json
from typing import Dict, Any, Optional

from ..models.deck import Deck
from ..intent.models import UserIntent
from ..brackets.standards import BracketTier, BRACKET_BENCHMARKS
from ..brackets.classifier import CardRoleClassifier, DeckClassification
from ..brackets.gap_analyzer import DeckGapAnalyzer, DeckGapReport
from .community_data import CommanderCommunityData, CommunityDataService
from .models import OptimizationReport


class AIPromptBuilder:
    """Builds structured system and user prompts for LLMs (OpenAI, Gemini, Anthropic)."""

    SYSTEM_INSTRUCTIONS = """You are MTG Deck Optimizer AI — an elite Magic: The Gathering Commander (EDH) deckbuilding authority, Level 3 Rules Judge, and EDHREC Data Scientist.
Your mission is to perform a rigorous mathematical, strategic, and tactical optimization on a player's Commander deck to elevate or align it with their chosen Power Bracket.

You must strictly obey the following rules:
1. UNTOUCHABLE CARDS: The user will specify a list of "untouchable" or sacred cards. You MUST NOT cut any card from this list under any circumstance.
2. BUDGET CONSTRAINT: If the user provides a maximum budget in USD, your net upgrade cost (added cards cost minus cut cards value, or total added cards cost) must strictly adhere to the budget.
3. BRACKET STANDARDS:
   - Bracket 1 (Jank/Casual): No fast mana, no infinite combos, average CMC 3.4-4.5, relaxed land base.
   - Bracket 2 (Mid-Power/Casual Optimized): Clear synergy, defined fair wincons, standard interaction (CMC 2.8-3.4), no fast mana.
   - Bracket 3 (High-Power/Optimized): Fast mana permitted, efficient 2-3 card combos, high tutor density, cheap interaction (CMC 2.0-2.8).
   - Bracket 4 (cEDH/Maximum Power): Maximum efficiency, turn 2-4 wincons (e.g. Thoracle + Consultation), free counterspells/removal, lowest CMC (1.2-2.0).
4. COMMUNITY DATA: Prioritize high-synergy inclusions with positive community win rates from EDHREC data.
5. ANTI-SYNERGY TRAP FILTER: Strictly prioritize mana efficiency over pure thematic resonance. Avoid suggesting spells with CMC > 4 unless they are direct game-ending win conditions or indispensable engine cornerstones. Reject slow, win-more cards.
6. CARD-BY-CARD TRADE-OFF JUSTIFICATION: Every suggested change must explicitly justify the cause-and-effect transition: [Card Cut (CMC)] vs [Card In (CMC)] detailing the exact curve reduction and technical acceleration.
7. STRATEGY SYNERGY ALIGNMENT: Rigorously evaluate and optimize every card inclusion and cut based on its alignment with the key elements, gameplay description, and win conditions of the chosen strategy/archetype.
8. STRICT JSON OUTPUT: Return ONLY a valid, single JSON object adhering exactly to the requested JSON schema. No surrounding conversational markdown or backticks outside the JSON.
"""

    @classmethod
    def build_prompt(
        cls,
        deck: Deck,
        intent: UserIntent,
        gap_report: Optional[DeckGapReport] = None,
        community_data: Optional[CommanderCommunityData] = None,
    ) -> Dict[str, str]:
        """
        Constructs the complete prompt dictionary with 'system' and 'user' components.
        """
        # Retrieve or compute gap report and community data if not provided
        if gap_report is None:
            gap_report = DeckGapAnalyzer.analyze(deck, intent)

        primary_cmdr_name = deck.commanders[0].effective_name if deck.commanders else "Unknown Commander"
        cmdr_card = deck.commanders[0].card if deck.commanders else None

        if community_data is None:
            community_data = CommunityDataService.get_commander_data(
                commander_name=primary_cmdr_name,
                color_identity=deck.color_identity,
                type_line=cmdr_card.type_line if cmdr_card else None,
            )

        # 1. Format Current Deck Cards
        active_items = deck.commanders + deck.maindeck
        card_lines = []
        for it in active_items:
            c = it.card
            price_str = f"${it.total_price_usd:.2f}" if it.total_price_usd is not None else "N/A"
            cmc_val = c.cmc if c else "N/A"
            type_val = c.primary_type if c else "Unknown"
            foil_mark = " (Foil)" if it.is_foil else ""
            card_lines.append(f"- {it.quantity}x {it.effective_name} [CMC: {cmc_val}, Type: {type_val}, Price: {price_str}]{foil_mark}")
        current_deck_str = "\n".join(card_lines)

        # 2. Format Untouchable Cards
        untouchables_str = ", ".join(intent.untouchable_cards) if intent.untouchable_cards else "None (all cards are eligible for cuts)"

        # 3. Format Budget
        budget_str = f"${intent.max_budget_usd:,.2f} USD" if intent.max_budget_usd is not None else "Unlimited / No restriction"

        # 4. Format Community Synergy Data
        top_synergies = []
        for s in community_data.top_synergy_cards[:8]:
            top_synergies.append(f"- {s.name} ({s.type_line}, CMC: {s.cmc}) | Inclusion: {s.inclusion_percent}% | Synergy: +{s.synergy_score}% | Role: {s.primary_role} | Price: ${s.estimated_price_usd:.2f}")
        synergies_str = "\n".join(top_synergies) if top_synergies else "No specific community data found."

        top_staples = []
        for s in community_data.top_staples[:6]:
            top_staples.append(f"- {s.name} ({s.type_line}, CMC: {s.cmc}) | Role: {s.primary_role} | Price: ${s.estimated_price_usd:.2f}")
        staples_str = "\n".join(top_staples)

        combos_str = "\n".join(f"- {c}" for c in community_data.popular_combos)

        # 5. Format Recent / Spoiled Innovations Block
        from .context_injector import RecentCardsContextInjector
        injector = RecentCardsContextInjector()
        recent_innovations_str = injector.format_recent_innovations_block(
            color_identity=deck.color_identity,
            limit=6,
        )

        # 5b. Format Strategy Theoretical Guide
        strat = getattr(intent, "strategy_profile", None) or {}
        strat_name = getattr(intent, "strategy_name", None) or strat.get("name", "")
        if strat or strat_name:
            strat_desc = strat.get("description", "Not specified")
            key_elems = strat.get("key_elements", [])
            key_elems_str = "\n".join(f"  * {el}" for el in key_elems) if key_elems else "  * Dynamic archetype synergies"
            win_cons = strat.get("win_conditions", [])
            win_cons_str = "\n".join(f"  * {wc}" for wc in win_cons) if win_cons else "  * General Commander combat or combo win conditions"
            
            strategy_block = f"""
=== SELECTED STRATEGY & THEORETICAL GUIDE ===
- Archetype Name: {strat_name}
- Category: {strat.get('category', 'Commander Archetype')}
- Description: {strat_desc}
- Key Strategic Elements (Must Support):
{key_elems_str}
- Primary Win Conditions (Target Game Plan):
{win_cons_str}
"""
        else:
            strategy_block = ""

        # 6. Schema representation
        json_schema_example = json.dumps(
            {
                "deck_name": deck.name,
                "commander_name": primary_cmdr_name,
                "initial_bracket": gap_report.current_bracket.value,
                "target_bracket": intent.target_bracket.value,
                "estimated_new_power_score": 3.2,
                "summary_overview": "Comprehensive explanation of changes...",
                "cuts": [
                    {
                        "card_name": "Card Name",
                        "type_line": "Creature — Dragon",
                        "cmc": 7.0,
                        "reason": "Technical justification for cut...",
                        "estimated_price_usd": 4.50,
                    }
                ],
                "inclusions": [
                    {
                        "card_name": "Card Name",
                        "type_line": "Instant",
                        "cmc": 1.0,
                        "role": "Ramp / Interaction / Wincon",
                        "synergy_explanation": "Why this card improves deck consistency...",
                        "estimated_price_usd": 12.00,
                        "synergy_score": 55.0,
                    }
                ],
                "mana_base_analysis": {
                    "color_balance_status": "Status of color fixing...",
                    "recommended_land_count": 33,
                    "utility_lands_recommendations": ["Ancient Tomb", "Boseiju, Who Endures"],
                    "fixing_recommendations": ["Add shocklands", "Replace taplands"],
                    "ramp_assessment": "Assessment of rocks and dorks...",
                },
                "win_conditions": {
                    "primary_win_path": "Description of main win path...",
                    "combos_or_synergies": ["Combo line 1", "Combat overrun line"],
                    "estimated_turn_to_win": "Turn 5-7",
                },
                "budget_summary": {
                    "total_cut_value_usd": 25.50,
                    "total_added_cost_usd": 85.00,
                    "net_upgrade_cost_usd": 59.50,
                    "is_within_budget": True,
                    "budget_notes": "Budget allocation notes...",
                },
            },
            indent=2,
        )

        user_prompt = f"""=== CURRENT DECK INPUT ===
- Deck Name: {deck.name}
- Commander: {primary_cmdr_name}
- Color Identity: {''.join(deck.color_identity) if deck.color_identity else 'Colorless'}
- Total Cards: {deck.total_card_count}
- Current Estimated Value: ${deck.estimated_total_usd if deck.estimated_total_usd else 0:.2f} USD
- Current Power Bracket: {gap_report.current_bracket.label} (Score: {gap_report.current_bracket_score}/4.0)

=== USER INTENT & CONSTRAINTS ===
- Target Bracket: {intent.target_bracket.label}
- Max Upgrade Budget: {budget_str}
- UNTOUCHABLE CARDS (DO NOT CUT): {untouchables_str}
- Allow Infinite Combos: {intent.effective_allow_combos}
- Allow Fast Mana: {intent.effective_allow_fast_mana}
{strategy_block}
=== GAP ANALYSIS METRICS ===
- Current Avg CMC (non-land): {gap_report.cmc_detail.current_value:.2f} (Target: {gap_report.cmc_detail.target_benchmark_range}) -> {gap_report.cmc_detail.status}
- Lands Count: {int(gap_report.lands_detail.current_value)} (Target: {gap_report.lands_detail.target_benchmark_range}) -> {gap_report.lands_detail.status}
- Ramp Count: {int(gap_report.ramp_detail.current_value)} (Target: {gap_report.ramp_detail.target_benchmark_range}) -> {gap_report.ramp_detail.status}
- Fast Mana: {int(gap_report.fast_mana_detail.current_value)} (Target: {gap_report.fast_mana_detail.target_benchmark_range}) -> {gap_report.fast_mana_detail.status}
- Interaction: {int(gap_report.interaction_detail.current_value)} (Target: {gap_report.interaction_detail.target_benchmark_range}) -> {gap_report.interaction_detail.status}
- Tutors: {int(gap_report.tutors_detail.current_value)} (Target: {gap_report.tutors_detail.target_benchmark_range}) -> {gap_report.tutors_detail.status}

=== EDHREC / COMMUNITY DATA FOR {primary_cmdr_name.upper()} ===
Archetype: {community_data.archetype_theme} (Analyzed across {community_data.total_decks_analyzed:,} decks)

Top Synergy Inclusions:
{synergies_str}

Format Staples:
{staples_str}

Known Wincon Combos:
{combos_str}

{recent_innovations_str}

=== CURRENT DECKLIST ===
{current_deck_str}

=== REQUIRED OUTPUT ===
Generate a comprehensive, mathematically rigorous optimization plan aligned with the selected strategy. Provide balanced 1-for-1 swaps (Cuts and Inclusions) that maintain the 100-card Commander legal deck limit, optimize the mana curve and color fixing, and respect all untouchable cards, strategy guidelines, and budget constraints.

Format your output strictly as a valid JSON object following this exact schema:
{json_schema_example}
"""

        return {
            "system": cls.SYSTEM_INSTRUCTIONS,
            "user": user_prompt,
        }
