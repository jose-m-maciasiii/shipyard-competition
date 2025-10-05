import streamlit as st
import leafmap.foliumap as leafmap
import geopandas as gpd
import folium
from folium.features import GeoJsonTooltip
import pandas as pd  
import numpy as np
import re

st.set_page_config(layout="wide")

# --- Sidebar ---
markdown = """
County demographic data is from the U.S. Census American Community Survey (2023, 5-year estimates). 
Labor statistics are from the Bureau of Labor Statistics (BLS, NAICS 336600).
"""
st.sidebar.title("Source")
logo = "https://upload.wikimedia.org/wikipedia/commons/9/99/CSIS_logo_blue.svg"
st.sidebar.info(markdown)
st.sidebar.image(logo)

# --- Page title ---
st.title("Shipbuilding Labor Market Indicators")

st.markdown(
    """
    This map allows users to explore key labor and socioeconomic characteristics 
    across U.S. counties relevant to shipbuilding. Use the dropdown menu to 
    visualize indicators such as unemployment rate, worker earnings, or home values.
    """
)

# --- Load data from S3 ---
cbp_url = "https://f-lab-shipyard-competition.s3.amazonaws.com/clean_cbp_population_data.geojson"
shipyards_url = "https://f-lab-shipyard-competition.s3.us-east-1.amazonaws.com/ship_yards_sf.gpkg"
buffers_url = "https://f-lab-shipyard-competition.s3.us-east-1.amazonaws.com/ship_yards_buffers_ll.gpkg"

cbp = gpd.read_file(cbp_url)
shipyards = gpd.read_file(shipyards_url)
buffers = gpd.read_file(buffers_url)

# --- Define columns available for mapping ---
cbp_options = [
    "Unemployement Rate",
    "Median Worker Earnings",
    "Median Home Value",
    "Median Rent Paid",
    "Shipbuilders Employed",
    "Recruitment Radius Count"
]
selected_col = st.sidebar.selectbox("Select CBP layer to visualize:", cbp_options, index=0)
cbp[selected_col] = cbp[selected_col].fillna(0)
# --- Define color palette ---
palette = [
    "#E58606", "#5D69B1", "#52BCA3", "#99C945", "#CC61B0", "#24796C",
    "#DAA51B", "#2F8AC4", "#764E9F", "#ED645A", "#CC3A8E", "#A5AA99"
]

# Assign each yard a unique color (loop if more yards than colors)
unique_yards = shipyards["yard_unique_id"].unique()
color_map = {
    yard_id: palette[i % len(palette)] for i, yard_id in enumerate(unique_yards)
}
buffers = buffers.rename(columns={
    "yard_name": "Shipyard Name",
    "state_coverage": "States Covered",
    "county_coverage": "Counties Covered"
})

# --- Create interactive map ---
m = leafmap.Map(minimap_control=True, locate_control=True)
m.add_basemap("Stadia.AlidadeSmoothDark")
m.add_data(
    cbp,
    column=selected_col,
    layer_name=f"{selected_col} by County",
    cmap="viridis",
    legend_title=selected_col,
    scheme="FisherJenks",
    k=5,
    add_legend=True
)
# --- Dynamic tooltip fields and aliases ---
tooltip_fields = [
    "County Name",
    "State",
    selected_col,
    "Recruitment Radius Count",
    "Shipyards in Radius"
]
tooltip_aliases = [
    "County:",
    "State:",
    f"{selected_col}:",
    "Recruitment Radius (Shipyards):",
    "Nearby Shipyards:"
]

# --- Optional: clean display formatting ---
def format_value(val, col):
    if pd.isna(val) or val == "":
        return "N/A"
    if "Rate" in col:
        return f"{val:.1f}%"
    elif "Earnings" in col or "Home Value" in col or "Rent" in col:
        return f"${val:,.0f}"
    elif isinstance(val, (int, float)):
        return f"{val:,.0f}"
    else:
        return str(val)


