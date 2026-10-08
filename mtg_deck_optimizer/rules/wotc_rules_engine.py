"""
WOTC_Commander_Rules_Engine: Official MTG Commander Rules Engine.
Validates Color Identity, Real-Time Banlists (via Scryfall API),
Singleton Constraints, Land Rules, and acts as a strict Middleware Filter.
"""

import logging
from typing import List, Set, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field

from ..models.card import Card, CardPrices
from ..models.deck import Deck, DeckItem
from ..ai.models import OptimizationReport, CardInclusion, CardCut
from ..ai.community_data import CommunityDataService
from ..scryfall.client import ScryfallClient
from .color_identity import ColorIdentityExtractor, WUBRG_ORDER
from .legality import (
    SingletonValidator,
    BanlistValidator,
    BASIC_LANDS,
    UNLIMITED_COPY_CARDS,
    OFFICIAL_COMMANDER_BANLIST,
)

logger = logging.getLogger(__name__)


class CardLegalityResult(BaseModel):
    """Detailed legality verdict for an individual card in a Commander deck context."""
    card_name: str
    is_legal: bool
    color_identity: List[str] = Field(default_factory=list)
    commander_identity: List[str] = Field(default_factory=list)
    is_color_legal: bool = True
    is_banlist_legal: bool = True
    is_singleton_legal: bool = True
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class RuleViolation(BaseModel):
    rule_name: str = "WotC Rule"
    rule_type: str = "WotC Rule"
    offending_card: str = ""
    explanation: str = ""
    message: str = ""


class DeckValidationResult(BaseModel):
    """Complete diagnostic report for an entire Commander deck."""
    deck_name: str
    commander_names: List[str]
    commander_color_identity: List[str]
    total_cards: int
    is_fully_legal: bool
    color_identity_errors: List[str] = Field(default_factory=list)
    banlist_errors: List[str] = Field(default_factory=list)
    singleton_errors: List[str] = Field(default_factory=list)
    general_errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    @property
    def is_legal(self) -> bool:
        return self.is_fully_legal

    @property
    def violations(self) -> List[RuleViolation]:
        v_list = []
        for e in self.color_identity_errors:
            v_list.append(RuleViolation(rule_name="Color Identity", rule_type="Color Identity", explanation=e, message=e))
        for e in self.banlist_errors:
            v_list.append(RuleViolation(rule_name="Banlist", rule_type="Banlist", explanation=e, message=e))
        for e in self.singleton_errors:
            v_list.append(RuleViolation(rule_name="Singleton", rule_type="Singleton", explanation=e, message=e))
        for e in self.general_errors:
            v_list.append(RuleViolation(rule_name="Regla WotC", rule_type="Regla WotC", explanation=e, message=e))
        return v_list

    @property
    def all_errors(self) -> List[str]:
        return (
            self.color_identity_errors
            + self.banlist_errors
            + self.singleton_errors
            + self.general_errors
        )


