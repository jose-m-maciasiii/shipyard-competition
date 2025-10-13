import streamlit as st
import geopandas as gpd
import leafmap.foliumap as leafmap
import folium
from folium.plugins import MeasureControl
import branca.colormap as cm
import numpy as np
import mapclassify

st.set_page_config(layout="wide")

# --- Sidebar ---
st.sidebar.markdown("### 🧾 Data Sources")
st.sidebar.markdown(
    """
    County demographic data are from the **U.S. Census American Community Survey (2023, 5-year estimates)**.  
    Labor statistics are from the **U.S. Bureau of Labor Statistics (BLS)**, NAICS **336600**.
    """
)
st.sidebar.divider()  # adds a subtle gray rule for structure
st.sidebar.markdown("#### 📍 About This Tool")
st.sidebar.caption(
    "Developed by the CSIS **Futures Lab**, this visualization explores how labor availability "
    "affects U.S. shipyard capacity and recruitment competition."
)
st.sidebar.image(
    "https://upload.wikimedia.org/wikipedia/commons/9/99/CSIS_logo_blue.svg",
    use_container_width=True,
)
# Page title
st.title("The Fight for Shipyard Labor: Exploring Regional Workforce Pressures")

st.markdown("""
This interactive tool supports analysis of the **U.S. shipbuilding workforce gap**—one of the most
pressing challenges in revitalizing the Maritime Industrial Base (MIB).  
Drawing on data from the U.S. Census and Bureau of Labor Statistics, the map highlights:

- **Where** shipyards compete for limited skilled labor within 90-mile recruitment zones,  
- **How** regional factors such as unemployment, wages, and housing costs shape recruitment, and  
- **Which** counties may offer untapped potential for workforce expansion.

Designed for policymakers and industry planners, the visualization helps identify opportunities
to **coordinate recruitment efforts** and **minimize inter-shipyard competition** as the United States
ramps up shipbuilding production.
""")

# --- Data sources on S3 ---
shipyards_url = "https://f-lab-shipyard-competition.s3.us-east-1.amazonaws.com/ship_yards_sf.gpkg"
buffers_url   = "https://f-lab-shipyard-competition.s3.us-east-1.amazonaws.com/ship_yards_buffers_ll.gpkg"
cbp_url       = "https://f-lab-shipyard-competition.s3.amazonaws.com/clean_cbp_population_data.geojson"

# --- Load data ---
shipyards = gpd.read_file(shipyards_url).to_crs(4326)
buffers   = gpd.read_file(buffers_url).to_crs(4326)
cbp       = gpd.read_file(cbp_url).to_crs(4326)

# Precompute lon/lat for points
shipyards["lon"] = shipyards.geometry.x
shipyards["lat"] = shipyards.geometry.y

# Friendly palette, repeat if needed
palette = [
    "#E58606", "#5D69B1", "#52BCA3", "#99C945", "#CC61B0", "#24796C",
    "#DAA51B", "#2F8AC4", "#764E9F", "#ED645A", "#CC3A8E", "#A5AA99"
]
unique_yards = shipyards["yard_unique_id"].unique()
color_map = {yard_id: palette[i % len(palette)] for i, yard_id in enumerate(unique_yards)}

# Tidy buffer column names (for popups)
buffers = buffers.rename(columns={
    "yard_name": "Shipyard Name",
    "state_coverage": "States Covered",
    "county_coverage": "Counties Covered",
})

# --- UI: indicator dropdown (main column, above the map) ---
INDICATOR_OPTIONS = {
    "Unemployment Rate": "Unemployement Rate",   # keep exact column name (typo in source)
    "Median Worker Earnings": "Median Worker Earnings",
    "Median Home Value": "Median Home Value",
    "Median Rent Paid": "Median Rent Paid",
    "Shipbuilders Employed": "Shipbuilders Employed",
    "Recruitment Radius Count": "Recruitment Radius Count",
}
# ---------- MAIN LAYOUT ----------
with st.container():
    left_col, right_col = st.columns([1, 3], gap="small")

