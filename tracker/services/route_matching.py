"""Opt-in map matching and OSM context lookups with bounded public requests."""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .gps_service import validate_coordinate

logger = logging.getLogger(__name__)


class RouteServiceError(RuntimeError):
    """External routing service failed or returned an unusable response."""


def _request_json(url, *, method="GET", data=None, headers=None, timeout=8):
    request_headers = {"User-Agent": "GreenMove-Mobility-Tracker/1.0"}
    request_headers.update(headers or {})
    request = Request(url, data=data, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(2 * 1024 * 1024 + 1)
    except HTTPError as exc:
        error_body = exc.read(2 * 1024 * 1024 + 1)
        try:
            error_code = json.loads(error_body).get("code")
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            error_code = None
        if error_code in {"NoSegment", "NoMatch"}:
            raise RouteServiceError(
                "OSRM n'a associé aucun parcours exploitable."
            ) from exc
        logger.warning("Cartographic service returned HTTP %s.", exc.code)
        raise RouteServiceError(
            f"Le service cartographique a répondu HTTP {exc.code}."
        ) from exc
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RouteServiceError("Le service cartographique est indisponible.") from exc
    if len(body) > 2 * 1024 * 1024:
        raise RouteServiceError("Réponse cartographique trop volumineuse.")
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RouteServiceError("Réponse JSON cartographique invalide.") from exc


def match_osrm(coordinates, profile="driving"):
    """Request OSRM matching for an explicit caller; never called during capture."""
    if profile not in {"driving", "cycling", "walking"}:
        raise ValueError("Profil OSRM non pris en charge.")
    if not 2 <= len(coordinates) <= 1000:
        raise ValueError("Le map-matching nécessite entre 2 et 1000 points.")
    validated = [validate_coordinate(*point) for point in coordinates]
    encoded_coordinates = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in validated)
    query = urlencode({"overview": "full", "geometries": "geojson", "gaps": "split"})
    result = _request_json(
        f"https://router.project-osrm.org/match/v1/{profile}/"
        f"{encoded_coordinates}?{query}"
    )
    if result.get("code") != "Ok" or not result.get("matchings"):
        raise RouteServiceError("OSRM n'a associé aucun parcours exploitable.")
    matchings = result["matchings"]
    return {
        "geometry": [item.get("geometry") for item in matchings if item.get("geometry")],
        "confidence": max(float(item.get("confidence", 0)) for item in matchings),
        "unmatched_count": sum(item is None for item in result.get("tracepoints", [])),
        "service": "OSRM",
    }


def query_overpass_context(coordinates):
    """Return nearby cycling/public-transport OSM features for explicit verification."""
    if not coordinates or len(coordinates) > 1000:
        raise ValueError("La requête Overpass nécessite entre 1 et 1000 points.")
    validated = [validate_coordinate(*point) for point in coordinates]
    latitudes = [point[0] for point in validated]
    longitudes = [point[1] for point in validated]
    south, west = min(latitudes), min(longitudes)
    north, east = max(latitudes), max(longitudes)
    bbox = f"{south:.5f},{west:.5f},{north:.5f},{east:.5f}"
    query = (
        f'[out:json][timeout:15];(way["highway"="cycleway"]({bbox});'
        f'relation["route"~"bus|subway|tram"]({bbox}););out tags;'
    )
    result = _request_json(
        "https://overpass-api.de/api/interpreter",
        method="POST",
        data=urlencode({"data": query}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
    )
    elements = result.get("elements")
    if not isinstance(elements, list):
        raise RouteServiceError("Réponse Overpass incomplète.")
    return {
        "elements": elements,
        "feature_count": len(elements),
        "service": "Overpass",
    }
