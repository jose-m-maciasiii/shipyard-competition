import streamlit as st
import leafmap.foliumap as leafmap
import geopandas as gpd
import rioxarray
import numpy as np
from folium import Element
import mapclassify

st.set_page_config(layout="wide")

# --- Sidebar (kept simple) ---
st.sidebar.title("Source")
st.sidebar.markdown("""
County demographic data are from the **U.S. Census American Community Survey (2023, 5-year estimates)**.  
Labor statistics are from the **U.S. Bureau of Labor Statistics (BLS, NAICS 336600)**.  
Shipyard and NAICS data compiled by the **CSIS Futures Lab**.
""")
st.sidebar.image(
    "https://upload.wikimedia.org/wikipedia/commons/9/99/CSIS_logo_blue.svg",
    use_container_width=True,
)

# --- Manifest of pre-clipped rasters on S3 ---
RASTER_URLS = {
    "Unemployement Rate": "https://f-lab-shipyard-competition.s3.us-east-1.amazonaws.com/raster_unemployement_rate_clipped.tif",
    "Median Worker Earnings": "https://f-lab-shipyard-competition.s3.us-east-1.amazonaws.com/raster_median_worker_earnings_clipped.tif",
    "Median Home Value": "https://f-lab-shipyard-competition.s3.us-east-1.amazonaws.com/raster_median_home_value_clipped.tif",
    "Median Rent Paid": "https://f-lab-shipyard-competition.s3.us-east-1.amazonaws.com/raster_median_rent_paid_clipped.tif",
    "Shipbuilders Employed": "https://f-lab-shipyard-competition.s3.us-east-1.amazonaws.com/raster_shipbuilders_employed_clipped.tif",
    "Recruitment Radius Count": "https://f-lab-shipyard-competition.s3.us-east-1.amazonaws.com/raster_recruitment_radius_count_clipped.tif",
}

# --- Color and classification alignment with main app ---
COLOR_SETTINGS = {
    "Unemployement Rate": {
        "palette": ["#f7fbff", "#deebf7", "#9ecae1", "#6baed6", "#3182bd", "#08519c"],
        "method": "jenks",
        "classes": 6,
    },
    "Median Worker Earnings": {
        "palette": ["#f7fcf0", "#c7e9c0", "#74c476", "#31a354", "#006d2c"],
        "method": "jenks",
        "classes": 6,
    },
    "Median Home Value": {
        "palette": ["#fff5eb", "#fdbe85", "#fd8d3c", "#e6550d", "#a63603"],
        "method": "quantile",
        "classes": 5,
    },
    "Median Rent Paid": {
        "palette": ["#fff7fb", "#fbb4b9", "#f768a1", "#c51b8a", "#49006a"],
        "method": "jenks",
        "classes": 5,
    },
    "Shipbuilders Employed": {
        "palette": ["#3288bd", "#66c2a5", "#abdda4", "#fee08b", "#f46d43", "#d53e4f"],
        "method": "jenks",
        "classes": 6,
    },
    "Recruitment Radius Count": {
        "palette": ["#00204c", "#355e8d", "#7fa56e", "#d7c95f", "#f9f871", "#ffeb3b"],
        "method": "manual",
        "bins": [0, 0, 1, 3, 5, 6, 8],
        "classes": 6,
    },
}

# --- Page header ---
st.title("⚓ Shipbuilding Labor Market Comparison")
st.markdown("""
Compare two labor-market indicators side-by-side across U.S. counties.  
Drag the slider to explore differences between regions.
""")

col1, col2 = st.columns(2)
with col1:
    left_var = st.selectbox("Left Map Indicator", list(RASTER_URLS.keys()), index=0)
with col2:
    right_var = st.selectbox("Right Map Indicator", list(RASTER_URLS.keys()), index=1)

st.markdown(
    f"**Currently Comparing:** <span style='color:#1f77b4'>{left_var}</span> ↔ <span style='color:#2ca02c'>{right_var}</span>",
    unsafe_allow_html=True,
)