def format_shipyards_list(val):
    """Convert comma-separated shipyard names into a clean HTML bullet list, 
    preserving commas within legal suffixes like 'LLC' or 'Inc'."""
    if pd.isna(val) or val == "":
        return "None nearby"

    # Split on commas NOT followed by LLC or Inc (case-insensitive)
    yards = re.split(r", (?!LLC|Inc\b|inc\b|llc\b)", str(val).strip())

    # Clean and filter blanks
    yards = [y.strip() for y in yards if y.strip()]
    if len(yards) == 0:
        return "None nearby"

    return (
        "<ul style='margin:0; padding-left:16px; font-size:12px;'>"
        + "".join([f"<li>{y}</li>" for y in yards])
        + "</ul>"
    )

# --- Apply formatted text for tooltip display ---
cbp_display = cbp.copy()

# Apply normal formatting to numeric/text fields
for col in tooltip_fields:
    if col in cbp_display.columns and col != "Shipyards in Radius":
        cbp_display[col] = cbp_display[col].apply(lambda v: format_value(v, col))

# Apply bullet-list formatting only to the shipyards column
if "Shipyards in Radius" in cbp_display.columns:
    cbp_display["Shipyards in Radius"] = cbp_display["Shipyards in Radius"].apply(format_shipyards_list)

# --- Add the white-outline hover layer ---
folium.GeoJson(
    data=cbp_display.to_json(),
    name="County outlines",
    style_function=lambda feat: {
        "color": "#ffffff",
        "weight": 0.6,
        "opacity": 1.0,
        "fillColor": "#000000",
        "fillOpacity": 0.0,
    },
    tooltip=GeoJsonTooltip(
        fields=tooltip_fields,
        aliases=tooltip_aliases,
        localize=True,
        sticky=True,
        labels=True,
        style=(
            "background-color: rgba(255, 255, 255, 0.85); "
            "border-radius: 5px; padding: 5px; "
            "font-size: 12px; box-shadow: 0 0 3px rgba(0,0,0,0.2);"
        ),
        max_width=350,
    ),
    control=True,
    show=True,
).add_to(m)
# --- Create feature groups ---
fg_buffers = folium.FeatureGroup(name="Recruitment Radius", show=True)
fg_shipyards = folium.FeatureGroup(name="Shipyard Locations", show=True)

# Precompute lon/lat once
shipyards["lon"] = shipyards.geometry.x
shipyards["lat"] = shipyards.geometry.y

# --- Add layers ---
for yard_id, color in color_map.items():
    yard_point = shipyards[shipyards["yard_unique_id"] == yard_id]
    yard_buffer = buffers[buffers["yard_unique_id"] == yard_id]

    # Buffer polygons with popups
    if not yard_buffer.empty:
        for _, row in yard_buffer.iterrows():
            popup_html = f"""
            <b>{row['Shipyard Name']}</b><br><br>
            <table style='width:220px;font-size:12px;background-color:rgba(255,255,255,0.9); border-radius:6px;'>
                <tr><td><b>States Covered:</b></td><td>{row['States Covered']}</td></tr>
                <tr><td><b>Counties Covered:</b></td><td>{row['Counties Covered']}</td></tr>
            </table>
            """
            folium.GeoJson(
                row["geometry"],
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
                popup=folium.Popup(popup_html, max_width=250),
            ).add_to(fg_buffers)

    # Circle markers for yards
    if not yard_point.empty:
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

# --- Add layers and controls ---
fg_buffers.add_to(m)
fg_shipyards.add_to(m)
folium.LayerControl(collapsed=False).add_to(m)

# --- Fit to bounds ---
m.fit_bounds(shipyards.total_bounds[[1, 0, 3, 2]].reshape(2, 2).tolist())
# --- Legend ---

# Fix layer control box size and stacking
fix_css = """
<style>
.leaflet-control-layers {
    max-height: 280px !important;  /* taller toggle window */
    overflow-y: auto !important;   /* scroll if long */
    z-index: 9998 !important;      /* sit below legend (9999) */
}
.leaflet-control-layers-expanded {
    max-width: 220px !important;   /* wider layer panel */
}
</style>
"""
m.get_root().html.add_child(folium.Element(fix_css))
# --- Render ---
m.to_streamlit(height=700)