class WOTC_Commander_Rules_Engine:
    """
    Official Wizards of the Coast (WotC) Commander Rules Engine.
    
    Provides strict validation against MTG Comprehensive Rules:
    1. Strict Color Identity (CR 903.4) and Hybrid Mana Rules.
    2. Real-Time Scryfall Banlist Subscription (legalities.commander == 'legal') and Curated Official Banlist.
    3. Singleton Rule (CR 100.2a) and Basic Lands / Text-Exempt Exceptions.
    4. Middleware Sanitization: Discards any illegal recommendation before presenting to the user.
    """

    def __init__(self, scryfall_client: Optional[ScryfallClient] = None):
        self.scryfall_client = scryfall_client or ScryfallClient()
        self.community_service = CommunityDataService()

    # =========================================================================
    # 1. COLOR IDENTITY EXTRACTION & ENFORCEMENT
    # =========================================================================

    def extract_commander_color_identity(self, commander_cards: List[Card]) -> List[str]:
        """
        Extracts the aggregate Color Identity of the Commander(s) by analyzing:
        - Mana casting costs
        - Rules text mana symbols (excluding reminder text like Extort)
        - Multi-faced / Transform cards (DFCs, MDFCs)
        - Color indicators and alternative costs
        """
        return ColorIdentityExtractor.compute_commander_color_identity(commander_cards)

    def extract_card_color_identity(self, card: Card) -> List[str]:
        """Calculates the verified Color Identity of any individual card."""
        return ColorIdentityExtractor.compute_card_color_identity(card)

    def validate_color_identity(
        self,
        card: Card,
        commander_identity: List[str],
    ) -> Tuple[bool, Optional[str]]:
        """
        Strictly verifies that a card's color identity is a subset of the Commander's identity.
        Enforces that Hybrid Mana symbols (e.g., {R/G}) belong to both colors.
        """
        return ColorIdentityExtractor.validate_color_identity(card, commander_identity)

    # =========================================================================
    # 2. REAL-TIME BANLIST & FORMAT LEGALITY
    # =========================================================================

    def validate_banlist(self, card: Card, fetch_remote: bool = True) -> Tuple[bool, Optional[str]]:
        """
        Checks if a card is legal in Commander against Scryfall API legalities and official banlist.
        Returns: (is_legal, error_reason_if_illegal)
        """
        if not card.legalities and fetch_remote and card.name:
            resolved = self.scryfall_client.get_card_by_name(card.name)
            if resolved and resolved.legalities:
                card.legalities = resolved.legalities

        is_banned, ban_reason = BanlistValidator.is_banned_in_commander(card)
        if is_banned:
            return False, ban_reason
        return True, None

    # =========================================================================
    # 3. SINGLETON & LAND RULES
    # =========================================================================

    def is_singleton_exempt(self, card_name: str, requested_quantity: int = 1) -> bool:
        """Checks if a card is exempt from the 1-copy limit (Basic Lands, Relentless Rats, etc.)."""
        return SingletonValidator.is_singleton_exempt(card_name, requested_quantity)

    def validate_singleton(self, deck: Deck) -> List[str]:
        """Scans the deck for duplicate non-exempt cards."""
        return SingletonValidator.validate_deck_singleton(deck)

    # =========================================================================
    # 4. CARD-LEVEL & DECK-LEVEL DIAGNOSTICS
    # =========================================================================

    def validate_card(
        self,
        card: Card,
        commander_identity: List[str],
    ) -> CardLegalityResult:
        """Runs the complete suite of Commander rules on a single card."""
        errors: List[str] = []
        warnings: List[str] = []

        card_ci = self.extract_card_color_identity(card)
        
        # Color Identity Check
        is_color_legal, color_err = self.validate_color_identity(card, commander_identity)
        if not is_color_legal and color_err:
            errors.append(color_err)

        # Banlist Check
        is_banlist_legal, ban_err = self.validate_banlist(card)
        if not is_banlist_legal and ban_err:
            errors.append(ban_err)

        return CardLegalityResult(
            card_name=card.name,
            is_legal=len(errors) == 0,
            color_identity=card_ci,
            commander_identity=commander_identity,
            is_color_legal=is_color_legal,
            is_banlist_legal=is_banlist_legal,
            is_singleton_legal=True,
            errors=errors,
            warnings=warnings,
        )

    def validate_deck(self, deck: Deck) -> DeckValidationResult:
        """
        Performs a full audit of an entire Commander deck against all WotC Commander rules.
        """
        commander_cards = [it.card for it in deck.commanders if it.card]
        if commander_cards:
            cmdr_ci = self.extract_commander_color_identity(commander_cards)
        else:
            cmdr_ci = deck.color_identity

        cmdr_names = [it.effective_name for it in deck.commanders]
        color_errors: List[str] = []
        ban_errors: List[str] = []
        general_errors: List[str] = []
        warnings: List[str] = []

        # 1. Validate Commander Presence
        if not deck.commanders:
            general_errors.append("El mazo no tiene ningún Comandante designado.")

        # 2. Validate Singleton
        singleton_errors = self.validate_singleton(deck)

        # 3. Validate Each Card in Deck
        all_items = deck.commanders + deck.maindeck
        for it in all_items:
            card = it.card or self.scryfall_client.get_card_by_name(it.effective_name)
            if not card:
                card = Card(
                    id=f"check_{it.effective_name.lower().replace(' ', '_')}",
                    name=it.effective_name,
                )

            # Color Identity Check
            is_c_legal, c_err = self.validate_color_identity(card, cmdr_ci)
            if not is_c_legal and c_err:
                color_errors.append(c_err)

            # Banlist Check
            is_b_legal, b_err = self.validate_banlist(card)
            if not is_b_legal and b_err:
                ban_errors.append(b_err)

        # 4. Total Card Count Validation (Commander standard is 100 cards)
        total_qty = deck.total_card_count
        if total_qty != 100:
            warnings.append(
                f"El mazo contiene {total_qty} cartas en total. El estándar oficial de Commander es exactamente 100 cartas (1 Comandante + 99 cartas)."
            )

        is_fully_legal = (
            len(color_errors) == 0
            and len(ban_errors) == 0
            and len(singleton_errors) == 0
            and len(general_errors) == 0
        )

        return DeckValidationResult(
            deck_name=deck.name,
            commander_names=cmdr_names,
            commander_color_identity=cmdr_ci,
            total_cards=total_qty,
            is_fully_legal=is_fully_legal,
            color_identity_errors=color_errors,
            banlist_errors=ban_errors,
            singleton_errors=singleton_errors,
            general_errors=general_errors,
            warnings=warnings,
        )

    # =========================================================================
    # 5. MIDDLEWARE FILTER: SANITIZE RECOMMENDATIONS
    # =========================================================================

    def sanitize_recommendations(
        self,
        deck: Deck,
        report: OptimizationReport,
        untouchable_cards: Optional[List[str]] = None,
    ) -> OptimizationReport:
        """
        Middleware filter that intercepts all AI suggestions and proposed deck changes.
        Discards any card violating WotC Commander rules automatically before presenting to the user.
        """
        commander_cards = []
        for it in deck.commanders:
            c = it.card or self.scryfall_client.get_card_by_name(it.effective_name)
            if c:
                commander_cards.append(c)

        if commander_cards:
            cmdr_ci = self.extract_commander_color_identity(commander_cards)
        else:
            cmdr_ci = deck.color_identity or ["C"]

        existing_names: Set[str] = {
            it.effective_name.strip().lower() for it in deck.commanders + deck.maindeck
        }
        untouchables_set = set(c.strip().lower() for c in (untouchable_cards or []))

        valid_inclusions: List[CardInclusion] = []
        seen_inclusion_names: Set[str] = set()
        audit_logs: List[str] = []

        # 1. Audit Inclusions
        for inc in report.inclusions:
            inc_name_lower = inc.card_name.strip().lower()

            resolved_card = self.scryfall_client.get_card_by_name(inc.card_name)
            if not resolved_card:
                from ..deckbuilder.archetype_database import CARD_METADATA_REGISTRY
                meta = next((v for k, v in CARD_METADATA_REGISTRY.items() if k.lower() == inc_name_lower), None)
                if meta:
                    cmc_v, cols_v, tl_v, price_v = meta
                    resolved_card = Card(
                        id=f"audit_{inc_name_lower.replace(' ', '_')}",
                        name=inc.card_name,
                        cmc=cmc_v,
                        colors=cols_v,
                        color_identity=cols_v,
                        type_line=tl_v,
                        prices=CardPrices(usd=price_v),
                    )
                else:
                    resolved_card = Card(
                        id=f"audit_{inc_name_lower.replace(' ', '_')}",
                        name=inc.card_name,
                        cmc=inc.cmc,
                        type_line=inc.type_line,
                        prices=CardPrices(usd=inc.estimated_price_usd),
                    )

            # Check Color Identity
            is_color_legal, color_err = self.validate_color_identity(resolved_card, cmdr_ci)
            if not is_color_legal:
                audit_logs.append(f"❌ [WotC Rules Engine - Rechazado por Identidad de Color]: {color_err}")
                continue

            # Check Banlist
            is_ban_legal, ban_err = self.validate_banlist(resolved_card)
            if not is_ban_legal:
                audit_logs.append(f"❌ [WotC Rules Engine - Rechazado por Banlist]: {ban_err}")
                continue

            # Check Singleton against current deck
            if inc_name_lower in existing_names and not self.is_singleton_exempt(inc.card_name):
                audit_logs.append(
                    f"❌ [WotC Rules Engine - Rechazado por Singleton]: '{inc.card_name}' ya está presente en el mazo original."
                )
                continue

            # Check Duplicate Inclusions
            if inc_name_lower in seen_inclusion_names and not self.is_singleton_exempt(inc.card_name):
                audit_logs.append(
                    f"❌ [WotC Rules Engine - Rechazado por Duplicado]: '{inc.card_name}' fue sugerida más de una vez en las inclusiones."
                )
                continue

            # Card is fully legal
            valid_inclusions.append(inc)
            seen_inclusion_names.add(inc_name_lower)

        # 2. Audit Cuts (Protect untouchables)
        valid_cuts: List[CardCut] = []
        for cut in report.cuts:
            cut_name_lower = cut.card_name.strip().lower()
            if cut_name_lower in untouchables_set:
                audit_logs.append(
                    f"🛡️ [WotC Rules Engine - Corte Anulado]: '{cut.card_name}' está protegida en la lista de intocables."
                )
                continue
            valid_cuts.append(cut)

        # 3. Backfill Discarded Inclusions with Legal Community Staples
        if len(valid_inclusions) < len(valid_cuts):
            primary_cmdr_name = deck.commanders[0].effective_name if deck.commanders else "Unknown Commander"
            cmdr_data = self.community_service.get_commander_data(primary_cmdr_name, color_identity=cmdr_ci)
            candidates = cmdr_data.top_synergy_cards + cmdr_data.top_staples

            for cand in candidates:
                if len(valid_inclusions) >= len(valid_cuts):
                    break
                c_name_lower = cand.name.strip().lower()
                if c_name_lower in existing_names or c_name_lower in seen_inclusion_names:
                    continue

                cand_card = self.scryfall_client.get_card_by_name(cand.name)
                if not cand_card:
                    cand_card = Card(
                        id=f"backfill_{c_name_lower.replace(' ', '_')}",
                        name=cand.name,
                        cmc=cand.cmc,
                        type_line=cand.type_line,
                        prices=CardPrices(usd=cand.estimated_price_usd),
                    )

                is_c_legal, _ = self.validate_color_identity(cand_card, cmdr_ci)
                is_b_legal, _ = self.validate_banlist(cand_card)

                if is_c_legal and is_b_legal:
                    new_inc = CardInclusion(
                        card_name=cand.name,
                        type_line=cand.type_line,
                        cmc=cand.cmc,
                        role=cand.primary_role,
                        synergy_explanation=f"Sustituto legal validado por WotC Rules Engine con {cand.inclusion_percent:.0f}% de inclusión comunitaria.",
                        estimated_price_usd=cand.estimated_price_usd,
                        synergy_score=cand.synergy_score,
                    )
                    valid_inclusions.append(new_inc)
                    seen_inclusion_names.add(c_name_lower)
                    audit_logs.append(
                        f"✨ [WotC Rules Engine - Sustituto Legal Añadido]: '{cand.name}' incorporada para mantener el balance."
                    )

        # 4. Reconstruct Report
        report.cuts = valid_cuts
        report.inclusions = valid_inclusions

        total_cut_val = sum((c.estimated_price_usd or 0.0) for c in valid_cuts)
        total_add_val = sum((i.estimated_price_usd or 0.0) for i in valid_inclusions)
        report.budget_summary.total_cut_value_usd = round(total_cut_val, 2)
        report.budget_summary.total_added_cost_usd = round(total_add_val, 2)
        report.budget_summary.net_upgrade_cost_usd = round(total_add_val - total_cut_val, 2)

        if audit_logs:
            log_block = "\n\n[WOTC_COMMANDER_RULES_ENGINE AUDIT LOG]:\n" + "\n".join(audit_logs)
            report.summary_overview += log_block

        return report


# Convenient Aliases
WotcCommanderRulesEngine = WOTC_Commander_Rules_Engine
