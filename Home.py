import streamlit as st
import geopandas as gpd
import leafmap.foliumap as leafmap
import folium
from folium.plugins import MeasureControl
import branca.colormap as cm
import numpy as np

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
st.markdown("### Select an Indicator to Visualize with U.S. Shipyards")

col_main = st.container()
with col_main:
    indicator_label = st.selectbox(
        "Select a county indicator to display (optional):",
        ["None"] + list(INDICATOR_OPTIONS.keys()),
        index=0
    )

# --- Build the map (always) ---
m = leafmap.Map(minimap_control=True, locate_control=True)
# m.add_basemap("Stadia.AlidadeSmoothDark")

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
fg_cbp_show = indicator_label != "None"  # True when a CBP layer is chosen
fg_cbp       = folium.FeatureGroup(name="County Labor Indicator", show=fg_cbp_show)
fg_buffers   = folium.FeatureGroup(name="Recruitment Radius", show=True)
fg_shipyards = folium.FeatureGroup(name="Shipyard Locations", show=True)

# --- Only add CBP layer if user selects one ---
show_shipyard_legend = True

if indicator_label != "None":
    show_shipyard_legend = False  # hide legend when CBP selected
    indicator_col = INDICATOR_OPTIONS[indicator_label]

    vals = cbp[indicator_col].replace([np.inf, -np.inf], np.nan).dropna()
    if vals.empty:
        vmin, vmax = 0.0, 1.0
    else:
        vmin, vmax = float(vals.quantile(0.02)), float(vals.quantile(0.98))
        if vmin == vmax:
            vmin, vmax = float(vals.min()), float(vals.max())
            if vmin == vmax:
                vmin, vmax = vmin - 0.5, vmax + 0.5

    colormap = cm.LinearColormap(
        colors=["#f7fbff", "#6baed6", "#08519c"],
        vmin=vmin, vmax=vmax
    ).to_step(n=7)
    colormap.caption = indicator_label

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
        yard_name = shipyards.loc[
            shipyards["yard_unique_id"] == yard_id, "Yard"
        ].values[0]
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
m.set_center(lon=-98.35, lat=39.5, zoom=5.1)
m.to_streamlit(height=720)