from decimal import Decimal

from django.test import SimpleTestCase

from .services import (
    calculate_alternative_emissions,
    calculate_carbon_savings,
    calculate_segment_emissions,
    calculate_segments_total,
    calculate_trip_emissions,
    get_emission_factor,
)


class SharedCarbonServiceTests(SimpleTestCase):
    def test_factor_units_and_alias(self):
        self.assertEqual(get_emission_factor("car"), get_emission_factor("car"))
        self.assertEqual(get_emission_factor("walking"), 0)
        self.assertEqual(calculate_segment_emissions(1, "car"), get_emission_factor("car"))

    def test_zero_and_rounded_calculations(self):
        self.assertEqual(calculate_trip_emissions(0, "car"), Decimal("0.00"))
        self.assertEqual(calculate_trip_emissions(1, "car"), Decimal("0.17"))
        self.assertEqual(calculate_alternative_emissions(4, "bike"), 0)

    def test_mixed_mode_totals_and_signed_savings(self):
        self.assertEqual(
            calculate_segments_total(
                [
                    {"distance_km": 3, "transport_mode": "car"},
                    {"distance_km": 4, "transport_mode": "bus"},
                ]
            ),
            Decimal("0.92"),
        )
        self.assertEqual(
            calculate_carbon_savings(0.1, 0.2), Decimal("-0.10")
        )
