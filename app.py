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
VEHICLE_LABELS = ["Kendaraan 1", "Kendaraan 2", "Kendaraan 3"]

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
st.title("♻️ Dashboard Optimasi Rute Pengangkutan E-Waste")
st.caption("Kota Semarang | Berbasis Large Neighborhood Search (LNS)")
st.divider()

if not DATA_LOADED:
    st.error(
        "File data tidak ditemukan. Pastikan `data/distance_matrix.csv` "
        "dan `data/locations.csv` sudah ada di folder `data/`."
    )
    st.stop()

# ============================================================
# SIDEBAR — INFO PARAMETER
# ============================================================
with st.sidebar:
    st.header("⚙️ Parameter Sistem")

    st.subheader("Kendaraan")
    st.markdown(f"""
    - Jenis: Mitsubishi Canter
    - Kapasitas maks: **{Q_MAX:,} kg**
    - Minimum muatan: **{Q_MIN:,} kg**
    - Armada tersedia: **{K_MAX} unit**
    """)

    st.subheader("Komponen Biaya")
    st.markdown(f"""
    - Depresiasi: **Rp {C_DEP:,}/kendaraan/siklus**
    - Tenaga kerja: **Rp {C_LAB:,}/kendaraan/siklus**
    - BBM: **Rp {C_FUEL:,}/km**
    """)

    st.subheader("Parameter LNS")
    st.markdown(f"""
    - Minimum bobot lokasi: **{W_MIN} kg**
    - Destroy rate (ρ): **20%**
    - Stopping criterion: **100 iterasi tanpa improvement**
    """)

    st.divider()
    st.caption("Hibah: Dashboard System for Routing Optimization "
               "of E-Waste Collection in Smart Reverse Logistics")

# ============================================================
# BAGIAN 1 — INPUT BOBOT E-WASTE
# ============================================================
st.header("📥 Input Bobot E-Waste per Lokasi")
st.info(
    f"Masukkan estimasi bobot e-waste (kg) di setiap lokasi. "
    f"Lokasi dengan bobot **< {W_MIN} kg** akan otomatis di-skip "
    f"dan dijadwalkan ke siklus berikutnya."
)

# Ambil hanya lokasi non-depot
loc_nondepo = locations[locations["is_depot"] == 0].reset_index(drop=True)

# Buat form input dalam grid 3 kolom
weights_input = {}
weights_input[0] = 0  # depot, bobot 0

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
                help=f"ID: {loc['id']}"
            )
            weights_input[int(loc['id'])] = w

# Summary input
total_input    = sum(v for k, v in weights_input.items() if k != 0)
eligible_count = sum(1 for k, v in weights_input.items()
                     if k != 0 and v >= W_MIN)
skipped_count  = sum(1 for k, v in weights_input.items()
                     if k != 0 and v > 0 and v < W_MIN)

col1, col2, col3 = st.columns(3)
col1.metric("Total Bobot Input", f"{total_input:,.0f} kg")
col2.metric("Lokasi Eligible", f"{eligible_count} lokasi")
col3.metric("Lokasi Di-skip (< 10 kg)", f"{skipped_count} lokasi")

st.divider()

# ============================================================
# BAGIAN 2 — RUN OPTIMASI
# ============================================================
st.header("🚀 Jalankan Optimasi")

run_btn = st.button(
    "▶ Run Optimasi LNS",
    type="primary",
    use_container_width=True
)

