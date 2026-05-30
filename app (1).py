"""
app.py
======
Streamlit Dashboard - E-Waste Collection Route Optimization
Semarang City | Dashboard System for Smart Reverse Logistics
"""

import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from lns import run_lns, Q_MAX, Q_MIN, W_MIN, K_MAX, C_DEP, C_LAB, C_FUEL

# ============================================================
# CONFIG
# ============================================================
st.set_page_config(
    page_title="E-Waste Route Optimizer — Semarang",
    page_icon="♻️",
    layout="wide"
)

VEHICLE_COLORS = ["blue", "green", "red"]
VEHICLE_LABELS = ["Vehicle 1", "Vehicle 2", "Vehicle 3"]

# ============================================================
# LOAD DATA
# ============================================================
@st.cache_data
def load_data():
    dist_matrix = pd.read_csv("data/distance_matrix.csv", index_col=0)
    locations   = pd.read_csv("data/locations.csv")
    return dist_matrix, locations

try:
    dist_matrix, locations = load_data()
    DATA_LOADED = True
except FileNotFoundError:
    DATA_LOADED = False

# ============================================================
# HEADER
# ============================================================
st.title("♻️ E-Waste Collection Route Optimization Dashboard")
st.caption("Semarang City | Powered by Large Neighborhood Search (LNS)")
st.divider()

if not DATA_LOADED:
    st.error(
        "Data files not found. Please ensure `data/distance_matrix.csv` "
        "and `data/locations.csv` are available in the `data/` folder."
    )
    st.stop()

# ============================================================
# SIDEBAR — SYSTEM PARAMETERS
# ============================================================
with st.sidebar:
    st.header("⚙️ System Parameters")

    st.subheader("Vehicle")
    st.markdown(f"""
    - Type: Mitsubishi Canter
    - Max capacity: **{Q_MAX:,} kg**
    - Min load: **{Q_MIN:,} kg**
    - Available fleet: **{K_MAX} units**
    """)

    st.subheader("Cost Components")
    st.markdown(f"""
    - Depreciation: **IDR {C_DEP:,}/vehicle/cycle**
    - Labor: **IDR {C_LAB:,}/vehicle/cycle**
    - Fuel: **IDR {C_FUEL:,}/km**
    """)

    st.subheader("LNS Parameters")
    st.markdown(f"""
    - Min location weight: **{W_MIN} kg**
    - Destroy rate (ρ): **20%**
    - Stopping criterion: **100 iterations without improvement**
    """)

    st.divider()
    st.caption("Research Grant: Dashboard System for Routing Optimization "
               "of E-Waste Collection in Smart Reverse Logistics")

# ============================================================
# SECTION 1 — E-WASTE WEIGHT INPUT
# ============================================================
st.header("📥 E-Waste Weight Input per Location")
st.info(
    f"Enter the estimated e-waste weight (kg) at each collection location. "
    f"Locations with weight **< {W_MIN} kg** will be automatically skipped "
    f"and scheduled for the next collection cycle."
)

# Non-depot locations only
loc_nondepo = locations[locations["is_depot"] == 0].reset_index(drop=True)

# Input grid — 3 columns
weights_input = {}
weights_input[0] = 0  # depot weight = 0

cols_per_row = 3
rows = [loc_nondepo.iloc[i:i+cols_per_row]
        for i in range(0, len(loc_nondepo), cols_per_row)]

for row_data in rows:
    cols = st.columns(cols_per_row)
    for col, (_, loc) in zip(cols, row_data.iterrows()):
        with col:
            w = st.number_input(
                label=f"**{loc['nama']}**",
                min_value=0.0,
                max_value=float(Q_MAX),
                value=0.0,
                step=1.0,
                key=f"weight_{loc['id']}",
                help=f"Location ID: {loc['id']}"
            )
            weights_input[int(loc['id'])] = w

# Input summary metrics
total_input    = sum(v for k, v in weights_input.items() if k != 0)
eligible_count = sum(1 for k, v in weights_input.items()
                     if k != 0 and v >= W_MIN)
skipped_count  = sum(1 for k, v in weights_input.items()
                     if k != 0 and v > 0 and v < W_MIN)

col1, col2, col3 = st.columns(3)
col1.metric("Total Weight Input", f"{total_input:,.0f} kg")
col2.metric("Eligible Locations", f"{eligible_count} locations")
col3.metric("Skipped Locations (< 10 kg)", f"{skipped_count} locations")

st.divider()

# ============================================================
# SECTION 2 — RUN OPTIMIZATION
# ============================================================
st.header("Run Optimization")

run_btn = st.button(
    "▶ Run LNS Optimization",
    type="primary",
    use_container_width=True
)

