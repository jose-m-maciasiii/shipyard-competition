import streamlit as st
import leafmap.foliumap as leafmap
import geopandas as gpd
import rioxarray
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds
import numpy as np
import tempfile
import xarray as xr
import os

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

# --- Cached Data Load ---
@st.cache_data
def load_data():
    cbp_url = "https://f-lab-shipyard-competition.s3.amazonaws.com/clean_cbp_population_data.geojson"
    cbp = gpd.read_file(cbp_url)
    cbp["geometry"] = cbp["geometry"].simplify(0.01, preserve_topology=True)
    return cbp

cbp = load_data()

# --- Indicator options ---
cbp_options = [
    "Unemployement Rate",
    "Median Worker Earnings",
    "Median Home Value",
    "Median Rent Paid",
    "Shipbuilders Employed",
    "Recruitment Radius Count",
]

# --- UI layout ---
st.title("⚓ Shipbuilding Labor Market Comparison")
st.markdown("""
Use the dropdowns below to compare two county-level indicators side by side.  
Drag the slider on the map to visually compare differences across regions.
""")

col1, col2 = st.columns(2)
with col1:
    left_col = st.selectbox("Left Map Indicator", cbp_options, index=0)
with col2:
    right_col = st.selectbox("Right Map Indicator", cbp_options, index=1)

st.markdown(
    f"**Currently Comparing:** <span style='color:#1f77b4'>{left_col}</span> ↔ <span style='color:#2ca02c'>{right_col}</span>",
    unsafe_allow_html=True
)

# --- Classification (optional bin smoothing) ---
@st.cache_data
def classify_data(_data, column):
    import mapclassify
    _data = _data.copy()
    _data[column] = _data[column].fillna(0)
    classifier = mapclassify.FisherJenks(_data[column], k=5)
    bins = list(classifier.bins)
    bins[0] = min(_data[column]) - 1e-6
    bins[-1] = max(_data[column]) + 1e-6
    return _data, bins

left_data, _ = classify_data(cbp, left_col)
right_data, _ = classify_data(cbp, right_col)

# --- Rasterization helper ---
def rasterize_indicator(gdf, column, resolution=0.1):
    gdf = gdf.to_crs(4326)
    bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
    width = int((bounds[2] - bounds[0]) / resolution)
    height = int((bounds[3] - bounds[1]) / resolution)
    transform = from_bounds(*bounds, width, height)
    shapes = [(geom, val) for geom, val in zip(gdf.geometry, gdf[column])]
    raster = rasterize(
        shapes,
        out_shape=(height, width),
        transform=transform,
        fill=np.nan,
        dtype="float32",
    )
    da = xr.DataArray(
        raster,
        dims=("y", "x"),
        coords={
            "y": np.linspace(bounds[3], bounds[1], height),
            "x": np.linspace(bounds[0], bounds[2], width),
        },
        attrs={"transform": transform, "crs": "EPSG:4326"},
    )
    return da

# --- Create xarrays for both indicators ---
left_da = rasterize_indicator(left_data, left_col)
right_da = rasterize_indicator(right_data, right_col)

# --- Split map with DataArrays ---
with st.spinner("Rendering comparison map..."):
    m = leafmap.Map(center=[37.8, -96], zoom=4, minimap_control=True)

    m.split_map(
        left_da,
        right_da,
        left_args={"layer_name": left_col, "colormap": "viridis"},
        right_args={"layer_name": right_col, "colormap": "plasma"},
    )

    # Simple three-step color legend approximating viridis
    viridis_legend = {
        "Low": "#440154",
        "Medium": "#21908C",
        "High": "#FDE725"
    }

    # Simple three-step color legend approximating plasma
    plasma_legend = {
        "Low": "#0D0887",
        "Medium": "#CC4678",
        "High": "#F0F921"
    }

    m.add_legend(title=f"Left: {left_col}", legend_dict=viridis_legend)
    m.add_legend(title=f"Right: {right_col}", legend_dict=plasma_legend)

    m.to_streamlit(height=700)