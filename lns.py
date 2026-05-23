"""
lns.py
======
Backend Large Neighborhood Search (LNS) untuk
E-Waste Collection Route Optimization - Semarang City

Model : Capacitated Vehicle Routing Problem (CVRP)
Depot : TPA Jatibarang (node 0)
Fleet : K* kendaraan aktif (ditentukan otomatis dari total bobot)
OF    : min TC = FC + VC
"""

import random
import copy
import numpy as np
import pandas as pd

# ============================================================
# PARAMETER BIAYA (sesuai diskusi)
# ============================================================
C_DEP   = 82_192      # Rp/kendaraan/siklus (depresiasi Canter)
C_LAB   = 284_746     # Rp/kendaraan/siklus (supir + kru, UMR 2026)
C_FUEL  = 680         # Rp/km (solar Rp6.800 / 10 km per liter)

# PARAMETER KAPASITAS
Q_MAX   = 2_000       # kg, kapasitas maksimal per kendaraan
Q_MIN   = 1_000       # kg, minimum load per kendaraan
W_MIN   = 10          # kg, minimum bobot lokasi agar eligible
K_MAX   = 3           # jumlah armada maksimal

# PARAMETER LNS
P_WORST = 0.6         # probabilitas pilih Worst Removal
P_RAND  = 0.4         # probabilitas pilih Random Removal
RHO     = 0.2         # proporsi node yang di-remove tiap iterasi (20%)
N_STAG  = 100         # stopping: berhenti jika tidak ada improvement
                      # dalam N_STAG iterasi berturut-turut


# ============================================================
# PHASE 0: PRE-PROCESSING
# ============================================================

def preprocess(weights: dict) -> tuple:
    """
    Tentukan lokasi eligible, total bobot, dan K*.

    Parameters
    ----------
    weights : dict {node_id: bobot_kg}
              node 0 = depot, tidak perlu diisi

    Returns
    -------
    eligible  : list node id yang eligible (bobot >= W_MIN)
    skipped   : list node id yang di-skip (bobot < W_MIN)
    w_total   : total bobot eligible (kg)
    k_star    : jumlah kendaraan aktif
    dispatch  : bool, True jika ada pengangkutan
    """
    eligible = []
    skipped  = []

    for node_id, w in weights.items():
        if node_id == 0:
            continue  # depot diabaikan
        if w >= W_MIN:
            eligible.append(node_id)
        else:
            skipped.append(node_id)

    w_total = sum(weights[i] for i in eligible)

    # Tentukan K*
    if w_total < Q_MIN:
        return eligible, skipped, w_total, 0, False

    if w_total <= 2_000:
        k_star = 1
    elif w_total <= 4_000:
        k_star = 2
    else:
        k_star = 3

    return eligible, skipped, w_total, k_star, True


# ============================================================
# PERHITUNGAN COST
# ============================================================

def route_distance(route: list, dist_matrix: np.ndarray) -> float:
    """Total jarak satu rute (km). Rute sudah include depot di awal & akhir."""
    return sum(dist_matrix[route[i]][route[i+1]]
               for i in range(len(route) - 1))


def total_cost(routes: list, dist_matrix: np.ndarray, k_star: int) -> float:
    """
    Hitung total cost TC = FC + VC.

    FC = (C_DEP + C_LAB) * K*
    VC = C_FUEL * total jarak semua rute
    """
    fc = (C_DEP + C_LAB) * k_star
    total_dist = sum(route_distance(r, dist_matrix) for r in routes)
    vc = C_FUEL * total_dist
    return fc + vc, fc, vc, total_dist


def route_load(route: list, weights: dict) -> float:
    """Total bobot muatan satu rute (kg). Skip depot (node 0)."""
    return sum(weights[n] for n in route if n != 0)


# ============================================================
# PHASE 1: INITIAL SOLUTION (Greedy Nearest Neighbor)
# ============================================================

