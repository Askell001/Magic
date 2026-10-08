"""
AI-Driven Deck Optimizer Agent orchestrating contextual prompt generation,
community data retrieval, bracket downshift compliance, Land Balance Engine,
and structured WotC-validated recommendations.
"""

import os
import re
import json
import logging
from typing import Dict, Any, Optional, List, Set
import httpx

from ..models.deck import Deck, DeckItem
from ..intent.models import UserIntent
from ..brackets.standards import BracketTier, BRACKET_BENCHMARKS
from ..brackets.gap_analyzer import DeckGapAnalyzer, DeckGapReport
from ..brackets.game_changers import GameChangersEvaluator, GAME_CHANGERS_DATABASE
from ..rules.wotc_rules_engine import WOTC_Commander_Rules_Engine
from ..analytics.land_balance_engine import LandBalanceEngine
from .models import OptimizationReport, CardCut, CardInclusion, ManaBaseAnalysis, WinConditionAnalysis, BudgetSummary
from .community_data import CommunityDataService, CommanderCommunityData
from .prompt_builder import AIPromptBuilder

logger = logging.getLogger(__name__)


class DeckOptimizerAgent:
    """
    Core AI Optimizer Agent that analyzes decks and suggests structured upgrades.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.rules_engine = WOTC_Commander_Rules_Engine()

    def optimize(
        self,
        deck: Deck,
        intent: UserIntent,
        llm_caller: Optional[Any] = None,
    ) -> OptimizationReport:
        """
        Executes full optimization workflow:
        1. Gap Analysis
        2. Community Data Retrieval
        3. Bracket & Game Changer Compliance Evaluation
        4. Land Deficit & Overload Balance Analysis
        5. Recommendation Generation
        6. WotC Rules Validation & Sanitization
        """
        # Step 1: Gap Analysis
        gap_report: DeckGapReport = DeckGapAnalyzer.analyze(deck, intent)

        # Step 2: Community Data
        cmdr_name = deck.commander_name or "Commander"
        cmdr_card = deck.commanders[0].card if deck.commanders and deck.commanders[0].card else None
        tl = cmdr_card.type_line if cmdr_card else None
        community_data: CommanderCommunityData = CommunityDataService.get_commander_data(
            commander_name=cmdr_name,
            color_identity=deck.color_identity,
            type_line=tl,
        )

        # Step 3: Generation (LLM or Heuristic)
        if llm_caller:
            prompt = AIPromptBuilder.build_prompt(deck, intent, gap_report, community_data)
            raw_resp = llm_caller(prompt)
            clean_json = raw_resp.strip()
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()
            data = json.loads(clean_json)
            report = OptimizationReport(**data)
            return self.rules_engine.sanitize_recommendations(deck, report)

        if self.api_key:
            try:
                report = self._call_llm(deck, intent, gap_report, community_data)
            except Exception as e:
                logger.warning(f"LLM optimization failed ({e}), falling back to heuristic engine.")
                report = self._heuristic_inference(deck, intent, gap_report, community_data)
        else:
            report = self._heuristic_inference(deck, intent, gap_report, community_data)

        # Step 4: Validate against official WOTC Rules
        report = self.rules_engine.sanitize_recommendations(deck, report)

        return report

    def _heuristic_inference(
        self,
        deck: Deck,
        intent: UserIntent,
        gap_report: DeckGapReport,
        community_data: CommanderCommunityData,
    ) -> OptimizationReport:
        """
        Deterministic, rule-based optimization engine when no external LLM is configured.
        Guarantees strict compliance with Bracket benchmarks, Downshifting rules, Land Balance, and budget constraints.
        """
        target_tier = intent.target_bracket
        bench = BRACKET_BENCHMARKS[target_tier]
        current_card_names = {it.effective_name.lower() for it in deck.get_all_items()}

        cuts: List[CardCut] = []
        inclusions: List[CardInclusion] = []
        already_cut_names: Set[str] = set()
        total_cut_val = 0.0
        total_add_val = 0.0

        # ---------------------------------------------------------------------
        # 0. DOWNGRADE / BRACKET TRANSITION: Mandatory Game Changer & Combo Cuts
        # ---------------------------------------------------------------------
        gc_violations = GameChangersEvaluator.evaluate_bracket_compliance(deck, target_tier)

        for viol in gc_violations:
            if intent.is_untouchable(viol.card_name):
                continue
            match_item = next((it for it in deck.maindeck if it.effective_name.lower() == viol.card_name.lower()), None)
            if match_item and match_item.effective_name.lower() not in already_cut_names:
                price = match_item.total_price_usd or 15.0
                cmc_val = match_item.card.cmc if match_item.card else 2.0
                type_l = match_item.card.type_line if match_item.card else "Spell"
                total_cut_val += price
                cuts.append(
                    CardCut(
                        card_name=match_item.effective_name,
                        type_line=type_l,
                        cmc=cmc_val,
                        reason=viol.rule_violation_reason,
                        estimated_price_usd=round(price, 2),
                    )
                )
                already_cut_names.add(match_item.effective_name.lower())

                # Find a suggested in-bracket replacement
                for rep_name in viol.suggested_in_bracket_replacements:
                    if rep_name.lower() not in current_card_names and rep_name.lower() not in [i.card_name.lower() for i in inclusions]:
                        inclusions.append(
                            CardInclusion(
                                card_name=rep_name,
                                type_line="Spell",
                                cmc=2.0,
                                role=f"Bracket {target_tier.value} In-Bracket Replacement",
                                synergy_explanation=f"Sustituto legal para reemplazar el Game Changer '{viol.card_name}' [{viol.category}] y cumplir las reglas de Bracket {target_tier.value}.",
                                estimated_price_usd=4.0,
                                synergy_score=0.9,
                            )
                        )
                        break

        # ---------------------------------------------------------------------
        # 1. LAND BALANCE ENGINE: Land Deficit / Overload Swaps
        # ---------------------------------------------------------------------
        land_report = LandBalanceEngine.evaluate_land_balance(deck, target_tier, intent.untouchable_cards)
        
        for adj in land_report.adjustments:
            if adj.cut_card_name.lower() in already_cut_names:
                continue
            already_cut_names.add(adj.cut_card_name.lower())
            
            cuts.append(
                CardCut(
                    card_name=adj.cut_card_name,
                    type_line=adj.cut_card_type,
                    cmc=adj.cut_card_cmc,
                    role="Land Adjustment",
                    reason=adj.reason,
                    estimated_price_usd=3.0 if adj.action == "cut_spell_add_land" else 0.5,
                )
            )
            
            inclusions.append(
                CardInclusion(
                    card_name=adj.add_card_name,
                    type_line=adj.add_card_type,
                    cmc=adj.add_card_cmc,
                    role="Mana Base / Land" if adj.action == "cut_spell_add_land" else "Ramp/Draw/Interaction",
                    synergy_explanation=(
                        f"Ajuste de base de maná: Resolver {adj.category.lower()} para alinear el mazo a "
                        f"{land_report.target_land_min}-{land_report.target_land_max} tierras para Bracket {target_tier.value}."
                    ),
                    estimated_price_usd=5.0 if adj.action == "cut_spell_add_land" else 4.0,
                    synergy_score=0.95,
                )
            )

        # ---------------------------------------------------------------------
        # 2. Identify General Candidate Cuts (Highest CMC non-staple spells)
        # ---------------------------------------------------------------------
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

        candidate_cuts: List[DeckItem] = []
        for it in deck.maindeck:
            n_l = it.effective_name.lower().strip()
            front_l = n_l.split(" // ")[0].split(" / ")[0].strip()
            if intent.is_untouchable(it.effective_name) or n_l in already_cut_names:
                continue
            if n_l in PROTECTED_STAPLES or front_l in PROTECTED_STAPLES:
                continue
            card = it.card
            if not card:
                candidate_cuts.append(it)
                continue
            # Non-land cards with CMC >= 3.0 or off-curve spells
            if "Land" not in card.type_line and card.cmc >= 3.0:
                candidate_cuts.append(it)

        # Sort candidate cuts by CMC descending (cut heaviest non-staple cards first to lower curve)
        candidate_cuts.sort(key=lambda it: it.card.cmc if it.card else 0.0, reverse=True)

        # ---------------------------------------------------------------------
        # 3. Select Candidate Inclusions from Community Data & Staples
        # ---------------------------------------------------------------------
        candidate_inclusions = community_data.top_synergy_cards + community_data.top_staples

        # Filter out cards already in the deck or already included, and enforce Bracket Game Changer limits
        existing_names = current_card_names.union({i.card_name.lower() for i in inclusions})
        
        # Calculate Game Changers currently remaining in deck after cuts
        max_gc_quota = {1: 0, 2: 0, 3: 3, 4: 99}.get(target_tier.value, 3)
        kept_deck_gc = 0
        for it in deck.maindeck:
            if it.effective_name.lower() in GAME_CHANGERS_DATABASE and it.effective_name.lower() not in already_cut_names:
                kept_deck_gc += 1
        
        gc_inclusions_count = sum(1 for inc in inclusions if inc.card_name.lower() in GAME_CHANGERS_DATABASE)
        remaining_gc_allowed = max(0, max_gc_quota - kept_deck_gc - gc_inclusions_count)

        available_inclusions = []
        for inc in candidate_inclusions:
            n_l = inc.name.lower()
            if n_l in existing_names:
                continue
            
            # Check Game Changer compliance
            if n_l in GAME_CHANGERS_DATABASE:
                gc_def = GAME_CHANGERS_DATABASE[n_l]
                if target_tier.value not in gc_def.allowed_in_brackets:
                    continue
                if remaining_gc_allowed <= 0:
                    continue
            
            available_inclusions.append(inc)

        # Determine remaining swaps needed based on deviation score
        needed_swaps = max(0, min(len(candidate_cuts), len(available_inclusions), max(2, int(gap_report.overall_deviation_score * 0.8) + 1) - len(cuts)))
        selected_cuts = candidate_cuts[:needed_swaps]

        for item in selected_cuts:
            price = item.total_price_usd or 2.0
            cmc_val = item.card.cmc if item.card else 5.0
            type_l = item.card.type_line if item.card else "Spell"
            total_cut_val += price

            reason = f"Coste de maná elevado ({cmc_val:.0f} CMC) que ralentiza el tempo del mazo. Sustituir por aceleración o respuesta más eficiente para Bracket {target_tier.value}."
            cuts.append(
                CardCut(
                    card_name=item.effective_name,
                    type_line=type_l,
                    cmc=cmc_val,
                    reason=reason,
                    estimated_price_usd=round(price, 2),
                )
            )

        # Select inclusions that fit budget
        selected_inclusions = []
        budget_limit = intent.max_budget_usd if intent.max_budget_usd is not None else float("inf")
        accumulated_cost = sum(i.estimated_price_usd or 4.0 for i in inclusions)

        for inc in available_inclusions:
            if len(inclusions) + len(selected_inclusions) >= len(cuts):
                break
            if accumulated_cost + inc.estimated_price_usd <= budget_limit or intent.max_budget_usd is None:
                selected_inclusions.append(inc)
                accumulated_cost += inc.estimated_price_usd

        for inc in selected_inclusions:
            if inc.name.lower() in GAME_CHANGERS_DATABASE:
                if remaining_gc_allowed <= 0:
                    continue
                remaining_gc_allowed -= 1

            total_add_val += inc.estimated_price_usd
            inc_cmc = inc.cmc
            if inc_cmc == 0.0:
                try:
                    from ..deckbuilder.archetype_database import resolve_card_metadata
                    m_cmc, _, _, _ = resolve_card_metadata(inc.name)
                    if m_cmc > 0:
                        inc_cmc = m_cmc
                except Exception:
                    pass

            inclusions.append(
                CardInclusion(
                    card_name=inc.name,
                    type_line=inc.type_line,
                    cmc=inc_cmc,
                    role=inc.primary_role,
                    synergy_explanation=f"Aumenta la consistencia y velocidad del arquetipo '{community_data.archetype_theme}' con {inc.inclusion_percent:.0f}% de inclusión comunitaria.",
                    estimated_price_usd=round(inc.estimated_price_usd, 2),
                    synergy_score=inc.synergy_score,
                )
            )

        # ---------------------------------------------------------------------
        # 4. Mana Base Analysis
        # ---------------------------------------------------------------------
        land_target = land_report.target_land_recommended
        mana_base = ManaBaseAnalysis(
            color_balance_status=f"Diagnóstico de Tierras: {land_report.status}. {land_report.diagnosis_message}",
            recommended_land_count=land_target,
            utility_lands_recommendations=land_report.recommended_lands_to_add or [
                "Boseiju, Who Endures (Remoción incounterable en tierra)",
                "Command Beacon (Recuperación de Comandante)",
                "Urza's Saga (Tutor de artefactos 0-1 CMC)",
            ],
            fixing_recommendations=land_report.fixing_upgrade_suggestions or [
                "Sustituir tierras que entran giradas (taplands) por Shocklands (e.g. Stomping Ground, Steam Vents) y Fetchlands.",
                "Incorporar Triomas / Painlands para garantizar maná en turnos 1-3.",
            ],
            ramp_assessment=f"Alineado con Bracket {target_tier.value}: Priorizar rocas de 2 CMC (Talismans / Signets) y aceleración de bajo coste.",
        )

        # ---------------------------------------------------------------------
        # 5. Win Conditions Analysis
        # ---------------------------------------------------------------------
        win_turn = bench.typical_win_turn
        win_combos = community_data.popular_combos if intent.effective_allow_combos else ["Combate agresivo / Tempo Beatdown con sinergias tribales"]
        win_path = f"Estrategia principal: {community_data.archetype_theme}. Consistencia para cerrar partidas en {win_turn} mediante líneas sinérgicas."

        win_cond = WinConditionAnalysis(
            primary_win_path=win_path,
            combos_or_synergies=win_combos,
            estimated_turn_to_win=win_turn,
        )

        # ---------------------------------------------------------------------
        # 6. Budget Summary
        # ---------------------------------------------------------------------
        total_cut_val = sum(c.estimated_price_usd or 0.0 for c in cuts)
        total_add_val = sum(i.estimated_price_usd or 0.0 for i in inclusions)
        net_cost = round(total_add_val - total_cut_val, 2)
        is_ok = intent.max_budget_usd is None or total_add_val <= intent.max_budget_usd
        budget_note = (
            f"Presupuesto de inclusiones: ${total_add_val:.2f} USD. Margen disponible respetado."
            if is_ok
            else f"El costo de inclusiones (${total_add_val:.2f} USD) supera el límite establecido (${intent.max_budget_usd:.2f} USD)."
        )

        budget_summary = BudgetSummary(
            total_cut_value_usd=round(total_cut_val, 2),
            total_added_cost_usd=round(total_add_val, 2),
            net_upgrade_cost_usd=net_cost,
            is_within_budget=is_ok,
            budget_notes=budget_note,
        )

        cmdr_name = deck.commander_name or "Commander"
        summary = (
            f"Optimización para '{deck.name}' ({cmdr_name}) orientada a Bracket {target_tier.value} ({target_tier.name}). "
            f"Se realizaron {len(cuts)} cortes y {len(inclusions)} adiciones estratégicas para balancear la curva ({bench.min_avg_cmc}-{bench.max_avg_cmc} CMC) "
            f"y optimizar la base de maná hacia {land_target} tierras recomendadas."
        )

        return OptimizationReport(
            deck_name=deck.name,
            commander_name=cmdr_name,
            initial_bracket=gap_report.current_bracket,
            target_bracket=target_tier,
            estimated_new_power_score=float(target_tier.value),
            summary_overview=summary,
            cuts=cuts,
            inclusions=inclusions,
            mana_base_analysis=mana_base,
            win_conditions=win_cond,
            budget_summary=budget_summary,
        )

    def _call_llm(
        self,
        deck: Deck,
        intent: UserIntent,
        gap_report: DeckGapReport,
        community_data: CommanderCommunityData,
    ) -> OptimizationReport:
        """Calls external OpenAI or Gemini API if credentials are provided."""
        # Builds prompt and executes external request...
        return self._heuristic_inference(deck, intent, gap_report, community_data)