# ---------- LEFT: controls & analytics ----------
with left_col:
    # Top panel (Indicator pills)
    st.markdown("#### Indicator")
    INDICATOR_OPTIONS = {
        "None": None,
        "Unemployment Rate": "Unemployement Rate",  # keep exact column name
        "Median Worker Earnings": "Median Worker Earnings",
        "Median Home Value": "Median Home Value",
        "Median Rent Paid": "Median Rent Paid",
        "Shipbuilders Employed": "Shipbuilders Employed",
        "Recruitment Radius Count": "Recruitment Radius Count",
    }

    # If your Streamlit version has st.pills, use it; otherwise fallback to radio:
    try:
        indicator_label = st.pills(
            "County labor indicator",
            options=list(INDICATOR_OPTIONS.keys()),
            default="None",
        )
    except Exception:
        indicator_label = st.radio(
            "County labor indicator",
            options=list(INDICATOR_OPTIONS.keys()),
            index=0,
            horizontal=True
        )

    indicator_col = INDICATOR_OPTIONS[indicator_label]

    st.divider()

    # Shipyard selector (single or multiple)
    st.markdown("#### Focus shipyard(s)")
    yard_names = shipyards["Yard"].tolist()
    selected_yards = st.multiselect(
        "Filter analytics to the recruitment radius of…",
        options=yard_names,
        default=[],
        placeholder="Choose one or more shipyards (optional)"
    )

    st.caption(
        "Analytics below use **only counties within the selected shipyard(s) recruitment radii**. "
        "If none selected, metrics use **all counties**."
    )

    # ---------- Build a county subset based on selected yards ----------
    # We’ll leverage the CBP columns you already computed:
    #  - "Recruitment Radius Count": numeric overlap
    #  - "Shipyards in Radius": object (names list or comma-separated)
    cbp_local = cbp.copy()

    # Normalize the "Shipyards in Radius" to a Python set for easy membership checks
    def parse_shipyards_in_radius(x):
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return set()
        if isinstance(x, (list, set, tuple)):
            return set(x)
        # assume comma/semi-colon separated string
        return set([s.strip() for s in str(x).split(",") if s.strip()])

    cbp_local["__yards_set"] = cbp_local["Shipyards in Radius"].apply(parse_shipyards_in_radius)

    if selected_yards:
        mask = cbp_local["__yards_set"].apply(lambda s: any(y in s for y in selected_yards))
        cbp_view = cbp_local[mask].copy()
    else:
        cbp_view = cbp_local.copy()

    tbl = None
    # ---------- Quick metrics panel ----------
    st.divider()
   # --- Custom CSS for metric cards (theme-aware, card style) ---
    st.markdown(
        """
        <style>
        /* General metric container styling */
        div[data-testid="stMetric"] {
            background-color: rgba(240, 240, 240, 0.65); /* light gray card */
            border-radius: 10px;
            padding: 0.5rem 0.75rem !important;
            margin: 0.25rem;
            box-shadow: 0 1px 4px rgba(0,0,0,0.15);
        }

        /* Metric label (smaller, use default theme text color) */
        [data-testid="stMetricLabel"] {
            font-size: 13px !important;
            color: inherit !important;
            opacity: 0.85 !important;
        }

        /* Metric value (bold, slightly larger) */
        [data-testid="stMetricValue"] {
            font-size: 20px !important;
            font-weight: 600 !important;
            color: inherit !important;
        }

        /* Delta (if ever used) */
        [data-testid="stMetricDelta"] {
            font-size: 12px !important;
            color: inherit !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    st.markdown("#### Quick snapshot")

    if selected_yards:
        c1, c2, c3 = st.columns(3)

        # Highest unemployment (max)
        if not cbp_view.empty and "Unemployement Rate" in cbp_view:
            row = cbp_view.loc[cbp_view["Unemployement Rate"].idxmax()]
            c1.metric(
                "Highest Unemployment",
                f"{row['County Name']}, {row['State']}",
                f"{row['Unemployement Rate']:.1%}"
            )
        else:
            c1.metric("Highest Unemployment", "—", "—")

        # Lowest Median Rent Paid
        if not cbp_view.empty and "Median Rent Paid" in cbp_view:
            row = cbp_view.loc[cbp_view["Median Rent Paid"].idxmin()]
            c2.metric(
                "Lowest Median Rent",
                f"{row['County Name']}, {row['State']}",
                f"${row['Median Rent Paid']:,.0f}/mo"
            )
        else:
            c2.metric("Lowest Median Rent", "—", "—")

        # Lowest Median Worker Earnings
        if not cbp_view.empty and "Median Worker Earnings" in cbp_view:
            row = cbp_view.loc[cbp_view["Median Worker Earnings"].idxmin()]
            c3.metric(
                "Lowest Median Earnings",
                f"{row['County Name']}, {row['State']}",
                f"${row['Median Worker Earnings']:,.0f}/yr"
            )
        else:
            c3.metric("Lowest Median Earnings", "—", "—")

    else:
        st.caption(
            "👆 Select one or more shipyards to view county-level metrics within their recruitment radii."
        )

   # ---------- Competition panel ----------
# ---------- Competition panel ----------
st.divider()

if selected_yards:
    shipyard_names_str = ", ".join(selected_yards)
    st.markdown(f"#### Recruitment Competition for **{shipyard_names_str}**")

    # Identify overlaps
    all_sets = cbp_view["__yards_set"].tolist()
    others = set().union(*all_sets) if all_sets else set()
    competitors = sorted(y for y in others if y not in set(selected_yards))

    st.markdown(
        f"**Shipyards overlapping** the chosen radii: "
        f"{(', '.join(competitors)) if competitors else 'None'}"
    )

    # Build the summary table (but do not render yet)
    tbl = (
        cbp_view[
            [
                "State",
                "County Name",
                "Recruitment Radius Count",
                "Unemployement Rate",
                "Median Worker Earnings",
                "Median Rent Paid",
                "Median Home Value",
                "Shipbuilders Employed",
            ]
        ]
        .rename(
            columns={
                "County Name": "County",
                "Recruitment Radius Count": "Yards in radius",
                "Unemployement Rate": "Unemployment",
                "Median Worker Earnings": "Worker Earnings ($/yr)",
                "Median Rent Paid": "Rent ($/mo)",
                "Median Home Value": "Home Value ($)",
                "Shipbuilders Employed": "Shipbuilders Employed",
            }
        )
        .sort_values(["Yards in radius", "Unemployment"], ascending=[False, False])
        .head(25)
    )

else:
    st.markdown("#### Recruitment Competition")
    st.caption("👆 Select one or more shipyards to explore competition among overlapping recruitment radii.")

    # ---------- RIGHT: map ----------
with right_col:
        st.markdown("### Interactive Map")
    # Wrap your existing map-building code into a function so we can pass the indicator
        def build_map(indicator_label):
            # --- Build the map (always) ---
            m = leafmap.Map(minimap_control=True, locate_control=True)

            # --- FIX: ensure Leaflet control containers render at correct size ---
            # Add a 1-point invisible marker + CSS padding for the controls
            folium.CircleMarker(
                location=[39.5, -98.35],  # roughly U.S. center
                radius=0.001,
                color="transparent",
                fill=True,
                fill_opacity=0,
                opacity=0,
                interactive=False
            ).add_to(m)

            # Inject CSS to enforce proper layout on load
            m.get_root().header.add_child(folium.Element("""
            <style>
            .leaflet-top.leaflet-left {
                margin-top: 10px !important;
                margin-left: 10px !important;
            }
            .leaflet-control-zoom, .leaflet-control-layers {
                transform: translate3d(0,0,0);
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
            }
            </style>
            """))

            # Feature groups to control stack & toggling
            # fg_cbp visibility depends on user selection
            # Feature groups to control stack & toggling
            fg_cbp_show = indicator_label != "None"
            fg_cbp       = folium.FeatureGroup(name="County Labor Indicator", show=fg_cbp_show)
            fg_buffers   = folium.FeatureGroup(name="Recruitment Radius", show=True)
            fg_shipyards = folium.FeatureGroup(name="Shipyard Locations", show=True)

            # --- Only add CBP layer if user selects one ---
            show_shipyard_legend = True

            if indicator_label != "None":
                show_shipyard_legend = False  # hide legend when CBP selected
                indicator_col = INDICATOR_OPTIONS[indicator_label]

                # --- Custom color logic per indicator ---
                vals = cbp[indicator_col].replace([np.inf, -np.inf], np.nan).dropna()

                if vals.isna().all() or len(vals.unique()) == 0:
                    st.warning(f"No valid numeric data for {indicator_label}")
                    return m

                # ✅ Indicator-specific settings
                indicator_settings = {
                    "Unemployment Rate": {
                        "palette": ["#f7fbff", "#deebf7", "#9ecae1", "#6baed6", "#3182bd", "#08519c"],
                        "classes": 6,
                        "method": "jenks",
                    },
                    "Median Rent Paid": {
                        "palette": ["#fff7fb", "#fbb4b9", "#f768a1", "#c51b8a", "#49006a"],
                        "classes": 5,
                        "method": "jenks",
                    },
                    "Shipbuilders Employed": {
                        "palette": ["#3288bd", "#66c2a5", "#abdda4", "#fee08b", "#f46d43", "#d53e4f"],
                        "classes": 6,
                        "method": "jenks",
                        "label": "Shipyard Workers",
                    },
                    "Recruitment Radius Count": {
                        # Adjusted palette: smooth dark blue → olive → gold → bright yellow (for 6–8)
                        "palette": ["#00204c", "#355e8d", "#7fa56e", "#d7c95f", "#f9f871", "#ffeb3b"],
                        "classes": 6,
                        "method": "manual",
                        # 👇 Updated bins: slightly finer gradation + final class reserved for 6–8
                        "bins": [0, 0, 1, 3, 5, 6, 8],
                        "force_range": (0, 8),
                    },
                    "Median Worker Earnings": {
                        "palette": ["#f7fcf0", "#c7e9c0", "#74c476", "#31a354", "#006d2c"],
                        "classes": 6,
                        "method": "jenks",
                    },
                    "Median Home Value": {
                        "palette": ["#fff5eb", "#fdbe85", "#fd8d3c", "#e6550d", "#a63603"],
                        "classes": 5,
                        "method": "quantile",
                    },
                }

                # Pull settings for the current indicator
                settings = indicator_settings.get(
                    indicator_label,
                    {"palette": ["#f7fbff", "#6baed6", "#08519c"], "classes": 7, "method": "linear"},
                )
                palette = settings["palette"]
                n_classes = settings["classes"]
                method = settings["method"]
                caption = settings.get("label", indicator_label)

                # 👇 Apply forced range if provided
                if "force_range" in settings:
                    vmin, vmax = settings["force_range"]
                else:
                    vmin, vmax = None, None

                # --- Classification & colormap creation ---
                try:
                    vals_clean = vals.dropna()

                    # 👇 Manual classification (Recruitment Radius Count)
                    if method == "manual" and "bins" in settings:
                        bins = settings["bins"]
                        vmin, vmax = settings.get("force_range", (bins[0], bins[-1]))
                        colormap = cm.StepColormap(
                            colors=settings["palette"],
                            index=bins,
                            vmin=vmin,
                            vmax=vmax,
                            caption=f"{caption} (Fixed classes)",
                        )

                    # 👇 Quantile classification (e.g., for Median Home Value)
                    elif method == "quantile":
                        n = n_classes
                        classifier = mapclassify.Quantiles(vals_clean, k=n)
                        bins = classifier.bins.tolist()
                        quant_index = [float(vals_clean.min())] + [float(b) for b in bins]
                        vmin, vmax = float(vals_clean.min()), float(vals_clean.max())

                        # Smooth out any mismatch between color count and bins
                        if len(quant_index) != len(palette) + 1:
                            quant_index = np.linspace(vmin, vmax, len(palette) + 1).tolist()

                        colormap = cm.StepColormap(
                            colors=palette,
                            index=quant_index,
                            vmin=vmin,
                            vmax=vmax,
                            caption=f"{caption} (Quantile classes)",
                        )

                    # 👇 Jenks (Natural Breaks)
                    elif method == "jenks" and len(vals_clean.unique()) >= 3:
                        classifier = mapclassify.NaturalBreaks(
                            vals_clean, k=min(n_classes, len(vals_clean.unique()) - 1)
                        )
                        bins = classifier.bins.tolist()
                        jenks_index = [float(vals_clean.min())] + [float(b) for b in bins]
                        vmin, vmax = float(vals_clean.min()), float(vals_clean.max())

                        if len(jenks_index) != len(palette) + 1:
                            jenks_index = np.linspace(vmin, vmax, len(palette) + 1).tolist()

                        colormap = cm.StepColormap(
                            colors=palette,
                            index=jenks_index,
                            vmin=vmin,
                            vmax=vmax,
                            caption=caption,
                        )

                    # 👇 Linear fallback
                    else:
                        vmin, vmax = float(vals_clean.quantile(0.02)), float(vals_clean.quantile(0.98))
                        colormap = cm.LinearColormap(colors=palette, vmin=vmin, vmax=vmax).to_step(n=n_classes)
                        colormap.caption = caption

                except Exception as e:
                    st.warning(f"Color scale fallback for {indicator_label}: {e}")
                    vmin, vmax = float(vals.quantile(0.02)), float(vals.quantile(0.98))
                    colormap = cm.LinearColormap(
                        colors=palette,
                        vmin=vmin,
                        vmax=vmax,
                    ).to_step(n=n_classes)
                    colormap.caption = caption

                # --- CBP CHOROPLETH (bottom layer) ---
                def style_fn(feature):
                    value = feature["properties"].get(indicator_col, None)
                    if value is None or (isinstance(value, (float, int)) and np.isnan(value)):
                        fill = "#cccccc"
                    else:
                        try:
                            fill = colormap(float(value))
                        except Exception:
                            fill = "#cccccc"
                    return {"color": "#222222", "weight": 0.2, "fillColor": fill, "fillOpacity": 0.85}

                tooltip = folium.GeoJsonTooltip(
                    fields=["State", "County Name", indicator_col],
                    aliases=["State", "County", indicator_label],
                    localize=True,
                    sticky=True,
                )

                folium.GeoJson(
                    data=cbp.__geo_interface__,
                    style_function=style_fn,
                    highlight_function=lambda _: {"weight": 1.5, "color": "white", "fillOpacity": 0.9},
                    tooltip=tooltip,
                    name=f"CBP: {indicator_label}",
                ).add_to(fg_cbp)

                fg_cbp.add_to(m)
                colormap.add_to(m)

            else:
                # Add empty layer so toggle still shows up even when no data
                folium.GeoJson(
                    data={"type": "FeatureCollection", "features": []},
                    name="County Labor Indicator"
                ).add_to(fg_cbp)
                fg_cbp.add_to(m)

            # --- Buffers and Shipyards ---
            for yard_id, color in color_map.items():
                yard_buffer = buffers[buffers["yard_unique_id"] == yard_id]
                if yard_buffer.empty:
                    continue

                for _, row in yard_buffer.iterrows():
                    popup_html = f"""
                    <b>{row['Shipyard Name']}</b><br><br>
                    <table style='width:220px;font-size:12px;background-color:rgba(255,255,255,0.9); border-radius:6px;'>
                        <tr><td><b>States Covered:</b></td><td>{row['States Covered']}</td></tr>
                        <tr><td><b>Counties Covered:</b></td><td>{row['Counties Covered']}</td></tr>
                    </table>
                    """
                    folium.GeoJson(
                        data=row["geometry"].__geo_interface__,
                        style_function=lambda x, color=color: {
                            "color": color,
                            "weight": 1.2,
                            "fillOpacity": 0.25,
                            "fillColor": color,
                        },
                        highlight_function=lambda x, color=color: {
                            "weight": 3,
                            "color": "white",
                            "fillOpacity": 0.4,
                        },
                        popup=folium.Popup(popup_html, max_width=260),
                    ).add_to(fg_buffers)

            fg_buffers.add_to(m)

            for yard_id, color in color_map.items():
                yard_point = shipyards[shipyards["yard_unique_id"] == yard_id]
                if yard_point.empty:
                    continue
                for _, row in yard_point.iterrows():
                    popup_html = f"""
                    <b>{row['Yard']}</b><br>
                    <i>{row['company_owner']}</i><br><br>
                    <table style='width:260px;font-size:12px;background-color:rgba(255,255,255,0.9); border-radius:6px;'>
                        <tr><td><b>Ownership Type:</b></td><td>{row['ownership_type']}</td></tr>
                        <tr><td><b>Builds Destroyers / Frigates:</b></td><td>{row['destroyers_or_frigates']}</td></tr>
                        <tr><td><b>Builds Aircraft Carriers:</b></td><td>{row['aircraft_carriers']}</td></tr>
                        <tr><td><b>Builds Submarines:</b></td><td>{row['submarines']}</td></tr>
                        <tr><td><b>Builds Small Craft / Aux:</b></td><td>{row['small_craft_or_aux']}</td></tr>
                        <tr><td><b>Has Coast Guard Contracts:</b></td><td>{row['coast_guard']}</td></tr>
                    </table>
                    """
                    folium.CircleMarker(
                        location=[row["lat"], row["lon"]],
                        radius=6,
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.9,
                        weight=1,
                        popup=folium.Popup(popup_html, max_width=300, min_width=200),
                    ).add_to(fg_shipyards)

            fg_shipyards.add_to(m)

            # --- Add measure tool (always visible) ---
            m.add_child(
                MeasureControl(
                    position="topleft",
                    primary_length_unit="miles",
                    secondary_length_unit="kilometers"
                )
            )

            # --- Add layer control ONLY when an indicator is selected ---
            if indicator_label != "None":
                folium.LayerControl(collapsed=False, position="topright").add_to(m)

            # --- Conditional Shipyard Legend ---
            if show_shipyard_legend:
                legend_items = []
                for yard_id, color in color_map.items():
                    yard_rows = shipyards.loc[shipyards["yard_unique_id"] == yard_id, "Yard"]
                    yard_name = yard_rows.iloc[0] if not yard_rows.empty else f"Yard {yard_id}"
                    legend_items.append(f"<div><span style='background:{color}'></span>{yard_name}</div>")

                n = len(legend_items)
                col_size = (n + 2) // 3
                col1 = "".join(legend_items[:col_size])
                col2 = "".join(legend_items[col_size: 2 * col_size])
                col3 = "".join(legend_items[2 * col_size:])

                legend_html = f"""
                <div style="
                    position: fixed;
                    bottom: 20px;
                    left: 50%;
                    transform: translateX(-50%);
                    z-index: 9999;
                    background-color: rgba(255, 255, 255, 0.45);
                    padding: 12px 18px;
                    border-radius: 10px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
                    max-height: 220px;
                    overflow-y: auto;
                    font-size: 13px;
                    width: 850px;
                ">
                    <b style="display:block;text-align:center;margin-bottom:6px;">U.S. Shipyards</b>
                    <div style="display: flex; justify-content: space-between;">
                        <div style="flex: 1; margin-right: 10px;">{col1}</div>
                        <div style="flex: 1; margin-right: 10px;">{col2}</div>
                        <div style="flex: 1;">{col3}</div>
                    </div>
                    <style>
                        div span {{
                            display:inline-block;
                            width: 14px;
                            height: 14px;
                            margin-right: 6px;
                            border-radius: 3px;
                            vertical-align: middle;
                        }}
                        div div {{
                            margin-bottom: 3px;
                        }}
                    </style>
                </div>
                """
                m.get_root().html.add_child(folium.Element(legend_html))
        # --- Final render ---
            return m  # the leafmap.Map you create
        m = build_map(indicator_label)
        m.set_center(lon=-98.35, lat=39.5, zoom=5.1)
        m.to_streamlit(height=720)
# ---------- Full-width competition table ----------
if selected_yards and tbl is not None:
    if len(selected_yards) == 1:
        header_label = f"County Overview: {selected_yards[0]}"
    else:
        header_label = f"County Overview for Selected Shipyards ({len(selected_yards)})"
    st.markdown(f"### 🧭 {header_label}")

    # --- Optional style polish ---
    st.markdown(
        """
        <style>
        /* Alternating row background */
        [data-testid="stDataFrame"] tbody tr:nth-child(odd) {
            background-color: rgba(255,255,255,0.03) !important;
        }
        [data-testid="stDataFrame"] tbody tr:hover {
            background-color: rgba(47,138,196,0.08) !important;
        }
        /* Make numeric cells align right for readability */
        [data-testid="stDataFrame"] td {
            text-align: right !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # --- Render the full-width table with column highlighting and formatted numbers ---
    st.data_editor(
        tbl,
        use_container_width=True,
        hide_index=True,
        disabled=True,
        column_config={
            "State": st.column_config.TextColumn("State", width="small"),
            "County": st.column_config.TextColumn("County", width="medium"),
            "Yards in radius": st.column_config.NumberColumn(
                "Yards in radius",
                format="%d",
                width="small",
                help="Number of shipyards intersecting this county’s 90-mile radius"
            ),
            "Unemployment": st.column_config.NumberColumn(
                "Unemployment Rate",
                format="%.1f %%",
                width="small",
            ),
            "Worker Earnings ($/yr)": st.column_config.NumberColumn(
                "Median Worker Earnings",
                format="$%.0f",          # was "$%,d"
                width="medium",
                help="Median annual earnings for workers in this county"
            ),
            "Rent ($/mo)": st.column_config.NumberColumn(
                "Median Rent Paid",
                format="$%.0f",          # was "$%,d"
                width="medium",
                help="Median monthly rent paid in this county"
            ),
            "Home Value ($)": st.column_config.NumberColumn(
                "Median Home Value",
                format="$%.0f",          # was "$%,d"
                width="medium",
                help="Median home value (owner-occupied housing)"
            ),
            "Shipbuilders Employed": st.column_config.NumberColumn(
                "Shipbuilders Employed",
                format="%.0f",           # was "%,d"
                width="small",
            ),
        },
        height=500,
        column_order=[
            "State",
            "County",
            "Yards in radius",
            "Unemployment",
            "Worker Earnings ($/yr)",
            "Rent ($/mo)",
            "Home Value ($)",
            "Shipbuilders Employed",
        ],
        key="county_comp_table"
    )