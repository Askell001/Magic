"""
Comprehensive Game Changers Database & Bracket Compliance Evaluator for Commander (EDH).
Defines all format-warping staples, fast mana, mass locks, tutors, free spells, and 2-card combos,
evaluates card efficiency (S/A/B tier), and enforces strict Bracket quotas:
- Bracket 1 (Casual/Jank): EXACTLY 0 Game Changers
- Bracket 2 (Mid-Power): EXACTLY 0 Game Changers
- Bracket 3 (High-Power): MÁXIMO 3 Game Changers en total
- Bracket 4 (cEDH): Ilimitados
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from pydantic import BaseModel, Field
from .standards import BracketTier
from ..models.deck import Deck, DeckItem
from ..models.card import Card


class GameChangerDefinition(BaseModel):
    name: str
    category: str  # 'Fast Mana', 'Free Interaction', 'Mass Stax/Lock', 'Value Engine/Tax', '2-Card Combo Wincon', 'Mass Land Destruction', 'Tutor', 'Mass Sweeper'
    allowed_in_brackets: List[int] = Field(default_factory=list, description="List of Bracket numbers where this card is legal without downshift violations.")
    efficiency_tier: str = Field(default="S-Tier", description="Efficiency rating: S-Tier (Máxima Eficiencia/Format Warping), A-Tier (Alta Eficiencia), B-Tier (Eficiencia Situacional)")
    efficiency_explanation: str = Field(default="", description="Explicación detallada de la eficiencia de la carta, tempo y ratio maná/impacto.")
    description: str = Field(default="", description="Descripción funcional del impacto de la carta.")
    suggested_replacements_by_bracket: Dict[int, List[str]] = Field(
        default_factory=dict,
        description="Suggested replacement cards when downshifting to Bracket 3, Bracket 2, or Bracket 1.",
    )


# -----------------------------------------------------------------------------
# COMPREHENSIVE GAME CHANGERS REGISTRY
# -----------------------------------------------------------------------------
GAME_CHANGERS_DATABASE: Dict[str, GameChangerDefinition] = {
    # ==================== 1. 2-Card Instant Wincons & cEDH Combos ====================
    "Thassa's Oracle": GameChangerDefinition(
        name="Thassa's Oracle",
        category="2-Card Combo Wincon",
        allowed_in_brackets=[4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Victoria instantánea incondicional por solo {U}{U} (2 manás). Su habilidad comprueba devoción tras vaciar la biblioteca.",
        description="Condición de victoria de turno 2-3 prácticamente imparable con Demonic Consultation / Tainted Pact.",
        suggested_replacements_by_bracket={
            3: ["Laboratory Maniac", "Triskaidekaphile", "Aetherflux Reservoir"],
            2: ["Psychosis Crawler", "Approach of the Second Sun", "Niv-Mizzet, Parun"],
            1: ["Sphinx of the Second Sun", "Diluvian Primordial"],
        },
    ),
    "Demonic Consultation": GameChangerDefinition(
        name="Demonic Consultation",
        category="2-Card Combo Wincon",
        allowed_in_brackets=[4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="1 maná instantáneo {B} para exiliar toda la baraja en respuesta al trigger de Thassa's Oracle.",
        description="Exilio completo de biblioteca instantáneo de 1 maná para ganar con Thassa's Oracle.",
        suggested_replacements_by_bracket={
            3: ["Diabolic Intent", "Beseech the Mirror", "Grim Tutor"],
            2: ["Diabolic Tutor", "Mastermind's Acquisition", "Read the Bones"],
            1: ["Sign in Blood", "Night's Whisper"],
        },
    ),
    "Tainted Pact": GameChangerDefinition(
        name="Tainted Pact",
        category="2-Card Combo Wincon",
        allowed_in_brackets=[4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Tutor instantáneo por {1}{B} que además vacía la biblioteca para líneas de victoria cEDH.",
        description="Tutor instantáneo y vaciado de biblioteca de 2 manás para líneas de victoria cEDH.",
        suggested_replacements_by_bracket={
            3: ["Grim Tutor", "Vampiric Tutor", "Wishclaw Talisman"],
            2: ["Diabolic Tutor", "Increasing Ambition"],
            1: ["Ambition's Cost", "Read the Bones"],
        },
    ),
    "Underworld Breach": GameChangerDefinition(
        name="Underworld Breach",
        category="2-Card Combo Wincon",
        allowed_in_brackets=[4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por solo {1}{R}, otorga Escape a todo el cementerio. Con Brain Freeze o LED genera tormenta infinita.",
        description="Motor de tormenta y combo con Brain Freeze y Lion's Eye Diamond para ciclar todo el mazo.",
        suggested_replacements_by_bracket={
            3: ["Past in Flames", "Mizzix's Mastery", "Jeska's Will"],
            2: ["Anarchist", "Recoup", "Faithless Looting"],
            1: ["Tormenting Voice", "Wild Guess"],
        },
    ),
    "Ad Nauseam": GameChangerDefinition(
        name="Ad Nauseam",
        category="2-Card Combo Wincon",
        allowed_in_brackets=[4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="A velocidad instantánea por {3}{B}{B}, roba 20-30 cartas en mazos con curva baja, garantizando victoria inmediata.",
        description="Robo masivo de 20-30 cartas por 5 manás para victoria inmediata en el mismo turno.",
        suggested_replacements_by_bracket={
            3: ["Peer into the Abyss", "Necropotence", "Bolas's Citadel"],
            2: ["Read the Bones", "Promise of Power", "Phyrexian Arena"],
            1: ["Ambition's Cost", "Ancient Craving"],
        },
    ),
    "Food Chain": GameChangerDefinition(
        name="Food Chain",
        category="2-Card Combo Wincon",
        allowed_in_brackets=[4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Genera maná infinito de criaturas con permanentes exiliables como Squee o Misthollow Griffin.",
        description="Maná de criaturas infinito con criaturas exiliables como Squee o Misthollow Griffin.",
        suggested_replacements_by_bracket={
            3: ["Birthing Pod", "Eldritch Evolution", "Chord of Calling"],
            2: ["Yisan, the Wanderer Bard", "Evolutionary Leap"],
            1: ["Cultivate", "Kodama's Reach"],
        },
    ),
    "Hermit Druid": GameChangerDefinition(
        name="Hermit Druid",
        category="2-Card Combo Wincon",
        allowed_in_brackets=[4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Activa por {G} para vaciar toda la biblioteca al cementerio en bases de maná sin tierras básicas.",
        description="Vacía todo el cementerio en turnos tempranos si el mazo carece de tierras básicas.",
        suggested_replacements_by_bracket={
            3: ["Life from the Loam", "Golgari Grave-Troll", "Stitcher's Supplier"],
            2: ["Satyr Wayfinder", "Grisly Salvage"],
            1: ["Mulch", "Grapple with the Past"],
        },
    ),
    "Doomsday": GameChangerDefinition(
        name="Doomsday",
        category="2-Card Combo Wincon",
        allowed_in_brackets=[4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Reduce la biblioteca a 5 cartas exactas por {B}{B}{B} para resolver una pila de victoria en el mismo turno.",
        description="Pila de 5 cartas de victoria inmediata para líneas de combo de alta velocidad.",
        suggested_replacements_by_bracket={
            3: ["Insidious Dreams", "Beseech the Mirror", "Bolas's Citadel"],
            2: ["Increasing Ambition", "Diabolic Tutor"],
            1: ["Read the Bones", "Sign in Blood"],
        },
    ),
    "Dualcaster Mage": GameChangerDefinition(
        name="Dualcaster Mage",
        category="2-Card Combo Wincon",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Combo instantáneo de criaturas infinitas con Twinflame / Saw in Half por solo 5 manás totales.",
        description="Combo instantáneo de copias infinitas con Twinflame o Saw in Half.",
        suggested_replacements_by_bracket={
            2: ["Guttersnipe", "Young Pyromancer", "Electrostatic Field"],
            1: ["Thermo-Alchemist", "Firebrand Archer"],
        },
    ),
    "Twinflame": GameChangerDefinition(
        name="Twinflame",
        category="2-Card Combo Wincon",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Copia criaturas con prisa y genera combo infinito con Dualcaster Mage por 2 manás.",
        description="Pieza de combo infinito de 2 manás con Dualcaster Mage.",
        suggested_replacements_by_bracket={
            2: ["Heat Shimmer", "Riku of Two Reflections"],
            1: ["Act of Treason", "Threaten"],
        },
    ),
    "Isochron Scepter": GameChangerDefinition(
        name="Isochron Scepter",
        category="2-Card Combo Wincon",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Maná infinito e interacción ilimitada con Dramatic Reversal e instantáneos de 2 manás.",
        description="Maná y lanzamientos infinitos imprimiendo Dramatic Reversal.",
        suggested_replacements_by_bracket={
            2: ["Panharmonicon", "Mirari", "Thousand-Year Storm"],
            1: ["Strionic Resonator", "Primal Amulet"],
        },
    ),
    "Dramatic Reversal": GameChangerDefinition(
        name="Dramatic Reversal",
        category="2-Card Combo Wincon",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Endereza todos los no-tierra por {1}{U}. Con Isochron Scepter y 3+ manás de rocas es maná infinito.",
        description="Enderezador masivo y pieza clave de Isochron Scepter.",
        suggested_replacements_by_bracket={
            2: ["Turnabout", "Frantic Search", "Snap"],
            1: ["Unwind", "Rewind"],
        },
    ),

    # ==================== 2. Fast Mana & Explosive Accelerators ====================
    "Sol Ring": GameChangerDefinition(
        name="Sol Ring",
        category="Fast Mana",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por {1} maná incoloro produce {C}{C} cada turno. Genera una aceleración de +1 maná neto en turno 1 y ventaja de tempo insalvable.",
        description="Acelerador format-defining ({1} de coste para obtener {C}{C} indefinidamente).",
        suggested_replacements_by_bracket={
            2: ["Arcane Signet", "Fellwar Stone", "Thought Vessel", "Mind Stone"],
            1: ["Commander's Sphere", "Worn Powerstone", "Hedron Archive"],
        },
    ),
    "Mana Crypt": GameChangerDefinition(
        name="Mana Crypt",
        category="Fast Mana",
        allowed_in_brackets=[4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Coste {0} que produce {C}{C} cada turno indefinidamente. Genera una ventaja de tempo insalvable.",
        description="Aceleración de coste 0 ({T}: {C}{C}) que distorsiona el tempo de la partida.",
        suggested_replacements_by_bracket={
            3: ["Sol Ring", "Mana Vault", "Mind Stone"],
            2: ["Arcane Signet", "Fellwar Stone", "Thought Vessel"],
            1: ["Commander's Sphere", "Worn Powerstone"],
        },
    ),
    "Jeweled Lotus": GameChangerDefinition(
        name="Jeweled Lotus",
        category="Fast Mana",
        allowed_in_brackets=[4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Coste {0} que produce 3 manás para el comandante. Permite bajar comandantes en turno 1.",
        description="Baja al comandante 3 turnos antes de tiempo de forma gratuita ({T}, Sacrificar: +3 manás).",
        suggested_replacements_by_bracket={
            3: ["Lotus Petal", "Mox Amber", "Sol Ring"],
            2: ["Arcane Signet", "Fellwar Stone"],
            1: ["Commander's Sphere", "Mind Stone"],
        },
    ),
    "Dockside Extortionist": GameChangerDefinition(
        name="Dockside Extortionist",
        category="Fast Mana",
        allowed_in_brackets=[4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Coste {1}{R}. Genera entre 4 y 10 tesoros al entrar, facilitando victorias tempranas.",
        description="Generación explosiva de tesoros de 2 manás proporcional a artefactos y encantamientos rivales.",
        suggested_replacements_by_bracket={
            3: ["Smothering Tithe", "Jeska's Will", "Professional Face-Breaker"],
            2: ["Goldspan Dragon", "Storm-Kiln Artist", "Strike It Rich"],
            1: ["Seething Song", "Irencrag Feat"],
        },
    ),
    "Chrome Mox": GameChangerDefinition(
        name="Chrome Mox",
        category="Fast Mana",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Aceleración de {0} manás exiliando 1 carta de la mano. Clave para acelerar turnos 1 y 2.",
        description="Acelerador libre de maná ({0} CMC) a cambio de una carta de la mano.",
        suggested_replacements_by_bracket={
            2: ["Arcane Signet", "Talisman of Progress", "Fellwar Stone"],
            1: ["Commander's Sphere", "Mind Stone"],
        },
    ),
    "Mox Diamond": GameChangerDefinition(
        name="Mox Diamond",
        category="Fast Mana",
        allowed_in_brackets=[4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Aceleración de coste {0} descartando una tierra. Fija cualquier color en turno 1.",
        description="Aceleración incolora libre descartando una tierra al entrar al campo.",
        suggested_replacements_by_bracket={
            3: ["Mox Amber", "Lotus Petal", "Fellwar Stone"],
            2: ["Arcane Signet", "Mind Stone"],
            1: ["Prismatic Lens", "Wayfarer's Bauble"],
        },
    ),
    "Lion's Eye Diamond": GameChangerDefinition(
        name="Lion's Eye Diamond",
        category="Fast Mana",
        allowed_in_brackets=[4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Coste {0} que da 3 manás descartando la mano. Motor central de combos con Underworld Breach.",
        description="Pieza fundamental de combos de tormenta y Underworld Breach.",
        suggested_replacements_by_bracket={
            3: ["Lotus Petal", "Mana Vault", "Jeska's Will"],
            2: ["Sol Ring", "Mind Stone"],
            1: ["Worn Powerstone", "Hedron Archive"],
        },
    ),
    "Mana Vault": GameChangerDefinition(
        name="Mana Vault",
        category="Fast Mana",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Pagas 1 maná y obtienes 3 manás incoloros inmediatamente (+2 manás netos en turno 1).",
        description="Inyección de +2 manás en turno 1 ({1} de coste para obtener {C}{C}{C}).",
        suggested_replacements_by_bracket={
            2: ["Sol Ring", "Thought Vessel", "Mind Stone"],
            1: ["Worn Powerstone", "Commander's Sphere"],
        },
    ),
    "Grim Monolith": GameChangerDefinition(
        name="Grim Monolith",
        category="Fast Mana",
        allowed_in_brackets=[4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Coste {2} para dar 3 manás. Genera maná infinito con Power Artifact o Kinnan.",
        description="Maná incoloro explosivo y combo de maná infinito con Power Artifact.",
        suggested_replacements_by_bracket={
            3: ["Basalt Monolith", "Thran Dynamo", "Mind Stone"],
            2: ["Worn Powerstone", "Hedron Archive"],
            1: ["Firemind Vessel", "Otepek Huntmaster"],
        },
    ),
    "Jeska's Will": GameChangerDefinition(
        name="Jeska's Will",
        category="Fast Mana",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por 3 manás genera típicamente 5 a 7 manás rojos e impulsa 3 cartas con el comandante en juego.",
        description="Generador masivo de maná rojo y ventaja de cartas simultánea por 3 manás.",
        suggested_replacements_by_bracket={
            2: ["Seething Song", "Irencrag Feat", "Mana Geyser"],
            1: ["Pyretic Ritual", "Desperate Ritual"],
        },
    ),
    "Ancient Tomb": GameChangerDefinition(
        name="Ancient Tomb",
        category="Fast Mana",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Tierra de turno 1 que produce {C}{C} a cambio de 2 vidas. Acelera permanentemente la curva.",
        description="Tierra rápida que produce 2 manás incoloros a coste de 2 vidas.",
        suggested_replacements_by_bracket={
            2: ["Temple of the False God", "Guildless Commons", "Evolving Wilds"],
            1: ["Wastes", "Command Tower"],
        },
    ),

    # ==================== 3. Format-Warping Value Engines & Taxes ====================
    "The One Ring": GameChangerDefinition(
        name="The One Ring",
        category="Value Engine/Tax",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Otorga protección contra todo por 1 turno y roba 1, 2, 3, 4 cartas acumulativamente por turno sin coste de maná.",
        description="Protección incondicional y motor de robo acumulativo masivo e incoloro.",
        suggested_replacements_by_bracket={
            2: ["Reckoner Bankbuster", "Mind's Eye", "Mazemind Tome"],
            1: ["Staff of Nin", "Arcane Encyclopedia"],
        },
    ),
    "Rhystic Study": GameChangerDefinition(
        name="Rhystic Study",
        category="Value Engine/Tax",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Tasa a cada rival con {1} por cada hechizo o roba 1 carta. Genera de 3 a 6 cartas por ronda.",
        description="Motor de robo y tasa asimétrico por 3 manás que genera ventaja de cartas extrema.",
        suggested_replacements_by_bracket={
            2: ["Mystic Remora", "Archivist of Oghma", "Bident of Thassa", "Reconnaissance Mission"],
            1: ["Coastal Piracy", "Fact or Fiction", "Deep Analysis"],
        },
    ),
    "Mystic Remora": GameChangerDefinition(
        name="Mystic Remora",
        category="Value Engine/Tax",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por solo 1 maná azul {U}, tasa hechizos no-criatura con {4} o roba carta.",
        description="El pez de 1 maná: roba cartas masivamente contra artefactos, maná rápido e interacción enemiga.",
        suggested_replacements_by_bracket={
            2: ["Reconnaissance Mission", "Bident of Thassa", "Curiosity"],
            1: ["Divination", "Winged Words"],
        },
    ),
    "Smothering Tithe": GameChangerDefinition(
        name="Smothering Tithe",
        category="Value Engine/Tax",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Genera 1 tesoro por cada robo rival a menos que paguen {2}. Produce entre 3 y 6 manás por ronda.",
        description="Generador masivo de maná y tesoros castigando el robo natural y acumulativo de los rivales.",
        suggested_replacements_by_bracket={
            2: ["Monologue Tax", "Loran of the Third Path", "Trouble in Pairs"],
            1: ["Smuggler's Share", "Keeper of the Accord"],
        },
    ),
    "Esper Sentinel": GameChangerDefinition(
        name="Esper Sentinel",
        category="Value Engine/Tax",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por {W} tasa el primer hechizo no-criatura de cada rival exigiendo pagar su fuerza o robas carta.",
        description="Motor de robo de 1 maná para castigar hechizos no-criatura de oponentes.",
        suggested_replacements_by_bracket={
            2: ["Archivist of Oghma", "Mangara, the Diplomat", "Welcoming Vampire"],
            1: ["Mentor of the Meek", "Cut a Deal"],
        },
    ),
    "Necropotence": GameChangerDefinition(
        name="Necropotence",
        category="Value Engine/Tax",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por {B}{B}{B} te permite pagar cualquier cantidad de vidas para robar ese número exacto de cartas al paso final.",
        description="Motor supremo de robo negro: convierte directamente puntos de vida en cartas en mano.",
        suggested_replacements_by_bracket={
            2: ["Phyrexian Arena", "Greed", "Underworld Connections"],
            1: ["Read the Bones", "Sign in Blood"],
        },
    ),
    "Orcish Bowmasters": GameChangerDefinition(
        name="Orcish Bowmasters",
        category="Value Engine/Tax",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por {1}{B} con destello castiga instantáneamente los robos rivales haciendo daño y creando un ejército creciente.",
        description="Castigo mortal instantáneo de 2 manás contra motores de robo acumulativo.",
        suggested_replacements_by_bracket={
            2: ["Underworld Dreams", "Fate Unraveler", "Sheoldred, the Apocalypse"],
            1: ["Spiteful Visions", "Ob Nixilis, the Hate-Twisted"],
        },
    ),
    "Bolas's Citadel": GameChangerDefinition(
        name="Bolas's Citadel",
        category="Value Engine/Tax",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Te permite jugar la carta superior de tu biblioteca pagando vidas en lugar de maná. Combo con Sensei's Divining Top.",
        description="Lanza cartas desde el top de la biblioteca pagando vidas.",
        suggested_replacements_by_bracket={
            2: ["Phyrexian Arena", "Twilight Prophet", "Black Market Connections"],
            1: ["Sign in Blood", "Night's Whisper"],
        },
    ),

    # ==================== 4. Universal 1-2 Mana Tutors ====================
    "Demonic Tutor": GameChangerDefinition(
        name="Demonic Tutor",
        category="Tutor",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por {1}{B} busca cualquier carta de la baraja y la pone directamente en la mano sin revelarla.",
        description="El tutor incondicional más eficiente y versátil de Magic (2 manás a la mano).",
        suggested_replacements_by_bracket={
            2: ["Diabolic Tutor", "Mastermind's Acquisition", "Grim Tutor"],
            1: ["Diabolic Revelation", "Razaketh's Rite"],
        },
    ),
    "Vampiric Tutor": GameChangerDefinition(
        name="Vampiric Tutor",
        category="Tutor",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por {B} a velocidad de instantáneo pone cualquier carta del mazo en el top por 2 vidas.",
        description="Tutor instantáneo incondicional de 1 maná al top de la biblioteca.",
        suggested_replacements_by_bracket={
            2: ["Wishclaw Talisman", "Diabolic Tutor", "Scheming Symmetry"],
            1: ["Read the Bones", "Sign in Blood"],
        },
    ),
    "Imperial Seal": GameChangerDefinition(
        name="Imperial Seal",
        category="Tutor",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por {B} conjuro busca cualquier carta y la coloca en el top perdiendo 2 vidas.",
        description="Tutor de 1 maná al top de la biblioteca.",
        suggested_replacements_by_bracket={
            2: ["Diabolic Tutor", "Grim Tutor"],
            1: ["Sign in Blood", "Night's Whisper"],
        },
    ),
    "Mystical Tutor": GameChangerDefinition(
        name="Mystical Tutor",
        category="Tutor",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por {U} instantáneo busca cualquier instantáneo o conjuro y lo coloca en el top.",
        description="Tutor instantáneo de 1 maná para hechizos de victoria o contrahechizos.",
        suggested_replacements_by_bracket={
            2: ["Solve the Equation", "Merchant Scroll"],
            1: ["Compulsive Research", "Ponder"],
        },
    ),
    "Worldly Tutor": GameChangerDefinition(
        name="Worldly Tutor",
        category="Tutor",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por {G} instantáneo busca cualquier criatura del mazo y la coloca en el top.",
        description="Tutor instantáneo de 1 maná para piezas clave de criatura.",
        suggested_replacements_by_bracket={
            2: ["Time of Need", "Fauna Shaman", "Fierce Empath"],
            1: ["Elvish Visionary", "Llanowar Visionary"],
        },
    ),
    "Enlightened Tutor": GameChangerDefinition(
        name="Enlightened Tutor",
        category="Tutor",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por {W} instantáneo busca cualquier artefacto o encantamiento (fast mana, stax, combo) al top.",
        description="Tutor instantáneo de 1 maná para artefactos o encantamientos.",
        suggested_replacements_by_bracket={
            2: ["Idyllic Tutor", "Open the Armory", "Heliod's Pilgrim"],
            1: ["Relic Seeker", "Danitha Capashen, Paragon"],
        },
    ),
    "Gamble": GameChangerDefinition(
        name="Gamble",
        category="Tutor",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Por {R} busca cualquier carta a la mano y descarta una carta al azar.",
        description="Tutor universal rojo de 1 maná a la mano.",
        suggested_replacements_by_bracket={
            2: ["Faithless Looting", "Thrill of Possibility"],
            1: ["Tormenting Voice", "Cathartic Reunion"],
        },
    ),
    "Urza's Saga": GameChangerDefinition(
        name="Urza's Saga",
        category="Tutor",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Tierra encantamiento que crea autómatas gigantes y en capítulo III tutora artefactos de coste 0-1 (Sol Ring, Mana Crypt, Skullclamp) directamente al campo.",
        description="Tierra que genera amenazas y tutora artefactos de coste 0 o 1 directamente a la mesa.",
        suggested_replacements_by_bracket={
            2: ["Reliquary Tower", "Buried Ruin", "Command Beacon"],
            1: ["Wastes", "Rogue's Passage"],
        },
    ),

    # ==================== 5. Free Interaction & Unfair Counterspells ====================
    "Force of Will": GameChangerDefinition(
        name="Force of Will",
        category="Free Interaction",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Contrahechizo de coste {0} (exiliando carta azul y 1 vida). Detiene victorias enemigas con tierras giradas.",
        description="Contrahechizo de coste 0 ({0} exiliando carta azul) para proteger combos y frenar amenazas.",
        suggested_replacements_by_bracket={
            2: ["Counterspell", "Negate", "Dovin's Veto", "Swan Song"],
            1: ["Cancel", "Saw It Coming", "Dissolve"],
        },
    ),
    "Fierce Guardianship": GameChangerDefinition(
        name="Fierce Guardianship",
        category="Free Interaction",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Coste {0} con el comandante en mesa. Niega cualquier hechizo no-criatura gratis.",
        description="Negación incondicional de coste 0 si controlas a tu comandante.",
        suggested_replacements_by_bracket={
            2: ["Swan Song", "Negate", "Arcane Denial"],
            1: ["Dissipate", "Spell Pierce"],
        },
    ),
    "Deflecting Swat": GameChangerDefinition(
        name="Deflecting Swat",
        category="Free Interaction",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Coste {0} con comandante en juego. Redirige hechizos y habilidades al objetivo que elijas.",
        description="Redirección gratuita de cualquier hechizo o habilidad que tenga un objetivo.",
        suggested_replacements_by_bracket={
            2: ["Bolt Bend", "Wild Ricochet", "Tibalt's Trickery"],
            1: ["Chef's Kiss", "Ricochet Trap"],
        },
    ),
    "Deadly Rollick": GameChangerDefinition(
        name="Deadly Rollick",
        category="Free Interaction",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Exilio incondicional de criatura de coste {0} con el comandante en juego.",
        description="Exilio gratuito instantáneo de criatura si controlas a tu comandante.",
        suggested_replacements_by_bracket={
            2: ["Infernal Grasp", "Snuff Out", "Go for the Throat"],
            1: ["Murder", "Hero's Downfall", "Doom Blade"],
        },
    ),
    "Pact of Negation": GameChangerDefinition(
        name="Pact of Negation",
        category="Free Interaction",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Contrahechizo de coste {0} puro para proteger el turno de victoria.",
        description="Contrahechizo absoluto de coste 0 utilizado para asegurar el turno de victoria.",
        suggested_replacements_by_bracket={
            2: ["Counterspell", "Dispel", "Spell Pierce"],
            1: ["Cancel", "Convolute"],
        },
    ),
    "Mindbreak Trap": GameChangerDefinition(
        name="Mindbreak Trap",
        category="Free Interaction",
        allowed_in_brackets=[4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Exilia cualquier número de hechizos en la pila por {0} si un oponente lanzó 3+ hechizos.",
        description="Exilio masivo de hechizos en la pila gratis contra cadenas de tormenta y contrahechizos.",
        suggested_replacements_by_bracket={
            3: ["Flusterstorm", "Sublime Epiphany", "Disallow"],
            2: ["Whirlwind Denial", "Counterspell"],
            1: ["Cancel", "Spell Contortion"],
        },
    ),
    "Cyclonic Rift": GameChangerDefinition(
        name="Cyclonic Rift",
        category="Mass Sweeper",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por {6}{U} a velocidad instantánea regresa TODOS los permanentes no-tierra de TODOS los rivales a la mano, limpiando mesas asimétricamente.",
        description="Limpieza asimétrica masiva instantánea de toda la mesa rival.",
        suggested_replacements_by_bracket={
            2: ["Aetherize", "Evacuation", "Aetherspouts", "Whelming Wave"],
            1: ["Engulf the Shore", "Flood of Tears"],
        },
    ),

    # ==================== 6. Mass Stax / Hard Locks ====================
    "Winter Orb": GameChangerDefinition(
        name="Winter Orb",
        category="Mass Stax/Lock",
        allowed_in_brackets=[4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Por {2} manás restringe el enderezar de tierras a solo 1 por turno para todos los jugadores.",
        description="Bloqueo masivo de maná: los jugadores solo enderezan 1 tierra durante el paso de enderezar.",
        suggested_replacements_by_bracket={
            3: ["Static Orb", "Damping Sphere", "Thalia, Guardian of Thraben"],
            2: ["Blind Obedience", "Authority of the Consuls", "Ghostly Prison"],
            1: ["Propaganda", "Sphere of Safety"],
        },
    ),
    "Armageddon": GameChangerDefinition(
        name="Armageddon",
        category="Mass Land Destruction",
        allowed_in_brackets=[4, 5],
        efficiency_tier="B-Tier (Eficiencia Situacional)",
        efficiency_explanation="Destruye todas las tierras por {3}{W}, destruyendo el ritmo de juego.",
        description="Destrucción masiva de todas las tierras de la mesa.",
        suggested_replacements_by_bracket={
            3: ["Fall of the Thran", "Cataclysm", "Farewell"],
            2: ["Cleansing Nova", "Austere Command", "Wrath of God"],
            1: ["Day of Judgment", "Fumigate"],
        },
    ),
    "Stasis": GameChangerDefinition(
        name="Stasis",
        category="Mass Stax/Lock",
        allowed_in_brackets=[4, 5],
        efficiency_tier="A-Tier (Alta Eficiencia)",
        efficiency_explanation="Por {1}{U} nadie endereza nada en su turno, creando un bloqueo absoluto del juego.",
        description="Parálisis total de enderezado para todos los jugadores ({1}{U} encantamiento).",
        suggested_replacements_by_bracket={
            3: ["Frozen Aether", "Tangle Wire", "Archon of Emeria"],
            2: ["Kismet", "Blind Obedience", "Aven Mindcensor"],
            1: ["Ghostly Prison", "Baird, Steward of Argive"],
        },
    ),
    "Drannith Magistrate": GameChangerDefinition(
        name="Drannith Magistrate",
        category="Mass Stax/Lock",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por {1}{W} bloquea el lanzamiento de comandantes enemigos desde la zona de mando.",
        description="Impide que los oponentes lancen cartas desde cualquier zona que no sea la mano.",
        suggested_replacements_by_bracket={
            2: ["Aven Mindcensor", "Hushbringer", "Thalia, Heretic Cathar"],
            1: ["Imposing Sovereign", "Leonin Arbiter"],
        },
    ),
    "Opposition Agent": GameChangerDefinition(
        name="Opposition Agent",
        category="Mass Stax/Lock",
        allowed_in_brackets=[3, 4, 5],
        efficiency_tier="S-Tier (Máxima Eficiencia / Format Warping)",
        efficiency_explanation="Por {2}{B} con destello, te permite controlar al oponente mientras busca en su biblioteca y robar la carta buscada.",
        description="Secuestro instantáneo de tutores y búsquedas de tierras/cartas enemigas.",
        suggested_replacements_by_bracket={
            2: ["Aven Mindcensor", "Dauthi Voidwalker", "Kambal, Consul of Allocation"],
            1: ["Huture Hater", "Mindcrank"],
        },
    ),
}


class GameChangerViolation(BaseModel):
    card_name: str
    category: str
    current_allowed_brackets: List[int]
    target_bracket: int
    rule_violation_reason: str
    suggested_in_bracket_replacements: List[str]


class GameChangerAuditItem(BaseModel):
    card_name: str
    category: str
    is_allowed: bool
    status_label: str  # e.g., "PERMANECE (Permitido)" or "DEBE SALIR (Prohibido)"
    allowed_brackets: List[int]
    target_bracket: int
    efficiency_tier: str
    efficiency_explanation: str
    description: str
    suggested_in_bracket_replacements: List[str]


class GameChangersEvaluator:
    """Evaluates presence of Game Changers, individual efficiency, and bracket compliance."""

    @classmethod
    def find_game_changers_in_deck(cls, deck: Deck) -> List[Tuple[DeckItem, GameChangerDefinition]]:
        """Returns all cards in the deck that match the Game Changers registry."""
        found: List[Tuple[DeckItem, GameChangerDefinition]] = []
        all_items = deck.commanders + deck.maindeck
        
        for item in all_items:
            name_clean = item.effective_name.strip()
            for gc_name, gc_def in GAME_CHANGERS_DATABASE.items():
                if name_clean.lower() == gc_name.lower():
                    found.append((item, gc_def))
                    break
        return found

    @classmethod
    def audit_deck_game_changers(cls, deck: Deck, target_bracket: int) -> List[GameChangerAuditItem]:
        """
        Performs an individual, card-by-card audit of all Game Changers found in the deck,
        evaluating bracket legality, quota limits (Max 3 in Bracket 3, 0 in Brackets 1-2),
        efficiency tier, and suitable in-bracket replacements.
        """
        audit_items: List[GameChangerAuditItem] = []
        found_changers = cls.find_game_changers_in_deck(deck)

        max_allowed_quota = {1: 0, 2: 0, 3: 3, 4: 99}.get(target_bracket, 3)
        allowed_count = 0

        for item, gc_def in found_changers:
            bracket_legal = target_bracket in gc_def.allowed_in_brackets
            is_allowed = False
            status_label = ""

            if not bracket_legal:
                is_allowed = False
                status_label = f"DEBE SALIR (Prohibido en Bracket {target_bracket})"
            elif allowed_count < max_allowed_quota:
                is_allowed = True
                allowed_count += 1
                if target_bracket == 3:
                    status_label = f"PERMANECE EN EL MAZO (Game Changer #{allowed_count}/3 en Bracket 3)"
                else:
                    status_label = f"PERMANECE EN EL MAZO (Permitido en Bracket {target_bracket})"
            else:
                is_allowed = False
                status_label = f"EXCEDE EL CUPO (Máximo {max_allowed_quota} Game Changers en Bracket {target_bracket} - Debe salir)"

            replacements = gc_def.suggested_replacements_by_bracket.get(target_bracket, [])
            if not replacements:
                replacements = gc_def.suggested_replacements_by_bracket.get(2, ["Sol Ring", "Arcane Signet", "Counterspell"])

            audit_items.append(
                GameChangerAuditItem(
                    card_name=gc_def.name,
                    category=gc_def.category,
                    is_allowed=is_allowed,
                    status_label=status_label,
                    allowed_brackets=gc_def.allowed_in_brackets,
                    target_bracket=target_bracket,
                    efficiency_tier=gc_def.efficiency_tier,
                    efficiency_explanation=gc_def.efficiency_explanation,
                    description=gc_def.description,
                    suggested_in_bracket_replacements=replacements,
                )
            )

        return audit_items

    @classmethod
    def evaluate_bracket_compliance(
        cls,
        deck: Deck,
        target_bracket: int,
    ) -> List[GameChangerViolation]:
        """
        Determines which Game Changers in the deck MUST be removed to comply with target_bracket rules,
        including absolute tier bans and the strict 3-Game-Changer quota limit in Bracket 3 (0 in Brackets 1-2).
        """
        violations: List[GameChangerViolation] = []
        found_changers = cls.find_game_changers_in_deck(deck)

        max_quota = {1: 0, 2: 0, 3: 3, 4: 99, 5: 99}.get(target_bracket, 3)
        kept_count = 0

        for item, gc_def in found_changers:
            replacements = gc_def.suggested_replacements_by_bracket.get(target_bracket, [])
            if not replacements:
                replacements = gc_def.suggested_replacements_by_bracket.get(2, ["Sol Ring", "Counterspell", "Heroic Intervention"])

            # 1. Card is strictly prohibited in this bracket tier
            if target_bracket not in gc_def.allowed_in_brackets:
                violation = GameChangerViolation(
                    card_name=gc_def.name,
                    category=gc_def.category,
                    current_allowed_brackets=gc_def.allowed_in_brackets,
                    target_bracket=target_bracket,
                    rule_violation_reason=(
                        f"La carta '{gc_def.name}' [{gc_def.category}] está prohibida en Bracket {target_bracket} "
                        f"(solo legal en Bracket(s) {', '.join(str(b) for b in gc_def.allowed_in_brackets)}). {gc_def.description}"
                    ),
                    suggested_in_bracket_replacements=replacements,
                )
                violations.append(violation)
            # 2. Card exceeds the allowed numerical quota for this bracket
            elif kept_count < max_quota:
                kept_count += 1
            else:
                violation = GameChangerViolation(
                    card_name=gc_def.name,
                    category=gc_def.category,
                    current_allowed_brackets=gc_def.allowed_in_brackets,
                    target_bracket=target_bracket,
                    rule_violation_reason=(
                        f"La carta '{gc_def.name}' [{gc_def.category}] es un Game Changer legal en Bracket {target_bracket}, "
                        f"pero el mazo ya alcanzó el límite máximo permitido de {max_quota} Game Changers. Debe ser sustituida para no subir de Bracket."
                    ),
                    suggested_in_bracket_replacements=replacements,
                )
                violations.append(violation)

        return violations
