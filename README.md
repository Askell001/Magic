# MTG Deck Optimizer: Ingestion & Normalization Module

Módulo en Python diseñado para la ingesta universal, normalización y enriquecimiento de mazos de **Magic: The Gathering** (Commander y formatos construidos) mediante la API pública de **Scryfall**.

---

## 🚀 Características Principales

1. **Parser Universal de Texto Plano (`MTGDeckTextParser`)**:
   - Compatible con exportaciones directas de **Moxfield**, **Archidekt**, **DeckStats**, **TCGplayer**, **MTG Arena** y **Magic Online**.
   - Soporta sintaxis de cantidades (`1x`, `4`), códigos de edición y número de coleccionista (`(LEA) 270`, `(CMM:123)`, `[SLD]`, `[LEA] Sol Ring`), marcas de foil (`*F*`, `*Foil*`, `(foil)`), tags personalizados (`#Ramp`, `[Draw]`) y cartas de doble cara/split (`Fire // Ice`, `Delver of Secrets // ...`).
   - Clasificación automática y separación en secciones: **Commander(s)**, **Maindeck**, **Sideboard** y **Maybeboard / Considering**.

2. **Sincronización Eficiente con Scryfall (`ScryfallClient`)**:
   - Implementa el endpoint por lotes `/cards/collection` (hasta 75 identificadores por solicitud HTTP POST) reduciendo el tiempo de red al mínimo.
   - Cumple con las directrices de Scryfall (User-Agent identificativo y delay de 50-100ms entre solicitudes).
   - Mecanismo de fallback por nombre de carta y sistema de caché en memoria para evitar peticiones redundantes.

3. **Modelo de Datos Robusto con Pydantic v2 (`models`)**:
   - `Card`: Representación exhaustiva Scryfall (tipos, CMC, colores, identidad de color, Oracle Text, keywords, precios USD/EUR, imágenes, legalidades, caras DFC).
   - `DeckItem`: Representa cada línea de carta (cantidad, foil, tags, sección y metadatos de Scryfall).
   - `Deck`: Representación integral del mazo con cálculo dinámico de curva, conteos, identidad de color y valor económico total.
   - `DeckAnalysis`: Análisis diagnóstico (curva de maná sin tierras, promedios de CMC, distribución por colores y tipos de permanente/hechizo, advertencias de formato Commander).

4. **Definición de Brackets de Poder y Clasificador (`brackets`)**:
   - **Bracket 1 (Jank / Casual)**: Sin combos, presupuesto bajo, curva alta (CMC > 3.5), tierras lentas.
   - **Bracket 2 (Mid-Power / Casual Optimizado)**: Sinergia clara, wincons definidas, sin fast mana (CMC ~2.8-3.4).
   - **Bracket 3 (High-Power / Optimized)**: Fast mana permitido, combos eficientes de 2-3 cartas, tutores e interacción barata (CMC ~2.0-2.8).
   - **Bracket 4 (cEDH / Máximo Nivel)**: Eficiencia absoluta, wincons t2-t4 (Thoracle/Consultation), interactividad máxima (CMC ~1.4-2.0).
   - `CardRoleClassifier`: Detección automática de Fast Mana, Tutores, Interacción gratuita/barata, Wipes, Rampa y Combos infinitos conocidos.

5. **Evaluación de Intención y Métrica de Desviación (`intent` y `gap_analyzer`)**:
   - `UserIntent`: Captura Bracket objetivo (1 a 4), presupuesto en USD y cartas 'intocables' o icónicas protegidas.
   - `ask_user_intent_cli()`: Cuestionario interactivo por terminal / API builder.
   - `DeckGapAnalyzer`: Algoritmo que calcula la métrica de desviación global (0.0 a 10.0), brechas de CMC, tierras, rampa, tutores, interacción, margen de presupuesto y recomendaciones accionables.

6. **Motor de Inteligencia Artificial y Datos Comunitarios (`ai`)**:
   - `CommunityDataService`: Extrae sinergias de alto win-rate, staples del comandante y tasas de inclusión comunitarias (estilo EDHREC/MTGGoldfish).
   - `AIPromptBuilder`: Transforma el mazo, la intención del usuario, el gap report y los datos comunitarios en un prompt estructurado para LLMs (Gemini / OpenAI / Anthropic).
   - `DeckOptimizerAgent`: Orquesta la inferencia con IA (soporte para llamadas a APIs de LLM externas o inferencia inteligente heurística integrada).
