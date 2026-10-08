"""
Moxfield-style interactive deck and EDHREC visual viewer.
Renders responsive, pure-client-side HTML/JS components with 0ms hover/click image previews,
strict MTG type categorization, and no page reload latency.
"""
from typing import Dict, List, Any, Callable, Optional
import html

def escape(s: Any) -> str:
    if s is None:
        return ""
    return html.escape(str(s))

def render_moxfield_deck_html(deck: Any, get_image_fn: Callable[[Any], str]) -> str:
    """
    Renders an authentic Moxfield-style deck viewer with sticky left card preview
    and right column MTG categories (Commander, Planeswalkers, Creatures, Instants,
    Sorceries, Artifacts, Enchantments, Battles, Lands).
    """
    categories: Dict[str, list] = deck.get_moxfield_categorized_items()
    all_items = deck.commanders + deck.maindeck
    
    # Determine default card for preview
    default_item = deck.commanders[0] if deck.commanders else (deck.maindeck[0] if deck.maindeck else None)
    if default_item:
        default_img = get_image_fn(default_item)
        default_name = default_item.effective_name
        default_type = default_item.card.type_line if default_item.card else "Magic: The Gathering Card"
        default_cmc = f"CMC: {default_item.card.cmc:.0f}" if (default_item.card and "Land" not in default_item.card.type_line) else ""
        p_val = getattr(default_item, "total_price_usd", None) or (default_item.card.price_usd if default_item.card else None) or 0.0
        default_price = f"${p_val:.2f} USD" if p_val else ""
    else:
        default_img = "https://cards.scryfall.io/back.jpg"
        default_name = "Sin Cartas"
        default_type = ""
        default_cmc = ""
        default_price = ""

    # Generate category columns HTML
    cats_html = []
    for cat_name, items in categories.items():
        total_cat_qty = sum(it.quantity for it in items)
        cards_html = []
        for it in items:
            img_url = get_image_fn(it)
            c_name = it.effective_name
            c_type = it.card.type_line if it.card else ""
            c_cmc = f"CMC {it.card.cmc:.0f}" if (it.card and "Land" not in it.card.type_line) else ""
            p_val = getattr(it, "total_price_usd", None) or (it.card.price_usd if it.card else None) or 0.0
            p_str = f"${p_val:.2f}" if p_val > 0 else ""
            qty_str = f"{it.quantity}x" if it.quantity > 1 else "1x"
            
            cards_html.append(f"""
            <div class="mox-row"
                 data-img="{escape(img_url)}"
                 data-name="{escape(c_name)}"
                 data-type="{escape(c_type)}"
                 data-cmc="{escape(c_cmc)}"
                 data-price="{escape(p_str)}"
                 onmouseenter="previewCard(this)"
                 onclick="previewCard(this)">
                <span class="mox-qty">{escape(qty_str)}</span>
                <span class="mox-name">{escape(c_name)}</span>
                <span class="mox-cmc">{escape(c_cmc)}</span>
                <span class="mox-price">{escape(p_str)}</span>
            </div>
            """)
        
        cats_html.append(f"""
        <div class="mox-category-box">
            <div class="mox-cat-title">{escape(cat_name)} <span class="mox-cat-count">({total_cat_qty})</span></div>
            <div class="mox-card-list">
                {"".join(cards_html)}
            </div>
        </div>
        """)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }}
        body {{
            background: #0d1117;
            color: #c9d1d9;
            padding: 12px;
        }}
        .mox-container {{
            display: flex;
            gap: 20px;
            align-items: flex-start;
        }}
        /* Left Column: Sticky Card Art Preview */
        .mox-left-pane {{
            position: sticky;
            top: 10px;
            flex: 0 0 280px;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            align-items: center;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }}
        .mox-img-wrapper {{
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 350px;
        }}
        .mox-preview-image {{
            width: 100%;
            max-width: 250px;
            border-radius: 11px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.6);
            transition: transform 0.15s ease, opacity 0.15s ease;
        }}
        .mox-meta-box {{
            width: 100%;
            margin-top: 12px;
            padding-top: 10px;
            border-top: 1px solid #21262d;
            text-align: left;
        }}
        .mox-card-title {{
            font-size: 1.05rem;
            font-weight: 700;
            color: #58a6ff;
            margin-bottom: 4px;
            line-height: 1.25;
        }}
        .mox-card-type {{
            font-size: 0.82rem;
            color: #8b949e;
            margin-bottom: 6px;
        }}
        .mox-card-extra {{
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            font-weight: 600;
            color: #f0f6fc;
        }}
        .mox-card-price-badge {{
            color: #3fb950;
        }}
        /* Right Column: Multi-Column Category Layout */
        .mox-right-pane {{
            flex: 1;
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
            gap: 16px;
        }}
        .mox-category-box {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 10px 12px;
            height: fit-content;
        }}
        .mox-cat-title {{
            font-size: 0.95rem;
            font-weight: 700;
            color: #f0f6fc;
            padding-bottom: 6px;
            border-bottom: 1px solid #30363d;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .mox-cat-count {{
            color: #8b949e;
            font-weight: 400;
            font-size: 0.85rem;
        }}
        .mox-card-list {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}
        .mox-row {{
            display: flex;
            align-items: center;
            padding: 5px 8px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.88rem;
            color: #c9d1d9;
            transition: background 0.12s ease, color 0.12s ease;
            gap: 8px;
        }}
        .mox-row:hover, .mox-row.active {{
            background: #1f2937;
            color: #58a6ff;
        }}
        .mox-qty {{
            color: #8b949e;
            font-weight: 600;
            font-size: 0.8rem;
            min-width: 22px;
        }}
        .mox-name {{
            flex: 1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            font-weight: 500;
        }}
        .mox-cmc {{
            font-size: 0.75rem;
            color: #8b949e;
            background: #21262d;
            padding: 1px 5px;
            border-radius: 3px;
        }}
        .mox-price {{
            font-size: 0.78rem;
            color: #3fb950;
            font-weight: 500;
            min-width: 40px;
            text-align: right;
        }}
        .mox-instructions {{
            grid-column: 1 / -1;
            font-size: 0.82rem;
            color: #8b949e;
            margin-bottom: 4px;
        }}
    </style>
    </head>
    <body>
        <div class="mox-container">
            <!-- Sticky Left Preview -->
            <div class="mox-left-pane">
                <div class="mox-img-wrapper">
                    <img id="mox-preview-img" class="mox-preview-image" src="{escape(default_img)}" alt="{escape(default_name)}" onerror="this.src='https://cards.scryfall.io/back.jpg'">
                </div>
                <div class="mox-meta-box">
                    <div id="mox-preview-name" class="mox-card-title">{escape(default_name)}</div>
                    <div id="mox-preview-type" class="mox-card-type">{escape(default_type)}</div>
                    <div class="mox-card-extra">
                        <span id="mox-preview-cmc">{escape(default_cmc)}</span>
                        <span id="mox-preview-price" class="mox-card-price-badge">{escape(default_price)}</span>
                    </div>
                </div>
            </div>

            <!-- Right Categories Grid -->
            <div class="mox-right-pane">
                <div class="mox-instructions">💡 <em>Coloca el cursor o haz clic sobre cualquier carta para ver su arte oficial al instante:</em></div>
                {"".join(cats_html)}
            </div>
        </div>

        <script>
            function previewCard(el) {{
                const imgEl = document.getElementById('mox-preview-img');
                const nameEl = document.getElementById('mox-preview-name');
                const typeEl = document.getElementById('mox-preview-type');
                const cmcEl = document.getElementById('mox-preview-cmc');
                const priceEl = document.getElementById('mox-preview-price');

                if (el.dataset.img) {{
                    imgEl.src = el.dataset.img;
                }}
                nameEl.innerText = el.dataset.name || '';
                typeEl.innerText = el.dataset.type || '';
                cmcEl.innerText = el.dataset.cmc || '';
                priceEl.innerText = el.dataset.price ? el.dataset.price + ' USD' : '';

                // Active row highlight
                document.querySelectorAll('.mox-row.active').forEach(r => r.classList.remove('active'));
                el.classList.add('active');
            }}
        </script>
    </body>
    </html>
    """
    return html_content


def render_moxfield_edhrec_html(edhrec_syn: Any, get_image_fn: Callable[[Any], str]) -> str:
    """
    Renders an interactive Moxfield-style viewer for EDHREC suggestions (High Synergy, Top Staples, New Releases)
    with instant 0ms hover preview and strict legal filtering.
    """
    sections = [
        ("⚡ Sinergia Máxima (High Synergy)", edhrec_syn.high_synergy_cards or []),
        ("👑 Staples del Comandante (Top Cards)", edhrec_syn.top_cards or []),
        ("🚀 Novedades de Sets (New Releases)", edhrec_syn.new_cards or []),
    ]
    
    # Default preview card
    first_card = None
    for _, cards in sections:
        if cards:
            first_card = cards[0]
            break
            
    if first_card:
        default_img = get_image_fn(first_card.name)
        default_name = first_card.name
        default_type = first_card.type_line or "Magic Card"
        default_cmc = f"CMC {first_card.cmc:.0f}"
        p_val = getattr(first_card, "price_usd", None) or 0.0
        default_price = f"${p_val:.2f} USD" if p_val > 0 else ""
        default_stat = f"Sinergia: +{first_card.synergy:.0f}% | Inclusión: {first_card.inclusion_percent:.0f}%"
    else:
        default_img = "https://cards.scryfall.io/back.jpg"
        default_name = "Sin Sugerencias"
        default_type = ""
        default_cmc = ""
        default_price = ""
        default_stat = ""

    sec_html = []
    for sec_title, cards in sections:
        if not cards:
            continue
        rows = []
        for c in cards:
            img_url = get_image_fn(c.name)
            syn_badge = f"+{c.synergy:.0f}%" if c.synergy > 0 else f"{c.synergy:.0f}%"
            inc_badge = f"{c.inclusion_percent:.0f}% inc"
            cmc_str = f"CMC {c.cmc:.0f}"
            p_val = getattr(c, "price_usd", None) or 0.0
            p_str = f"${p_val:.2f}" if p_val > 0 else ""
            stat_summary = f"Sinergia: {syn_badge} | Inclusión: {c.inclusion_percent:.0f}%"

            rows.append(f"""
            <div class="mox-row"
                 data-img="{escape(img_url)}"
                 data-name="{escape(c.name)}"
                 data-type="{escape(c.type_line)}"
                 data-cmc="{escape(cmc_str)}"
                 data-price="{escape(p_str)}"
                 data-stat="{escape(stat_summary)}"
                 onmouseenter="previewEDHCard(this)"
                 onclick="previewEDHCard(this)">
                <span class="mox-syn-pill">{escape(syn_badge)}</span>
                <span class="mox-name">{escape(c.name)}</span>
                <span class="mox-cmc">{escape(cmc_str)}</span>
                <span class="mox-price">{escape(p_str or inc_badge)}</span>
            </div>
            """)

        sec_html.append(f"""
        <div class="mox-category-box">
            <div class="mox-cat-title">{escape(sec_title)} <span class="mox-cat-count">({len(cards)})</span></div>
            <div class="mox-card-list">
                {"".join(rows)}
            </div>
        </div>
        """)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }}
        body {{
            background: #0d1117;
            color: #c9d1d9;
            padding: 12px;
        }}
        .mox-container {{
            display: flex;
            gap: 20px;
            align-items: flex-start;
        }}
        .mox-left-pane {{
            position: sticky;
            top: 10px;
            flex: 0 0 280px;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            align-items: center;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }}
        .mox-img-wrapper {{
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 350px;
        }}
        .mox-preview-image {{
            width: 100%;
            max-width: 250px;
            border-radius: 11px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.6);
        }}
        .mox-meta-box {{
            width: 100%;
            margin-top: 12px;
            padding-top: 10px;
            border-top: 1px solid #21262d;
            text-align: left;
        }}
        .mox-card-title {{
            font-size: 1.05rem;
            font-weight: 700;
            color: #58a6ff;
            margin-bottom: 4px;
            line-height: 1.25;
        }}
        .mox-card-type {{
            font-size: 0.82rem;
            color: #8b949e;
            margin-bottom: 4px;
        }}
        .mox-stat-line {{
            font-size: 0.82rem;
            color: #e3b341;
            font-weight: 600;
            margin-bottom: 6px;
        }}
        .mox-card-extra {{
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            font-weight: 600;
            color: #f0f6fc;
        }}
        .mox-card-price-badge {{
            color: #3fb950;
        }}
        .mox-right-pane {{
            flex: 1;
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
            gap: 16px;
        }}
        .mox-category-box {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 10px 12px;
            height: fit-content;
        }}
        .mox-cat-title {{
            font-size: 0.92rem;
            font-weight: 700;
            color: #f0f6fc;
            padding-bottom: 6px;
            border-bottom: 1px solid #30363d;
            margin-bottom: 8px;
            letter-spacing: 0.3px;
        }}
        .mox-cat-count {{
            color: #8b949e;
            font-weight: 400;
            font-size: 0.85rem;
        }}
        .mox-card-list {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}
        .mox-row {{
            display: flex;
            align-items: center;
            padding: 5px 8px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.88rem;
            color: #c9d1d9;
            transition: background 0.12s ease, color 0.12s ease;
            gap: 8px;
        }}
        .mox-row:hover, .mox-row.active {{
            background: #1f2937;
            color: #58a6ff;
        }}
        .mox-syn-pill {{
            background: #238636;
            color: #ffffff;
            font-weight: 700;
            font-size: 0.72rem;
            padding: 2px 5px;
            border-radius: 4px;
            min-width: 38px;
            text-align: center;
        }}
        .mox-name {{
            flex: 1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            font-weight: 500;
        }}
        .mox-cmc {{
            font-size: 0.75rem;
            color: #8b949e;
            background: #21262d;
            padding: 1px 5px;
            border-radius: 3px;
        }}
        .mox-price {{
            font-size: 0.78rem;
            color: #3fb950;
            font-weight: 500;
            min-width: 45px;
            text-align: right;
        }}
        .mox-instructions {{
            grid-column: 1 / -1;
            font-size: 0.82rem;
            color: #8b949e;
            margin-bottom: 4px;
        }}
    </style>
    </head>
    <body>
        <div class="mox-container">
            <div class="mox-left-pane">
                <div class="mox-img-wrapper">
                    <img id="mox-preview-img" class="mox-preview-image" src="{escape(default_img)}" alt="{escape(default_name)}" onerror="this.src='https://cards.scryfall.io/back.jpg'">
                </div>
                <div class="mox-meta-box">
                    <div id="mox-preview-name" class="mox-card-title">{escape(default_name)}</div>
                    <div id="mox-preview-type" class="mox-card-type">{escape(default_type)}</div>
                    <div id="mox-preview-stat" class="mox-stat-line">{escape(default_stat)}</div>
                    <div class="mox-card-extra">
                        <span id="mox-preview-cmc">{escape(default_cmc)}</span>
                        <span id="mox-preview-price" class="mox-card-price-badge">{escape(default_price)}</span>
                    </div>
                </div>
            </div>

            <div class="mox-right-pane">
                <div class="mox-instructions">💡 <em>Pasa el ratón sobre cualquier recomendación para inspeccionar su arte y estadísticas instantáneamente:</em></div>
                {"".join(sec_html)}
            </div>
        </div>

        <script>
            function previewEDHCard(el) {{
                const imgEl = document.getElementById('mox-preview-img');
                const nameEl = document.getElementById('mox-preview-name');
                const typeEl = document.getElementById('mox-preview-type');
                const statEl = document.getElementById('mox-preview-stat');
                const cmcEl = document.getElementById('mox-preview-cmc');
                const priceEl = document.getElementById('mox-preview-price');

                if (el.dataset.img) {{
                    imgEl.src = el.dataset.img;
                }}
                nameEl.innerText = el.dataset.name || '';
                typeEl.innerText = el.dataset.type || '';
                statEl.innerText = el.dataset.stat || '';
                cmcEl.innerText = el.dataset.cmc || '';
                priceEl.innerText = el.dataset.price ? el.dataset.price + ' USD' : '';

                document.querySelectorAll('.mox-row.active').forEach(r => r.classList.remove('active'));
                el.classList.add('active');
            }}
        </script>
    </body>
    </html>
    """
    return html_content
