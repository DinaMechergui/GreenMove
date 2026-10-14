"""
Similarité de trajectoires (MobilityMatch).
Compare deux tracés [lat, lon] avec :
  - distance de Fréchet (discrete Fréchet)
  - distance de Hausdorff
  - % de chevauchement du parcours (buffer d'intersection)

Deux chemins d'exécution :
  1. PostGIS (ST_FrechetDistance / ST_HausdorffDistance / ST_Buffer) automatiquement
     utilisé si la base active est PostgreSQL avec l'extension PostGIS.
  2. Fallback Python/Shapely pour SQLite ou si PostGIS est indisponible.
"""
import json
import logging
import math
from functools import lru_cache
from typing import Dict, List, Optional, Sequence

from django.db import connection

logger = logging.getLogger(__name__)

OVERLAP_BUFFER_M = 30.0  # tolérance de chevauchement en mètres


# -----------------------------------------
# Utilitaires géométriques
# -----------------------------------------

def _to_local_meters(coords: Sequence[Sequence[float]], origin: Optional[Sequence[float]] = None) -> List[tuple]:
    """
    Projection locale approximée (lat/lon → x/y en mètres) autour d'un point de référence.
    Précision suffisante à l'échelle d'une ville (Grand Tunis).
    """
    if not coords:
        return []
    lat0, lon0 = origin if origin else (coords[0][0], coords[0][1])
    m_lat = 111320.0
    m_lon = 111320.0 * math.cos(math.radians(lat0))
    return [((c[1] - lon0) * m_lon, (c[0] - lat0) * m_lat) for c in coords]


def _clean_coords(coords: Sequence[Sequence[float]]) -> List[tuple]:
    """Valide et normalise une polyline : [(lat, lon), ...]."""
    clean = []
    for c in coords or []:
        try:
            lat, lon = float(c[0]), float(c[1])
        except (TypeError, ValueError, IndexError):
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            clean.append((lat, lon))
    return clean