7. **Servicio de Actualización Diaria y Detección de Spoiled/New Cards (`scryfall/recent_cards_service.py` y `mongo_storage.py`)**:
   - **Filtro de Lanzamientos Recientes**: Consulta automática al endpoint `/cards/search?q=is:spoiler+OR+year>=2026` extrayendo las últimas revelaciones, Secret Lair y Universes Beyond.
   - **Almacenamiento Incremental con MongoDB Atlas**: Conexión a base de datos (`mongodb+srv://user:12345@registrousuarios.e6jeny6.mongodb.net/`) con índices y fallback automático a caché local JSON en caso de desconexión.
   - **Context Injection para la IA (`context_injector.py`)**: Filtra las últimas innovaciones según la identidad de color del comandante e inyecta un bloque contextual en el prompt para considerar cartas del meta actual.

8. **Interfaz Gráfica Interactiva en Streamlit (`app.py`)**:
   - **Área de carga**: Textarea universal para pegar listas de cartas o subir archivos `.txt` / `.dec`, con presets para carga rápida.
   - **Panel de configuración**: Slider interactivo de Bracket objetivo (1 al 4) con tarjetas informativas, selector de presupuesto USD, campo para cartas intocables y botón de sincronización de spoilers.
   - **Dashboard de Resultados**:
     - Visualización comparativa de la curva de maná (**Antes vs Después**) con gráficos de barras interactivos.
     - Tabla comparativa estilizada de cambios (**Cortes vs Inclusiones**) con CMC, roles, justificaciones y precios.
     - Pestaña de **Innovaciones & Spoilers 2026** filtradas por comandante.
     - Pestañas de análisis profundo (Base de maná, Wincons, Gap Analysis y Finanzas).
   - **Exportador 1-Clic**: Generador de lista en formato estándar de Moxfield / Archidekt con botón de descarga directa de archivo `.txt`.

---

## 📁 Estructura del Proyecto

```
magic proyect/
├── mtg_deck_optimizer/
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── card.py          # Clases Card, CardPrices, CardImageUris, CardFace
│   │   ├── deck.py          # Clases Deck, DeckItem, DeckSection
│   │   └── analysis.py      # Clase DeckAnalysis (curva CMC, colores, tipos, precios)
│   ├── parser/
│   │   ├── __init__.py
│   │   ├── patterns.py      # Regexes para cabeceras, líneas, tags y sets
│   │   └── text_parser.py   # MTGDeckTextParser universal
│   ├── scryfall/
│   │   ├── __init__.py
│   │   └── client.py        # ScryfallClient con batch collection y caché
│   └── service.py           # DeckIngestionService (orquestador)
├── tests/
│   ├── __init__.py
│   ├── fixtures/
│   │   └── sample_decks.py  # Muestras reales Moxfield, Archidekt, DeckStats, TCGplayer
│   ├── test_parser.py       # Pruebas unitarias del parser
│   ├── test_models.py       # Pruebas de modelos Pydantic y serialización
│   └── test_scryfall.py     # Pruebas unitarias de Scryfall (mock y caché)
├── run_demo.py              # Script ejecutable de demostración completa
├── pyproject.toml
└── requirements.txt
```

---

## 🛠️ Instalación y Requisitos

Requiere **Python 3.10+**.

```bash
pip install -r requirements.txt
```

---

## 🧪 Ejecución de Pruebas Unitarias

```bash
pytest -v
```

---

## 🌐 Ejecución de la Interfaz Web (Streamlit)

Para abrir la aplicación interactiva en tu navegador:

```bash
streamlit run app.py
```

Accede a `http://localhost:8501` para interactuar con la interfaz completa de optimización.

---

## 🎮 Ejecución de Scripts CLI y Demostraciones

```bash
python run_demo.py
```

### Ejemplo de Uso en Código

```python
from mtg_deck_optimizer.service import DeckIngestionService

raw_text = """
// Commander
1 The Ur-Dragon (C17) 48 *F*

// Mainboard
1 Sol Ring (LEA) 270
1 Rhystic Study (JMP) 169 *F*
1 Cyclonic Rift (RTR) 35
"""

service = DeckIngestionService()
deck, analysis = service.ingest_from_text(
    raw_text=raw_text,
    deck_name="Ur-Dragon Deck",
    default_format="commander",
    enrich=True  # Consulta Scryfall API
)

# Imprimir JSON estructurado
print(deck.model_dump_json(indent=2))

# Acceder al análisis
print(f"Curva de maná: {analysis.mana_curve}")
print(f"Identidad de color: {deck.color_identity}")
print(f"Valor estimado USD: ${deck.estimated_total_usd}")
```
