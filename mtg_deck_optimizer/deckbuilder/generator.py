"""
MTG Deckbuilder Generator Engine.
Builds tournament-grade, balanced 100-card Commander decks from scratch
strictly complying with WotC Commander rules, color identity, and bracket targets.
"""

import logging
import urllib.parse
from typing import List, Set, Dict, Any, Optional, Tuple

from ..models.card import Card, CardPrices, CardImageUris
from ..models.deck import Deck, DeckItem, DeckSection
from ..brackets.standards import BracketTier, BRACKET_BENCHMARKS
from ..brackets.game_changers import GAME_CHANGERS_DATABASE, GameChangerDefinition
from ..rules.wotc_rules_engine import WOTC_Commander_Rules_Engine
from ..scryfall.client import ScryfallClient
from ..exporter import DeckExporter
from .models import (
    DeckbuilderParams,
    CommanderSuggestion,
    GeneratedDeckResult,
    DeckRoleBreakdown,
)
from .archetype_database import (
    ARCHETYPE_DEFINITIONS,
    COLOR_STAPLES,
    CARD_METADATA_REGISTRY,
)

logger = logging.getLogger(__name__)


class MTGDeckbuilderGenerator:
    """
    Engine to synthesize complete, balanced 100-card Commander decks from scratch.
    """

    def __init__(self, scryfall_client: Optional[ScryfallClient] = None):
        self.scryfall_client = scryfall_client or ScryfallClient()
        self.rules_engine = WOTC_Commander_Rules_Engine(self.scryfall_client)

    def resolve_card_metadata(self, name: str) -> Card:
        """
        Fast in-memory card resolver using CARD_METADATA_REGISTRY with fallback to ScryfallClient.
        Always equips cards with high-res Scryfall direct image endpoints.
        """
        clean_name = self.scryfall_client.clean_card_name(name)
        n_lower = clean_name.lower()
        fallback_img = self.scryfall_client.get_card_image_url(clean_name)

        # 1. Fast in-memory metadata registry
        for reg_name, meta in CARD_METADATA_REGISTRY.items():
            if reg_name.lower() == n_lower:
                cmc, colors, type_line, price_usd = meta
                card_id = f"card_{reg_name.lower().replace(' ', '_').replace(',', '')}"
                return Card(
                    id=card_id,
                    name=reg_name,
                    cmc=cmc,
                    colors=colors,
                    color_identity=colors,
                    type_line=type_line,
                    prices=CardPrices(usd=price_usd),
                    image_uris=CardImageUris(
                        normal=fallback_img,
                        large=fallback_img,
                    ),
                    legalities={"commander": "legal"},
                )

        # 2. Query Scryfall Client (memory/disk/API)
        scry_card = self.scryfall_client.get_card_by_name(clean_name, fuzzy=True)
        if scry_card:
            if not scry_card.image_uris or not scry_card.image_uris.normal or "cards.scryfall.io/back.jpg" in (scry_card.image_uris.normal or ""):
                scry_card.image_uris = CardImageUris(normal=fallback_img, large=fallback_img)
            return scry_card

        # 3. Fallback lightweight stub with valid Scryfall image URL
        return Card(
            id=f"card_{n_lower.replace(' ', '_')}",
            name=clean_name,
            cmc=3.0,
            type_line="Legendary Creature",
            image_uris=CardImageUris(normal=fallback_img, large=fallback_img),
            legalities={"commander": "legal"},
        )

    def _resolve_archetype_key(self, strategy: str) -> str:
        if strategy in ARCHETYPE_DEFINITIONS:
            return strategy
        s_lower = strategy.strip().lower()
        for k in ARCHETYPE_DEFINITIONS:
            if k.lower() == s_lower or s_lower in k.lower() or k.lower() in s_lower:
                return k
        return list(ARCHETYPE_DEFINITIONS.keys())[0]

    def suggest_commanders(self, strategy: str, target_bracket: int = 3) -> List[CommanderSuggestion]:
        """Suggests top-tier commanders for a chosen strategy/archetype."""
        strat_key = self._resolve_archetype_key(strategy)
        archetype_data = ARCHETYPE_DEFINITIONS[strat_key]

        suggestions: List[CommanderSuggestion] = []
        for cmdr in archetype_data["commanders"]:
            clean_cmdr_name = cmdr["name"]
            img_url = self.scryfall_client.get_card_image_url(clean_cmdr_name)

            suggestions.append(
                CommanderSuggestion(
                    name=clean_cmdr_name,
                    color_identity=cmdr["color_identity"],
                    cmc=cmdr["cmc"],
                    type_line=cmdr["type_line"],
                    reason=cmdr["reason"],
                    typical_tier=cmdr.get("typical_tier", target_bracket),
                    image_url=img_url,
                )
            )
        return suggestions

    def build_deck(self, params: DeckbuilderParams) -> GeneratedDeckResult:
        """
        Builds a complete, 100-card legal Commander deck from scratch.
        Strictly enforces Color Identity, Singleton rules, and Target Bracket constraints.
        """
        strat_key = self._resolve_archetype_key(params.strategy_archetype)
        archetype_info = ARCHETYPE_DEFINITIONS[strat_key]
        strategy = strat_key
        target_tier = BracketTier(params.target_bracket)
        bench = BRACKET_BENCHMARKS[target_tier]

        # 1. Resolve Commander
        commander_name = params.commander_name
        if not commander_name or not commander_name.strip():
            commander_name = archetype_info["commanders"][0]["name"]

        cmdr_card = self.resolve_card_metadata(commander_name)
        cmdr_ci = self.rules_engine.extract_commander_color_identity([cmdr_card])
        
        # If commander was custom/unregistered and returned empty CI, check archetype or inferred colors
        if not cmdr_ci or cmdr_ci == ["C"]:
            # Check if any commander in the archetype matches
            matched = False
            for sc in archetype_info.get("commanders", []):
                if sc["name"].lower() == commander_name.strip().lower():
                    cmdr_ci = sc["color_identity"]
                    cmdr_card.color_identity = sc["color_identity"]
                    cmdr_card.colors = sc["color_identity"]
                    matched = True
                    break
            if not matched:
                # Default to archetype color identity if still unknown
                cmdr_ci = archetype_info.get("commanders", [{}])[0].get("color_identity", ["B", "R"])
                cmdr_card.color_identity = cmdr_ci
                cmdr_card.colors = cmdr_ci

        cmdr_ci_set = set(cmdr_ci)

        # Collections
        selected_maindeck: List[DeckItem] = []
        selected_names: Set[str] = {commander_name.strip().lower()}
        role_breakdown = DeckRoleBreakdown()

        # Game Changer Bracket Quotas
        max_game_changers_allowed = {
            1: 0,
            2: 0,
            3: 3,
            4: 99,
        }.get(params.target_bracket, 3)

        current_game_changers: List[str] = []

        def try_add_card(name: str, custom_role: str = "") -> bool:
            """Attempts to add a card if legal, strictly within commander color identity, and adhering to bracket quotas."""
            n_lower = name.strip().lower()
            if n_lower in selected_names and not self.rules_engine.is_singleton_exempt(name):
                return False

            # Check Game Changers Quota & Legality for Target Bracket
            gc_def = None
            for gck, gcd in GAME_CHANGERS_DATABASE.items():
                if gck.lower() == n_lower:
                    gc_def = gcd
                    break

            if gc_def is not None:
                # If card is not allowed at all in target bracket, reject
                if params.target_bracket not in gc_def.allowed_in_brackets:
                    return False
                # If adding this would exceed max allowed Game Changers for this bracket, reject
                if len(current_game_changers) >= max_game_changers_allowed:
                    return False

            card = self.resolve_card_metadata(name)

            # Strict Color Identity check via metadata registry & rules engine
            reg_colors = None
            for rk, rm in CARD_METADATA_REGISTRY.items():
                if rk.lower() == n_lower:
                    reg_colors = set(rm[1])
                    break
            
            if reg_colors is not None:
                # If registered card contains any color outside commander identity, reject immediately
                if any(c not in cmdr_ci_set for c in reg_colors if c in ("W", "U", "B", "R", "G")):
                    return False

            # Check Color Identity via rules engine
            is_c_legal, _ = self.rules_engine.validate_color_identity(card, cmdr_ci)
            if not is_c_legal:
                return False

            # Extra safety: check card.colors and card.color_identity directly
            if card.colors and any(c not in cmdr_ci_set for c in card.colors if c in ("W", "U", "B", "R", "G")):
                return False
            if card.color_identity and any(c not in cmdr_ci_set for c in card.color_identity if c in ("W", "U", "B", "R", "G")):
                return False

            # Check Banlist
            is_b_legal, _ = self.rules_engine.validate_banlist(card, fetch_remote=False)
            if not is_b_legal:
                return False

            # Check Budget Limit if active
            if params.max_budget_usd and card.prices and card.prices.usd:
                if params.max_budget_usd < 150.0 and card.prices.usd > 35.0:
                    return False

            # Passed all checks
            selected_maindeck.append(
                DeckItem(
                    raw_name=name,
                    quantity=1,
                    card=card,
                    section=DeckSection.MAINDECK,
                    custom_tags=[custom_role] if custom_role else [],
                )
            )
            selected_names.add(n_lower)
            if gc_def is not None:
                current_game_changers.append(gc_def.name)
            return True

        # 2. Core Strategy & Synergy Cards
        for syn_tuple in archetype_info.get("synergy_cards", []):
            card_name, t_line, c_cmc, c_colors, role_desc = syn_tuple
            # Strictly ensure ALL colors of this synergy card are within commander identity
            if any(c not in cmdr_ci_set for c in c_colors if c in ("W", "U", "B", "R", "G")):
                continue
            if try_add_card(card_name, custom_role=f"Synergy: {role_desc}"):
                role_breakdown.synergy_and_wincons += 1

        # 3. Ramp / Fast Mana Package
        ramp_target = bench.target_ramp_min
        if try_add_card("Sol Ring", "Ramp"):
            role_breakdown.ramp_and_mana += 1
        if len(cmdr_ci) >= 2 or cmdr_ci[0] != "C":
            if try_add_card("Arcane Signet", "Ramp"):
                role_breakdown.ramp_and_mana += 1
            if try_add_card("Fellwar Stone", "Ramp"):
                role_breakdown.ramp_and_mana += 1
            if try_add_card("Thought Vessel", "Ramp"):
                role_breakdown.ramp_and_mana += 1

        # Fast mana package (Carefully capped according to bracket quota)
        if params.target_bracket == 4:
            for fm in ["Mana Crypt", "Jeweled Lotus", "Mox Diamond", "Lion's Eye Diamond", "Mana Vault", "Chrome Mox", "Lotus Petal", "Mox Amber", "Mox Opal"]:
                if try_add_card(fm, "Fast Mana"):
                    role_breakdown.ramp_and_mana += 1
        elif params.target_bracket == 3:
            # Bracket 3: Include legal fast mana only up to bracket game changer quota
            for fm in ["Lotus Petal", "Mox Amber", "Chrome Mox"]:
                if try_add_card(fm, "Fast Mana"):
                    role_breakdown.ramp_and_mana += 1

        for col in cmdr_ci:
            if col in COLOR_STAPLES and "ramp" in COLOR_STAPLES[col]:
                for r_name, _ in COLOR_STAPLES[col]["ramp"]:
                    if role_breakdown.ramp_and_mana >= ramp_target:
                        break
                    if try_add_card(r_name, "Ramp"):
                        role_breakdown.ramp_and_mana += 1

        # 4. Card Draw & Engines
        for col in cmdr_ci:
            if col in COLOR_STAPLES:
                for dk in ["draw", "draw_tax", "impulse_mana"]:
                    if dk in COLOR_STAPLES[col]:
                        for d_name, _ in COLOR_STAPLES[col][dk]:
                            if try_add_card(d_name, "Card Draw"):
                                role_breakdown.card_draw_and_engines += 1

        for util_name, _ in COLOR_STAPLES.get("Colorless", {}).get("utility", []):
            if try_add_card(util_name, "Utility / Draw"):
                role_breakdown.card_draw_and_engines += 1

        # 5. Targeted Removal & Interaction
        for col in cmdr_ci:
            if col in COLOR_STAPLES:
                for rem_key in ["removal", "counters", "protection_combos"]:
                    if rem_key in COLOR_STAPLES[col]:
                        for rem_name, _ in COLOR_STAPLES[col][rem_key]:
                            if try_add_card(rem_name, "Interaction"):
                                role_breakdown.targeted_removal += 1

        # 6. Tutors (Scaled to Bracket)
        max_tutors = 0
        if params.target_bracket == 2:
            max_tutors = 1
        elif params.target_bracket == 3:
            max_tutors = 4
        elif params.target_bracket == 4:
            max_tutors = 8

        tutor_count = 0
        if max_tutors > 0:
            for col in cmdr_ci:
                if col in COLOR_STAPLES and "tutors" in COLOR_STAPLES[col]:
                    for t_name, _ in COLOR_STAPLES[col]["tutors"]:
                        if tutor_count >= max_tutors:
                            break
                        if try_add_card(t_name, "Tutor"):
                            role_breakdown.tutors += 1
                            tutor_count += 1

        # 7. Calculate Lands Needed to reach EXACTLY 99 Maindeck Cards
        target_lands_benchmark = (bench.target_lands_min + bench.target_lands_max) // 2
        max_spells = 99 - target_lands_benchmark

        if len(selected_maindeck) > max_spells:
            selected_maindeck = selected_maindeck[:max_spells]

        lands_needed = 99 - len(selected_maindeck)

        # 8. Assemble Mana Base strictly adhering to Color Identity
        added_lands = 0

        # Multi-color fixing lands (only if 2+ colors)
        if len(cmdr_ci) >= 2:
            for fc in ["Command Tower", "Exotic Orchard", "Path of Ancestry", "City of Brass", "Mana Confluence", "Reflecting Pool"]:
                if added_lands >= lands_needed:
                    break
                if try_add_card(fc, "Land"):
                    added_lands += 1
                    role_breakdown.lands += 1

            # Dual lands & Fetch lands for color pairs in commander identity
            dual_land_map = {
                ("W", "U"): ["Hallowed Fountain", "Flooded Strand"],
                ("W", "B"): ["Godless Shrine", "Marsh Flats"],
                ("W", "R"): ["Sacred Foundry", "Arid Mesa"],
                ("W", "G"): ["Temple Garden", "Windswept Heath"],
                ("U", "B"): ["Watery Grave", "Polluted Delta"],
                ("U", "R"): ["Steam Vents", "Scalding Tarn"],
                ("U", "G"): ["Breeding Pool", "Misty Rainforest"],
                ("B", "R"): ["Blood Crypt", "Bloodstained Mire"],
                ("B", "G"): ["Overgrown Tomb", "Verdant Catacombs"],
                ("R", "G"): ["Stomping Ground", "Wooded Foothills"],
            }
            ci_list = sorted([c for c in cmdr_ci if c in ("W", "U", "B", "R", "G")])
            for i in range(len(ci_list)):
                for j in range(i + 1, len(ci_list)):
                    pair = (ci_list[i], ci_list[j])
                    if pair in dual_land_map:
                        for d_land in dual_land_map[pair]:
                            if added_lands >= lands_needed:
                                break
                            if try_add_card(d_land, "Dual Land"):
                                added_lands += 1
                                role_breakdown.lands += 1

        # Channel & Color-Specific Utility Lands (ONLY if color is in commander CI)
        channel_lands = {
            "W": ["Eiganjo, Seat of the Empire"],
            "U": ["Otawara, Soaring City"],
            "B": ["Takenuma, Abandoned Mire"],
            "R": ["Sokenzan, Crucible of Defiance"],
            "G": ["Boseiju, Who Endures"],
        }
        for col in cmdr_ci:
            if col in channel_lands:
                for c_land in channel_lands[col]:
                    if added_lands >= lands_needed:
                        break
                    if try_add_card(c_land, "Utility Land"):
                        added_lands += 1
                        role_breakdown.lands += 1

        # Colorless Utility Lands (safe in all decks)
        for ul in ["Reliquary Tower", "Ancient Tomb", "Urza's Saga", "Strip Mine", "Scavenger Grounds", "War Room", "Command Beacon"]:
            if added_lands >= lands_needed:
                break
            if try_add_card(ul, "Utility Land"):
                added_lands += 1
                role_breakdown.lands += 1

        # Basic Lands (strictly for active colors in commander identity)
        remaining_basics = max(0, lands_needed - added_lands)
        color_to_basic = {
            "W": "Plains",
            "U": "Island",
            "B": "Swamp",
            "R": "Mountain",
            "G": "Forest",
            "C": "Wastes",
        }

        active_colors = [c for c in cmdr_ci if c in color_to_basic and c != "C"] or ["Wastes"]
        basics_per_color = remaining_basics // len(active_colors)
        basics_remainder = remaining_basics % len(active_colors)

        for idx, col in enumerate(active_colors):
            b_name = color_to_basic[col]
            count = basics_per_color + (1 if idx < basics_remainder else 0)
            if count > 0:
                b_card = self.resolve_card_metadata(b_name)
                selected_maindeck.append(
                    DeckItem(
                        raw_name=b_name,
                        quantity=count,
                        card=b_card,
                        section=DeckSection.MAINDECK,
                        custom_tags=["Basic Land"],
                    )
                )
                role_breakdown.lands += count

        # Guarantee exact 99 maindeck cards (100 total with commander)
        current_main_count = sum(it.quantity for it in selected_maindeck)
        if current_main_count < 99:
            missing_cards = 99 - current_main_count
            active_cols = [c for c in cmdr_ci if c in color_to_basic and c != "C"] or ["Wastes"]
            for m_idx in range(missing_cards):
                m_col = active_cols[m_idx % len(active_cols)]
                b_name = color_to_basic[m_col]
                b_card = self.resolve_card_metadata(b_name)
                found_b = next((it for it in selected_maindeck if it.effective_name.lower() == b_name.lower()), None)
                if found_b:
                    found_b.quantity += 1
                else:
                    selected_maindeck.append(
                        DeckItem(
                            raw_name=b_name,
                            quantity=1,
                            card=b_card,
                            section=DeckSection.MAINDECK,
                            custom_tags=["Basic Land"],
                        )
                    )
                role_breakdown.lands += 1

        # 9. Build Deck Object
        cmdr_item = DeckItem(
            raw_name=cmdr_card.name,
            quantity=1,
            card=cmdr_card,
            section=DeckSection.COMMANDER,
        )

        final_deck = Deck(
            name=f"{cmdr_card.name} — {strategy} (Bracket {params.target_bracket})",
            format="commander",
            commanders=[cmdr_item],
            maindeck=selected_maindeck,
        )

        # 10. Audit with WotC Commander Rules Engine
        validation = self.rules_engine.validate_deck(final_deck)

        # 11. Calculate Financials & Average CMC
        total_price = sum((it.total_price_usd or 0.0) for it in [cmdr_item] + selected_maindeck)
        non_land_spells = [it for it in selected_maindeck if it.card and "Land" not in it.card.type_line]
        total_cmc = sum((it.card.cmc * it.quantity) for it in non_land_spells if it.card)
        spell_count = sum(it.quantity for it in non_land_spells)
        avg_cmc = round(total_cmc / spell_count, 2) if spell_count > 0 else 2.5

        # 12. Export Text
        exporter = DeckExporter()
        export_text = exporter.export_to_text(final_deck)

        return GeneratedDeckResult(
            deck=final_deck,
            commander=cmdr_card,
            bracket=target_tier,
            strategy=strategy,
            total_price_usd=round(total_price, 2),
            average_cmc=avg_cmc,
            role_breakdown=role_breakdown,
            suggested_commanders=self.suggest_commanders(strategy, params.target_bracket),
            key_combos_or_synergies=archetype_info.get("combos", []),
            validation=validation,
            export_text=export_text,
        )


# Convenient Alias
MTG_Deckbuilder_Generator = MTGDeckbuilderGenerator
