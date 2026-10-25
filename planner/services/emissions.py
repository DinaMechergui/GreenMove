"""Facteurs d'émission locaux (ordres de grandeur ADEME/DEFRA, sans appel API)."""

# kg CO2e par passager-km
EMISSION_FACTORS = {
    'WALK': 0.0,
    'BIKE': 0.0,
    'METRO': 0.004,
    'BUS': 0.105,
    'CARPOOL': 0.06,
    'CAR': 0.192,
}

# Vitesse moyenne urbaine (km/h) et coût (TND/km), confort de base (0-1)
SPEED_KMH = {'WALK': 5, 'BIKE': 15, 'METRO': 30, 'BUS': 18, 'CARPOOL': 25, 'CAR': 25}
COST_TND_KM = {'WALK': 0.0, 'BIKE': 0.0, 'METRO': 0.12, 'BUS': 0.10, 'CARPOOL': 0.20, 'CAR': 0.45}
BASE_COMFORT = {'WALK': 0.7, 'BIKE': 0.7, 'METRO': 0.75, 'BUS': 0.55, 'CARPOOL': 0.7, 'CAR': 0.9}

# Un arbre absorbe environ 25 kg CO2 / an
KG_CO2_PER_TREE_YEAR = 25.0


def co2_kg(mode, distance_km):
    return round(EMISSION_FACTORS.get(mode, EMISSION_FACTORS['CAR']) * max(distance_km, 0), 4)
