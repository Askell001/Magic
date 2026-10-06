"""
Post-AI Integrity Middleware validating all AI suggestions against Commander rules,
Color Identity, Singleton constraints, and Banlists before returning to user.
"""

import logging
from typing import List, Set, Optional, Tuple

from ..models.deck import Deck
from ..models.card import Card, CardPrices
from ..ai.models import OptimizationReport, CardInclusion, CardCut
from ..ai.community_data import CommunityDataService, SynergyCard
from ..scryfall.client import ScryfallClient
from .color_identity import ColorIdentityExtractor
from .legality import SingletonValidator, BanlistValidator

logger = logging.getLogger(__name__)


def validate_recommendations(
    deck: Deck,
    report: OptimizationReport,
    untouchable_cards: Optional[List[str]] = None,
    scryfall_client: Optional[ScryfallClient] = None,
) -> OptimizationReport:
    """
    Middleware function that audits and cleans all AI recommendations.
    Enforces:
    1. Strict Color Identity (including hybrid mana restrictions).
    2. Format Legality & Official Commander Banlist.
    3. Singleton rule (no duplicates of non-basic cards).
    4. Untouchable cards protection in cuts.

    Any invalid suggestion is automatically removed or replaced by a legal alternative.
    """
    client = scryfall_client or ScryfallClient()

    commander_cards = [it.card for it in deck.commanders if it.card]
    if commander_cards:
        cmdr_ci = ColorIdentityExtractor.compute_commander_color_identity(commander_cards)
    else:
        cmdr_ci = deck.color_identity

    existing_names: Set[str] = {it.effective_name.strip().lower() for it in deck.commanders + deck.maindeck}
    untouchables_set = set(c.strip().lower() for c in (untouchable_cards or []))

    valid_inclusions: List[CardInclusion] = []
    seen_inclusion_names: Set[str] = set()
    audit_logs: List[str] = []

    # 1. Audit Inclusions
    for inc in report.inclusions:
        inc_name_lower = inc.card_name.strip().lower()

        # Resolve card data from Scryfall or build fallback
        resolved_card = client.get_card_by_name(inc.card_name)
        if not resolved_card:
            resolved_card = Card(
                id=f"audit_{inc_name_lower.replace(' ', '_')}",
                name=inc.card_name,
                cmc=inc.cmc,
                type_line=inc.type_line,
                prices=CardPrices(usd=inc.estimated_price_usd),
            )

        # Check Color Identity (strictly with hybrid mana rules)
        is_color_legal, color_err = ColorIdentityExtractor.validate_color_identity(resolved_card, cmdr_ci)
        if not is_color_legal:
            audit_logs.append(f"❌ [Rechazado por Identidad de Color]: {color_err}")
            continue

        # Check Banlist
        is_banned, ban_err = BanlistValidator.is_banned_in_commander(resolved_card)
        if is_banned:
            audit_logs.append(f"❌ [Rechazado por Banlist]: {ban_err}")
            continue

        # Check Singleton
        if inc_name_lower in existing_names and not SingletonValidator.is_singleton_exempt(inc.card_name):
            audit_logs.append(
                f"❌ [Rechazado por Singleton]: '{inc.card_name}' ya está presente en el mazo original."
            )
            continue

        if inc_name_lower in seen_inclusion_names and not SingletonValidator.is_singleton_exempt(inc.card_name):
            audit_logs.append(
                f"❌ [Rechazado por Duplicado]: '{inc.card_name}' fue sugerida más de una vez en las inclusiones."
            )
            continue

        # Validated inclusion
        valid_inclusions.append(inc)
        seen_inclusion_names.add(inc_name_lower)

    # 2. Audit Cuts (Ensure no untouchables are cut)
    valid_cuts: List[CardCut] = []
    for cut in report.cuts:
        cut_name_lower = cut.card_name.strip().lower()
        if cut_name_lower in untouchables_set:
            audit_logs.append(
                f"🛡️ [Corte Anulado]: '{cut.card_name}' está en la lista de cartas intocables y fue preservada."
            )
            continue
        valid_cuts.append(cut)

    # 3. If any inclusion was discarded, try to backfill with a legal community staple
    if len(valid_inclusions) < len(valid_cuts):
        comm_service = CommunityDataService()
        primary_cmdr_name = deck.commanders[0].effective_name if deck.commanders else "Unknown Commander"
        cmdr_data = comm_service.get_commander_data(primary_cmdr_name, color_identity=cmdr_ci)
        
        candidates = cmdr_data.top_synergy_cards + cmdr_data.top_staples
        for cand in candidates:
            if len(valid_inclusions) >= len(valid_cuts):
                break
            c_name_lower = cand.name.strip().lower()
            if c_name_lower in existing_names or c_name_lower in seen_inclusion_names:
                continue
            
            cand_card = client.get_card_by_name(cand.name)
            if not cand_card:
                cand_card = Card(
                    id=f"backfill_{c_name_lower.replace(' ', '_')}",
                    name=cand.name,
                    cmc=cand.cmc,
                    type_line=cand.type_line,
                    colors=ColorIdentityExtractor.extract_colors_from_symbol_string(cand.type_line),
                    prices=CardPrices(usd=cand.estimated_price_usd),
                )

            is_c_legal, _ = ColorIdentityExtractor.validate_color_identity(cand_card, cmdr_ci)
            is_c_banned, _ = BanlistValidator.is_banned_in_commander(cand_card)
            
            if is_c_legal and not is_c_banned:
                new_inc = CardInclusion(
                    card_name=cand.name,
                    type_line=cand.type_line,
                    cmc=cand.cmc,
                    role=cand.primary_role,
                    synergy_explanation=f"Sustituto legal validado por el filtro de reglas con {cand.inclusion_percent:.0f}% de inclusión comunitaria.",
                    estimated_price_usd=cand.estimated_price_usd,
                    synergy_score=cand.synergy_score,
                )
                valid_inclusions.append(new_inc)
                seen_inclusion_names.add(c_name_lower)
                audit_logs.append(f"✨ [Sustituto Legal Añadido]: '{cand.name}' incorporada para mantener el balance de cartas.")

    # 4. Update Report
    report.cuts = valid_cuts
    report.inclusions = valid_inclusions

    # Recalculate financial summary
    total_cut_val = sum((c.estimated_price_usd or 0.0) for c in valid_cuts)
    total_add_val = sum((i.estimated_price_usd or 0.0) for i in valid_inclusions)
    report.budget_summary.total_cut_value_usd = round(total_cut_val, 2)
    report.budget_summary.total_added_cost_usd = round(total_add_val, 2)
    report.budget_summary.net_upgrade_cost_usd = round(total_add_val - total_cut_val, 2)

    # Append audit logs if any rule adjustments were made
    if audit_logs:
        log_block = "\n\n[AUDITORÍA DE REGLAS DE COMMANDER / COLOR IDENTITY]:\n" + "\n".join(audit_logs)
        report.summary_overview += log_block

    return report
