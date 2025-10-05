import streamlit as st
import leafmap.foliumap as leafmap
import geopandas as gpd

st.set_page_config(layout="wide")

# Sidebar content
markdown = """
The
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
# (Make sure your files are publicly readable per the bucket policy)
cbp_url = "https://f-lab-shipyard-competition.s3.amazonaws.com/clean_cbp_population_data.geojson"
shipyards_url = "https://f-lab-shipyard-competition.s3.amazonaws.com/ship_yards_sf.gpkg"
buffers_url = "https://f-lab-shipyard-competition.s3.amazonaws.com/ship_yards_buffers_ll.gpkg"

@st.cache_data(show_spinner=True)
def load_data():
    try:
        cbp = gpd.read_file(cbp_url)
        shipyards = gpd.read_file(shipyards_url)
        buffers = gpd.read_file(buffers_url)
        return cbp, shipyards, buffers
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None, None, None

cbp, shipyards, buffers = load_data()

# --- Initialize map ---
m = leafmap.Map(center=[38.9, -77.03], zoom=4, minimap_control=True)

if cbp is not None:
    m.add_gdf(cbp, layer_name="U.S. County Data", style={"color": "#3182bd"})

if shipyards is not None:
    m.add_gdf(shipyards, layer_name="Shipyards", style={"color": "#e34a33", "fillColor": "#fb6a4a"})

if buffers is not None:
    m.add_gdf(buffers, layer_name="Recuritment Radius", style={"color": "#31a354", "fillOpacity": 0.2})

# Add basemap and render map
m.add_basemap("Stadia.AlidadeSmoothDark")
m.to_streamlit(height=700)