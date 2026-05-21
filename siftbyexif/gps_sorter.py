# Copyright (c) 2026 FireSwordss. Free for non-commercial use.
"""GPS extraction, DBSCAN clustering, and city-based sorting."""

import os, json, math, shutil, sys, time
from collections import defaultdict
from urllib.request import urlopen, Request
from urllib.parse import urlencode

# Load China cities database (works in PyInstaller bundle too)
def _data_path(filename):
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(__file__), filename)

_cities_path = _data_path("cities.json")
_cities_db = []
try:
    with open(_cities_path, "r", encoding="utf-8") as f:
        _cities_db = json.load(f)
except Exception:
    pass


def extract_gps(filepath):
    """Extract GPS coordinates from a file using Pillow.
    Returns (lat, lon) or None.
    """
    from PIL import Image

    try:
        img = Image.open(filepath)
        exif = img.getexif()
        gps = exif.get_ifd(0x8825)
        lat_ref = gps.get(1)
        lat_raw = gps.get(2)
        lon_ref = gps.get(3)
        lon_raw = gps.get(4)
        img.close()
        if lat_raw and lon_raw and lat_ref and lon_ref:
            lat = _gps_to_decimal(lat_raw, lat_ref)
            lon = _gps_to_decimal(lon_raw, lon_ref)
            return lat, lon
    except Exception:
        pass
    return None


def _gps_to_decimal(values, ref):
    if not values or not ref:
        return None
    try:
        d = float(values[0])
        m = float(values[1])
        s = float(values[2])
        dec = d + m / 60.0 + s / 3600.0
        if ref in ('S', 'W'):
            dec = -dec
        return dec
    except (ValueError, TypeError, IndexError):
        return None


def cluster_gps(points, eps_meters=100, min_samples=3):
    """DBSCAN on GPS coordinates. Returns list of cluster labels."""
    import math
    n = len(points)
    UNVISITED, NOISE = -1, -2
    labels = [UNVISITED] * n
    cluster_id = 0

    def neighbors_of(i):
        lat_i, lon_i = points[i]
        result = []
        for j in range(n):
            lat_j, lon_j = points[j]
            dlat = (lat_i - lat_j) * 111320
            dlon = (lon_i - lon_j) * 111320 * math.cos(
                math.radians((lat_i + lat_j) / 2))
            if (dlat * dlat + dlon * dlon) < eps_meters * eps_meters:
                result.append(j)
        return result

    for i in range(n):
        if labels[i] != UNVISITED:
            continue
        neighbors = neighbors_of(i)
        if len(neighbors) < min_samples:
            labels[i] = NOISE
            continue
        labels[i] = cluster_id
        seed = list(neighbors)
        for j in seed:
            if labels[j] == NOISE:
                labels[j] = cluster_id
                continue
            if labels[j] != UNVISITED:
                continue
            labels[j] = cluster_id
            sn = neighbors_of(j)
            if len(sn) >= min_samples:
                seed.extend(sn)
        cluster_id += 1

    return labels


def match_city(lat, lon, max_km=50):
    """Match a coordinate to nearest Chinese city. Returns city name or None."""
    if not _cities_db:
        return None
    best, best_dist = None, float('inf')
    for city in _cities_db:
        dist = _haversine(lat, lon, city["lat"], city["lon"])
        if dist < best_dist:
            best_dist = dist
            best = city["name"]
    return best if best_dist <= max_km else None


def reverse_geocode_online(lat, lon):
    """Reverse geocode via Nominatim. Returns city name or None."""
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"lat": lat, "lon": lon, "format": "json", "accept-language": "zh"}
    query = urlencode(params)
    try:
        req = Request(f"{url}?{query}",
                      headers={"User-Agent": "nef-recovery/1.0"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        addr = data.get('address', {})
        time.sleep(1.1)  # Nominatim rate limit
        return addr.get('city') or addr.get('town') or addr.get('village') or None
    except Exception:
        return None


def _haversine(lat1, lon1, lat2, lon2):
    """Distance in km between two coordinates."""
    import math
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def sort_by_gps(file_list, use_online=False, progress_cb=None):
    """Sort files by GPS into city groups.

    file_list: [(full_path, lat, lon), ...]
    Returns: {city_name: [full_path, ...], None: [full_path, ...]}
      None key = no GPS data
    """
    if not file_list:
        return {}

    # Separate GPS vs no-GPS
    with_gps = [(p, lat, lon) for p, lat, lon in file_list
                if lat is not None and lon is not None]
    without_gps = [p for p, lat, lon in file_list
                   if lat is None or lon is None]

    if not with_gps:
        return {None: without_gps} if without_gps else {}

    # Cluster
    points = [(lat, lon) for _, lat, lon in with_gps]
    labels = cluster_gps(points, eps_meters=100, min_samples=3)

    # Group by cluster
    clusters = defaultdict(list)
    noise = []
    for i, label in enumerate(labels):
        if label >= 0:
            clusters[label].append(with_gps[i])
        else:
            noise.append(with_gps[i])

    if progress_cb:
        progress_cb(0, len(clusters) + (1 if noise else 0))

    # Identify city for each cluster
    result = defaultdict(list)
    for cid, files in enumerate(sorted(clusters.values(),
                                        key=len, reverse=True)):
        lats = [f[1] for f in files]
        lons = [f[2] for f in files]
        med_lat = sorted(lats)[len(lats) // 2]
        med_lon = sorted(lons)[len(lons) // 2]

        # Try coordinate match first
        city = match_city(med_lat, med_lon)
        if not city and use_online:
            city = reverse_geocode_online(med_lat, med_lon)
        if not city:
            city = "其他"

        for fpath, _, _ in files:
            result[city].append(fpath)

        if progress_cb:
            progress_cb(cid + 1, len(clusters))

    # Noise → 其他
    for fpath, _, _ in noise:
        result["其他"].append(fpath)

    # No-GPS
    for fpath in without_gps:
        result[None].append(fpath)

    if progress_cb:
        progress_cb(len(clusters), len(clusters))

    return result


def move_to_city_folders(root_dir, city_groups, parent_name=None):
    """Move files into city-named subfolders.

    city_groups: {city_name: [full_path, ...], None: [full_path, ...]}
    parent_name: if given, create folders under root_dir/parent_name/
    """
    base = os.path.join(root_dir, parent_name) if parent_name else root_dir
    moved = 0
    no_gps_dir = os.path.join(base, "无GPS信息")
    quarantine = os.path.join

    for city, files in city_groups.items():
        if city is None:
            dest_dir = no_gps_dir
        else:
            dest_dir = os.path.join(base, city)

        os.makedirs(dest_dir, exist_ok=True)
        for fpath in files:
            if os.path.dirname(fpath) == dest_dir:
                continue
            dst = os.path.join(dest_dir, os.path.basename(fpath))
            shutil.move(fpath, dst)
            moved += 1

    return moved
