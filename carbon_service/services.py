"""Reusable, unit-explicit carbon calculations."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable, Mapping

from .factors import EMISSION_FACTORS, TRANSPORT_ALIASES

_TWO_PLACES = Decimal("0.01")


def _distance(value: object) -> Decimal:
    try:
        distance = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("La distance doit être un nombre valide.") from exc
    if not distance.is_finite() or distance < 0:
        raise ValueError("La distance doit être positive ou nulle.")
    return distance


def get_emission_factor(transport_mode: str) -> Decimal:
    """Return kg CO2e per passenger-km for a supported transport mode."""
    mode = TRANSPORT_ALIASES.get(transport_mode.strip().lower(), transport_mode.strip().lower())
    try:
        return Decimal(str(EMISSION_FACTORS[mode]))
    except KeyError as exc:
        raise ValueError(f"Mode de transport inconnu : {transport_mode}.") from exc


def calculate_segment_emissions(distance_km: object, transport_mode: str) -> Decimal:
    """Calculate unrounded kg CO2e for one passenger-kilometre segment."""
    return _distance(distance_km) * get_emission_factor(transport_mode)


def calculate_trip_emissions(distance_km: object, transport_mode: str) -> Decimal:
    """Calculate emissions rounded to 0.01 kg CO2e for a single-mode trip."""
    return calculate_segment_emissions(distance_km, transport_mode).quantize(
        _TWO_PLACES, rounding=ROUND_HALF_UP
    )


def calculate_alternative_emissions(distance_km: object, transport_mode: str) -> Decimal:
    """Calculate emissions for an alternative using the same distance estimate."""
    return calculate_trip_emissions(distance_km, transport_mode)


def calculate_carbon_savings(
    baseline_kg: object, alternative_kg: object
) -> Decimal:
    """Return signed savings; negative values mean the alternative emits more."""
    baseline = _distance(baseline_kg)
    alternative = _distance(alternative_kg)
    return (baseline - alternative).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def calculate_segments_total(segments: Iterable[Mapping[str, object]]) -> Decimal:
    """Sum mixed-mode segments and round only once at the trip boundary."""
    total = Decimal("0")
    for segment in segments:
        total += calculate_segment_emissions(
            segment["distance_km"], str(segment["transport_mode"])
        )
    return total.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
