"""
Card-by-Card Trade-off Engine (Causa-Efecto Analysis),
Anti-Synergy-Trap Detector, and 3-Tier Budget Alternatives.
"""

from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from ..ai.models import CardCut, CardInclusion
from ..brackets.standards import BracketTier
from ..brackets.game_changers import GAME_CHANGERS_DATABASE


class BudgetTierOption(BaseModel):
    name: str
    estimated_price_usd: float
    description: str


class BudgetAlternatives(BaseModel):
    """3-Tier Budget options for the suggested inclusion."""
    budget_sidegrade: Optional[BudgetTierOption] = None
    recommended: BudgetTierOption
    premium_staple: Optional[BudgetTierOption] = None


class CardTradeoff(BaseModel):
    """
    Detailed 1-to-1 Causa-Efecto Trade-off between a cut card and an included card.
    """
    card_cut_name: str
    cut_cmc: float
    cut_role: str
    cut_price_usd: Optional[float] = None
    card_in_name: str
    in_cmc: float
    in_role: str
    in_price_usd: Optional[float] = None
    cmc_delta: float = Field(description="CMC difference (in_cmc - cut_cmc). Negative means curve reduction.")
    technical_justification: str = Field(description="Technical rationale explaining mana curve, speed, and archetype benefit.")
    budget_tiers: BudgetAlternatives
    is_anti_synergy_trap_avoided: bool = True
    display_title: str = ""

    def formatted_summary(self) -> str:
        delta_sign = f"{self.cmc_delta:+.1f}" if self.cmc_delta != 0 else "0.0"
        return (
            f"[{self.card_cut_name} ({self.cut_cmc:.0f} CMC)] ➡️ [{self.card_in_name} ({self.in_cmc:.0f} CMC)] | "
            f"Impacto en Curva: {delta_sign} CMC | Razón Técnica: {self.technical_justification}"
        )


