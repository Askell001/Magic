"""
Streamlit Web Application for MTG Commander Studio & Advanced Analytics Suite.
Complete Graphical UI with Scryfall Images, Visual Trade-offs, WotC Rules Validation,
Game Changers Database & Downshifting Transitions, Land Balance (Deficit/Overload) Engine,
Monte Carlo 1,000-Draw Simulator, and Deckbuilder from scratch.
"""

import time
import urllib.parse
import streamlit as st
import pandas as pd
from typing import List, Optional, Any

from mtg_deck_optimizer.models.deck import Deck, DeckSection, DeckItem
from mtg_deck_optimizer.service import DeckIngestionService
from mtg_deck_optimizer.rules.wotc_rules_engine import WOTC_Commander_Rules_Engine
from mtg_deck_optimizer.deckbuilder.generator import MTGDeckbuilderGenerator
from mtg_deck_optimizer.deckbuilder.models import DeckbuilderParams
from mtg_deck_optimizer.deckbuilder.archetype_database import ARCHETYPE_DEFINITIONS
from mtg_deck_optimizer.exporter.deck_exporter import DeckExporter
from mtg_deck_optimizer.intent import build_user_intent
from mtg_deck_optimizer.brackets.standards import BracketTier
from mtg_deck_optimizer.brackets.game_changers import (
    GAME_CHANGERS_DATABASE,
    GameChangersEvaluator,
    GameChangerViolation,
    GameChangerAuditItem,
)
from mtg_deck_optimizer.analytics.advanced_analytics import Advanced_Deck_Analytics
from mtg_deck_optimizer.analytics.mulligan_simulator import MulliganSimulator
from mtg_deck_optimizer.analytics.tradeoff_engine import TradeoffEngine
from mtg_deck_optimizer.analytics.land_balance_engine import LandBalanceEngine, LandBalanceReport