def _discrete_frechet_m(p: List[tuple], q: List[tuple]) -> float:
    """Distance de Fréchet discrète (DP O(n·m)) en mètres sur coordonnées locales."""
    n, m = len(p), len(q)
    if n == 0 or m == 0:
        return 0.0
    ca = [[0.0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            d = math.hypot(p[i][0] - q[j][0], p[i][1] - q[j][1])
            if i == 0 and j == 0:
                ca[i][j] = d
            elif i == 0:
                ca[i][j] = max(ca[i][j - 1], d)
            elif j == 0:
                ca[i][j] = max(ca[i - 1][j], d)
            else:
                ca[i][j] = max(min(ca[i - 1][j], ca[i][j - 1], ca[i - 1][j - 1]), d)
    return ca[n - 1][m - 1]


def _directed_hausdorff_m(p: List[tuple], q: List[tuple]) -> float:
    """Distance de Hausdorff dirigée max(d(p, q)) en mètres."""
    if not p or not q:
        return 0.0
    best = 0.0
    for px, py in p:
        d_min = min(math.hypot(px - qx, py - qy) for qx, qy in q)
        best = max(best, d_min)
    return best


def _hausdorff_m(p: List[tuple], q: List[tuple]) -> float:
    return max(_directed_hausdorff_m(p, q), _directed_hausdorff_m(q, p))


def _overlap_pct_m(p: List[tuple], q: List[tuple], buffer_m: float = OVERLAP_BUFFER_M) -> float:
    """
    % de chevauchement : longueur de l'intersection des deux tracés bufferisés
    divisée par la longueur du tracé de référence (p).
    """
    try:
        from shapely.geometry import LineString
    except ImportError:  # pragma: no cover
        return 0.0
    if len(p) < 2:
        return 0.0
    try:
        line_p = LineString(p)
        if len(q) < 2:
            # Point unique : chevauchement si contenu dans le buffer du tracé p
            from shapely.geometry import Point
            line_q = Point(q[0]) if q else None
            if line_q is None:
                return 0.0
            return 100.0 if line_p.buffer(buffer_m).contains(line_q) else 0.0
        line_q = LineString(q)
        if line_p.length == 0:
            return 0.0
        # Longueur du cœur commun : intersection de p avec le buffer de q,
        # ramenée à la longueur du tracé p.
        shared = line_p.intersection(line_q.buffer(buffer_m))
        if shared.is_empty:
            return 0.0
        return round(min(100.0, (shared.length / line_p.length) * 100.0), 1)
    except Exception as exc:  # pragma: no cover
        logger.warning("Calcul de chevauchement impossible: %s", exc)
        return 0.0


# -----------------------------------------
# Chemin PostGIS
# -----------------------------------------

@lru_cache(maxsize=1)
def postgis_available() -> bool:
    """Détecte (mise en cache) si PostGIS est réellement utilisable."""
    if connection.vendor != 'postgresql':
        return False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT PostGIS_Version()")
            row = cursor.fetchone()
            return bool(row and row[0])
    except Exception as exc:
        logger.info("PostGIS indisponible (%s) — fallback Python/Shapely.", exc)
        return False


def _wkt_linestring(coords: Sequence[Sequence[float]]) -> str:
    pts = ", ".join(f"{lon} {lat}" for lat, lon in coords)
    return f"LINESTRING({pts})"


def _postgis_similarity(coords_a, coords_b) -> Optional[Dict[str, float]]:
    """Calcule la similarité via SQL PostGIS. Retourne None si indisponible."""
    if not postgis_available() or len(coords_a) < 2 or len(coords_b) < 2:
        return None
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    ST_FrechetDistance(ST_GeomFromText(%s, 4326), ST_GeomFromText(%s, 4326)) AS frechet_deg,
                    ST_HausdorffDistance(ST_GeomFromText(%s, 4326), ST_GeomFromText(%s, 4326)) AS hausdorff_deg,
                    CASE WHEN ST_Length(ST_Transform(ST_GeomFromText(%s, 4326), 32632)) = 0 THEN 0 ELSE
                        GREATEST(0, LEAST(100,
                            100.0 * ST_Length(ST_Intersection(
                                ST_Buffer(ST_Transform(ST_GeomFromText(%s, 4326), 32632), %s),
                                ST_Buffer(ST_Transform(ST_GeomFromText(%s, 4326), 32632), %s)
                            )) / ST_Length(ST_Transform(ST_GeomFromText(%s, 4326), 32632))
                        ))
                    END AS overlap_pct
                """,
                [
                    _wkt_linestring(coords_a), _wkt_linestring(coords_b),
                    _wkt_linestring(coords_a), _wkt_linestring(coords_b),
                    _wkt_linestring(coords_a),
                    _wkt_linestring(coords_a), OVERLAP_BUFFER_M,
                    _wkt_linestring(coords_b), OVERLAP_BUFFER_M,
                    _wkt_linestring(coords_a),
                ],
            )
            row = cursor.fetchone()
            if not row or row[0] is None:
                return None
            # ST_FrechetDistance / ST_HausdorffDistance renvoient des degrés → conversion locale
            ref = coords_a[0]
            m_per_deg_lat = 111320.0
            m_per_deg_lon = 111320.0 * math.cos(math.radians(ref[0]))
            avg_m_per_deg = (m_per_deg_lat + m_per_deg_lon) / 2.0
            return {
                "frechet_m": round(float(row[0]) * avg_m_per_deg, 1),
                "hausdorff_m": round(float(row[1]) * avg_m_per_deg, 1),
                "overlap_pct": round(float(row[2] or 0.0), 1),
                "backend": "postgis",
            }
    except Exception as exc:
        logger.warning("Échec du calcul PostGIS, fallback Python: %s", exc)
        return None


# -----------------------------------------
# API publique
# -----------------------------------------

def trajectory_similarity(coords_a: Sequence[Sequence[float]],
                          coords_b: Sequence[Sequence[float]]) -> Dict:
    """
    Compare deux trajectoires.

    Returns:
        {
          "frechet_m": float,      # distance de Fréchet (m)
          "hausdorff_m": float,    # distance de Hausdorff (m)
          "overlap_pct": float,    # % de chevauchement du parcours
          "similarity_pct": float, # score 0-100 combiné
          "backend": "postgis" | "python",
        }
    """
    a = _clean_coords(coords_a)
    b = _clean_coords(coords_b)

    if len(a) < 2 and len(b) >= 2:
        a = [a[0], b[-1]] if a else b[:2]
    if len(b) < 2 and len(a) >= 2:
        b = [b[0], a[-1]] if b else a[:2]
    if len(a) < 2 or len(b) < 2:
        return {
            "frechet_m": 0.0,
            "hausdorff_m": 0.0,
            "overlap_pct": 0.0,
            "similarity_pct": 0.0,
            "backend": "python",
        }

    result = _postgis_similarity(a, b)
    if result is None:
        # ---- Fallback Python / Shapely ----
        origin = a[0]
        p = _to_local_meters(a, origin)
        q = _to_local_meters(b, origin)
        # alignement : on translate q pour superposer les départs si très proches
        result = {
            "frechet_m": round(_discrete_frechet_m(p, q), 1),
            "hausdorff_m": round(_hausdorff_m(p, q), 1),
            "overlap_pct": _overlap_pct_m(p, q),
            "backend": "python",
        }

    # Score combiné : 60% chevauchement + 40% précision de Fréchet
    # (Fréchet = 100% si < 50 m, = 0% si > 1500 m)
    frechet = result["frechet_m"]
    frechet_score = max(0.0, 1.0 - (frechet / 1500.0)) * 100.0
    result["similarity_pct"] = round(
        max(0.0, min(100.0, result["overlap_pct"] * 0.6 + frechet_score * 0.4)), 1
    )
    return result


def ride_similarity(ride_a, ride_b) -> Dict:
    """Similarité entre deux objets Ride (utilise leur polyline, sinon extrémités)."""
    def _coords(ride):
        poly = ride.polyline_coords
        if len(poly) >= 2:
            return poly
        return [(ride.origin_lat, ride.origin_lon), (ride.destination_lat, ride.destination_lon)]

    return trajectory_similarity(_coords(ride_a), _coords(ride_b))


def load_polyline(raw: str) -> List[tuple]:
    """Désérialise une polyline JSON stockée en base."""
    try:
        data = json.loads(raw or "[]")
        return _clean_coords(data) if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []
