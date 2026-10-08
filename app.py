"""
MTG Commander Studio & Visual Analytics Suite
Official WOTC 5-Bracket Compliance, Real-time Deck Auditing, AI Optimization & Deckbuilder Engine.
"""

import time
import json
import logging
import pandas as pd
import streamlit as st
from typing import List, Dict, Any, Optional, Set

from mtg_deck_optimizer.service import DeckIngestionService
from mtg_deck_optimizer.models.deck import Deck, DeckItem, DeckSection
from mtg_deck_optimizer.rules.wotc_rules_engine import WOTC_Commander_Rules_Engine
from mtg_deck_optimizer.deckbuilder.generator import MTGDeckbuilderGenerator
from mtg_deck_optimizer.deckbuilder.models import DeckbuilderParams
from mtg_deck_optimizer.deckbuilder.archetype_database import ARCHETYPE_DEFINITIONS
from mtg_deck_optimizer.deckbuilder.strategy_service import (
    get_strategies_by_bracket,
    resolve_dynamic_strategy,
    get_strategy_service,
)
from mtg_deck_optimizer.edhrec.synergy_engine import get_edhrec_engine, fetch_edhrec_data
from mtg_deck_optimizer.exporter.deck_exporter import DeckExporter
from mtg_deck_optimizer.intent import build_user_intent
from mtg_deck_optimizer.brackets.standards import (
    BracketTier,
    BRACKET_BENCHMARKS,
    GAME_CHANGERS_MAX_ALLOWED,
)
from mtg_deck_optimizer.brackets.game_changers import (
    GAME_CHANGERS_DATABASE,
    GameChangersEvaluator,
    GameChangerViolation,
    GameChangerAuditItem,
)
from mtg_deck_optimizer.brackets.wotc_bracket_engine import (
    WOTC_Bracket_Engine,
    BracketAuditReport,
    BracketViolation,
    CardRemovalRecommendation,
    ViolationCategory,
)
from mtg_deck_optimizer.analytics.advanced_analytics import Advanced_Deck_Analytics
from mtg_deck_optimizer.analytics.mulligan_simulator import MulliganSimulator
from mtg_deck_optimizer.analytics.tradeoff_engine import TradeoffEngine
from mtg_deck_optimizer.analytics.land_balance_engine import LandBalanceEngine, LandBalanceReport
from seed_banned_cards import validate_banned_cards

# -----------------------------------------------------------------------------
# Streamlit UI Setup & Global Theming
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="MTG Commander Studio & 5-Bracket Engine",
    page_icon="🧙",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main {
        background-color: #0d1117;
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
    .bracket-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 14px;
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
    .alert-box-red {
        background: #3b1219;
        border: 2px solid #f85149;
        border-radius: 10px;
        padding: 16px 20px;
        margin: 14px 0;
        color: #ff7b72;
    }
    .alert-box-green {
        background: #0d2818;
        border: 2px solid #2ea043;
        border-radius: 10px;
        padding: 16px 20px;
        margin: 14px 0;
        color: #56d364;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Cached Global Services & Helpers
# -----------------------------------------------------------------------------
@st.cache_resource
def get_services():
    return DeckIngestionService(), WOTC_Commander_Rules_Engine(), MTGDeckbuilderGenerator()

ingestion_service, rules_engine, deckbuilder_gen = get_services()

def get_card_image_url(card_or_name: Any) -> str:
    """Helper accepting Card, DeckItem, or card name string to return verified high-res Scryfall image."""
    card = getattr(card_or_name, "card", card_or_name)
    if hasattr(card, "image_uris") and card.image_uris and card.image_uris.normal:
        url = card.image_uris.normal
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


def extract_commander_for_preview(raw_text: str, override: Optional[str] = None) -> Optional[str]:
    """Extracts commander accurately from Moxfield tags/sections or explicit override without line 0 bias."""
    if override and override.strip():
        return override.strip()
    if not raw_text or not raw_text.strip():
        return None
    try:
        temp_deck = MTGDeckTextParser.parse(raw_text=raw_text, default_format="commander")
        if temp_deck.commanders:
            return temp_deck.commanders[0].effective_name
        if temp_deck.maindeck:
            return temp_deck.maindeck[0].effective_name
    except Exception:
        pass
    return None


# Session State Initialization
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
if "current_bracket_audit" not in st.session_state:
    st.session_state.current_bracket_audit = None
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
st.title("🧙 MTG Commander Studio & 5-Bracket Engine")
app_mode = st.radio(
    "Selecciona el Modo de Trabajo:",
    ["🔄 Optimizar Mazo Existente (5-Bracket Engine & Visual Studio)", "🔨 Generar Mazo desde Cero (Deckbuilder Generator)"],
    horizontal=True,
)

# =============================================================================
# MODO 1: OPTIMIZAR MAZO EXISTENTE (5-BRACKET ENGINE)
# =============================================================================
if "Optimizar Mazo" in app_mode:
    st.markdown('<div class="step-header">⚙️ PASO 1: Configuración & Selección Oficial de 5 Brackets WotC</div>', unsafe_allow_html=True)
    
    # Obligatory Moxfield Format Banner
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #2b1d03 0%, #161b22 100%); border: 2px solid #d29922; border-radius: 12px; padding: 16px 20px; margin-bottom: 18px; box-shadow: 0 4px 14px rgba(0,0,0,0.5);">
            <div style="font-size: 1.28rem; font-weight: 900; color: #f0883e; letter-spacing: 0.5px; margin-bottom: 6px;">
                ⚠️ FORMATO OBLIGATORIO: EXCLUSIVAMENTE FORMATO MOXFIELD
            </div>
            <div style="font-size: 0.95rem; color: #e6edf3; line-height: 1.45;">
                Para garantizar la correcta lectura del <strong>Comandante</strong>, su <strong>Identidad de Color</strong> y la auditoría WOTC, el sistema requiere estrictamente el formato estándar de exportación de <strong>Moxfield</strong> (incluyendo la etiqueta <code>*CMDR*</code> o la sección <code>// Commander</code>).<br>
                <span style="color: #58a6ff;">💡 <em>En Moxfield: Entra a tu mazo ➔ botón <strong>Export</strong> ➔ selecciona <strong>Text</strong> o <strong>MTG Arena</strong> ➔ Copia y pega la lista aquí.</em></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_deck_in, col_config = st.columns([3, 2])

    with col_deck_in:
        deck_text_input = st.text_area(
            "📋 Lista del Mazo (EXCLUSIVAMENTE FORMATO MOXFIELD) * (Obligatorio):",
            value=st.session_state.raw_decklist,
            height=280,
            placeholder="""// Commander
1 Atraxa, Praetors' Voice (2X2) 196 *F* *CMDR*

// Deck
1 Sol Ring (C21) 263
1 Arcane Signet (C21) 259
1 Rhystic Study (WOT) 25
1 Demonic Tutor (STA) 27
1 Cyclonic Rift (RTR) 35
...""",
        )
        
        # Invalidate old deck state if input list changed
        if deck_text_input != st.session_state.raw_decklist:
            st.session_state.raw_decklist = deck_text_input
            st.session_state.deck_analyzed = False
            st.session_state.current_deck = None
            st.session_state.current_wotc = None
            st.session_state.current_pip = None
            st.session_state.current_bracket_audit = None
        # Live detected commander pill (always line 1 or *CMDR* tag)
        detected_cmdr_preview = extract_commander_for_preview(deck_text_input)
        if detected_cmdr_preview:
            st.markdown(
                f"""
                <div style="background:#0d1117; border:1px solid #30363d; border-radius:8px; padding:10px 14px; margin-top:10px; margin-bottom:12px; display:flex; align-items:center; justify-content:space-between;">
                    <div>
                        <span style="font-size:0.95rem; color:#58a6ff; font-weight:bold;">👑 Comandante:</span> 
                        <span style="font-size:1.02rem; color:#f0f6fc; font-weight:bold; margin-left:6px;">{detected_cmdr_preview}</span>
                    </div>
                    <span class="badge-in">1ª Carta / Tag CMDR</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif deck_text_input.strip():
            st.markdown("<div style='margin-top:8px; margin-bottom:12px; font-size:0.86rem; color:#f0883e;'>⚠️ <em>Pega tu lista de cartas. La primera carta será reconocida automáticamente como el Comandante.</em></div>", unsafe_allow_html=True)

    with col_config:
        st.markdown("#### 🏆 Sistema Oficial de 5 Brackets WotC")
        opt_bracket_num = st.selectbox(
            "Bracket Objetivo para el Mazo * (Obligatorio):",
            options=[1, 2, 3, 4, 5],
            index=None,
            placeholder="-- Selecciona un Bracket (1 al 5) --",
            format_func=lambda x: {
                1: "Bracket 1: Exhibition (Ultra-Casual / Temático)",
                2: "Bracket 2: Core (Preconstruido Promedio)",
                3: "Bracket 3: Upgraded (Precon Mejorado / Optimizado Medio)",
                4: "Bracket 4: Optimized (Alta Potencia)",
                5: "Bracket 5: cEDH (Competitive Commander / Tournament Meta)",
            }.get(x, f"Bracket {x}"),
        )

        b_info = None
        if opt_bracket_num is not None:
            # Real-time Bracket Specification Card
            bracket_matrix = WOTC_Bracket_Engine.get_bracket_matrix()
            b_info = bracket_matrix[opt_bracket_num]

            st.markdown(
                f"""
                <div class="bracket-card">
                    <div style="font-size:1.05rem; font-weight:bold; color:#58a6ff; margin-bottom:6px;">
                        🎯 Experiencia de Juego ({b_info['label']})
                    </div>
                    <div style="font-size:0.92rem; margin-bottom:8px; line-height:1.4;">
                        {b_info['experience']}
                    </div>
                    <div style="font-size:0.88rem; color:#8b949e; margin-bottom:8px;">
                        <strong>📜 Reglas Oficiales:</strong> {b_info['deckbuilding_rules']}
                    </div>
                    <div style="display:flex; gap:10px; flex-wrap:wrap; font-size:0.82rem;">
                        <span class="badge-gc">Game Changers: {'Máx ' + str(b_info['max_game_changers']) if b_info['max_game_changers'] < 900 else 'Ilimitados'}</span>
                        <span class="badge-tier-a">Victoria Típica: {b_info['typical_win_turn']}</span>
                        <span class="badge-tier-b">Curva Objetivo: {b_info['target_avg_cmc']} CMC</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Dynamically retrieve strategies compatible with the chosen bracket
            bracket_strategies = get_strategies_by_bracket(opt_bracket_num)
            if not bracket_strategies:
                service = get_strategy_service()
                bracket_strategies = service.get_all_strategies()
        else:
            service = get_strategy_service()
            bracket_strategies = service.get_all_strategies()

        # Build list of options with dynamic name and subtype resolution based on detected commander
        strategy_display_map = {}
        strategy_options = []
        for s in bracket_strategies:
            resolved_s = resolve_dynamic_strategy(s, detected_cmdr_preview)
            strat_label = f"{resolved_s['name']} ({resolved_s.get('category', 'General')})"
            strategy_display_map[strat_label] = resolved_s
            strategy_options.append(strat_label)

        strat_prompt = f"🎯 Estrategia / Arquetipo Objetivo (Filtrado para Bracket {opt_bracket_num}):" if opt_bracket_num else "🎯 Estrategia / Arquetipo Objetivo * (Obligatorio):"
        selected_strat_label = st.selectbox(
            strat_prompt,
            options=strategy_options,
            index=None,
            placeholder="-- Selecciona una Estrategia --",
        )
        selected_strategy = strategy_display_map.get(selected_strat_label, {}) if selected_strat_label else {}
        st.session_state.selected_strategy = selected_strategy

        # Strategy Preview Card
        if selected_strategy:
            strat_elements = selected_strategy.get("key_elements", [])
            strat_elements_str = " · ".join(strat_elements[:3]) if strat_elements else ""
            st.markdown(
                f"""
                <div style="background:#161b22; border:1px solid #30363d; border-radius:8px; padding:10px 14px; margin-top:-6px; margin-bottom:12px; font-size:0.86rem;">
                    <div style="font-weight:bold; color:#58a6ff; margin-bottom:4px;">📖 Plan de Juego: {selected_strategy.get('name', '')}</div>
                    <div style="color:#c9d1d9; margin-bottom:6px; line-height:1.35;">{selected_strategy.get('description', '')}</div>
                    {f'<div style="color:#8b949e;"><strong>⚡ Elementos Clave:</strong> {strat_elements_str}</div>' if strat_elements_str else ''}
                </div>
                """,
                unsafe_allow_html=True,
            )

        budget_unlimited = st.checkbox("Sin límite de presupuesto", value=True)
        opt_max_budget = None
        if not budget_unlimited:
            opt_max_budget = st.number_input("Presupuesto Máximo de Upgrade (USD):", min_value=5.0, value=150.0, step=10.0)

        untouchables_str = st.text_area("Cartas Intocables (separadas por comas):", placeholder="Sol Ring, Doubling Season")
        untouchable_cards = [c.strip() for c in untouchables_str.split(",") if c.strip()]

    # -------------------------------------------------------------------------
    # AUDITORÍA PREVIA EN TIEMPO REAL: BANLIST & REGLAS DE BRACKET
    # -------------------------------------------------------------------------
    pre_audit_report: Optional[BracketAuditReport] = None
    has_banned_block = False

    if deck_text_input.strip():
        # 1. Absolute Banlist Validation (MongoDB/Cache)
        ban_eval = validate_banned_cards(deck_text_input)
        if not ban_eval["is_legal"]:
            has_banned_block = True
            st.markdown(
                f"""
                <div class="alert-box-red" style="border: 3px solid #da3633; background:#490202;">
                    <div style="font-size:1.25rem; font-weight:bold; margin-bottom:8px; color:#ff7b72;">
                        🚨 BLOQUEO PRE-PROCESAMIENTO: VIOLACIÓN CRÍTICA DE BANLIST OFICIAL WOTC
                    </div>
                    <div style="font-size:1.0rem; margin-bottom:10px; line-height:1.4;">
                        {ban_eval["error_message"]}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("#### 🚫 Cartas Prohibidas Detectadas (No legales en Commander):")
            b_cols = st.columns(min(len(ban_eval["banned_names"]), 4) if ban_eval["banned_names"] else 1)
            for b_idx, b_name in enumerate(ban_eval["banned_names"]):
                with b_cols[b_idx % len(b_cols)]:
                    st.markdown(f"<span class='badge-out'>🚫 BANNED</span> **{b_name}**", unsafe_allow_html=True)
                    st.image(get_card_image_url(b_name), use_container_width=True)

            st.error("⛔ Debes retirar las cartas prohibidas de tu lista arriba para poder continuar con el análisis y la optimización.")

        if opt_bracket_num is not None:
            pre_deck, _ = ingestion_service.ingest_from_text(
                raw_text=deck_text_input,
                deck_name="Deck Preview",
                enrich=False,
            )
            for it in pre_deck.get_all_items():
                if not it.card:
                    it.card = ingestion_service.scryfall._find_in_cache(it.raw_name, it.set_code, it.collector_number) or ingestion_service.scryfall._create_synthetic_fallback_card(it.raw_name)
            
            pre_audit_report = WOTC_Bracket_Engine.audit_deck(pre_deck, opt_bracket_num)

            if not pre_audit_report.is_legal_for_bracket and not has_banned_block:
                st.markdown(
                    f"""
                    <div class="alert-box-red">
                        <div style="font-size:1.15rem; font-weight:bold; margin-bottom:6px;">
                            🚨 ALERTA DE INFRACCIÓN: El mazo ingresado viola las reglas de Bracket {opt_bracket_num} ({b_info['label'] if b_info else ''})
                        </div>
                        <div style="font-size:0.95rem; margin-bottom:10px;">
                            {pre_audit_report.actionable_summary}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Violations breakdown table / visual cards
                st.markdown(f"#### ⚠️ Cartas que deben ser removidas para cumplir con Bracket {opt_bracket_num}:")
                v_cols = st.columns(min(len(pre_audit_report.cards_to_remove), 3) if pre_audit_report.cards_to_remove else 1)
                
                for r_idx, rem in enumerate(pre_audit_report.cards_to_remove):
                    with v_cols[r_idx % len(v_cols)]:
                        st.markdown(f"<span class='badge-out'>❌ SACAR</span> **{rem.card_name}**", unsafe_allow_html=True)
                        st.image(get_card_image_url(rem.card_name), use_container_width=True)
                        st.caption(f"**Motivo:** {rem.reason}")
                        if rem.suggested_replacements:
                            st.markdown(f"**Sustitutos sugeridos:** {', '.join(rem.suggested_replacements[:2])}")

                # Auto-Remediation One-Click Button
                if st.button(f"🔧 Auto-Corregir Lista de Mazo para Bracket {opt_bracket_num}", type="secondary", use_container_width=True):
                    updated_lines = []
                    # Map cuts to replacements
                    replacements_map = {}
                    for rem in pre_audit_report.cards_to_remove:
                        if rem.suggested_replacements:
                            replacements_map[rem.card_name.lower()] = rem.suggested_replacements[0]

                    for line in deck_text_input.splitlines():
                        clean_name = ingestion_service.scryfall.clean_card_name(line)
                        if clean_name.lower() in replacements_map:
                            new_card = replacements_map[clean_name.lower()]
                            # replace card name in line while preserving quantity
                            if line.strip().startswith("1 ") or line.strip().startswith("1x "):
                                updated_lines.append(f"1 {new_card}")
                            else:
                                updated_lines.append(new_card)
                        else:
                            updated_lines.append(line)

                    new_text = "\n".join(updated_lines)
                    st.session_state.raw_decklist = new_text
                    st.success(f"✨ ¡Lista de mazo auto-corregida con sustitutos legales para Bracket {opt_bracket_num}!")
                    st.rerun()

            elif opt_bracket_num in [1, 2, 3] and not has_banned_block:
                st.markdown(
                    f"""
                    <div class="alert-box-green">
                        <div style="font-weight:bold; font-size:1.05rem;">
                            ✅ ¡Verificación Exitosa! El mazo cumple 100% con las restricciones de Bracket {opt_bracket_num} ({b_info['label'] if b_info else ''}).
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # Foolproof UX: Validate all mandatory fields before enabling action button
    has_deck_text = bool(deck_text_input.strip())
    has_bracket_selected = (opt_bracket_num is not None)
    has_strat_selected = bool(selected_strat_label)
    can_process = has_deck_text and has_bracket_selected and has_strat_selected and not has_banned_block

    if not can_process:
        missing_fields = []
        if not has_deck_text:
            missing_fields.append("📝 Pegar la lista de cartas del mazo en formato Moxfield")
        if not has_bracket_selected:
            missing_fields.append("🏆 Seleccionar un Bracket Objetivo (1 al 5)")
        if not has_strat_selected:
            missing_fields.append("🎯 Seleccionar una Estrategia / Arquetipo")
        if has_banned_block:
            missing_fields.append("🚫 Retirar cartas prohibidas por la Banlist oficial")

        st.warning("⚠️ **Completa los siguientes campos obligatorios para habilitar el procesamiento:**\n" + "\n".join(f"- {f}" for f in missing_fields))

    # Transition to Step 2
    col_btn_proc, col_btn_clear = st.columns([3, 1])
    with col_btn_proc:
        analyze_btn = st.button("▶️ Procesar y Analizar Mazo (Pasar al Paso 2)", type="primary", use_container_width=True, disabled=not can_process)
    with col_btn_clear:
        if st.button("🔄 Limpiar / Reset", use_container_width=True):
            st.session_state.deck_analyzed = False
            st.session_state.current_deck = None
            st.session_state.current_wotc = None
            st.session_state.current_pip = None
            st.session_state.current_bracket_audit = None
            st.session_state.optimized_report = None
            st.session_state.raw_decklist = ""
            st.rerun()

    if analyze_btn and can_process:
        if not deck_text_input.strip():
            st.warning("⚠️ Por favor ingresa una lista de mazo antes de procesar.")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()

            # Step 1: Normalize & Detect Commander
            active_cmdr_name = extract_commander_for_preview(deck_text_input)
            status_text.markdown(f"📖 **Paso 1/4:** Leyendo lista Moxfield y detectando comandante (**{active_cmdr_name or 'Auto-detectando'}**)...")
            progress_bar.progress(25)
            time.sleep(0.05)

            # Step 2: Ingest & Scryfall CDN Enrichment
            status_text.markdown("🌐 **Paso 2/4:** Consultando metadatos, precios e imágenes en Scryfall CDN...")
            progress_bar.progress(50)
            deck, _ = ingestion_service.ingest_from_text(
                raw_text=deck_text_input,
                deck_name="Commander Deck",
            )

            # Step 3: WotC Rules Validation & Mana Pips
            status_text.markdown("⚖️ **Paso 3/4:** Validando reglas oficiales WotC (Identidad de color, Singleton, Banlist)...")
            progress_bar.progress(75)
            wotc_result = rules_engine.validate_deck(deck)
            pip_report = Advanced_Deck_Analytics.analyze_mana_pip_balance(deck)

            # Step 4: Master 5-Bracket Engine Audit
            status_text.markdown("🏆 **Paso 4/4:** Ejecutando WOTC_Bracket_Engine (Auditoría de 5 Brackets, Game Changers y Combos)...")
            progress_bar.progress(100)
            bracket_audit = WOTC_Bracket_Engine.audit_deck(deck, opt_bracket_num)
            time.sleep(0.1)

            status_text.empty()
            progress_bar.empty()

            # Reset previous results and store fresh deck analysis
            st.session_state.current_deck = deck
            st.session_state.current_wotc = wotc_result
            st.session_state.current_pip = pip_report
            st.session_state.current_bracket_audit = bracket_audit
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
    bracket_audit = st.session_state.current_bracket_audit or WOTC_Bracket_Engine.audit_deck(deck, opt_bracket_num)

    st.markdown('<div class="step-header">📊 PASO 2: Previsualización Gráfica & Diagnóstico Integral WotC</div>', unsafe_allow_html=True)

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
            rule_badge = getattr(v, 'rule_name', None) or (v.rule_type.value if hasattr(getattr(v, 'rule_type', None), 'value') else getattr(v, 'rule_type', 'Regla WOTC'))
            msg = getattr(v, 'message', None) or getattr(v, 'explanation', str(v))
            st.markdown(f"- 🔴 **[{rule_badge}]** {msg}")
    else:
        st.success("✅ **Reglamento WOTC:** Identidad de color, singleton y banlist 100% legales.")

    # Interactive Step 2 Diagnostic Tabs
    tab_gallery, tab_edhrec, tab_mana_land, tab_wotc_audit, tab_gc_db = st.tabs([
        "🖼️ Galería Visual del Mazo",
        "🌐 Sugerencias de la Comunidad (EDHREC Sync)",
        "⚖️ Balance de Maná y Tierras",
        "🏆 Auditoría WOTC 5-Bracket Engine",
        "📚 Catálogo Oficial de Game Changers",
    ])

    with tab_gallery:
        st.markdown("### 🎴 Galería Visual de Cartas en el Mazo")
        all_deck_items = deck.commanders + deck.maindeck
        
        # Grid layout with 5 columns per row
        for row_start in range(0, len(all_deck_items), 5):
            row_chunk = all_deck_items[row_start:row_start + 5]
            cols = st.columns(5)
            for c_i, item in enumerate(row_chunk):
                with cols[c_i]:
                    img_url = get_card_image_url(item)
                    st.image(img_url, use_container_width=True)
                    st.markdown(f"**{item.quantity}x {item.effective_name}**")
                    if item.card:
                        cmc_label = f"{item.card.cmc:.0f} CMC" if "Land" not in item.card.type_line else "Tierra"
                        price_label = f"${item.total_price_usd:.2f}" if item.total_price_usd else ""
                        st.caption(f"{cmc_label} | {price_label}")

    with tab_edhrec:
        st.markdown(f"### 🌐 Sugerencias de la Comunidad (EDHREC Sync) para {deck.commander_name or 'tu Comandante'}")
        st.caption("Extracción en tiempo real desde la base comunitaria de EDHREC, almacenada en MongoDB Atlas con filtro obligatorio de Color Identity, Banlist y límites de Bracket.")

        if not deck.commander_name:
            st.info("Ingresa o selecciona un Comandante en el Paso 1 para ver las sugerencias de la comunidad de EDHREC.")
        else:
            with st.spinner("Consultando datos comunitarios y sincronizando con MongoDB Atlas..."):
                edh_engine = get_edhrec_engine()
                raw_edhrec = edh_engine.fetch_edhrec_data(deck.commander_name)
                edhrec_syn = edh_engine.filter_by_wotc_rules(raw_edhrec, deck.color_identity, opt_bracket_num)

            # Metadata header
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("📊 Mazos Analizados", f"{edhrec_syn.total_decks:,}")
            m2.metric("🏷️ Tema / Arquetipo", edhrec_syn.archetype_theme)
            m3.metric("🎯 Bracket Seleccionado", f"Bracket {opt_bracket_num}")
            cache_label = "💾 MongoDB Cache" if edhrec_syn.from_cache else "🌐 En Vivo (EDHREC)"
            m4.metric("🔄 Origen de Datos", cache_label)

            st.divider()

            # 1. New Releases / Novedades de Sets Recientes
            if edhrec_syn.new_cards:
                st.markdown("#### 🚀 Novedades de Sets Recientes (New Releases)")
                st.caption("Cartas recién lanzadas compatibles con tu comandante y filtradas por reglas WotC:")
                n_cols = st.columns(min(len(edhrec_syn.new_cards[:6]), 6))
                for idx, c in enumerate(edhrec_syn.new_cards[:6]):
                    with n_cols[idx % len(n_cols)]:
                        card_img = c.image_url or get_card_image_url(c.name)
                        st.image(card_img, use_container_width=True)
                        st.markdown(f"**{c.name}**")
                        syn_badge = f"+{c.synergy:.0f}%" if c.synergy > 0 else f"{c.synergy:.0f}%"
                        st.caption(f"Sinergia: `{syn_badge}` | {c.cmc:.0f} CMC")

            # 2. High Synergy / Sinergia Máxima
            if edhrec_syn.high_synergy_cards:
                st.markdown("#### ⚡ Cartas de Sinergia Máxima (High Synergy)")
                st.caption("Cartas con la mayor tasa de sinergia única con este comandante:")
                s_cols = st.columns(min(len(edhrec_syn.high_synergy_cards[:6]), 6))
                for idx, c in enumerate(edhrec_syn.high_synergy_cards[:6]):
                    with s_cols[idx % len(s_cols)]:
                        card_img = c.image_url or get_card_image_url(c.name)
                        st.image(card_img, use_container_width=True)
                        st.markdown(f"**{c.name}**")
                        st.caption(f"Sinergia: `+{c.synergy:.0f}%` | Inclusión: `{c.inclusion_percent:.0f}%`")

            # 3. Top Cards / Staples del Comandante
            if edhrec_syn.top_cards:
                st.markdown("#### 👑 Soportes / Staples del Comandante (Top Cards)")
                st.caption("Las cartas más populares y consistentes jugadas en este arquetipo:")
                t_cols = st.columns(min(len(edhrec_syn.top_cards[:6]), 6))
                for idx, c in enumerate(edhrec_syn.top_cards[:6]):
                    with t_cols[idx % len(t_cols)]:
                        card_img = c.image_url or get_card_image_url(c.name)
                        st.image(card_img, use_container_width=True)
                        st.markdown(f"**{c.name}**")
                        p_str = f"${c.price_usd:.2f}" if c.price_usd else ""
                        st.caption(f"Inclusión: `{c.inclusion_percent:.0f}%` {(' | ' + p_str) if p_str else ''}")

    with tab_mana_land:
        st.markdown("### 🎨 Densidad de Pips de Color vs Fuentes de Maná")
        st.caption("Compara el porcentaje de símbolos de color exigidos en los costes de tus hechizos contra las fuentes de maná que producen tus tierras y rocas:")
        
        pip_rows = []
        for col_sym, b in pip_report.color_breakdowns.items():
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

    with tab_wotc_audit:
        st.markdown(f"### 🏆 Auditoría del WOTC_Bracket_Engine para {bracket_audit.target_bracket_label}")
        st.caption("Verificación estricta de las 5 matrices de reglas oficiales: cuotas de Game Changers, combos infinitos, destrucción masiva de tierras (MLD) y turnos extra.")

        # KPI row
        bk1, bk2, bk3, bk4 = st.columns(4)
        bk1.metric("🎯 Bracket Objetivo", f"Bracket {bracket_audit.target_bracket}")
        bk2.metric("🔍 Bracket Detectado", f"Bracket {bracket_audit.detected_bracket}")
        bk3.metric("🃏 Game Changers Presentes", f"{bracket_audit.total_game_changers_count} (Máx: {bracket_audit.max_allowed_game_changers if bracket_audit.max_allowed_game_changers < 900 else '∞'})")
        legal_label = "🟢 Cumple Reglas" if bracket_audit.is_legal_for_bracket else "🔴 Infracciones"
        bk4.metric("⚖️ Estado Legal", legal_label)

        if not bracket_audit.is_legal_for_bracket:
            st.error(f"⚠️ **Infracciones de Bracket {opt_bracket_num} encontradas ({len(bracket_audit.violations)}):**")
            for viol in bracket_audit.violations:
                v_cat = viol.category.value if hasattr(viol.category, 'value') else str(getattr(viol, 'category', 'Infracción'))
                st.markdown(f"- 🔴 **[{v_cat}]**: {viol.message}")
        else:
            st.success(bracket_audit.status_headline)

        st.divider()
        st.markdown("#### 🃏 Auditoría Individual de Game Changers:")
        if not bracket_audit.game_changers_detected:
            st.info("🌿 No se detectaron Game Changers format-warping en este mazo.")
        else:
            for gc_item in bracket_audit.game_changers_detected:
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
                    c_img, c_exp, c_rep = st.columns([1, 2, 2])
                    with c_img:
                        st.image(get_card_image_url(gc_item.card_name), use_container_width=True)
                    with c_exp:
                        st.markdown(f"**⚡ Eficiencia:** {gc_item.efficiency_tier}")
                        st.markdown(f"**💡 Explicación Técnica:** {gc_item.efficiency_explanation}")
                        if not gc_item.is_allowed:
                            st.error(f"⚠️ {gc_item.status_label}")
                        else:
                            st.success(f"✅ Permitida legalmente en Bracket {opt_bracket_num}.")
                    with c_rep:
                        if not gc_item.is_allowed and gc_item.suggested_replacements:
                            st.markdown(f"**🔄 Sustitutos Legales para Bracket {opt_bracket_num}:**")
                            r_cols = st.columns(min(len(gc_item.suggested_replacements), 2))
                            for r_i, r_name in enumerate(gc_item.suggested_replacements[:2]):
                                with r_cols[r_i % 2]:
                                    st.markdown(f"**{r_name}**")
                                    st.image(get_card_image_url(r_name), use_container_width=True)
                        else:
                            st.info("Esta carta se mantiene dentro del estándar de potencia permitido.")
                    st.divider()

        # Extra Turns, MLD, Combos breakdown
        if bracket_audit.combos_detected:
            st.markdown(f"#### ♾️ Combos Infinitos Detectados ({len(bracket_audit.combos_detected)}):")
            for combo in bracket_audit.combos_detected:
                st.warning(f"⚡ Combo: **{' + '.join(combo)}**")

        if bracket_audit.mld_detected:
            st.markdown(f"#### 🌋 Destrucción Masiva de Tierras (MLD) Detectada ({len(bracket_audit.mld_detected)}):")
            st.error(f"Cartas de MLD: {', '.join(bracket_audit.mld_detected)}")

        if bracket_audit.extra_turns_detected:
            st.markdown(f"#### ⏳ Turnos Extra Detectados ({len(bracket_audit.extra_turns_detected)}):")
            st.info(f"Cartas de turnos extra: {', '.join(bracket_audit.extra_turns_detected)}")

    with tab_gc_db:
        st.markdown("### 📚 Catálogo Oficial de Game Changers & Reglas de Brackets")
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
            selected_strat = st.session_state.get("selected_strategy", {})
            user_intent = build_user_intent(
                target_bracket=opt_bracket_num,
                max_budget_usd=opt_max_budget,
                untouchable_cards=untouchable_cards,
                allow_infinite_combos=(opt_bracket_num >= 4),
                allow_fast_mana=(opt_bracket_num >= 4),
                strategy_profile=selected_strat,
                strategy_name=selected_strat.get("name") if selected_strat else None,
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
        s_col3.metric("⭐ Power Score Estimado", f"{report.estimated_new_power_score:.1f} / 5.0")
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
                    mull_report = Advanced_Deck_Analytics.simulate_opening_hands(opt_deck, num_simulations=1000)
                    st.session_state.mulligan_result = mull_report

        if st.session_state.mulligan_result:
            mull = st.session_state.mulligan_result
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("🃏 Manos Jugables (2-5 Tierras)", f"{mull.playable_hands_percentage:.1f}%")
            mc2.metric("⚡ Manos con Aceleración Turno 1-2", f"{mull.turn_2_ramp_probability:.1f}%")
            mc3.metric("🛡️ Manos con Interacción Temprana", f"{mull.early_interaction_probability:.1f}%")

        # ---------------------------------------------------------------------
        # 3. Mana Curve Comparison (Before vs After)
        # ---------------------------------------------------------------------
        st.divider()
        st.subheader("📈 Comparación de la Curva de Maná (Antes vs Después)")
        
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
        # Multi-Format Deck Exporter
        # ---------------------------------------------------------------------
        st.divider()
        st.subheader("📦 Exportador Multi-Formato Oficial")
        st.caption("Exporta tu lista optimizada con 1 clic en el formato nativo de tu simulador o plataforma preferida:")

        mox_tab, mtga_tab, mtgo_tab, plain_tab = st.tabs([
            "📋 Moxfield / Archidekt",
            "⚔️ MTG Arena (MTGA)",
            "🖥️ MTG Online (MTGO)",
            "📄 Texto Plano",
        ])

        mox_text = DeckExporter.export_to_moxfield_text(opt_deck)
        mtga_text = DeckExporter.export_to_mtga(opt_deck)
        mtgo_text = DeckExporter.export_to_mtgo(opt_deck)
        plain_text = DeckExporter.export_to_plain_text(opt_deck)

        with mox_tab:
            st.text_area("Formato Moxfield / Archidekt:", value=mox_text, height=200, key="export_mox_m1")
            st.download_button(
                label="💾 Descargar para Moxfield (.txt)",
                data=mox_text,
                file_name=f"{opt_deck.name.replace(' ', '_').lower()}_moxfield.txt",
                mime="text/plain",
                type="primary",
                key="btn_mox_m1",
            )

        with mtga_tab:
            st.text_area("Formato MTG Arena:", value=mtga_text, height=200, key="export_mtga_m1")
            st.download_button(
                label="💾 Descargar para MTGA (.txt)",
                data=mtga_text,
                file_name=f"{opt_deck.name.replace(' ', '_').lower()}_mtga.txt",
                mime="text/plain",
                key="btn_mtga_m1",
            )

        with mtgo_tab:
            st.text_area("Formato MTG Online (.dek / .txt):", value=mtgo_text, height=200, key="export_mtgo_m1")
            st.download_button(
                label="💾 Descargar para MTGO (.txt)",
                data=mtgo_text,
                file_name=f"{opt_deck.name.replace(' ', '_').lower()}_mtgo.txt",
                mime="text/plain",
                key="btn_mtgo_m1",
            )

        with plain_tab:
            st.text_area("Formato Texto Plano:", value=plain_text, height=200, key="export_plain_m1")
            st.download_button(
                label="💾 Descargar Texto Plano (.txt)",
                data=plain_text,
                file_name=f"{opt_deck.name.replace(' ', '_').lower()}_plain.txt",
                mime="text/plain",
                key="btn_plain_m1",
            )

# =============================================================================
# MODO 2: MTG DECKBUILDER GENERATOR (CONSTRUCCIÓN DESDE CERO - 5 BRACKETS)
# =============================================================================
else:
    st.markdown('<div class="step-header">🔨 MTG Deckbuilder Generator: Construcción de Mazo desde Cero (5 Brackets)</div>', unsafe_allow_html=True)
    st.markdown("Sintetiza un mazo de 100 cartas perfectamente balanceado, sinérgico y conforme a rajatabla con el sistema oficial de 5 Brackets de WotC.")

    gen_col1, gen_col2 = st.columns([1, 1])

    with gen_col1:
        gen_bracket = st.selectbox(
            "Bracket Objetivo para Construcción * (Obligatorio):",
            [1, 2, 3, 4, 5],
            index=None,
            placeholder="-- Selecciona un Bracket (1 al 5) --",
            format_func=lambda x: {
                1: "Bracket 1: Exhibition (0 Game Changers, Jank / Temático)",
                2: "Bracket 2: Core (0 Game Changers, Nivel Precon)",
                3: "Bracket 3: Upgraded (Máx 3 Game Changers, Optimizado Medio)",
                4: "Bracket 4: Optimized (Alta Potencia, Sin restricciones)",
                5: "Bracket 5: cEDH (Competitive Commander / Tournament Meta)",
            }.get(x, f"Bracket {x}"),
            key="gen_bracket_select",
        )

        # Retrieve bracket strategies dynamically from MongoDB / Cache
        if gen_bracket is not None:
            available_strategies = get_strategies_by_bracket(gen_bracket)
            if not available_strategies:
                service = get_strategy_service()
                available_strategies = service.get_all_strategies()
        else:
            service = get_strategy_service()
            available_strategies = service.get_all_strategies()

        # Build dynamic strategy options map
        gen_strat_map = {}
        gen_strat_options = []
        cur_gen_cmdr = st.session_state.chosen_gen_cmdr
        for s in available_strategies:
            resolved_s = resolve_dynamic_strategy(s, cur_gen_cmdr)
            s_label = f"{resolved_s['name']} ({resolved_s.get('category', 'General')})"
            gen_strat_map[s_label] = resolved_s
            gen_strat_options.append(s_label)

        gen_strat_prompt = f"🎯 Estrategia / Arquetipo * (Filtrado para Bracket {gen_bracket}):" if gen_bracket is not None else "🎯 Estrategia / Arquetipo * (Obligatorio):"
        gen_strat_label = st.selectbox(
            gen_strat_prompt,
            options=gen_strat_options,
            index=None,
            placeholder="-- Selecciona una Estrategia --",
            key="gen_strat_select",
        )
        selected_gen_strategy = gen_strat_map.get(gen_strat_label, {}) if gen_strat_label else {}
        selected_archetype_key = selected_gen_strategy.get("id", "") if selected_gen_strategy else ""

        if selected_gen_strategy:
            s_elems = selected_gen_strategy.get("key_elements", [])
            s_elems_str = " · ".join(s_elems[:3]) if s_elems else ""
            st.markdown(
                f"""
                <div style="background:#161b22; border:1px solid #30363d; border-radius:8px; padding:10px 14px; margin-top:-6px; margin-bottom:12px; font-size:0.86rem;">
                    <div style="font-weight:bold; color:#58a6ff; margin-bottom:4px;">📖 Plan de Juego: {selected_gen_strategy.get('name', '')}</div>
                    <div style="color:#c9d1d9; margin-bottom:6px; line-height:1.35;">{selected_gen_strategy.get('description', '')}</div>
                    {f'<div style="color:#8b949e;"><strong>⚡ Elementos Clave:</strong> {s_elems_str}</div>' if s_elems_str else ''}
                </div>
                """,
                unsafe_allow_html=True,
            )

    with gen_col2:
        gen_budget_unlimited = st.checkbox("Presupuesto Ilimitado", value=True, key="gen_unlimited")
        gen_max_budget = None
        if not gen_budget_unlimited:
            gen_max_budget = st.number_input("Presupuesto Máximo (USD):", min_value=20.0, value=250.0, step=25.0)

    st.markdown("#### 👑 Selección de Comandante * (Obligatorio)")
    st.caption("Escribe el nombre de tu Comandante o haz clic en una de las recomendaciones optimizadas:")

    if selected_archetype_key and gen_bracket is not None:
        suggested_cmdrs = deckbuilder_gen.suggest_commanders(selected_archetype_key, target_bracket=gen_bracket)
    else:
        suggested_cmdrs = []

    if suggested_cmdrs:
        s_cols = st.columns(min(len(suggested_cmdrs), 4))
        for s_idx, cmdr in enumerate(suggested_cmdrs):
            with s_cols[s_idx % len(s_cols)]:
                img_c_url = get_card_image_url(cmdr.name)
                st.image(img_c_url, use_container_width=True)
                st.markdown(f"**{cmdr.name}**")
                st.caption(f"🎨 {''.join(cmdr.color_identity)} | {cmdr.reason}")
                if st.button(f"Seleccionar {cmdr.name}", key=f"btn_cmdr_{s_idx}"):
                    st.session_state.chosen_gen_cmdr = cmdr.name
                    st.rerun()

    typed_cmdr = st.text_input(
        "Nombre del Comandante deseado:",
        value=st.session_state.chosen_gen_cmdr or "",
        placeholder="Ej: Yuriko, the Tiger's Shadow, Korvold, Fae-Cursed King, Atraxa, Praetors' Voice...",
    )
    if typed_cmdr != (st.session_state.chosen_gen_cmdr or ""):
        st.session_state.chosen_gen_cmdr = typed_cmdr

    # Real-time EDHREC preview if commander is specified
    if st.session_state.chosen_gen_cmdr and gen_bracket is not None:
        with st.expander(f"🌐 Ver Sugerencias Comunitarias (EDHREC) para {st.session_state.chosen_gen_cmdr}", expanded=False):
            edh_eng = get_edhrec_engine()
            raw_edh = edh_eng.fetch_edhrec_data(st.session_state.chosen_gen_cmdr)
            if raw_edh.get("highsynergycards") or raw_edh.get("topcards"):
                st.caption("Top cartas más sinérgicas y populares extraídas desde la base de datos de EDHREC:")
                edh_cards_to_show = (raw_edh.get("highsynergycards", [])[:3] + raw_edh.get("topcards", [])[:3])
                e_cols = st.columns(min(len(edh_cards_to_show), 6))
                for e_i, e_c in enumerate(edh_cards_to_show):
                    with e_cols[e_i % len(e_cols)]:
                        st.image(get_card_image_url(e_c["name"]), use_container_width=True)
                        st.markdown(f"**{e_c['name']}**")
                        syn_val = e_c.get("synergy", 0)
                        st.caption(f"Sinergia: `{syn_val:+.0%}`" if isinstance(syn_val, float) else f"Sinergia: `{syn_val}`")

    # Foolproof UX: Action Button Locking
    has_gen_bracket = (gen_bracket is not None)
    has_gen_strat = bool(gen_strat_label)
    has_gen_cmdr = bool(st.session_state.chosen_gen_cmdr and st.session_state.chosen_gen_cmdr.strip())
    can_build = has_gen_bracket and has_gen_strat and has_gen_cmdr

    if not can_build:
        gen_missing = []
        if not has_gen_bracket:
            gen_missing.append("🏆 Seleccionar un Bracket Objetivo (1 al 5)")
        if not has_gen_strat:
            gen_missing.append("🎯 Seleccionar una Estrategia / Arquetipo")
        if not has_gen_cmdr:
            gen_missing.append("👑 Seleccionar o escribir un Comandante")
        st.warning("⚠️ **Completa los siguientes campos obligatorios para generar el mazo:**\n" + "\n".join(f"- {f}" for f in gen_missing))

    st.divider()
    if st.button("🔨 Construir Mazo de 100 Cartas", type="primary", use_container_width=True, disabled=not can_build):
        gen_progress = st.progress(0)
        gen_status = st.empty()

        gen_status.markdown("👑 **Paso 1/4:** Extrayendo identidad de color del Comandante y aplicando reglas WotC...")
        gen_progress.progress(25)
        time.sleep(0.05)

        gen_status.markdown(f"🃏 **Paso 2/4:** Ensamblando paquete de sinergia para '{selected_gen_strategy.get('name', 'Estrategia')}' y aplicando cuota de Bracket {gen_bracket}...")
        gen_progress.progress(50)
        params = DeckbuilderParams(
            commander_name=st.session_state.chosen_gen_cmdr.strip(),
            target_bracket=int(gen_bracket),
            strategy_archetype=selected_archetype_key or "general_synergy",
            max_budget_usd=gen_max_budget,
        )
        time.sleep(0.05)

        gen_status.markdown("🌲 **Paso 3/4:** Sintetizando base de maná equilibrada por pips y colores requeridos...")
        gen_progress.progress(75)
        gen_result = deckbuilder_gen.build_deck(params)

        gen_status.markdown("✅ **Paso 4/4:** Validando singleton, banlist y exportador multi-formato...")
        gen_progress.progress(100)
        time.sleep(0.1)

        gen_status.empty()
        gen_progress.empty()

        st.session_state.generated_deck_result = gen_result

    if st.session_state.generated_deck_result:
        res = st.session_state.generated_deck_result
        g_deck = res.deck
        g_wotc = res.validation

        st.success(f"🎉 ¡Mazo '{g_deck.name}' generado exitosamente con {g_deck.total_cards} cartas para Bracket {gen_bracket}!")

        gc1, gc2, gc3, gc4 = st.columns(4)
        gc1.metric("🃏 Total Cartas", f"{g_deck.total_cards}")
        gc2.metric("🌲 Tierras", f"{len([it for it in g_deck.maindeck if it.card and 'Land' in it.card.type_line])}")
        gc3.metric("📈 Curva Promedio", f"{g_deck.average_cmc_without_lands:.2f} CMC")
        gc4.metric("💰 Coste Estimado", f"${g_deck.total_price_usd:,.2f} USD")

        if g_wotc.is_legal:
            st.success("✅ Validación WotC: 100% Legal en Commander (Identidad de color y singleton cumplidos).")
        else:
            st.warning(f"⚠️ Alertas WotC: {len(g_wotc.violations)} advertencias.")

        # Multi-tab view: Visual Gallery & Multi-Format Exporter
        g_tab_all, g_tab_export = st.tabs(["🖼️ Galería Visual del Mazo Generado", "📦 Exportar Lista (Multi-Formato)"])
        
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
            g_mox = DeckExporter.export_to_moxfield_text(g_deck)
            g_mtga = DeckExporter.export_to_mtga(g_deck)
            g_mtgo = DeckExporter.export_to_mtgo(g_deck)
            g_plain = DeckExporter.export_to_plain_text(g_deck)

            gx_mox, gx_mtga, gx_mtgo, gx_plain = st.tabs([
                "📋 Moxfield / Archidekt",
                "⚔️ MTG Arena (MTGA)",
                "🖥️ MTG Online (MTGO)",
                "📄 Texto Plano",
            ])

            with gx_mox:
                st.text_area("Formato Moxfield / Archidekt:", value=g_mox, height=250, key="gen_mox_txt")
                st.download_button(
                    label="💾 Descargar para Moxfield (.txt)",
                    data=g_mox,
                    file_name=f"{g_deck.name.replace(' ', '_').lower()}_moxfield.txt",
                    mime="text/plain",
                    type="primary",
                    key="btn_gen_mox",
                )

            with gx_mtga:
                st.text_area("Formato MTG Arena:", value=g_mtga, height=250, key="gen_mtga_txt")
                st.download_button(
                    label="💾 Descargar para MTGA (.txt)",
                    data=g_mtga,
                    file_name=f"{g_deck.name.replace(' ', '_').lower()}_mtga.txt",
                    mime="text/plain",
                    key="btn_gen_mtga",
                )

            with gx_mtgo:
                st.text_area("Formato MTG Online (.dek / .txt):", value=g_mtgo, height=250, key="gen_mtgo_txt")
                st.download_button(
                    label="💾 Descargar para MTGO (.txt)",
                    data=g_mtgo,
                    file_name=f"{g_deck.name.replace(' ', '_').lower()}_mtgo.txt",
                    mime="text/plain",
                    key="btn_gen_mtgo",
                )

            with gx_plain:
                st.text_area("Formato Texto Plano:", value=g_plain, height=250, key="gen_plain_txt")
                st.download_button(
                    label="💾 Descargar Texto Plano (.txt)",
                    data=g_plain,
                    file_name=f"{g_deck.name.replace(' ', '_').lower()}_plain.txt",
                    mime="text/plain",
                    key="btn_gen_plain",
                )

