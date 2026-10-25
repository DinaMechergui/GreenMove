"""Versioned well-to-wheel emission factors in kg CO2e per passenger-km.

Factors are estimates based on the UK Government GHG Conversion Factors
2024 passenger-transport tables. Walking and cycling include direct travel
emissions only; they are not lifecycle assessments.
"""

FACTOR_SET_VERSION = "DEFRA-2024"
FACTOR_SOURCE = (
    "UK DESNZ, Greenhouse gas reporting: conversion factors 2024, "
    "passenger transport tables"
)
FACTOR_SOURCE_URL = (
    "https://www.gov.uk/government/publications/"
    "greenhouse-gas-reporting-conversion-factors-2024"
)

EMISSION_FACTORS = {
    "walk": 0.0,
    "bicycle": 0.0,
    "car": 0.17049,
    "bus": 0.10291,
    "metro": 0.03546,
    "train": 0.03546,
}

TRANSPORT_ALIASES = {
    "walking": "walk",
    "foot": "walk",
    "bike": "bicycle",
    "cycling": "bicycle",
    "tram": "metro",
    "public_transport": "bus",
}