def greedy_nearest_neighbor(eligible: list,
                             weights: dict,
                             dist_matrix: np.ndarray,
                             k_star: int) -> list:
    """
    Buat solusi awal dengan Greedy Nearest Neighbor.
    Setiap kendaraan berangkat dari depot (0), pilih
    lokasi terdekat yang belum dikunjungi dan masih
    muat di kapasitas, sampai tidak ada lagi.
    Semua rute diakhiri kembali ke depot (0).
    """
    unvisited = eligible.copy()
    routes    = []

    for k in range(k_star):
        route        = [0]   # mulai dari depot
        current_node = 0
        load         = 0

        while unvisited:
            # Cari node terdekat yang masih muat
            best_node = None
            best_dist = float('inf')

            for node in unvisited:
                if load + weights[node] <= Q_MAX:
                    d = dist_matrix[current_node][node]
                    if d < best_dist:
                        best_dist = d
                        best_node = node

            if best_node is None:
                break  # kendaraan penuh atau tidak ada yang muat

            route.append(best_node)
            load        += weights[best_node]
            current_node = best_node
            unvisited.remove(best_node)

        route.append(0)  # kembali ke depot
        routes.append(route)

    # Kalau masih ada unvisited (edge case), paksa masukkan ke rute terakhir
    # ini seharusnya tidak terjadi kalau K* dihitung dengan benar
    if unvisited:
        for node in unvisited:
            routes[-1].insert(-1, node)

    return routes


# ============================================================
# PHASE 2: LNS — DESTROY OPERATORS
# ============================================================

def worst_removal(routes: list,
                  weights: dict,
                  dist_matrix: np.ndarray,
                  n_remove: int) -> tuple:
    """
    Worst Removal: hapus node dengan removal cost tertinggi.
    Removal cost = selisih TC sebelum dan sesudah node dihapus.
    """
    routes      = copy.deepcopy(routes)
    removed     = []

    for _ in range(n_remove):
        best_node    = None
        best_saving  = -float('inf')
        best_r_idx   = None
        best_pos     = None

        for r_idx, route in enumerate(routes):
            # Cari node non-depot di rute ini
            for pos in range(1, len(route) - 1):
                node = route[pos]

                # Hitung saving kalau node ini dihapus
                prev_node = route[pos - 1]
                next_node = route[pos + 1]

                cost_before = (dist_matrix[prev_node][node] +
                               dist_matrix[node][next_node])
                cost_after  =  dist_matrix[prev_node][next_node]
                saving      =  cost_before - cost_after

                if saving > best_saving:
                    best_saving = saving
                    best_node   = node
                    best_r_idx  = r_idx
                    best_pos    = pos

        if best_node is not None:
            routes[best_r_idx].pop(best_pos)
            removed.append(best_node)

    return routes, removed


def random_removal(routes: list,
                   n_remove: int) -> tuple:
    """
    Random Removal: hapus node secara acak dari semua rute.
    """
    routes  = copy.deepcopy(routes)
    removed = []

    # Kumpulkan semua node non-depot
    all_nodes = [(r_idx, pos)
                 for r_idx, route in enumerate(routes)
                 for pos in range(1, len(route) - 1)]

    n_remove = min(n_remove, len(all_nodes))
    selected = random.sample(all_nodes, n_remove)

    # Hapus dari belakang agar index tidak geser
    selected_sorted = sorted(selected, key=lambda x: (x[0], -x[1]))
    for r_idx, pos in selected_sorted:
        removed.append(routes[r_idx][pos])
        routes[r_idx].pop(pos)

    return routes, removed


# ============================================================
# PHASE 2: LNS — REPAIR OPERATOR (Greedy Best Insertion)
# ============================================================

def greedy_best_insertion(routes: list,
                           removed: list,
                           weights: dict,
                           dist_matrix: np.ndarray) -> list:
    """
    Greedy Best Insertion: sisipkan setiap node yang dihapus
    ke posisi dengan insertion cost paling rendah,
    dengan tetap memperhatikan kapasitas kendaraan.
    """
    routes  = copy.deepcopy(routes)

    for node in removed:
        best_cost    = float('inf')
        best_r_idx   = None
        best_pos     = None

        for r_idx, route in enumerate(routes):
            # Cek kapasitas dulu
            if route_load(route, weights) + weights[node] > Q_MAX:
                continue

            # Coba semua posisi insertion (antara dua node)
            for pos in range(1, len(route)):
                prev_node = route[pos - 1]
                next_node = route[pos]

                # Delta cost kalau node disisipkan di sini
                delta = (dist_matrix[prev_node][node] +
                         dist_matrix[node][next_node] -
                         dist_matrix[prev_node][next_node])

                if delta < best_cost:
                    best_cost  = delta
                    best_r_idx = r_idx
                    best_pos   = pos

        if best_r_idx is not None:
            routes[best_r_idx].insert(best_pos, node)
        else:
            # Tidak ada posisi yang feasible → paksa ke rute dengan load paling kecil
            # (ini safety net, seharusnya jarang terjadi)
            loads    = [route_load(r, weights) for r in routes]
            min_r    = loads.index(min(loads))
            routes[min_r].insert(-1, node)

    return routes