if run_btn:
    with st.spinner("Running LNS optimization... please wait"):
        result = run_lns(
            weights=weights_input,
            dist_matrix_df=dist_matrix
        )

    # ── NO DISPATCH ──
    if not result['dispatch']:
        st.warning(f"⚠️ {result['message']}")
        if result['skipped']:
            st.write("**Skipped locations:**",
                     [locations.loc[locations['id'] == i, 'nama'].values[0]
                      for i in result['skipped']])
        st.stop()

    # ── DISPATCH ──
    st.success(
        f"✅ Optimization completed in **{result['iterations']} iterations**. "
        f"**{result['k_star']} vehicle(s)** active for this collection cycle."
    )

    # ============================================================
    # SECTION 3 — COST SUMMARY
    # ============================================================
    st.header("💰 Cost Summary")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Cost (TC)",
                f"IDR {result['tc']:,}")
    col2.metric("Fixed Cost (FC)",
                f"IDR {result['fc']:,}",
                help="Depreciation + Labor")
    col3.metric("Variable Cost (VC)",
                f"IDR {result['vc']:,}",
                help="Fuel cost")
    col4.metric("Total Distance",
                f"{result['total_dist']:,.2f} km")

    # LNS vs Initial Solution comparison
    st.subheader("📊 LNS vs Initial Solution (Greedy Nearest Neighbor)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Initial Distance",
              f"{result['dist_initial']:,.2f} km")
    c2.metric("LNS Distance",
              f"{result['total_dist']:,.2f} km",
              delta=f"-{result['improvement_dist']}%",
              delta_color="inverse")
    c3.metric("Initial Cost",
              f"IDR {result['tc_initial']:,}")
    c4.metric("LNS Cost",
              f"IDR {result['tc']:,}",
              delta=f"-{result['improvement_tc']}%",
              delta_color="inverse")

    # Per-vehicle breakdown table
    st.subheader("Breakdown per Vehicle")
    breakdown_data = []
    fc_per_vehicle = (C_DEP + C_LAB)

    for k in range(result['k_star']):
        vc_k = C_FUEL * result['dist_per_route'][k]
        breakdown_data.append({
            "Vehicle"        : VEHICLE_LABELS[k],
            "Distance (km)"  : f"{result['dist_per_route'][k]:,.2f}",
            "Load (kg)"      : f"{result['load_per_route'][k]:,.0f}",
            "Fixed Cost"     : f"IDR {fc_per_vehicle:,}",
            "Variable Cost"  : f"IDR {round(vc_k):,}",
            "Total"          : f"IDR {round(fc_per_vehicle + vc_k):,}"
        })

    st.dataframe(
        pd.DataFrame(breakdown_data),
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # ============================================================
    # SECTION 4 — OPTIMAL ROUTES MAP
    # ============================================================
    st.header("🗺️ Optimal Routes")

    center_lat = locations['lat'].mean()
    center_lon = locations['lon'].mean()
    peta = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles="CartoDB positron"
    )

    # Depot marker
    depot = locations[locations['is_depot'] == 1].iloc[0]
    folium.Marker(
        location=[depot['lat'], depot['lon']],
        popup="<b>DEPOT: TPA Jatibarang</b>",
        tooltip="DEPOT: TPA Jatibarang",
        icon=folium.Icon(color='black', icon='home', prefix='fa')
    ).add_to(peta)

    # Route polylines and markers per vehicle
    for k, route in enumerate(result['routes']):
        color = VEHICLE_COLORS[k]
        label = VEHICLE_LABELS[k]

        route_coords = []
        for node in route:
            loc_row = locations[locations['id'] == node].iloc[0]
            route_coords.append([loc_row['lat'], loc_row['lon']])

        folium.PolyLine(
            locations=route_coords,
            color=color,
            weight=3,
            opacity=0.8,
            tooltip=label
        ).add_to(peta)

        for stop_num, node in enumerate(route):
            if node == 0:
                continue
            loc_row = locations[locations['id'] == node].iloc[0]
            folium.CircleMarker(
                location=[loc_row['lat'], loc_row['lon']],
                radius=8,
                color=color,
                fill=True,
                fill_opacity=0.9,
                popup=(
                    f"<b>[{label}] Stop {stop_num}</b><br>"
                    f"{loc_row['nama']}<br>"
                    f"Weight: {weights_input[node]:,.0f} kg"
                ),
                tooltip=f"[{label}] {loc_row['nama']}"
            ).add_to(peta)

    st_folium(peta, width=None, height=500, returned_objects=[])

    # ============================================================
    # SECTION 5 — ROUTE DETAILS
    # ============================================================
    st.subheader("Visit Sequence Detail")

    for k, route in enumerate(result['routes']):
        label = VEHICLE_LABELS[k]

        with st.expander(
            f"🚛 {label} — "
            f"{result['dist_per_route'][k]:,.2f} km | "
            f"{result['load_per_route'][k]:,.0f} kg",
            expanded=True
        ):
            route_detail = []
            for stop_num, node in enumerate(route):
                loc_row = locations[locations['id'] == node].iloc[0]
                route_detail.append({
                    "Stop"       : stop_num,
                    "Location"   : "🏭 DEPOT (TPA Jatibarang)"
                                   if node == 0
                                   else loc_row['nama'],
                    "Weight (kg)": "—" if node == 0
                                   else f"{weights_input[node]:,.0f}"
                })

            st.dataframe(
                pd.DataFrame(route_detail),
                use_container_width=True,
                hide_index=True
            )

    # ============================================================
    # SECTION 6 — SKIPPED LOCATIONS
    # ============================================================
    if result['skipped']:
        st.divider()
        st.subheader("⏭️ Skipped Locations (Scheduled for Next Cycle)")
        skip_data = []
        for node in result['skipped']:
            loc_row = locations[locations['id'] == node].iloc[0]
            skip_data.append({
                "Location"   : loc_row['nama'],
                "Weight (kg)": weights_input.get(node, 0),
                "Reason"     : f"Weight < {W_MIN} kg — deferred to next collection cycle"
            })
        st.dataframe(
            pd.DataFrame(skip_data),
            use_container_width=True,
            hide_index=True
        )