# --- Helper to load and classify raster ---
@st.cache_data(show_spinner=False)
def load_and_classify(url, label):
    """Load raster from S3, crop to valid data extent, and apply classification."""
    import rioxarray
    import rasterio
    import numpy as np
    import mapclassify

    # Load masked raster
    da = rioxarray.open_rasterio(url, masked=True).squeeze()

    # 🧭 Find valid pixels and crop raster metadata to match data bounds
    mask = ~np.isnan(da.values)
    if np.any(mask):
        ys, xs = np.where(mask)
        xmin, xmax = da.x.values[xs].min(), da.x.values[xs].max()
        ymin, ymax = da.y.values[ys].min(), da.y.values[ys].max()
        da = da.rio.clip_box(minx=xmin, miny=ymin, maxx=xmax, maxy=ymax)

    # 🪶 Make sure missing data are transparent
    nodata_value = -9999
    da = da.fillna(nodata_value)
    da.rio.write_nodata(nodata_value, inplace=True)
    da = da.where(da != nodata_value)

    # --- Classification ---
    vals = da.values[~np.isnan(da.values)]
    settings = COLOR_SETTINGS.get(
        label, {"palette": ["#f7fbff", "#6baed6", "#08519c"], "classes": 6, "method": "linear"}
    )
    method = settings["method"]
    n_classes = settings["classes"]

    if method == "jenks" and len(np.unique(vals)) >= 3:
        classifier = mapclassify.NaturalBreaks(vals, k=n_classes)
        bins = classifier.bins.tolist()
    elif method == "quantile":
        classifier = mapclassify.Quantiles(vals, k=n_classes)
        bins = classifier.bins.tolist()
    elif method == "manual" and "bins" in settings:
        bins = settings["bins"]
    else:
        bins = np.linspace(np.nanmin(vals), np.nanmax(vals), n_classes + 1).tolist()

    return da, bins, settings["palette"]

# --- Load both rasters ---
with st.spinner("Loading rasters..."):
    left_da, left_bins, left_palette = load_and_classify(RASTER_URLS[left_var], left_var)
    right_da, right_bins, right_palette = load_and_classify(RASTER_URLS[right_var], right_var)

# --- Render split map ---
with st.spinner("Rendering split map..."):
    m = leafmap.Map(center=[37.8, -96], zoom=4, minimap_control=True)

    m.split_map(
        left_da,
        right_da,
        left_args={
            "layer_name": f"{left_var}",
            "colormap": left_palette,
        },
        right_args={
            "layer_name": f"{right_var}",
            "colormap": right_palette,
        },
    )

    # --- Dynamic legends (matches color palettes) ---
    def gradient_html(label, palette, align="left"):
        grad = ", ".join(palette)
        pos = "left: 10px;" if align == "left" else "right: 10px;"
        arrow = "◀ " if align == "left" else " ▶"
        return f"""
        <div style="
            position: fixed;
            bottom: 40px;
            {pos}
            z-index: 9999;
            background-color: rgba(255, 255, 255, 0.9);
            padding: 10px 14px;
            border-radius: 6px;
            box-shadow: 0 0 6px rgba(0,0,0,0.3);
            font-size: 13px;
            line-height: 1.3;
        ">
        <b>{arrow}{label}</b><br>
        <div style="height: 10px; width: 140px;
            background: linear-gradient(to right, {grad});
            border-radius: 3px; margin-top: 5px;"></div>
        <div style="display: flex; justify-content: space-between; font-size: 11px; color:#333;">
        <span>Low</span><span>High</span>
        </div>
        </div>
        """

    m.get_root().html.add_child(Element(gradient_html(left_var, left_palette, align="left")))
    m.get_root().html.add_child(Element(gradient_html(right_var, right_palette, align="right")))

    m.to_streamlit(height=700)