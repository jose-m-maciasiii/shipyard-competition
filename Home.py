import streamlit as st
import leafmap.foliumap as leafmap
import geopandas as gpd

st.set_page_config(layout="wide")

# Sidebar content
markdown = """
County demographic data is from the U.S. Census American Community Survey, 2023 5 year estimates, Labor statistics is from the U.S. Beauru of Labor Statistics (BLS) using NAICS 336600.
"""

st.sidebar.title("Data Sources")
logo = "https://upload.wikimedia.org/wikipedia/commons/9/99/CSIS_logo_blue.svg"
st.sidebar.info(markdown)
st.sidebar.image(logo)

# Page title
st.title("Shipyard Competition Map")

st.markdown(
    """
    This interactive map displays key layers from the CSIS Shipyard Labor Competition project.
    Data are sourced from pre-processed spatial datasets hosted on AWS S3.
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

# Loop through each yard and add its layers
for yard_id, color in color_map.items():
    yard_point = shipyards[shipyards["yard_unique_id"] == yard_id]
    yard_buffer = buffers[buffers["yard_unique_id"] == yard_id]

    # Add semi-transparent buffer polygon
    if not yard_buffer.empty:
        m.add_gdf(
            yard_buffer,
            layer_name=f"{yard_id} Buffer",
            style={"color": color, "fillColor": color, "fillOpacity": 0.25, "weight": 1},
        )

    # Add yard point as a circle marker
    if not yard_point.empty:
        # Extract coordinates into separate columns
        yard_point = yard_point.assign(
            lon=yard_point.geometry.x,
            lat=yard_point.geometry.y
        )

        m.add_points_from_xy(
            data=yard_point,
            x="lon",
            y="lat",
            color=color,
            radius=8,
            popup=["Yard", "company_owner", "ownership_type"],
            layer_name=f"{yard_id} Yard",
        )

# --- Render map in Streamlit ---
st.subheader("U.S. Shipyards and Buffer Zones")
m.to_streamlit(height=700)