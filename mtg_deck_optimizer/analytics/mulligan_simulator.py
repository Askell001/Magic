"""
Monte Carlo Opening Hand & Mulligan Simulator for MTG Commander.
Simulates 1,000 opening hands and calculates playable rates, mana screw/flood risks,
early interaction access, and expected Commander turn arrival.
"""

import random
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from ..models.card import Card
from ..models.deck import Deck


class MulliganSimulationReport(BaseModel):
    """Statistical summary of 1,000 opening hand simulations."""
    total_simulations: int = 1000
    playable_hand_rate_percent: float = Field(description="Percentage of hands with 2-4 lands and at least 1 early play/ramp")
    turn_2_ramp_rate_percent: float = Field(default=0.0, description="Probability of drawing ramp/acceleration playable by turn 2")
    mana_screw_rate_percent: float = Field(description="Percentage of hands with 0 or 1 land")
    mana_flood_rate_percent: float = Field(description="Percentage of hands with 5 or more lands")
    interaction_turn_1_to_3_percent: float = Field(description="Probability of holding interaction by turn 3")
    avg_commander_cast_turn: float = Field(description="Average turn on which the Commander can be reliably cast")
    sample_opening_hands: List[List[str]] = Field(default_factory=list, description="3 randomized sample hands for inspection")
    mulligan_advice: str = Field(description="Strategic feedback on mana base stability and opening hand safety")

    @property
    def playable_hands_percentage(self) -> float:
        return self.playable_hand_rate_percent

    @property
    def turn_2_ramp_probability(self) -> float:
        return self.turn_2_ramp_rate_percent

    @property
    def early_interaction_probability(self) -> float:
        return self.interaction_turn_1_to_3_percent

    @property
    def mana_screw_probability(self) -> float:
        return self.mana_screw_rate_percent

    @property
    def mana_flood_probability(self) -> float:
        return self.mana_flood_rate_percent