# -----------------------------------------------------------------------------
# Streamlit UI Setup
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="MTG Commander Studio & Visual Analytics",
    page_icon="🧙",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main {
        background-color: #0e1117;
        color: #e6edf3;
    }
    .step-header {
        background: linear-gradient(90deg, #1f6feb 0%, #238636 100%);
        color: white;
        padding: 10px 18px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 1.15rem;
        margin-top: 15px;
        margin-bottom: 15px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .tradeoff-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 14px;
    }
    .gc-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .stMetric {
        background: #161b22;
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #30363d;
    }
    .badge-out {
        background: #da3633;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .badge-in {
        background: #238636;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .badge-gc {
        background: #8957e5;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .badge-tier-s {
        background: #d97706;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .badge-tier-a {
        background: #2563eb;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .badge-tier-b {
        background: #4b5563;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .badge-land {
        background: #059669;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Services & State
# -----------------------------------------------------------------------------
@st.cache_resource
def get_services():
    return DeckIngestionService(), WOTC_Commander_Rules_Engine(), MTGDeckbuilderGenerator()

ingestion_service, rules_engine, deckbuilder_gen = get_services()

def get_card_image_url(card_or_name: Any) -> str:
    """Helper accepting Card, DeckItem, or card name string to return verified high-res image."""
    if hasattr(card_or_name, "image_uris") and card_or_name.image_uris and card_or_name.image_uris.normal:
        url = card_or_name.image_uris.normal
        if url and "cards.scryfall.io/back.jpg" not in url and "4c565076-5db2-47ea-8ee0-4a4fd7bb353d" not in url:
            return url
    if hasattr(card_or_name, "effective_name"):
        raw_n = card_or_name.effective_name
    elif hasattr(card_or_name, "name"):
        raw_n = card_or_name.name
    elif hasattr(card_or_name, "raw_name"):
        raw_n = card_or_name.raw_name
    else:
        raw_n = str(card_or_name)
    return ingestion_service.scryfall.get_card_image_url(raw_n)

if "raw_decklist" not in st.session_state:
    st.session_state.raw_decklist = ""
if "cmdr_override" not in st.session_state:
    st.session_state.cmdr_override = ""
if "deck_analyzed" not in st.session_state:
    st.session_state.deck_analyzed = False
if "current_deck" not in st.session_state:
    st.session_state.current_deck = None
if "current_wotc" not in st.session_state:
    st.session_state.current_wotc = None
if "current_pip" not in st.session_state:
    st.session_state.current_pip = None
if "current_gc" not in st.session_state:
    st.session_state.current_gc = None
if "generated_deck_result" not in st.session_state:
    st.session_state.generated_deck_result = None
if "optimized_report" not in st.session_state:
    st.session_state.optimized_report = None
if "optimized_deck" not in st.session_state:
    st.session_state.optimized_deck = None
if "gap_report" not in st.session_state:
    st.session_state.gap_report = None
if "mulligan_result" not in st.session_state:
    st.session_state.mulligan_result = None
if "chosen_gen_cmdr" not in st.session_state:
    st.session_state.chosen_gen_cmdr = None

# -----------------------------------------------------------------------------
# Top-Level Navigation Mode Selector
# -----------------------------------------------------------------------------
st.title("🧙 MTG Commander Studio & Visual Analytics Suite")
app_mode = st.radio(
    "Selecciona el Modo de Trabajo:",
    ["🔄 Optimizar Mazo Existente (Optimizer & Visual Studio)", "🔨 Generar Mazo desde Cero (Deckbuilder Generator)"],
    horizontal=True,
)

# =============================================================================
# MODO 1: OPTIMIZAR MAZO EXISTENTE
# =============================================================================
if "Optimizar Mazo" in app_mode:
    st.markdown('<div class="step-header">⚙️ PASO 1: Configuración Inicial del Mazo</div>', unsafe_allow_html=True)
    
    col_deck_in, col_config = st.columns([3, 2])

    with col_deck_in:
        deck_text_input = st.text_area(
            "Pega tu lista de mazo (Moxfield, Archidekt, MTGO o texto plano):",
            value=st.session_state.raw_decklist,
            height=260,
            placeholder="""1 Atraxa, Praetors' Voice
1 Sol Ring
1 Arcane Signet
1 Rhystic Study
...""",
        )
        st.session_state.raw_decklist = deck_text_input

        cmdr_input = st.text_input(
            "👑 Comandante (Opcional - Si se deja vacío, el sistema lo detectará automáticamente como la primera carta de la lista):",
            value=st.session_state.cmdr_override,
            placeholder="Ej: Atraxa, Praetors' Voice",
        )
        st.session_state.cmdr_override = cmdr_input

    with col_config:
        st.markdown("#### Parámetros de Optimización")
        opt_bracket_num = st.selectbox(
            "Bracket Objetivo:",
            options=[1, 2, 3, 4],
            index=2,
            format_func=lambda x: {
                1: "Bracket 1: Casual / Jank (0 Game Changers, sin combos)",
                2: "Bracket 2: Core EDH / Mid Power (0 Game Changers, sin combos rápidos)",
                3: "Bracket 3: High Power (Máximo 3 Game Changers, interacción rápida)",
                4: "Bracket 4: Competitive EDH / cEDH (Game Changers ilimitados, fast mana, combos T1-T3)",
            }[x],
        )

        all_archetype_names = list(ARCHETYPE_DEFINITIONS.keys())
        selected_archetype = st.selectbox("Estrategia / Arquetipo Objetivo:", all_archetype_names, index=0)

        budget_unlimited = st.checkbox("Sin límite de presupuesto", value=True)
        opt_max_budget = None
        if not budget_unlimited:
            opt_max_budget = st.number_input("Presupuesto Máximo de Upgrade (USD):", min_value=5.0, value=150.0, step=10.0)

        untouchables_str = st.text_area("Cartas Intocables (separadas por comas):", placeholder="Sol Ring, Rhystic Study")
        untouchable_cards = [c.strip() for c in untouchables_str.split(",") if c.strip()]

    # Explicit Action Buttons for Transition to Step 2
    col_btn_proc, col_btn_clear = st.columns([3, 1])
    with col_btn_proc:
        analyze_btn = st.button("▶️ Procesar y Analizar Mazo (Pasar al Paso 2)", type="primary", use_container_width=True)
    with col_btn_clear:
        if st.button("🔄 Limpiar / Reset", use_container_width=True):
            st.session_state.deck_analyzed = False
            st.session_state.current_deck = None
            st.session_state.current_wotc = None
            st.session_state.current_pip = None
            st.session_state.current_gc = None
            st.session_state.optimized_report = None
            st.session_state.raw_decklist = ""
            st.rerun()

    if analyze_btn:
        if not deck_text_input.strip():
            st.warning("⚠️ Por favor ingresa una lista de mazo antes de procesar.")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()

            # Step 1: Normalize & Detect Commander
            status_text.markdown("📖 **Paso 1/4:** Leyendo lista de cartas y detectando comandante...")
            progress_bar.progress(25)
            time.sleep(0.05)

            active_cmdr = cmdr_input.strip() if cmdr_input.strip() else None
            if not active_cmdr:
                for line in deck_text_input.strip().splitlines():
                    clean_l = ingestion_service.scryfall.clean_card_name(line)
                    if clean_l and not clean_l.startswith("//") and not clean_l.startswith("#"):
                        active_cmdr = clean_l
                        break

            # Step 2: Ingest & Scryfall CDN Enrichment
            status_text.markdown("🌐 **Paso 2/4:** Consultando metadatos, precios e imágenes en alta resolución en Scryfall CDN...")
            progress_bar.progress(50)
            deck, _ = ingestion_service.ingest_from_text(
                raw_text=deck_text_input,
                deck_name="Commander Deck",
                commander_override=active_cmdr,
            )

            # Step 3: WotC Rules Validation
            status_text.markdown("⚖️ **Paso 3/4:** Validando reglas oficiales de WotC Commander (Identidad de color, Banlist, Singleton)...")
            progress_bar.progress(75)
            wotc_result = rules_engine.validate_deck(deck)
            pip_report = Advanced_Deck_Analytics.analyze_mana_pip_balance(deck)

            # Step 4: Game Changers & Bracket Evaluation
            status_text.markdown("🏆 **Paso 4/4:** Evaluando Game Changers, cuotas por Bracket y balance de tierras...")
            progress_bar.progress(100)
            gc_audit_items = GameChangersEvaluator.audit_deck_game_changers(deck, opt_bracket_num)
            time.sleep(0.1)

            status_text.empty()
            progress_bar.empty()

            st.session_state.current_deck = deck
            st.session_state.current_wotc = wotc_result
            st.session_state.current_pip = pip_report
            st.session_state.current_gc = gc_audit_items
            st.session_state.deck_analyzed = True

    # -------------------------------------------------------------------------
    # PASO 2: Ingesta, Validación Gráfica & Diagnósticos
    # -------------------------------------------------------------------------
    if not st.session_state.deck_analyzed or st.session_state.current_deck is None:
        st.info("👆 Ingresa tu lista de mazo arriba y haz clic en **'▶️ Procesar y Analizar Mazo (Pasar al Paso 2)'** para comenzar el diagnóstico visual interactivo.")
        st.stop()

    deck = st.session_state.current_deck
    wotc_result = st.session_state.current_wotc or rules_engine.validate_deck(deck)
    pip_report = st.session_state.current_pip or Advanced_Deck_Analytics.analyze_mana_pip_balance(deck)
    # Re-evaluate Game Changers for currently chosen bracket dynamically
    gc_audit_items = GameChangersEvaluator.audit_deck_game_changers(deck, opt_bracket_num)

    st.markdown('<div class="step-header">📊 PASO 2: Previsualización Gráfica & Diagnóstico Integral</div>', unsafe_allow_html=True)

    # Deck Header KPIs
    kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)
    kpi_col1.metric("🃏 Total Cartas", f"{deck.total_cards}")
    kpi_col2.metric("👑 Comandante", deck.commander_name or "No identificado")
    kpi_col3.metric("🎨 Identidad de Color", "".join(deck.color_identity) if deck.color_identity else "Incoloro")
    kpi_col4.metric("📈 Curva Promedio", f"{deck.average_cmc_without_lands:.2f} CMC")
    kpi_col5.metric("💰 Valor Estimado", f"${deck.total_price_usd:,.2f} USD" if deck.total_price_usd else "N/A")

    # WotC Rules Diagnostics Alerts
    if not wotc_result.is_legal:
        st.error(f"❌ **Infracciones del Reglamento WOTC ({len(wotc_result.violations)} encontradas):**")
        for v in wotc_result.violations:
            st.markdown(f"- 🚫 **{v.rule_name}** ({v.offending_card}): {v.explanation}")
    else:
        st.success(f"✅ **Mazo 100% Legal en Commander/EDH** (Identidad de color {''.join(deck.color_identity)}, Singleton y Banlist cumplidos).")

    # Visual Gallery Tabs including Dedicated Game Changers Audit Tab
    tab_gal_cmdr, tab_gal_creatures, tab_gal_spells, tab_gal_lands, tab_pip_math, tab_gc_audit, tab_gc_db = st.tabs([
        f"👑 Commander ({len(deck.commanders)})",
        f"🐉 Criaturas ({len([it for it in deck.maindeck if it.card and 'Creature' in it.card.type_line])})",
        f"🔮 Soportes y Hechizos ({len([it for it in deck.maindeck if it.card and 'Creature' not in it.card.type_line and 'Land' not in it.card.type_line])})",
        f"🌲 Tierras ({len([it for it in deck.maindeck if it.card and 'Land' in it.card.type_line])})",
        "⚖️ Balance de Tierras y Pips",
        f"🏆 Auditoría Game Changers ({len(gc_audit_items)})",
        "📚 Catálogo Completo Game Changers",
    ])

    def render_card_grid(items, cols_count=5):
        """Renders cards row by row in strict grid layout to prevent vertical displacement."""
        if not items:
            st.info("No hay cartas en esta categoría.")
            return
        for i in range(0, len(items), cols_count):
            row_items = items[i:i + cols_count]
            cols = st.columns(cols_count)
            for c_idx, item in enumerate(row_items):
                col = cols[c_idx]
                card = item.card
                img_url = get_card_image_url(card or item)
                with col:
                    st.markdown(f"**{item.quantity}x {item.effective_name}**")
                    st.image(img_url, use_container_width=True)
                    price_txt = f"${item.total_price_usd:.2f} USD" if item.total_price_usd else "N/A"
                    cmc_txt = f"{card.cmc:.0f} CMC" if card else ""
                    st.caption(f"{cmc_txt} | {price_txt}")

    with tab_gal_cmdr:
        render_card_grid(deck.commanders, cols_count=4)
    with tab_gal_creatures:
        render_card_grid([it for it in deck.maindeck if it.card and "Creature" in it.card.type_line])
    with tab_gal_spells:
        render_card_grid([it for it in deck.maindeck if not (it.card and ("Creature" in it.card.type_line or "Land" in it.card.type_line))])
    with tab_gal_lands:
        render_card_grid([it for it in deck.maindeck if it.card and "Land" in it.card.type_line])

    with tab_pip_math:
        st.markdown("### 📊 Balance de Símbolos Requeridos (Pips) vs Fuentes Producidas")
        pip_rows = []
        for c_code, b in pip_report.color_breakdowns.items():
            pip_rows.append({
                "Color": b.color_name,
                "Pips Requeridos (Costes)": f"{b.pips_required_count} ({b.pips_required_percentage}%)",
                "Fuentes Producidas (Tierras/Rocas)": f"{b.sources_produced_count} ({b.sources_produced_percentage}%)",
                "Diferencial": f"{b.deficit_or_surplus_percentage:+.1f}%",
                "Diagnóstico": b.status_summary,
            })
        st.dataframe(pd.DataFrame(pip_rows), use_container_width=True)

        st.divider()
        st.markdown("### ⚖️ Diagnóstico de Tierras: Déficit o Sobrecarga (Land Balance)")
        land_report = LandBalanceEngine.evaluate_land_balance(deck, BracketTier(opt_bracket_num), set(untouchable_cards))
        
        lb_col1, lb_col2, lb_col3, lb_col4 = st.columns(4)
        lb_col1.metric("🌲 Tierras Actuales", f"{land_report.current_land_count}")
        lb_col2.metric("🎯 Rango Recomendado", f"{land_report.target_land_min} - {land_report.target_land_max}")
        lb_col3.metric("⚖️ Estado de Tierras", land_report.status)
        diff_str = f"{land_report.deficit_or_surplus_count:+d}" if land_report.deficit_or_surplus_count != 0 else "0"
        lb_col4.metric("📈 Ajuste Recomendado", f"{diff_str} Tierras")

        st.info(land_report.diagnosis_message)

        if land_report.adjustments:
            st.markdown("#### 🔄 Plan de Corrección de Tierras (Cortes y Sustituciones Recomendadas):")
            for adj_idx, adj in enumerate(land_report.adjustments, 1):
                with st.container():
                    st.markdown(
                        f"""
                        <div class="tradeoff-card">
                            <div style="font-weight:bold; color:#f0883e; margin-bottom:6px;">
                                #{adj_idx}: {adj.category} ({adj.cut_card_name} ➔ {adj.add_card_name})
                            </div>
                            <div style="font-size:0.92rem;"><strong>💡 Justificación:</strong> {adj.reason}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    c_cut, c_add = st.columns(2)
                    with c_cut:
                        badge_label = "❌ SACAR HECHIZO PESADO" if adj.action == "cut_spell_add_land" else "❌ SACAR TIERRA SOBRANTE"
                        st.markdown(f"<span class='badge-out'>{badge_label}</span> **{adj.cut_card_name}**", unsafe_allow_html=True)
                        st.image(get_card_image_url(adj.cut_card_name), use_container_width=True)
                        st.caption(f"{adj.cut_card_type} | {adj.cut_card_cmc:.0f} CMC")
                    with c_add:
                        badge_label_in = "✅ METER TIERRA ÓPTIMA" if adj.action == "cut_spell_add_land" else "✅ METER HECHIZO DE VALOR"
                        st.markdown(f"<span class='badge-in'>{badge_label_in}</span> **{adj.add_card_name}**", unsafe_allow_html=True)
                        st.image(get_card_image_url(adj.add_card_name), use_container_width=True)
                        st.caption(f"{adj.add_card_type} | {adj.add_card_cmc:.0f} CMC")
                    st.divider()

        if land_report.fixing_upgrade_suggestions:
            st.markdown("**🛠️ Sugerencias de Fijación de Color (Color Fixing):**")
            for fix_sug in land_report.fixing_upgrade_suggestions:
                st.markdown(f"- 💡 {fix_sug}")

    with tab_gc_audit:
        st.markdown(f"### 🏆 Auditoría Individual de Game Changers en el Mazo (Bracket {opt_bracket_num})")
        st.caption("Identificación individual carta por carta, nivel de eficiencia competitiva, estatus de permanencia y sustitutos legales en el bracket.")

        if not gc_audit_items:
            st.success(f"🌿 **No se detectaron Game Changers format-warping en este mazo.** Es 100% compatible con partidas casuales y no altera las restricciones de Bracket {opt_bracket_num}.")
        else:
            allowed_count = sum(1 for it in gc_audit_items if it.is_allowed)
            forbidden_count = len(gc_audit_items) - allowed_count

            gc_k1, gc_k2, gc_k3 = st.columns(3)
            gc_k1.metric("🃏 Total Game Changers Detectados", f"{len(gc_audit_items)}")
            gc_k2.metric(f"🟢 Permitidos en Bracket {opt_bracket_num}", f"{allowed_count}")
            gc_k3.metric(f"🔴 Prohibidos / Exceden Cupo en Bracket {opt_bracket_num}", f"{forbidden_count}")

            for gc_item in gc_audit_items:
                tier_badge = "badge-tier-s" if "S-Tier" in gc_item.efficiency_tier else ("badge-tier-a" if "A-Tier" in gc_item.efficiency_tier else "badge-tier-b")
                status_badge = "badge-in" if gc_item.is_allowed else "badge-out"

                with st.container():
                    st.markdown(
                        f"""
                        <div class="gc-card">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                                <span style="font-size:1.2rem; font-weight:bold; color:#58a6ff;">🃏 {gc_item.card_name}</span>
                                <div>
                                    <span class="{status_badge}">{gc_item.status_label}</span>
                                    <span class="{tier_badge}">{gc_item.efficiency_tier.split(' ')[0]}</span>
                                    <span class="badge-gc">{gc_item.category}</span>
                                </div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    c_gc_img, c_gc_info, c_gc_reps = st.columns([1, 2, 2])

                    with c_gc_img:
                        st.image(get_card_image_url(gc_item.card_name), use_container_width=True)
                        st.caption(f"Brackets legales: {', '.join(str(b) for b in gc_item.allowed_brackets)}")

                    with c_gc_info:
                        st.markdown(f"**⚡ Eficiencia y Nivel:** {gc_item.efficiency_tier}")
                        st.markdown(f"**💡 Explicación de Eficiencia:** {gc_item.efficiency_explanation}")
                        st.markdown(f"**📖 Función Principal:** {gc_item.description}")
                        if not gc_item.is_allowed:
                            st.error(f"⚠️ {gc_item.status_label}")
                        else:
                            st.success(f"✅ Permitida dentro del cupo reglamentario de Bracket {opt_bracket_num}.")

                    with c_gc_reps:
                        if not gc_item.is_allowed:
                            st.markdown(f"**🔄 Sustitutos Legales Recomendados para Bracket {opt_bracket_num}:**")
                            rep_cols = st.columns(min(len(gc_item.suggested_in_bracket_replacements), 2))
                            for r_idx, rep_name in enumerate(gc_item.suggested_in_bracket_replacements[:2]):
                                with rep_cols[r_idx % 2]:
                                    st.markdown(f"**{rep_name}**")
                                    st.image(get_card_image_url(rep_name), use_container_width=True)
                        else:
                            st.markdown("**🛡️ Estado de Juego:**")
                            st.info(f"Esta carta aporta la máxima velocidad/interacción dentro del estándar de Bracket {opt_bracket_num}.")

                    st.divider()

    with tab_gc_db:
        st.markdown("### 📚 Catálogo Completo de Game Changers & Reglas de Brackets")
        st.caption("Los Game Changers son cartas determinantes del formato. Las reglas de Brackets limitan su presencia para garantizar partidas equilibradas:")
        gc_table_data = []
        for gc_name, gc in GAME_CHANGERS_DATABASE.items():
            gc_table_data.append({
                "Carta": gc.name,
                "Categoría": gc.category,
                "Nivel Eficiencia": gc.efficiency_tier,
                "Brackets Permitidos": ", ".join(f"Bracket {b}" for b in gc.allowed_in_brackets),
                "Descripción / Impacto": gc.description,
            })
        st.dataframe(pd.DataFrame(gc_table_data), use_container_width=True)

    # -------------------------------------------------------------------------
    # PASO 3: Optimización con IA & Advanced Analytics
    # -------------------------------------------------------------------------
    st.markdown('<div class="step-header">🚀 PASO 3: Optimización con IA & Análisis Avanzado</div>', unsafe_allow_html=True)
    if st.button("🚀 Optimizar Mazo con IA", type="primary", use_container_width=True):
        with st.spinner("Analizando sinergias, balanceando tierras, validando Game Changers y ejecutando WOTC Rules Engine..."):
            user_intent = build_user_intent(
                target_bracket=opt_bracket_num,
                max_budget_usd=opt_max_budget,
                untouchable_cards=untouchable_cards,
                allow_infinite_combos=(opt_bracket_num >= 3),
                allow_fast_mana=(opt_bracket_num >= 3),
            )

            from mtg_deck_optimizer.brackets.gap_analyzer import DeckGapAnalyzer
            from mtg_deck_optimizer.ai.optimizer_agent import DeckOptimizerAgent

            gap_report = DeckGapAnalyzer.analyze(deck, user_intent)
            agent = DeckOptimizerAgent()
            report = agent.optimize(deck, user_intent)

            exporter = DeckExporter()
            opt_deck, opt_curve, opt_cmc = exporter.apply_optimization(deck, report)
            export_text = exporter.export_to_text(opt_deck)

            st.session_state.optimized_report = report
            st.session_state.optimized_deck = opt_deck
            st.session_state.gap_report = gap_report
            st.session_state.export_text = export_text

    if st.session_state.optimized_report is not None:
        report = st.session_state.optimized_report
        opt_deck = st.session_state.optimized_deck
        gap_report = st.session_state.gap_report
        export_text = st.session_state.export_text

        st.success("🎉 ¡Optimización completada y validada contra el reglamento oficial de WotC!")

        s_col1, s_col2, s_col3, s_col4 = st.columns(4)
        s_col1.metric("📊 Diagnóstico Inicial", f"Bracket {report.initial_bracket.value}")
        s_col2.metric("🎯 Bracket Objetivo", f"Bracket {report.target_bracket.value}")
        s_col3.metric("⭐ Power Score Estimado", f"{report.estimated_new_power_score:.1f} / 4.0")
        s_col4.metric("💰 Coste Neto Upgrade", f"${report.budget_summary.net_upgrade_cost_usd:,.2f} USD")

        # ---------------------------------------------------------------------
        # 1. Card-by-Card Trade-off Table with Visual Comparison & 3-Tier Budget Alternatives
        # ---------------------------------------------------------------------
        st.divider()
        st.subheader("🔄 Sistema Visual de Sugerencias 'Card-by-Card Trade-off' (Análisis Causa-Efecto)")
        st.caption("Cada corte está emparejado visualmente con su sustituto óptimo, mostrando imágenes oficiales y opciones de presupuesto:")

        tradeoff_objs = TradeoffEngine.build_pairwise_tradeoffs(report.cuts, report.inclusions, BracketTier(opt_bracket_num))
        
        for idx, to in enumerate(tradeoff_objs, 1):
            with st.container():
                st.markdown(
                    f"""
                    <div class="tradeoff-card">
                        <div style="font-size:1.15rem; font-weight:bold; color:#58a6ff; margin-bottom:8px;">
                            #{idx}: {to.display_title}
                        </div>
                        <div style="margin-bottom:12px; font-size:0.95rem; line-height:1.4;">
                            <strong>💡 Justificación Técnica:</strong> {to.technical_justification}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Visual Side-by-side: Cut Card vs Added Card
                c_out_col, c_in_col, c_tiers_col = st.columns([1, 1, 2])
                
                with c_out_col:
                    st.markdown(f"<span class='badge-out'>❌ CORTAR</span> **{to.card_cut_name}**", unsafe_allow_html=True)
                    st.image(get_card_image_url(to.card_cut_name), use_container_width=True)
                    st.caption(f"CMC: {to.cut_cmc:.0f} | Rol: {to.cut_role}")

                with c_in_col:
                    badge_style = "badge-land" if "Land" in to.in_role or "Tierra" in to.in_role else "badge-in"
                    st.markdown(f"<span class='{badge_style}'>✅ INCLUIR</span> **{to.card_in_name}**", unsafe_allow_html=True)
                    st.image(get_card_image_url(to.card_in_name), use_container_width=True)
                    st.caption(f"CMC: {to.in_cmc:.0f} | Impacto: {to.cmc_delta:+.0f} CMC")

                with c_tiers_col:
                    st.markdown("#### 💰 Opciones de Presupuesto para este espacio:")
                    tb1, tb2, tb3 = st.columns(3)
                    
                    with tb1:
                        if to.budget_tiers.budget_sidegrade:
                            st.markdown("**🪙 Económica**")
                            st.markdown(f"**{to.budget_tiers.budget_sidegrade.name}** (`${to.budget_tiers.budget_sidegrade.estimated_price_usd:.2f}`)")
                            st.image(get_card_image_url(to.budget_tiers.budget_sidegrade.name), use_container_width=True)
                            st.caption(to.budget_tiers.budget_sidegrade.description)
                    with tb2:
                        st.markdown("**⭐ Óptima**")
                        st.markdown(f"**{to.budget_tiers.recommended.name}** (`${to.budget_tiers.recommended.estimated_price_usd:.2f}`)")
                        st.image(get_card_image_url(to.budget_tiers.recommended.name), use_container_width=True)
                        st.caption(to.budget_tiers.recommended.description)
                    with tb3:
                        if to.budget_tiers.premium_staple:
                            st.markdown("**💎 Premium**")
                            st.markdown(f"**{to.budget_tiers.premium_staple.name}** (`${to.budget_tiers.premium_staple.estimated_price_usd:.2f}`)")
                            st.image(get_card_image_url(to.budget_tiers.premium_staple.name), use_container_width=True)
                            st.caption(to.budget_tiers.premium_staple.description)

                st.divider()

        # ---------------------------------------------------------------------
        # 2. Monte Carlo Mulligan Simulator (1,000 Draws)
        # ---------------------------------------------------------------------
        st.divider()
        st.subheader("🎲 Simulador de Manos Iniciales Monte Carlo (1,000 Robos)")
        st.caption("Prueba la consistencia estadística de apertura antes y después de aplicar los cambios:")

        col_sim_btn, col_sim_stat = st.columns([1, 3])
        with col_sim_btn:
            if st.button("🎲 Ejecutar 1,000 Simulaciones", type="secondary", use_container_width=True):
                with st.spinner("Ejecutando 1,000 robos virtuales de 7 cartas..."):
                    st.session_state.mulligan_result = MulliganSimulator.simulate_opening_hands(opt_deck, num_simulations=1000)

        if st.session_state.mulligan_result is None:
            st.session_state.mulligan_result = MulliganSimulator.simulate_opening_hands(opt_deck, num_simulations=1000)

        m_res = st.session_state.mulligan_result
        ms_col1, ms_col2, ms_col3, ms_col4, ms_col5 = st.columns(5)
        ms_col1.metric("🟢 Manos Jugables", f"{m_res.playable_hand_rate_percent}%")
        ms_col2.metric("🔴 Atasco (Screw)", f"{m_res.mana_screw_rate_percent}%")
        ms_col3.metric("🔵 Inundación (Flood)", f"{m_res.mana_flood_rate_percent}%")
        ms_col4.metric("⚔️ Interacción T1-T3", f"{m_res.interaction_turn_1_to_3_percent}%")
        ms_col5.metric("👑 Turno Comandante", f"Turno {m_res.avg_commander_cast_turn:.1f}")

        st.info(f"💡 **Diagnóstico de Apertura:** {m_res.mulligan_advice}")

        with st.expander("👀 Ver 3 Manos Iniciales de Muestra Generadas por la Simulación"):
            for i, hand in enumerate(m_res.sample_opening_hands, 1):
                st.markdown(f"**Mano #{i}:**")
                hand_cols = st.columns(len(hand))
                for h_idx, card_name in enumerate(hand):
                    with hand_cols[h_idx]:
                        st.image(get_card_image_url(card_name), use_container_width=True)
                        st.caption(card_name)

        # ---------------------------------------------------------------------
        # Mana Curve Comparison Chart
        # ---------------------------------------------------------------------
        st.divider()
        st.subheader("📈 Comparativa de Curva de Maná (Antes vs Después)")
        before_counts = {i: 0 for i in range(8)}
        for it in deck.maindeck:
            if it.card and "Land" not in it.card.type_line:
                bucket = min(int(it.card.cmc), 7)
                before_counts[bucket] += it.quantity

        after_counts = {i: 0 for i in range(8)}
        for it in opt_deck.maindeck:
            if it.card and "Land" not in it.card.type_line:
                bucket = min(int(it.card.cmc), 7)
                after_counts[bucket] += it.quantity

        curve_df = pd.DataFrame({
            "CMC": ["0", "1", "2", "3", "4", "5", "6", "7+"],
            "Original": [before_counts[i] for i in range(8)],
            "Optimizado": [after_counts[i] for i in range(8)],
        }).set_index("CMC")
        st.bar_chart(curve_df, color=["#58a6ff", "#3fb950"])

        # ---------------------------------------------------------------------
        # Export
        # ---------------------------------------------------------------------
        st.divider()
        st.subheader("📦 Exportador a Moxfield / Archidekt")
        st.text_area("Lista optimizada:", value=export_text, height=220)
        st.download_button(
            label="💾 Descargar Mazo (.txt)",
            data=export_text,
            file_name=f"{opt_deck.name.replace(' ', '_').lower()}.txt",
            mime="text/plain",
            type="primary",
        )

# =============================================================================
# MODO 2: MTG DECKBUILDER GENERATOR (CONSTRUCCIÓN DESDE CERO)
# =============================================================================
else:
    st.markdown('<div class="step-header">🔨 MTG Deckbuilder Generator: Construcción de Mazo desde Cero</div>', unsafe_allow_html=True)
    st.markdown("Especifica tus parámetros estratégicos o selecciona entre los Comandantes visuales recomendados para sintetizar un mazo de 100 cartas perfectamente balanceado y conforme al reglamento de WotC.")

    gen_col1, gen_col2 = st.columns([1, 1])

    with gen_col1:
        gen_bracket = st.selectbox(
            "Bracket Objetivo para Construcción:",
            [1, 2, 3, 4],
            index=2,
            format_func=lambda x: f"Bracket {x} - { {1:'Casual / Jank (0 Game Changers)', 2:'Core EDH (0 Game Changers)', 3:'High Power (Máx 3 Game Changers)', 4:'cEDH (Ilimitados)'}[x] }",
        )
        gen_strat = st.selectbox("Estrategia / Arquetipo:", list(ARCHETYPE_DEFINITIONS.keys()))

    with gen_col2:
        gen_budget_unlimited = st.checkbox("Presupuesto Ilimitado", value=True, key="gen_unlimited")
        gen_max_budget = None
        if not gen_budget_unlimited:
            gen_max_budget = st.number_input("Presupuesto Máximo (USD):", min_value=20.0, value=250.0, step=25.0)

    st.markdown("#### 👑 Selección de Comandante")
    st.caption("Puedes escribir el nombre de un Comandante o hacer clic en una de las recomendaciones visuales optimizadas para la estrategia elegida:")

    suggested_cmdrs = deckbuilder_gen.suggest_commanders(gen_strat)
    s_cols = st.columns(min(len(suggested_cmdrs), 4))

    for s_idx, cmdr in enumerate(suggested_cmdrs):
        with s_cols[s_idx % 4]:
            img_c_url = get_card_image_url(cmdr.name)
            st.image(img_c_url, use_container_width=True)
            st.markdown(f"**{cmdr.name}**")
            st.caption(f"🎨 Identidad: {''.join(cmdr.color_identity)} | {cmdr.reason}")
            if st.button(f"Seleccionar {cmdr.name}", key=f"btn_cmdr_{s_idx}"):
                st.session_state.chosen_gen_cmdr = cmdr.name

    typed_cmdr = st.text_input("O escribe directamente el Comandante deseado:", value=st.session_state.chosen_gen_cmdr or "")
    if typed_cmdr:
        st.session_state.chosen_gen_cmdr = typed_cmdr

    st.divider()
    if st.button("🔨 Construir Mazo de 100 Cartas", type="primary", use_container_width=True):
        if not st.session_state.chosen_gen_cmdr:
            st.error("Por favor selecciona o escribe un Comandante para comenzar la construcción.")
        else:
            gen_progress = st.progress(0)
            gen_status = st.empty()

            gen_status.markdown("👑 **Paso 1/4:** Extrayendo identidad de color del Comandante y aplicando reglas WotC...")
            gen_progress.progress(25)
            time.sleep(0.05)

            gen_status.markdown(f"🃏 **Paso 2/4:** Ensamblando paquete de sinergia para '{gen_strat}' y aplicando cuota de Bracket {gen_bracket}...")
            gen_progress.progress(50)
            params = DeckbuilderParams(
                commander_name=st.session_state.chosen_gen_cmdr,
                target_bracket=int(gen_bracket),
                strategy_archetype=gen_strat,
                max_budget_usd=gen_max_budget,
            )
            time.sleep(0.05)

            gen_status.markdown("🌲 **Paso 3/4:** Sintetizando base de maná equilibrada por pips y colores requeridos...")
            gen_progress.progress(75)
            gen_result = deckbuilder_gen.build_deck(params)

            gen_status.markdown("✅ **Paso 4/4:** Validando singleton, banlist y exportador...")
            gen_progress.progress(100)
            time.sleep(0.1)

            gen_status.empty()
            gen_progress.empty()

            st.session_state.generated_deck_result = gen_result

    if st.session_state.generated_deck_result:
        res = st.session_state.generated_deck_result
        g_deck = res.deck
        g_wotc = res.validation

        st.success(f"🎉 ¡Mazo '{g_deck.name}' generado exitosamente con {g_deck.total_cards} cartas!")

        gc1, gc2, gc3, gc4 = st.columns(4)
        gc1.metric("🃏 Total Cartas", f"{g_deck.total_cards}")
        gc2.metric("🌲 Tierras", f"{len([it for it in g_deck.maindeck if it.card and 'Land' in it.card.type_line])}")
        gc3.metric("📈 Curva Promedio", f"{g_deck.average_cmc_without_lands:.2f} CMC")
        gc4.metric("💰 Coste Estimado", f"${g_deck.total_price_usd:,.2f} USD")

        if g_wotc.is_legal:
            st.success("✅ Validación WotC: 100% Legal en Commander (Identidad de color y singleton cumplidos).")
        else:
            st.warning(f"⚠️ Alertas WotC: {len(g_wotc.violations)} advertencias.")

        # Visual Deck Gallery with row chunking to guarantee proper layout
        g_tab_all, g_tab_export = st.tabs(["🖼️ Galería Visual del Mazo Generado", "📦 Exportar Lista"])
        
        with g_tab_all:
            g_items = g_deck.commanders + g_deck.maindeck
            for i in range(0, len(g_items), 5):
                row_items = g_items[i:i + 5]
                cols = st.columns(5)
                for c_idx, it in enumerate(row_items):
                    with cols[c_idx]:
                        st.markdown(f"**{it.quantity}x {it.effective_name}**")
                        st.image(get_card_image_url(it.card or it.effective_name), use_container_width=True)
                        st.caption(f"{it.card.type_line if it.card else ''}")

        with g_tab_export:
            st.text_area("Lista generada lista para Moxfield / Archidekt:", value=res.export_text, height=300)
            st.download_button(
                label="💾 Descargar Mazo Generado (.txt)",
                data=res.export_text,
                file_name=f"{g_deck.name.replace(' ', '_').lower()}.txt",
                mime="text/plain",
                type="primary",
            )
