import psutil  
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
from folium import Element

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
Use the dropdowns below to compare two county-level indicators side by side by draging the slider to visually compare differences across regions.
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
    """Rasterize vector data to an in-memory xarray raster, clipped to boundaries."""
    gdf = gdf.to_crs(4326)
    bounds = gdf.total_bounds
    xres = int((bounds[2] - bounds[0]) / resolution)
    yres = int((bounds[3] - bounds[1]) / resolution)

    transform = from_bounds(*bounds, xres, yres)
    shapes = [(geom, val) for geom, val in zip(gdf.geometry, gdf[column])]

    raster = rasterize(
        shapes,
        out_shape=(yres, xres),
        transform=transform,
        fill=np.nan,
        dtype="float32",
    )

    da = xr.DataArray(
        raster,
        dims=("y", "x"),
        coords={
            "y": np.linspace(bounds[3], bounds[1], raster.shape[0]),
            "x": np.linspace(bounds[0], bounds[2], raster.shape[1]),
        },
        attrs={"transform": transform, "crs": "EPSG:4326"},
    )
    return da

# --- Create xarrays for both indicators ---
left_raster = rasterize_indicator(left_data, left_col)
right_raster = rasterize_indicator(right_data, right_col)

# --- Split map with DataArrays ---
with st.spinner("Rendering comparison map..."):
    m = leafmap.Map(center=[37.8, -96], zoom=4, minimap_control=True)

    m.split_map(
    left_raster,
    right_raster,
    left_args={"layer_name": f"{left_col}", "colormap": "viridis"},
    right_args={"layer_name": f"{right_col}", "colormap": "plasma"},
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

# --- Custom legends with real color gradients ---
    left_legend_html = f"""
    <div style="
        position: fixed;
        bottom: 40px;
        left: 10px;
        z-index: 9999;
        background-color: rgba(255, 255, 255, 0.9);
        padding: 10px 14px;
        border-radius: 6px;
        box-shadow: 0 0 6px rgba(0,0,0,0.3);
        font-size: 13px;
        line-height: 1.3;
    ">
    <b>◀ {left_col}</b><br>
    <div style="height: 10px; width: 120px; 
        background: linear-gradient(to right, #440154, #3b528b, #21918c, #5ec962, #fde725);
        border-radius: 3px; margin-top: 5px;"></div>
    <div style="display: flex; justify-content: space-between; font-size: 11px; color:#333;">
    <span>Low</span><span>High</span>
    </div>
    </div>
    """

    right_legend_html = f"""
    <div style="
        position: fixed;
        bottom: 40px;
        right: 10px;
        z-index: 9999;
        background-color: rgba(255, 255, 255, 0.9);
        padding: 10px 14px;
        border-radius: 6px;
        box-shadow: 0 0 6px rgba(0,0,0,0.3);
        font-size: 13px;
        line-height: 1.3;
    ">
    <b>{right_col} ▶</b><br>
    <div style="height: 10px; width: 120px; 
        background: linear-gradient(to right, #0d0887, #6a00a8, #b12a90, #e16462, #fca636, #f0f921);
        border-radius: 3px; margin-top: 5px;"></div>
    <div style="display: flex; justify-content: space-between; font-size: 11px; color:#333;">
    <span>Low</span><span>High</span>
    </div>
    </div>
    """

    m.get_root().html.add_child(Element(left_legend_html))
    m.get_root().html.add_child(Element(right_legend_html))

    m.to_streamlit(height=700)





import geopandas as gpd
import numpy as np
import xarray as xr
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from rasterio.mask import mask
import rioxarray

# --- Load CBP data ---
cbp = gpd.read_file(
    "https://f-lab-shipyard-competition.s3.amazonaws.com/clean_cbp_population_data.geojson"
).to_crs(4326)

indicators = [
    "Unemployement Rate",
    "Median Worker Earnings",
    "Median Home Value",
    "Median Rent Paid",
    "Shipbuilders Employed",
    "Recruitment Radius Count",
]

# --- Rasterization function ---
def make_highres_raster(gdf, column, res_deg=0.02, out_path=None):
    """Rasterize vector data at high resolution and save to GeoTIFF."""
    bounds = gdf.total_bounds
    xres = int((bounds[2] - bounds[0]) / res_deg)
    yres = int((bounds[3] - bounds[1]) / res_deg)
    transform = from_bounds(*bounds, xres, yres)

    shapes = [(geom, float(val)) for geom, val in zip(gdf.geometry, gdf[column])]
    raster = rasterize(
        shapes,
        out_shape=(yres, xres),
        transform=transform,
        fill=np.nan,
        dtype="float32",
    )

    da = xr.DataArray(
        raster,
        dims=("y", "x"),
        coords={
            "y": np.linspace(bounds[3], bounds[1], yres),
            "x": np.linspace(bounds[0], bounds[2], xres),
        },
        attrs={"transform": transform, "crs": "EPSG:4326"},
    )

    if out_path:
        da.rio.write_crs("EPSG:4326", inplace=True)
        da.rio.to_raster(
            out_path,
            compress="LZW",
            tiled=True,
            dtype="float32",
        )
        print(f"✅ Saved raster: {out_path}")

    return out_path


# --- Clipping function ---
def crop_to_counties(in_tif, gdf, out_tif):
    """Clip raster tightly to county geometries."""
    with rasterio.open(in_tif) as src:
        out_img, out_transform = mask(src, gdf.geometry, crop=True, filled=True, nodata=np.nan)
        meta = src.meta.copy()
        meta.update({
            "driver": "GTiff",
            "height": out_img.shape[1],
            "width": out_img.shape[2],
            "transform": out_transform,
            "compress": "LZW",
            "tiled": True,
            "dtype": "float32",
            "nodata": np.nan,
        })

    with rasterio.open(out_tif, "w", **meta) as dst:
        dst.write(out_img)
    print(f"✂️ Clipped and saved: {out_tif}")


# --- Generate + clip all rasters ---
for col in indicators:
    safe = col.lower().replace(" ", "_").replace("/", "_")
    raw_out = f"raster_{safe}.tif"
    clipped_out = f"raster_{safe}_clipped.tif"

    # Step 1: rasterize
    make_highres_raster(cbp, col, res_deg=0.02, out_path=raw_out)

    # Step 2: clip to U.S. counties
    crop_to_counties(raw_out, cbp, clipped_out)
