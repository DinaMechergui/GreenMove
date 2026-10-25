"""Niveaux de congestion (fonction pure, partagée par l'API, les vues et les tests)."""

# (seuil exclusif, code ASCII pour le CSS, libellé affiché)
THRESHOLDS = [
    (0.3, 'fluide', 'fluide'),
    (0.6, 'modere', 'modéré'),
    (0.8, 'dense', 'dense'),
]
BLOCKED = ('bloque', 'bloqué')


def level_code(congestion):
    """'fluide' (<0.3), 'modere' (<0.6), 'dense' (<0.8) ou 'bloque'."""
    for limit, code, _label in THRESHOLDS:
        if congestion < limit:
            return code
    return BLOCKED[0]


def level(congestion):
    """Libellé français : fluide / modéré / dense / bloqué."""
    for limit, _code, label in THRESHOLDS:
        if congestion < limit:
            return label
    return BLOCKED[1]
