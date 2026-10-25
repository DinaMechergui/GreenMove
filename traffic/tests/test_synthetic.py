from datetime import datetime

from django.test import SimpleTestCase

from traffic.levels import level, level_code
from traffic.synthetic import FREE_FLOW, speeds, synthetic_congestion


class NoNoise:
    """Remplace random : bruit gaussien nul => résultats déterministes."""
    def gauss(self, mu, sigma):
        return 0.0


MONDAY = datetime(2026, 10, 26)   # lundi
SUNDAY = datetime(2026, 10, 25)   # dimanche


def at(day, hour, minute=0):
    return day.replace(hour=hour, minute=minute)


class SyntheticCongestionTests(SimpleTestCase):
    rng = NoNoise()

    def test_morning_peak_higher_than_night(self):
        for profile in FREE_FLOW:
            self.assertGreater(
                synthetic_congestion(profile, at(MONDAY, 8), rng=self.rng),
                synthetic_congestion(profile, at(MONDAY, 3), rng=self.rng) + 0.2)

    def test_sunday_lower_than_monday(self):
        self.assertLess(synthetic_congestion('center', at(SUNDAY, 8), rng=self.rng),
                        synthetic_congestion('center', at(MONDAY, 8), rng=self.rng))

    def test_holiday_like_sunday(self):
        self.assertLess(synthetic_congestion('am_heavy', at(MONDAY, 8), holiday=True, rng=self.rng),
                        synthetic_congestion('am_heavy', at(MONDAY, 8), rng=self.rng))

    def test_rain_increases_congestion(self):
        self.assertGreater(synthetic_congestion('highway', at(MONDAY, 17, 30), rain_mm=3, rng=self.rng),
                           synthetic_congestion('highway', at(MONDAY, 17, 30), rain_mm=0, rng=self.rng))

    def test_value_is_bounded(self):
        for h in range(24):
            c = synthetic_congestion('highway', at(MONDAY, h), rain_mm=50)
            self.assertGreaterEqual(c, 0.0)
            self.assertLessEqual(c, 0.98)


class SpeedsTests(SimpleTestCase):
    def test_congestion_matches_speed_ratio(self):
        for profile, free in FREE_FLOW.items():
            for c in (0.0, 0.25, 0.5, 0.9):
                current, free_flow = speeds(profile, c)
                self.assertEqual(free_flow, free)
                self.assertAlmostEqual(1 - current / free_flow, c, delta=0.01)

    def test_free_flow_when_no_congestion(self):
        self.assertEqual(speeds('center', 0.0), (40, 40))


class LevelTests(SimpleTestCase):
    def test_thresholds(self):
        cases = [(0.0, 'fluide'), (0.29, 'fluide'), (0.3, 'modéré'), (0.59, 'modéré'),
                 (0.6, 'dense'), (0.79, 'dense'), (0.8, 'bloqué'), (1.0, 'bloqué')]
        for value, expected in cases:
            self.assertEqual(level(value), expected, value)

    def test_codes_are_ascii(self):
        self.assertEqual([level_code(v) for v in (0.1, 0.4, 0.7, 0.9)],
                         ['fluide', 'modere', 'dense', 'bloque'])
