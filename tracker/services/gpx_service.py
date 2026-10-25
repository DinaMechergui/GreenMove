"""Bounded, entity-disabled GPX import/export helpers."""

from datetime import datetime
from xml.etree import ElementTree
from defusedxml import ElementTree as SafeElementTree

from .gps_service import GPSDataError, validate_coordinate

MAX_GPX_BYTES = 2 * 1024 * 1024
GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"


def parse_gpx(uploaded_file):
    if uploaded_file.size > MAX_GPX_BYTES:
        raise GPSDataError("Le fichier GPX dépasse la limite de 2 Mio.")
    contents = uploaded_file.read(MAX_GPX_BYTES + 1)
    if len(contents) > MAX_GPX_BYTES:
        raise GPSDataError("Le fichier GPX dépasse la limite de 2 Mio.")
    try:
        root = SafeElementTree.fromstring(
            contents, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except (SafeElementTree.DTDForbidden, SafeElementTree.EntitiesForbidden) as exc:
        raise GPSDataError("Les déclarations DTD et entités XML sont interdites.") from exc
    except ElementTree.ParseError as exc:
        raise GPSDataError("Le fichier GPX contient un XML invalide.") from exc
    if root.tag.rsplit("}", 1)[-1] != "gpx":
        raise GPSDataError("Le fichier XML ne contient pas une racine GPX.")
    points = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "trkpt":
            continue
        try:
            latitude, longitude = validate_coordinate(
                element.attrib.get("lat"), element.attrib.get("lon")
            )
            time_element = next(
                child for child in element if child.tag.rsplit("}", 1)[-1] == "time"
            )
            timestamp = datetime.fromisoformat(
                (time_element.text or "").replace("Z", "+00:00")
            )
            if timestamp.utcoffset() is None:
                raise ValueError
        except (StopIteration, TypeError, ValueError) as exc:
            raise GPSDataError("Un point GPX est incomplet ou invalide.") from exc
        points.append({"latitude": latitude, "longitude": longitude, "timestamp": timestamp})
    if not points:
        raise GPSDataError("Le fichier GPX ne contient aucun point de trace.")
    if len(points) > 20000:
        raise GPSDataError("Le fichier GPX dépasse la limite de 20 000 points.")
    if any(
        current["timestamp"] <= previous["timestamp"]
        for previous, current in zip(points, points[1:])
    ):
        raise GPSDataError("Les horodatages GPX doivent être strictement croissants.")
    return points


def build_gpx(points):
    root = ElementTree.Element(
        f"{{{GPX_NAMESPACE}}}gpx", {"version": "1.1", "creator": "GreenMove"}
    )
    track = ElementTree.SubElement(root, f"{{{GPX_NAMESPACE}}}trk")
    segment = ElementTree.SubElement(track, f"{{{GPX_NAMESPACE}}}trkseg")
    for point in points:
        latitude, longitude = validate_coordinate(
            point["latitude"], point["longitude"]
        )
        trackpoint = ElementTree.SubElement(
            segment,
            f"{{{GPX_NAMESPACE}}}trkpt",
            {"lat": f"{latitude:.7f}", "lon": f"{longitude:.7f}"},
        )
        time_element = ElementTree.SubElement(
            trackpoint, f"{{{GPX_NAMESPACE}}}time"
        )
        time_element.text = point["timestamp"].isoformat().replace("+00:00", "Z")
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