# ============================================================
# MAIN LNS ALGORITHM
# ============================================================

def run_lns(weights: dict,
            dist_matrix_df: pd.DataFrame,
            n_stag: int = N_STAG,
            rho: float = RHO,
            p_worst: float = P_WORST,
            seed: int = 42) -> dict:
    """
    Jalankan LNS untuk e-waste CVRP.

    Parameters
    ----------
    weights        : dict {node_id (int): bobot_kg (float)}
                     node 0 = depot TPA Jatibarang
    dist_matrix_df : pd.DataFrame, distance matrix (km)
    n_stag         : stopping criterion (iterasi tanpa improvement)
    rho            : proporsi node yang di-remove (0.0 - 1.0)
    p_worst        : probabilitas Worst Removal (sisanya Random)
    seed           : random seed untuk reproducibility

    Returns
    -------
    dict dengan keys:
        'routes'      : list of routes (list of node ids)
        'tc'          : total cost (Rp)
        'fc'          : fixed cost (Rp)
        'vc'          : variable cost (Rp)
        'total_dist'  : total jarak (km)
        'dist_per_route': jarak per rute (km)
        'load_per_route': muatan per rute (kg)
        'k_star'      : jumlah kendaraan aktif
        'eligible'    : list node eligible
        'skipped'     : list node di-skip
        'w_total'     : total bobot eligible (kg)
        'dispatch'    : bool
        'iterations'  : jumlah iterasi yang dijalankan
    """
    random.seed(seed)
    np.random.seed(seed)

    # Konversi dist_matrix ke numpy array
    dist_matrix = dist_matrix_df.values.astype(float)

    # Phase 0: Pre-processing
    eligible, skipped, w_total, k_star, dispatch = preprocess(weights)

    if not dispatch:
        return {
            'dispatch'  : False,
            'w_total'   : w_total,
            'skipped'   : skipped,
            'eligible'  : eligible,
            'k_star'    : 0,
            'message'   : f"Total bobot eligible ({w_total:.0f} kg) "
                          f"< minimum dispatch ({Q_MIN} kg). "
                          f"Pengangkutan ditunda."
        }

    # Phase 1: Initial solution
    routes_current = greedy_nearest_neighbor(
        eligible, weights, dist_matrix, k_star
    )

    tc_current, fc, vc, total_dist = total_cost(
        routes_current, dist_matrix, k_star
    )

    routes_best = copy.deepcopy(routes_current)
    tc_best     = tc_current

    # Phase 2: LNS iteration
    no_improve = 0
    iteration  = 0
    n_remove   = max(1, int(len(eligible) * rho))

    while no_improve < n_stag:
        iteration += 1

        # --- DESTROY ---
        if random.random() < p_worst:
            routes_new, removed = worst_removal(
                routes_current, weights, dist_matrix, n_remove
            )
        else:
            routes_new, removed = random_removal(
                routes_current, n_remove
            )

        # --- REPAIR ---
        routes_new = greedy_best_insertion(
            routes_new, removed, weights, dist_matrix
        )

        # --- EVALUATE ---
        tc_new, _, _, _ = total_cost(routes_new, dist_matrix, k_star)

        # --- ACCEPTANCE ---
        if tc_new < tc_best:
            routes_best = copy.deepcopy(routes_new)
            tc_best     = tc_new
            no_improve  = 0
        else:
            no_improve += 1

        routes_current = copy.deepcopy(routes_new)

    # Phase 3: Hitung detail output solusi terbaik
    tc_final, fc_final, vc_final, dist_final = total_cost(
        routes_best, dist_matrix, k_star
    )

    dist_per_route = [
        round(route_distance(r, dist_matrix), 3)
        for r in routes_best
    ]
    load_per_route = [
        round(route_load(r, weights), 1)
        for r in routes_best
    ]

    return {
        'dispatch'       : True,
        'routes'         : routes_best,
        'tc'             : round(tc_final),
        'fc'             : round(fc_final),
        'vc'             : round(vc_final),
        'total_dist'     : round(dist_final, 3),
        'dist_per_route' : dist_per_route,
        'load_per_route' : load_per_route,
        'k_star'         : k_star,
        'eligible'       : eligible,
        'skipped'        : skipped,
        'w_total'        : round(w_total, 1),
        'iterations'     : iteration,
        'dispatch'       : dispatch,
    }