class MulliganSimulator:
    """
    Monte Carlo engine executing virtual hand draws from the 99-card library.
    """

    @classmethod
    def simulate_opening_hands(
        cls,
        deck: Deck,
        num_simulations: int = 1000,
        seed: Optional[int] = 42,
    ) -> MulliganSimulationReport:
        """
        Executes Monte Carlo opening hand simulations.
        """
        if seed is not None:
            random.seed(seed)

        # Build library of 99 cards
        library_cards: List[Card] = []
        for it in deck.maindeck:
            card = it.card or Card(id=f"card_{it.effective_name.lower().replace(' ', '_')}", name=it.effective_name, cmc=2.0)
            for _ in range(it.quantity):
                library_cards.append(card)

        total_library_size = len(library_cards)
        if total_library_size < 10:
            # Fallback for empty or tiny decks
            return MulliganSimulationReport(
                total_simulations=0,
                playable_hand_rate_percent=0.0,
                mana_screw_rate_percent=0.0,
                mana_flood_rate_percent=0.0,
                interaction_turn_1_to_3_percent=0.0,
                avg_commander_cast_turn=4.0,
                mulligan_advice="El mazo contiene muy pocas cartas para simular aperturas.",
            )

        cmdr_cmc = deck.commanders[0].card.cmc if (deck.commanders and deck.commanders[0].card) else 4.0

        playable_count = 0
        screw_count = 0
        flood_count = 0
        ramp_turn_2_count = 0
        interaction_by_turn_3_count = 0
        commander_turns_sum = 0.0

        sample_hands: List[List[str]] = []

        for sim_idx in range(num_simulations):
            # Draw 7 cards without replacement
            drawn_sample = random.sample(library_cards, min(10, total_library_size))
            opening_7 = drawn_sample[:7]
            top_3_draws = drawn_sample[7:10]
            hand_10 = opening_7 + top_3_draws

            # Save first 3 opening hands for user inspection
            if sim_idx < 3:
                sample_hands.append([c.name for c in opening_7])

            # Classify lands in opening 7
            land_count = sum(1 for c in opening_7 if "Land" in (c.type_line or ""))
            has_early_ramp_or_play = any(
                ("Land" not in (c.type_line or "") and c.cmc <= 2.0) for c in opening_7
            )

            # Check Turn 1-2 Ramp
            has_turn_2_ramp = any(
                c.cmc <= 2.0
                and (
                    "Artifact" in (c.type_line or "")
                    or "Creature" in (c.type_line or "")
                    or "Sorcery" in (c.type_line or "")
                )
                and any(
                    r in c.name.lower()
                    for r in [
                        "sol ring",
                        "signet",
                        "talisman",
                        "mox",
                        "crypt",
                        "petal",
                        "dork",
                        "llanowar",
                        "elf",
                        "birds of paradise",
                        "farseek",
                        "rampant growth",
                        "three visits",
                        "nature's lore",
                    ]
                )
                for c in opening_7
            )
            if has_turn_2_ramp and land_count >= 1:
                ramp_turn_2_count += 1

            # Screw & Flood
            if land_count <= 1:
                screw_count += 1
            elif land_count >= 5:
                flood_count += 1

            # Playable: 2-4 lands + early play
            if 2 <= land_count <= 4 and has_early_ramp_or_play:
                playable_count += 1

            # Check interaction in first 10 cards (opening 7 + turns 1, 2, 3)
            has_interaction = any(
                (
                    "Instant" in (c.type_line or "")
                    or "Counter" in (c.oracle_text or "")
                    or "destroy" in (c.oracle_text or "").lower()
                    or "exile" in (c.oracle_text or "").lower()
                )
                and c.cmc <= 3.0
                for c in hand_10
            )
            if has_interaction:
                interaction_by_turn_3_count += 1

            # Estimate turn to cast Commander
            # Natural land drops + ramp rocks drawn in top 7
            ramp_rocks = sum(
                1 for c in opening_7
                if (
                    "Sol Ring" in c.name
                    or "Signet" in c.name
                    or "Talisman" in c.name
                    or "Birds of Paradise" in c.name
                    or "Llanowar" in c.name
                    or "Nature's Lore" in c.name
                    or "Three Visits" in c.name
                    or "Farseek" in c.name
                    or "Cultivate" in c.name
                )
            )
            est_turn = max(1.0, cmdr_cmc - (0.7 * ramp_rocks))
            commander_turns_sum += est_turn

        playable_pct = round((playable_count / num_simulations) * 100.0, 1)
        screw_pct = round((screw_count / num_simulations) * 100.0, 1)
        flood_pct = round((flood_count / num_simulations) * 100.0, 1)
        ramp_pct = round((ramp_turn_2_count / num_simulations) * 100.0, 1)
        interact_pct = round((interaction_by_turn_3_count / num_simulations) * 100.0, 1)
        avg_cmdr_turn = round(commander_turns_sum / num_simulations, 1)

        # Strategic advice
        if playable_pct >= 75.0:
            advice = f"Excelente consistencia de apertura ({playable_pct}% de manos jugables). Riesgo de atasco de maná controlado ({screw_pct}%)."
        elif playable_pct >= 60.0:
            advice = f"Consistencia moderada ({playable_pct}%). Considera añadir 2 tierras adicionales o 2 aceleradores de 1-2 CMC para mitigar el {screw_pct}% de atasco."
        else:
            advice = f"Inconsistencia de apertura ({playable_pct}%). Alto riesgo de manos no operativas. Se requiere ajustar la curva baja y base de maná."

        return MulliganSimulationReport(
            total_simulations=num_simulations,
            playable_hand_rate_percent=playable_pct,
            turn_2_ramp_rate_percent=ramp_pct,
            mana_screw_rate_percent=screw_pct,
            mana_flood_rate_percent=flood_pct,
            interaction_turn_1_to_3_percent=interact_pct,
            avg_commander_cast_turn=avg_cmdr_turn,
            sample_opening_hands=sample_hands,
            mulligan_advice=advice,
        )
