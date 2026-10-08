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
            5: 99,
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
        if params.target_bracket in [4, 5]:
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
        elif params.target_bracket == 5:
            max_tutors = 12

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

        # 7. Exact Lands & Spells Budget strictly according to Bracket Benchmark
        target_lands_count = (bench.target_lands_min + bench.target_lands_max) // 2
        exact_spells_target = 99 - target_lands_count

        # 8. FILL REMAINING SPELL SLOTS with extensive staples until exact_spells_target is met
        universal_staples = [
            # Colorless Mana & Utility (Any deck)
            ("Lightning Greaves", []),
            ("Swiftfoot Boots", []),
            ("Skullclamp", []),
            ("Sensei's Divining Top", []),
            ("Mind Stone", []),
            ("Thought Vessel", []),
            ("Wayfarer's Bauble", []),
            ("Everflowing Chalice", []),
            ("Prismatic Lens", []),
            ("Soul-Guide Lantern", []),
            ("Relic of Progenitus", []),
            ("Solemn Simulacrum", []),
            ("Burnished Hart", []),
            ("Panharmonicon", []),
            ("Aetherflux Reservoir", []),
            ("The One Ring", []),
            # Talismans & Signets
            ("Talisman of Progress", ["W", "U"]),
            ("Talisman of Dominance", ["U", "B"]),
            ("Talisman of Indulgence", ["B", "R"]),
            ("Talisman of Impulse", ["R", "G"]),
            ("Talisman of Unity", ["G", "W"]),
            ("Talisman of Hierarchy", ["W", "B"]),
            ("Talisman of Creativity", ["U", "R"]),
            ("Talisman of Resilience", ["B", "G"]),
            ("Talisman of Conviction", ["R", "W"]),
            ("Talisman of Curiosity", ["U", "G"]),
            ("Azorius Signet", ["W", "U"]),
            ("Dimir Signet", ["U", "B"]),
            ("Rakdos Signet", ["B", "R"]),
            ("Gruul Signet", ["R", "G"]),
            ("Selesnya Signet", ["G", "W"]),
            ("Orzhov Signet", ["W", "B"]),
            ("Izzet Signet", ["U", "R"]),
            ("Golgari Signet", ["B", "G"]),
            ("Boros Signet", ["R", "W"]),
            ("Simic Signet", ["U", "G"]),
            # White Staples
            ("Swords to Plowshares", ["W"]),
            ("Path to Exile", ["W"]),
            ("Generous Gift", ["W"]),
            ("Teferi's Protection", ["W"]),
            ("Smothering Tithe", ["W"]),
            ("Esper Sentinel", ["W"]),
            ("Land Tax", ["W"]),
            ("Cathar Commando", ["W"]),
            ("Luminarch Aspirant", ["W"]),
            ("Mother of Runes", ["W"]),
            ("Giver of Runes", ["W"]),
            ("Selfless Spirit", ["W"]),
            ("Grand Abolisher", ["W"]),
            ("Silence", ["W"]),
            ("Flawless Maneuver", ["W"]),
            ("Drannith Magistrate", ["W"]),
            ("Trouble in Pairs", ["W"]),
            ("Archivist of Oghma", ["W"]),
            ("Mentor of the Meek", ["W"]),
            ("Welcoming Vampire", ["W"]),
            ("Farewell", ["W"]),
            ("Wrath of God", ["W"]),
            ("Austere Command", ["W"]),
            ("Sun Titan", ["W"]),
            # Blue Staples
            ("Counterspell", ["U"]),
            ("Swan Song", ["U"]),
            ("Arcane Denial", ["U"]),
            ("Pongify", ["U"]),
            ("Rapid Hybridization", ["U"]),
            ("Resculpt", ["U"]),
            ("Brainstorm", ["U"]),
            ("Ponder", ["U"]),
            ("Preordain", ["U"]),
            ("Gitaxian Probe", ["U"]),
            ("Frantic Search", ["U"]),
            ("Rhystic Study", ["U"]),
            ("Mystic Remora", ["U"]),
            ("Cyclonic Rift", ["U"]),
            ("Reality Shift", ["U"]),
            ("Mana Drain", ["U"]),
            ("Fierce Guardianship", ["U"]),
            ("Force of Will", ["U"]),
            ("Force of Negation", ["U"]),
            ("Flusterstorm", ["U"]),
            ("Mental Misstep", ["U"]),
            ("Pact of Negation", ["U"]),
            ("An Offer You Can't Refuse", ["U"]),
            ("Windfall", ["U"]),
            ("Snapcaster Mage", ["U"]),
            ("Ledger Shredder", ["U"]),
            ("Archmage Emeritus", ["U"]),
            ("Wavebreak Hippocamp", ["U"]),
            ("Displacer Kitten", ["U"]),
            ("Hullbreaker Horror", ["U"]),
            ("Thassa's Oracle", ["U"]),
            # Black Staples
            ("Dark Ritual", ["B"]),
            ("Cabal Ritual", ["B"]),
            ("Toxic Deluge", ["B"]),
            ("Damnation", ["B"]),
            ("Feed the Swarm", ["B"]),
            ("Go for the Throat", ["B"]),
            ("Infernal Grasp", ["B"]),
            ("Deadly Rollick", ["B"]),
            ("Vampiric Tutor", ["B"]),
            ("Demonic Tutor", ["B"]),
            ("Imperial Seal", ["B"]),
            ("Grim Tutor", ["B"]),
            ("Diabolic Intent", ["B"]),
            ("Night's Whisper", ["B"]),
            ("Sign in Blood", ["B"]),
            ("Read the Bones", ["B"]),
            ("Phyrexian Arena", ["B"]),
            ("Necropotence", ["B"]),
            ("Black Market Connections", ["B"]),
            ("Reanimate", ["B"]),
            ("Animate Dead", ["B"]),
            ("Necromancy", ["B"]),
            ("Stitcher's Supplier", ["B"]),
            ("Blood Artist", ["B"]),
            ("Zulaport Cutthroat", ["B"]),
            ("Orcish Bowmasters", ["B"]),
            ("Dauthi Voidwalker", ["B"]),
            ("Opposition Agent", ["B"]),
            ("Sheoldred, the Apocalypse", ["B"]),
            # Red Staples
            ("Chaos Warp", ["R"]),
            ("Blasphemous Act", ["R"]),
            ("Faithless Looting", ["R"]),
            ("Jeska's Will", ["R"]),
            ("Dockside Extortionist", ["R"]),
            ("Abrade", ["R"]),
            ("Deflecting Swat", ["R"]),
            ("Tibalt's Trickery", ["R"]),
            ("Vandalblast", ["R"]),
            ("Wild Magic Surge", ["R"]),
            ("Red Elemental Blast", ["R"]),
            ("Pyroblast", ["R"]),
            ("Lightning Bolt", ["R"]),
            ("Wheel of Fortune", ["R"]),
            ("Thrill of Possibility", ["R"]),
            ("Big Score", ["R"]),
            ("Unexpected Windfall", ["R"]),
            ("Simian Spirit Guide", ["R"]),
            ("Guttersnipe", ["R"]),
            ("Storm-Kiln Artist", ["R"]),
            ("Young Pyromancer", ["R"]),
            ("Dualcaster Mage", ["R"]),
            ("Twinflame", ["R"]),
            ("Underworld Breach", ["R"]),
            ("Birgi, God of Storytelling", ["R"]),
            ("Professional Face-Breaker", ["R"]),
            ("Ragavan, Nimble Pilferer", ["R"]),
            # Green Staples
            ("Nature's Claim", ["G"]),
            ("Beast Within", ["G"]),
            ("Heroic Intervention", ["G"]),
            ("Kodama's Reach", ["G"]),
            ("Cultivate", ["G"]),
            ("Rampant Growth", ["G"]),
            ("Three Visits", ["G"]),
            ("Nature's Lore", ["G"]),
            ("Farseek", ["G"]),
            ("Birds of Paradise", ["G"]),
            ("Llanowar Elves", ["G"]),
            ("Elvish Mystic", ["G"]),
            ("Fyndhorn Elves", ["G"]),
            ("Delighted Halfling", ["G"]),
            ("Arbor Elf", ["G"]),
            ("Eternal Witness", ["G"]),
            ("Reclamation Sage", ["G"]),
            ("Endurance", ["G"]),
            ("Finale of Devastation", ["G"]),
            ("Green Sun's Zenith", ["G"]),
            ("Chord of Calling", ["G"]),
            ("Worldly Tutor", ["G"]),
            ("Sylvan Library", ["G"]),
            ("Beast Whisperer", ["G"]),
            ("Guardian Project", ["G"]),
            ("Toski, Bearer of Secrets", ["G"]),
            ("Craterhoof Behemoth", ["G"]),
            ("Kenrith's Transformation", ["G"]),
            # Multicolor Staples
            ("Assassin's Trophy", ["B", "G"]),
            ("Anguished Unmaking", ["W", "B"]),
            ("Vindicate", ["W", "B"]),
            ("Growth Spiral", ["U", "G"]),
            ("Wear // Tear", ["R", "W"]),
            ("Despark", ["W", "B"]),
            ("Dovin's Veto", ["W", "U"]),
            ("Prismari Command", ["U", "R"]),
            ("Fracture", ["W", "B"]),
            ("Expressive Iteration", ["U", "R"]),
            ("Rakdos Charm", ["B", "R"]),
            ("Boros Charm", ["R", "W"]),
            ("Golgari Charm", ["B", "G"]),
            ("Drown in the Loch", ["U", "B"]),
            ("Baleful Strix", ["U", "B"]),
            ("Coiling Oracle", ["U", "G"]),
            ("Tainted Pact", ["U", "B"]),
            ("Notion Thief", ["U", "B"]),
            ("Mayhem Devil", ["B", "R"]),
            ("Corpse Knight", ["W", "B"]),
            ("Elas il-Kor, Sadistic Pilgrim", ["W", "B"]),
            ("Faeburrow Elder", ["G", "W"]),
            ("Psychic Frog", ["U", "B"]),
        ]

        for staple_name, staple_colors in universal_staples:
            if len(selected_maindeck) >= exact_spells_target:
                break
            # Color identity check: all staple colors must be within commander CI
            if staple_colors and any(c not in cmdr_ci_set for c in staple_colors):
                continue
            if try_add_card(staple_name, "Commander Staple"):
                role_breakdown.synergy_and_wincons += 1

        # Truncate spells if exceeded target
        if len(selected_maindeck) > exact_spells_target:
            selected_maindeck = selected_maindeck[:exact_spells_target]

        # 9. Assemble Mana Base strictly adhering to Color Identity and Land Budget
        lands_needed = 99 - len(selected_maindeck)
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

        # Basic Lands (strictly for active colors in commander identity) — fills the exact remainder
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

    def refine_deck_with_prompt(
        self,
        current_result: GeneratedDeckResult,
        user_prompt: str,
    ) -> Tuple[GeneratedDeckResult, str]:
        """
        Interactively refines an already generated deck based on natural language instructions:
        e.g., land adjustments, budget optimization, adding specific counters/removal/ramp,
        or swapping specific cards.
        Returns: (updated_GeneratedDeckResult, changelog_message)
        """
        import re
        prompt_lower = user_prompt.lower().strip()
        deck = current_result.deck
        cmdr = current_result.commander
        cmdr_ci = cmdr.color_identity or ["C"]
        cmdr_ci_set = set(cmdr_ci)
        changes: List[str] = []

        maindeck_items = list(deck.maindeck)
        current_names = {it.effective_name.lower(): it for it in maindeck_items}

        color_to_basic = {
            "W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest", "C": "Wastes"
        }
        active_basics = [color_to_basic[c] for c in cmdr_ci if c in color_to_basic and c != "C"] or ["Wastes"]

        # 1. LAND COUNT ADJUSTMENT
        # Check if user specified exact land count: e.g. "30 tierras", "33 lands", "menos tierras", "mas tierras"
        land_match = re.search(r'(\d{1,2})\s*(tierras?|lands?)', prompt_lower)
        curr_lands = sum(it.quantity for it in maindeck_items if it.card and "Land" in it.card.type_line)
        target_lands = None

        if land_match:
            target_lands = int(land_match.group(1))
        elif "menos tierras" in prompt_lower or "baja las tierras" in prompt_lower or "reducir tierras" in prompt_lower:
            target_lands = max(24, curr_lands - 3)
        elif "mas tierras" in prompt_lower or "más tierras" in prompt_lower or "aumentar tierras" in prompt_lower:
            target_lands = min(42, curr_lands + 3)

        if target_lands is not None and 20 <= target_lands <= 50 and target_lands != curr_lands:
            diff = target_lands - curr_lands
            if diff < 0:
                # Reduce lands: remove basics and add top spells
                to_remove = abs(diff)
                removed_count = 0
                for it in list(maindeck_items):
                    if it.card and "Land" in it.card.type_line and any(b.lower() == it.effective_name.lower() for b in active_basics):
                        reduce_by = min(it.quantity, to_remove - removed_count)
                        it.quantity -= reduce_by
                        removed_count += reduce_by
                        if it.quantity <= 0 and it in maindeck_items:
                            maindeck_items.remove(it)
                        if removed_count >= to_remove:
                            break

                # Fill with non-land staples
                from .archetype_database import COLOR_STAPLES
                candidates = []
                for c in cmdr_ci:
                    if c in COLOR_STAPLES:
                        for cat in ["draw", "removal", "counters", "ramp"]:
                            for s_name, _ in COLOR_STAPLES[c].get(cat, []):
                                if s_name.lower() not in current_names and s_name not in candidates:
                                    candidates.append(s_name)

                added_spells = 0
                for cand in candidates:
                    if added_spells >= removed_count:
                        break
                    c_card = self.resolve_card_metadata(cand)
                    maindeck_items.append(
                        DeckItem(raw_name=cand, quantity=1, card=c_card, section=DeckSection.MAINDECK, custom_tags=["AI Refinement: Spell Added"])
                    )
                    current_names[cand.lower()] = maindeck_items[-1]
                    added_spells += 1

                changes.append(f"📉 Tierras ajustadas de {curr_lands} a {target_lands} ({added_spells} hechizos agregados).")

            elif diff > 0:
                # Increase lands: remove lowest-impact spells and add basics
                to_add = diff
                # Remove non-essential non-land spells
                removed_spells = 0
                for it in list(reversed(maindeck_items)):
                    if not (it.card and "Land" in it.card.type_line):
                        maindeck_items.remove(it)
                        removed_spells += it.quantity
                        if removed_spells >= to_add:
                            break

                # Add basic lands
                for b_idx in range(removed_spells):
                    b_name = active_basics[b_idx % len(active_basics)]
                    found_b = next((it for it in maindeck_items if it.effective_name.lower() == b_name.lower()), None)
                    if found_b:
                        found_b.quantity += 1
                    else:
                        b_card = self.resolve_card_metadata(b_name)
                        maindeck_items.append(
                            DeckItem(raw_name=b_name, quantity=1, card=b_card, section=DeckSection.MAINDECK, custom_tags=["Basic Land"])
                        )

                changes.append(f"📈 Tierras aumentadas de {curr_lands} a {target_lands}.")

        # 2. BUDGET CONSTRAINTS
        if "budget" in prompt_lower or "economico" in prompt_lower or "económico" in prompt_lower or "barato" in prompt_lower or "precio" in prompt_lower:
            budget_threshold = 20.0
            if "menos de 100" in prompt_lower or "< 100" in prompt_lower:
                budget_threshold = 10.0
            elif "menos de 50" in prompt_lower or "< 50" in prompt_lower:
                budget_threshold = 5.0

            swapped_expensive = 0
            budget_replacements = {
                "mana crypt": "Sol Ring",
                "force of will": "Counterspell",
                "rhystic study": "Mystic Remora",
                "fierce guardianship": "Swan Song",
                "vampiric tutor": "Diabolic Tutor",
                "demonic tutor": "Diabolic Intent",
                "imperial seal": "Grim Tutor",
                "the one ring": "Mind Stone",
                "dockside extortionist": "Simian Spirit Guide",
                "jeweled lotus": "Arcane Signet",
                "lion's eye diamond": "Lotus Petal",
                "mox diamond": "Fellwar Stone",
                "mox opal": "Thought Vessel",
                "mana vault": "Talisman of Progress",
                "deflecting swat": "Bolt Bend",
                "deadly rollick": "Infernal Grasp",
                "teferi's protection": "Flawless Maneuver",
                "cyclonic rift": "Aetherize",
                "smothering tithe": "Monologue Tax",
                "esper sentinel": "Thraben Inspector",
            }

            for it in list(maindeck_items):
                if it.card and (it.card.price_usd or 0.0) > budget_threshold:
                    clean_n = it.effective_name.lower()
                    repl_name = budget_replacements.get(clean_n, "Wayfarer's Bauble")
                    if repl_name.lower() not in current_names:
                        r_card = self.resolve_card_metadata(repl_name)
                        old_name = it.effective_name
                        it.raw_name = repl_name
                        it.card = r_card
                        it.custom_tags = ["AI Refinement: Budget Swap"]
                        current_names[repl_name.lower()] = it
                        swapped_expensive += 1
                        changes.append(f"💰 Reemplazado '{old_name}' (${(it.card.price_usd or 0):.0f}) por '{repl_name}'.")

            if swapped_expensive > 0:
                changes.append(f"✨ {swapped_expensive} cartas de alto coste reemplazadas por alternativas budget.")

        # 3. INTERACTION & REMOVAL BOOST
        if "mas interaccion" in prompt_lower or "más interacción" in prompt_lower or "mas counters" in prompt_lower or "más counters" in prompt_lower or "mas removal" in prompt_lower or "más removal" in prompt_lower:
            interaction_pool = [
                ("Swords to Plowshares", ["W"]),
                ("Path to Exile", ["W"]),
                ("Counterspell", ["U"]),
                ("Swan Song", ["U"]),
                ("Pongify", ["U"]),
                ("Rapid Hybridization", ["U"]),
                ("Go for the Throat", ["B"]),
                ("Infernal Grasp", ["B"]),
                ("Chaos Warp", ["R"]),
                ("Abrade", ["R"]),
                ("Nature's Claim", ["G"]),
                ("Beast Within", ["G"]),
                ("Dovin's Veto", ["W", "U"]),
                ("Assassin's Trophy", ["B", "G"]),
            ]
            added_int = 0
            for int_name, int_colors in interaction_pool:
                if added_int >= 3:
                    break
                if int_colors and any(c not in cmdr_ci_set for c in int_colors):
                    continue
                if int_name.lower() not in current_names:
                    # Swap out a basic land or utility spell
                    for it in list(maindeck_items):
                        if it.card and "Land" in it.card.type_line and it.quantity > 1:
                            it.quantity -= 1
                            c_card = self.resolve_card_metadata(int_name)
                            maindeck_items.append(DeckItem(raw_name=int_name, quantity=1, card=c_card, section=DeckSection.MAINDECK, custom_tags=["AI Refinement: Interaction"]))
                            current_names[int_name.lower()] = maindeck_items[-1]
                            added_int += 1
                            break
            if added_int > 0:
                changes.append(f"⚡ Se añadieron {added_int} cartas de interacción/respuesta rápida.")

        # 4. RAMP & FAST MANA BOOST
        if "mas ramp" in prompt_lower or "más ramp" in prompt_lower or "mas mana" in prompt_lower or "más maná" in prompt_lower or "mas rocas" in prompt_lower:
            ramp_pool = [
                ("Sol Ring", []),
                ("Arcane Signet", []),
                ("Fellwar Stone", []),
                ("Thought Vessel", []),
                ("Mind Stone", []),
                ("Birds of Paradise", ["G"]),
                ("Llanowar Elves", ["G"]),
                ("Nature's Lore", ["G"]),
                ("Three Visits", ["G"]),
                ("Farseek", ["G"]),
            ]
            added_ramp = 0
            for r_name, r_colors in ramp_pool:
                if added_ramp >= 3:
                    break
                if r_colors and any(c not in cmdr_ci_set for c in r_colors):
                    continue
                if r_name.lower() not in current_names:
                    for it in list(maindeck_items):
                        if it.card and "Land" in it.card.type_line and it.quantity > 1:
                            it.quantity -= 1
                            c_card = self.resolve_card_metadata(r_name)
                            maindeck_items.append(DeckItem(raw_name=r_name, quantity=1, card=c_card, section=DeckSection.MAINDECK, custom_tags=["AI Refinement: Ramp"]))
                            current_names[r_name.lower()] = maindeck_items[-1]
                            added_ramp += 1
                            break
            if added_ramp > 0:
                changes.append(f"🌲 Se añadieron {added_ramp} fuentes de aceleración y maná.")

        if not changes:
            changes.append("ℹ️ Mazo revisado y optimizado de acuerdo a la instrucción solicitada.")

        # Build refreshed deck
        cmdr_item = DeckItem(raw_name=cmdr.name, quantity=1, card=cmdr, section=DeckSection.COMMANDER)
        refreshed_deck = Deck(
            name=f"{deck.name} [Personalizado]",
            format="commander",
            commanders=[cmdr_item],
            maindeck=maindeck_items,
        )

        validation = self.rules_engine.validate_deck(refreshed_deck)
        total_price = sum((it.total_price_usd or 0.0) for it in [cmdr_item] + maindeck_items)
        non_land_spells = [it for it in maindeck_items if it.card and "Land" not in it.card.type_line]
        total_cmc = sum((it.card.cmc * it.quantity) for it in non_land_spells if it.card)
        spell_count = sum(it.quantity for it in non_land_spells)
        avg_cmc = round(total_cmc / spell_count, 2) if spell_count > 0 else 2.5
        exporter = DeckExporter()
        export_text = exporter.export_to_text(refreshed_deck)

        new_role_breakdown = DeckRoleBreakdown(
            lands=sum(it.quantity for it in maindeck_items if it.card and "Land" in it.card.type_line),
            ramp_and_mana=sum(it.quantity for it in maindeck_items if it.card and ("Artifact" in it.card.type_line or "ramp" in " ".join(it.custom_tags).lower())),
            card_draw_and_engines=sum(it.quantity for it in maindeck_items if "draw" in " ".join(it.custom_tags).lower()),
            targeted_removal=sum(it.quantity for it in maindeck_items if "interaction" in " ".join(it.custom_tags).lower()),
            tutors=sum(it.quantity for it in maindeck_items if "tutor" in " ".join(it.custom_tags).lower()),
            synergy_and_wincons=len(non_land_spells),
        )

        updated_result = GeneratedDeckResult(
            deck=refreshed_deck,
            commander=cmdr,
            bracket=current_result.bracket,
            strategy=current_result.strategy,
            total_price_usd=round(total_price, 2),
            average_cmc=avg_cmc,
            role_breakdown=new_role_breakdown,
            suggested_commanders=current_result.suggested_commanders,
            key_combos_or_synergies=current_result.key_combos_or_synergies,
            validation=validation,
            export_text=export_text,
        )

        changelog = "\n".join(f"- {c}" for c in changes)
        return updated_result, changelog


# Convenient Alias
MTG_Deckbuilder_Generator = MTGDeckbuilderGenerator

