import streamlit as st
import leafmap.foliumap as leafmap
import geopandas as gpd
import folium
st.set_page_config(layout="wide")

# Sidebar content
markdown = """
County demographic data is from the U.S. Census American Community Survey, 2023 5 year estimates, Labor statistics is from the U.S. Beauru of Labor Statistics (BLS) using NAICS 336600.
"""

st.sidebar.title("Source")
logo = "https://upload.wikimedia.org/wikipedia/commons/9/99/CSIS_logo_blue.svg"
st.sidebar.info(markdown)
st.sidebar.image(logo)

# Page title
st.title("Shipbuilding Labor Competition")

st.markdown(
    """
    As the United States begins to prioritze shipbuilding to meet the challenge of an agressive People's Republic of China (PRC), a key challenge it faces is a labor shortfall. This web based tool was design to highlight the labor competition shipbuilding firms will encounter in the short term as they prepare to scale production.
    """
)

# --- Load data from S3 ---
shipyards_url = "https://f-lab-shipyard-competition.s3.us-east-1.amazonaws.com/ship_yards_sf.gpkg"
buffers_url = "https://f-lab-shipyard-competition.s3.us-east-1.amazonaws.com/ship_yards_buffers_ll.gpkg"
cbp_url = "https://f-lab-shipyard-competition.s3.amazonaws.com/clean_cbp_population_data.geojson"

shipyards = gpd.read_file(shipyards_url)
buffers = gpd.read_file(buffers_url)
# (Make sure your files are publicly readable per the bucket policy)


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

# --- Create interactive map ---
m = leafmap.Map(minimap_control=True, draw_control=False)
m.add_basemap("Stadia.AlidadeSmoothDark")

# Precompute lon/lat once
shipyards = shipyards.to_crs(4326)  # just in case
shipyards["lon"] = shipyards.geometry.x
shipyards["lat"] = shipyards.geometry.y

# Loop through each yard and add its layers
for yard_id, color in color_map.items():
    yard_point = shipyards[shipyards["yard_unique_id"] == yard_id]
    yard_buffer = buffers[buffers["yard_unique_id"] == yard_id]

    # Buffer polygon, semi-transparent
    if not yard_buffer.empty:
        m.add_gdf(
            yard_buffer,
            layer_name=f"{yard_id} Buffer",
            style={"color": color, "fillColor": color, "fillOpacity": 0.25, "weight": 1},
        )

    
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
            ).add_to(m)
# --- Custom three-column legend ---
legend_items = []
for yard_id, color in color_map.items():
    yard_name = shipyards.loc[
        shipyards["yard_unique_id"] == yard_id, "Yard"
    ].values[0]
    legend_items.append(f"<div><span style='background:{color}'></span>{yard_name}</div>")

# Split legend into 3 roughly equal columns
n = len(legend_items)
col_size = (n + 2) // 3  # divide into 3 columns
col1 = "".join(legend_items[:col_size])
col2 = "".join(legend_items[col_size: 2*col_size])
col3 = "".join(legend_items[2*col_size:])

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
st.subheader("U.S. Shipyards & Recruitment Radius")
m.set_center(lon=-98.35, lat=39.5, zoom=5.2)
m.to_streamlit(height=700)