if run_btn:
    with st.spinner("Menjalankan LNS... harap tunggu"):
        result = run_lns(
            weights=weights_input,
            dist_matrix_df=dist_matrix
        )

    # ── TIDAK ADA DISPATCH ──
    if not result['dispatch']:
        st.warning(f"⚠️ {result['message']}")
        if result['skipped']:
            st.write("**Lokasi yang di-skip:**",
                     [locations.loc[locations['id'] == i, 'nama'].values[0]
                      for i in result['skipped']])
        st.stop()

    # ── ADA DISPATCH ──
    st.success(
        f"✅ Optimasi selesai dalam **{result['iterations']} iterasi**. "
        f"**{result['k_star']} kendaraan** aktif untuk siklus ini."
    )

    # ============================================================
    # BAGIAN 3 — HASIL: RINGKASAN BIAYA
    # ============================================================
    st.header("💰 Ringkasan Biaya")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Cost (TC)",
                f"Rp {result['tc']:,}")
    col2.metric("Fixed Cost (FC)",
                f"Rp {result['fc']:,}",
                help="Depresiasi + Tenaga Kerja")
    col3.metric("Variable Cost (VC)",
                f"Rp {result['vc']:,}",
                help="Biaya BBM")
    col4.metric("Total Jarak",
                f"{result['total_dist']:,.2f} km")

    # Tabel breakdown per kendaraan
    st.subheader("Breakdown per Kendaraan")
    breakdown_data = []
    fc_per_vehicle = (C_DEP + C_LAB)

    for k in range(result['k_star']):
        vc_k = C_FUEL * result['dist_per_route'][k]
        breakdown_data.append({
            "Kendaraan"     : VEHICLE_LABELS[k],
            "Jarak (km)"    : f"{result['dist_per_route'][k]:,.2f}",
            "Muatan (kg)"   : f"{result['load_per_route'][k]:,.0f}",
            "Fixed Cost"    : f"Rp {fc_per_vehicle:,}",
            "Variable Cost" : f"Rp {round(vc_k):,}",
            "Total"         : f"Rp {round(fc_per_vehicle + vc_k):,}"
        })

    st.dataframe(
        pd.DataFrame(breakdown_data),
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # ============================================================
    # BAGIAN 4 — HASIL: RUTE OPTIMAL
    # ============================================================
    st.header("🗺️ Rute Optimal")

    # Buat peta Folium
    center_lat = locations['lat'].mean()
    center_lon = locations['lon'].mean()
    peta = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles="CartoDB positron"
    )

    # Plot depot
    depot = locations[locations['is_depot'] == 1].iloc[0]
    folium.Marker(
        location=[depot['lat'], depot['lon']],
        popup="<b>DEPOT: TPA Jatibarang</b>",
        tooltip="DEPOT: TPA Jatibarang",
        icon=folium.Icon(color='black', icon='home', prefix='fa')
    ).add_to(peta)

    # Plot rute tiap kendaraan
    for k, route in enumerate(result['routes']):
        color = VEHICLE_COLORS[k]
        label = VEHICLE_LABELS[k]

        # Ambil koordinat rute
        route_coords = []
        for node in route:
            loc_row = locations[locations['id'] == node].iloc[0]
            route_coords.append([loc_row['lat'], loc_row['lon']])

        # Garis rute
        folium.PolyLine(
            locations=route_coords,
            color=color,
            weight=3,
            opacity=0.8,
            tooltip=label
        ).add_to(peta)

        # Marker tiap lokasi (non-depot)
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
                    f"Bobot: {weights_input[node]:,.0f} kg"
                ),
                tooltip=f"[{label}] {loc_row['nama']}"
            ).add_to(peta)

    # Render peta
    st_folium(peta, width=None, height=500, returned_objects=[])

    # ============================================================
    # BAGIAN 5 — DETAIL RUTE PER KENDARAAN
    # ============================================================
    st.subheader("Detail Urutan Kunjungan")

    for k, route in enumerate(result['routes']):
        color = VEHICLE_COLORS[k]
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
                    "Urutan" : stop_num,
                    "Lokasi" : "🏭 DEPOT (TPA Jatibarang)"
                               if node == 0
                               else loc_row['nama'],
                    "Bobot (kg)" : "—" if node == 0
                                   else f"{weights_input[node]:,.0f}"
                })

            st.dataframe(
                pd.DataFrame(route_detail),
                use_container_width=True,
                hide_index=True
            )

    # ============================================================
    # BAGIAN 6 — LOKASI YANG DI-SKIP
    # ============================================================
    if result['skipped']:
        st.divider()
        st.subheader("⏭️ Lokasi Di-skip (Dijadwalkan Siklus Berikutnya)")
        skip_data = []
        for node in result['skipped']:
            loc_row = locations[locations['id'] == node].iloc[0]
            skip_data.append({
                "Lokasi"        : loc_row['nama'],
                "Bobot (kg)"    : weights_input.get(node, 0),
                "Keterangan"    : f"Bobot < {W_MIN} kg, ditunda ke siklus berikutnya"
            })
        st.dataframe(
            pd.DataFrame(skip_data),
            use_container_width=True,
            hide_index=True
        )
