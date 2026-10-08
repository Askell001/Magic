"""
Interactive CLI Questionnaire and API builders for evaluating user intent and optimization goals.
"""

import sys
from typing import Optional, List, Dict, Any, Union

from .models import UserIntent
from ..brackets.standards import BracketTier


def ask_user_intent_cli(
    default_bracket: BracketTier = BracketTier.BRACKET_2_MID_POWER,
    input_func=input,
) -> UserIntent:
    """
    Prompts the user via interactive terminal questions to establish target Bracket,
    budget limits, and untouchable cards.
    """
    print("\n" + "=" * 65)
    print(" EVALUACION DE INTENCION DEL USUARIO - MTG DECK OPTIMIZER")
    print("=" * 65)

    # 1. Target Bracket
    print("\n[1] ¿A qué Bracket (Nivel de Poder) deseas llevar este mazo?")
    print("  1) Bracket 1 (Exhibition / Ultra-Casual): 0 Game Changers, 0 Combos 2-cartas, 0 MLD, 0 Extra turns.")
    print("  2) Bracket 2 (Core / Precon Promedio): 0 Game Changers, 0 Combos 2-cartas, 0 MLD.")
    print("  3) Bracket 3 (Upgraded / Precon Mejorado): Máx 3 Game Changers, 0 MLD, combos lentos.")
    print("  4) Bracket 4 (Optimized / Alta Potencia): Sin restricciones de Game Changers ni combos.")
    print("  5) Bracket 5 (cEDH / Torneo Meta): Eficiencia absoluta, wincons turnos 1-3.")
    
    bracket_choice_str = input_func(f"\nSelecciona una opción [1-5] (default {default_bracket.value}): ").strip()
    try:
        tier_val = int(bracket_choice_str) if bracket_choice_str else default_bracket.value
        if tier_val not in (1, 2, 3, 4, 5):
            tier_val = default_bracket.value
    except ValueError:
        tier_val = default_bracket.value

    target_tier = BracketTier(tier_val)
    print(f"  -> Seleccionado: {target_tier.label}")

    # 2. Budget Limit (USD)
    print("\n[2] ¿Tienes alguna restricción de presupuesto en USD?")
    print("  (Presiona Enter para 'Sin límite' o ingresa un monto numérico, ej: 150)")
    budget_str = input_func("Presupuesto máximo USD: ").strip()
    budget_val: Optional[float] = None
    if budget_str:
        try:
            budget_val = float(budget_str.replace("$", "").replace(",", ""))
            print(f"  -> Límite de presupuesto asignado: ${budget_val:,.2f} USD")
        except ValueError:
            print("  -> Valor no numérico, se asumirá 'Sin límite de presupuesto'.")

    # 3. Untouchable / Sacred Cards
    print("\n[3] ¿Hay cartas 'intocables' o icónicas que NO deseas quitar bajo ninguna circunstancia?")
    print("  (Ingresa los nombres separados por comas, ej: 'The Ur-Dragon, Doubling Season', o presiona Enter para ninguna)")
    untouchable_str = input_func("Cartas intocables: ").strip()
    untouchables: List[str] = []
    if untouchable_str:
        raw_list = [c.strip() for c in untouchable_str.split(",") if c.strip()]
        untouchables = raw_list
        print(f"  -> Cartas protegidas ({len(untouchables)}): {', '.join(untouchables)}")
    else:
        print("  -> Ninguna carta protegida.")

    # 4. Optional Combo preference
    allow_combos: Optional[bool] = None
    if target_tier in (BracketTier.BRACKET_2_MID_POWER, BracketTier.BRACKET_3_HIGH_POWER):
        print("\n[4] ¿Deseas permitir combos infinitos en el mazo? (s/n, Enter para default de bracket)")
        combo_str = input_func("Permitir combos [s/n]: ").strip().lower()
        if combo_str in ("s", "si", "y", "yes", "true", "1"):
            allow_combos = True
        elif combo_str in ("n", "no", "false", "0"):
            allow_combos = False

    intent = UserIntent(
        target_bracket=target_tier,
        max_budget_usd=budget_val,
        untouchable_cards=untouchables,
        allow_infinite_combos=allow_combos,
    )

    print("\n[OK] Perfil de intención configurado exitosamente.")
    print("=" * 65 + "\n")
    return intent


def build_user_intent(
    target_bracket: Union[int, BracketTier] = 2,
    max_budget_usd: Optional[float] = None,
    untouchable_cards: Optional[List[str]] = None,
    allow_infinite_combos: Optional[bool] = None,
    allow_fast_mana: Optional[bool] = None,
    strategy_profile: Optional[Dict[str, Any]] = None,
    strategy_name: Optional[str] = None,
) -> UserIntent:
    """Helper to programmatically build UserIntent from API endpoints or function calls."""
    if isinstance(target_bracket, BracketTier):
        tier = target_bracket
    else:
        tier = BracketTier(target_bracket) if target_bracket in (1, 2, 3, 4, 5) else BracketTier.BRACKET_2_MID_POWER

    return UserIntent(
        target_bracket=tier,
        max_budget_usd=max_budget_usd,
        untouchable_cards=untouchable_cards or [],
        allow_infinite_combos=allow_infinite_combos,
        allow_fast_mana=allow_fast_mana,
        strategy_profile=strategy_profile,
        strategy_name=strategy_name or (strategy_profile.get("name") if strategy_profile else None),
    )