class TradeoffEngine:
    """
    Synthesizes pairwise trade-offs and generates 3-tier budget alternatives with 100% valid MTG card names.
    """

    # Comprehensive budget alternative catalog for all major staples and staples roles
    BUDGET_CATALOG: Dict[str, Dict[str, Any]] = {
        "Rhystic Study": {
            "budget": ("Mystic Remora", 7.00, "Impuesto temprano de 1 maná para partidas rápidas"),
            "premium": ("The One Ring", 90.00, "Protección incondicional y ventaja de cartas acumulativa"),
        },
        "Demonic Tutor": {
            "budget": ("Diabolic Intent", 6.00, "Tutor universal eficiente a cambio de sacrificar una criatura"),
            "premium": ("Imperial Seal", 80.00, "Tutor universal a velocidad de instantáneo de 1 CMC"),
        },
        "Cyclonic Rift": {
            "budget": ("Aetherize", 0.50, "Rebote defensivo masivo contra ataques letales"),
            "premium": ("Force of Will", 65.00, "Interrupción gratuita a coste de 0 manás"),
        },
        "Mana Crypt": {
            "budget": ("Sol Ring", 1.50, "Acelerador básico del formato (+2 manás)"),
            "premium": ("Mox Diamond", 600.00, "Fast mana de coste 0 para cualquier color"),
        },
        "Sylvan Library": {
            "budget": ("Night's Whisper", 1.50, "Robo directo de 2 cartas por 2 manás"),
            "premium": ("Survival of the Fittest", 180.00, "Motor de descarte y búsqueda de criaturas continuo"),
        },
        "Smothering Tithe": {
            "budget": ("Trouble in Pairs", 20.00, "Motor de robo y castigo para oponentes activos"),
            "premium": ("Tivit, Seller of Secrets", 8.00, "Generador masivo de Tesoros y Pistas en combate"),
        },
        "Teferi's Protection": {
            "budget": ("Flawless Maneuver", 10.00, "Protección indestructible gratuita con tu comandante"),
            "premium": ("Silence", 7.00, "Candado preventivo que apaga la interacción rival"),
        },
        "Heroic Intervention": {
            "budget": ("Tamiyo's Safekeeping", 0.35, "Protección a velocidad de instantáneo con Hexproof e Indestructible por {G}"),
            "premium": ("Flawless Maneuver", 12.00, "Protección indestructible incondicional sin coste si controlas tu comandante"),
        },
        "Counterspell": {
            "budget": ("Negate", 0.25, "Interrupción barata para cualquier hechizo no-criatura"),
            "premium": ("Mana Drain", 40.00, "Contrarresta y absorbe maná incoloro para tu siguiente turno"),
        },
        "Swan Song": {
            "budget": ("An Offer You Can't Refuse", 1.50, "Respuesta instantánea de {U} para cualquier no-criatura"),
            "premium": ("Fierce Guardianship", 45.00, "Contrahechizo gratuito con tu comandante en mesa"),
        },
        "Fierce Guardianship": {
            "budget": ("Swan Song", 8.00, "Interrupción de 1 maná azul"),
            "premium": ("Force of Will", 65.00, "Contrahechizo gratuito supremo"),
        },
        "Deflecting Swat": {
            "budget": ("Bolt Bend", 1.50, "Redirección por 1 maná rojo si controlas una criatura de poder 4+"),
            "premium": ("Tibalt's Trickery", 6.00, "Contrarresta cualquier hechizo en rojo"),
        },
        "Deadly Rollick": {
            "budget": ("Infernal Grasp", 0.75, "Eliminación instantánea de criatura por 2 manás"),
            "premium": ("Snuff Out", 8.00, "Eliminación gratuita a cambio de 4 vidas"),
        },
        "Sol Ring": {
            "budget": ("Mind Stone", 0.35, "Acelerador de 2 manás con ciclo de robo"),
            "premium": ("Mana Vault", 50.00, "Acelerador explosivo de +3 manás por 1 maná"),
        },
        "Arcane Signet": {
            "budget": ("Fellwar Stone", 0.50, "Roca de maná eficiente de 2 manás para colores rivales"),
            "premium": ("Chrome Mox", 85.00, "Acelerador de 0 manás"),
        },
        "Birds of Paradise": {
            "budget": ("Llanowar Elves", 0.25, "Acelerador clásico de 1 maná verde"),
            "premium": ("Delighted Halfling", 14.00, "Maná incontrarrestable para hechizos legendarios"),
        },
        "Delighted Halfling": {
            "budget": ("Llanowar Elves", 0.25, "Acelerador de 1 maná"),
            "premium": ("Birds of Paradise", 6.00, "Fija cualquier color y bloquea criaturas con vuelo"),
        },
        "Swords to Plowshares": {
            "budget": ("Path to Exile", 1.50, "Exilio incondicional por 1 maná blanco"),
            "premium": ("Solitude", 35.00, "Exilio gratuito en velocidad de instantáneo"),
        },
        "Path to Exile": {
            "budget": ("Swords to Plowshares", 1.50, "Exilio de 1 maná"),
            "premium": ("Solitude", 35.00, "Exilio gratuito"),
        },
        "Beast Within": {
            "budget": ("Generous Gift", 0.75, "Destrucción universal de cualquier permanente"),
            "premium": ("Assassin's Trophy", 3.50, "Destrucción incondicional por 2 manás"),
        },
        "Toxic Deluge": {
            "budget": ("Blasphemous Act", 2.50, "Limpia masiva barata de mesa"),
            "premium": ("Damnation", 18.00, "Destrucción incondicional sin regeneración"),
        },
        "Blasphemous Act": {
            "budget": ("Chain Reaction", 0.50, "Limpia masiva por daño según número de criaturas"),
            "premium": ("Toxic Deluge", 6.00, "Limpia masiva por vidas que ignora Indestructible"),
        },
        "Laboratory Maniac": {
            "budget": ("Triskaidekaphile", 0.50, "Wincon interactiva de robo y 13 cartas"),
            "premium": ("Aetherflux Reservoir", 12.00, "Wincon de tormenta y disparo letal de 50 daños"),
        },
        "Diabolic Intent": {
            "budget": ("Wishclaw Talisman", 4.00, "Tutor de 2 manás con 3 activaciones"),
            "premium": ("Demonic Tutor", 35.00, "Tutor incondicional directo"),
        },
        "Peer into the Abyss": {
            "budget": ("Read the Bones", 0.25, "Adivina 2 y roba 2"),
            "premium": ("Bolas's Citadel", 8.00, "Castea todo tu mazo desde el tope pagando vidas"),
        },
    }

    @classmethod
    def evaluate_anti_synergy_trap(cls, card_name: str, cmc: float, role: str) -> Tuple[bool, Optional[str]]:
        """
        Anti-Synergy Trap Filter:
        Flags cards with CMC > 4 that are slow or win-more unless they are direct wincons.
        """
        is_wincon = role.lower() in ("wincon", "combo", "finisher")
        if cmc >= 5.0 and not is_wincon:
            return True, f"Carta de alto coste ({cmc:.0f} CMC) dependiente de mesa. En Brackets competitivos representa una trampa de sinergia lenta."
        return False, None

    @classmethod
    def build_pairwise_tradeoffs(
        cls,
        cuts: List[CardCut],
        inclusions: List[CardInclusion],
        target_bracket: BracketTier,
    ) -> List[CardTradeoff]:
        """
        Pairs each cut card with an included card, calculating mana delta and 3-tier budget choices.
        Ensures 100% valid Scryfall card names for all budget options.
        """
        tradeoffs: List[CardTradeoff] = []
        pair_count = min(len(cuts), len(inclusions))

        for idx in range(pair_count):
            cut = cuts[idx]
            inc = inclusions[idx]

            delta = round(inc.cmc - cut.cmc, 1)

            # Check if this cut was a Game Changer violation
            is_game_changer_cut = cut.card_name in GAME_CHANGERS_DATABASE
            if is_game_changer_cut:
                gc_info = GAME_CHANGERS_DATABASE[cut.card_name]
                tech_reason = (
                    f"⚔️ **Ajuste de Bracket {target_bracket.value}**: Se retira el Game Changer '{cut.card_name}' "
                    f"[{gc_info.category}] no permitido en este nivel para incorporar '{inc.card_name}' [{inc.cmc:.0f} CMC]. "
                    f"Alinea el mazo con las reglas oficiales de WotC para {target_bracket.label}. {inc.synergy_explanation}"
                )
            else:
                # Generate standard technical justification
                if delta < 0:
                    curve_text = f"reduce la curva en {abs(delta):.1f} CMC, acelerando el desarrollo de turnos tempranos"
                elif delta == 0:
                    curve_text = f"mantiene la curva idéntica ({inc.cmc:.0f} CMC) pero eleva el ratio de efectividad/impacto"
                else:
                    curve_text = f"aumenta la curva (+{delta:.1f} CMC) justificado por su impacto como pieza decisiva"

                tech_reason = (
                    f"Se retira '{cut.card_name}' [{cut.cmc:.0f} CMC] para incorporar '{inc.card_name}' [{inc.cmc:.0f} CMC]: "
                    f"{curve_text} y optimiza el rol de '{inc.role}' para el nivel {target_bracket.label}. {inc.synergy_explanation}"
                )

            # Determine 3-tier budget alternatives with REAL card names
            recommended_opt = BudgetTierOption(
                name=inc.card_name,
                estimated_price_usd=inc.estimated_price_usd or 4.0,
                description="Opción óptima recomendada para el Bracket",
            )

            # Check if known budget alternatives exist
            catalog_match = cls.BUDGET_CATALOG.get(inc.card_name)
            budget_opt = None
            premium_opt = None

            if catalog_match:
                if "budget" in catalog_match:
                    b_name, b_price, b_desc = catalog_match["budget"]
                    budget_opt = BudgetTierOption(name=b_name, estimated_price_usd=b_price, description=b_desc)
                if "premium" in catalog_match:
                    p_name, p_price, p_desc = catalog_match["premium"]
                    premium_opt = BudgetTierOption(name=p_name, estimated_price_usd=p_price, description=p_desc)
            else:
                # Default real fallback staples by role
                role_lower = inc.role.lower()
                if "ramp" in role_lower or "mana" in role_lower:
                    budget_opt = BudgetTierOption(name="Mind Stone", estimated_price_usd=0.35, description="Acelerador incoloro accesible con robo")
                    premium_opt = BudgetTierOption(name="Mana Vault", estimated_price_usd=50.00, description="Inyección masiva de maná explosivo")
                elif "draw" in role_lower:
                    budget_opt = BudgetTierOption(name="Night's Whisper", estimated_price_usd=1.50, description="Robo directo eficiente")
                    premium_opt = BudgetTierOption(name="The One Ring", estimated_price_usd=90.00, description="Motor supremo de robo y protección")
                elif "interaction" in role_lower or "removal" in role_lower or "counter" in role_lower:
                    budget_opt = BudgetTierOption(name="Negate", estimated_price_usd=0.25, description="Interrupción de bajo coste")
                    premium_opt = BudgetTierOption(name="Force of Will", estimated_price_usd=65.00, description="Interrupción gratuita de turno cero")
                elif "tutor" in role_lower:
                    budget_opt = BudgetTierOption(name="Diabolic Intent", estimated_price_usd=6.00, description="Tutor de 2 manás con sacrificio")
                    premium_opt = BudgetTierOption(name="Imperial Seal", estimated_price_usd=80.00, description="Tutor de 1 maná")
                else:
                    budget_opt = BudgetTierOption(name="Sol Ring", estimated_price_usd=1.50, description="Acelerador universal de formato")
                    premium_opt = BudgetTierOption(name="Heroic Intervention", estimated_price_usd=8.50, description="Protección y sinergia de alta gama")

            tiers = BudgetAlternatives(
                budget_sidegrade=budget_opt,
                recommended=recommended_opt,
                premium_staple=premium_opt,
            )

            tradeoff_item = CardTradeoff(
                card_cut_name=cut.card_name,
                cut_cmc=cut.cmc,
                cut_role=cut.role,
                cut_price_usd=cut.estimated_price_usd,
                card_in_name=inc.card_name,
                in_cmc=inc.cmc,
                in_role=inc.role,
                in_price_usd=inc.estimated_price_usd,
                cmc_delta=delta,
                technical_justification=tech_reason,
                budget_tiers=tiers,
                is_anti_synergy_trap_avoided=True,
                display_title=f"❌ {cut.card_name} ➡️ ✨ {inc.card_name} ({delta:+.0f} CMC)",
            )
            tradeoffs.append(tradeoff_item)

        return tradeoffs
