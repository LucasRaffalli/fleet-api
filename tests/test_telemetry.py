"""Tests du module de télémétrie.

Deux tests vous sont fournis en exemple : ils montrent le style attendu.
Tout le reste est à écrire — voir le TD 1.
"""

import pytest

from fleet_api.models import Position
from fleet_api.telemetry import (
    battery_percentage,
    distance_m,
    is_low_battery,
    path_length_m,
)

# ---------------------------------------------------------------------------
# Exemple 1 — un test simple, avec un cas nominal et les deux bornes.
# ---------------------------------------------------------------------------


def test_battery_percentage_bornes_et_cas_nominal():
    """La conversion est linéaire et bornée à [0, 100]."""
    assert battery_percentage(12_600) == 100.0
    assert battery_percentage(10_500) == 0.0
    assert battery_percentage(11_550) == 50.0
    # Hors bornes : on sature, on ne dépasse pas.
    assert battery_percentage(13_000) == 100.0
    assert battery_percentage(9_000) == 0.0


# ---------------------------------------------------------------------------
# Exemple 2 — le même test écrit en paramétré, quand les cas se ressemblent.
# On teste aussi que l'erreur attendue est bien levée.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "attendu"),
    [
        (Position(0, 0), Position(3, 4), 5.0),  # triplet pythagoricien
        (Position(0, 0), Position(0, 0), 0.0),  # distance à soi-même
        (Position(1, 1), Position(-2, -3), 5.0),  # coordonnées négatives
        (Position(3, 4), Position(0, 0), 5.0),  # symétrie
    ],
)
def test_distance_m(a, b, attendu):
    """La distance est euclidienne, positive et symétrique."""
    assert distance_m(a, b) == pytest.approx(attendu)


def test_battery_percentage_rejette_des_bornes_incoherentes():
    """Une plage de tension invalide lève une ValueError."""
    with pytest.raises(ValueError, match="strictement supérieur"):
        battery_percentage(11_000, empty_mv=12_000, full_mv=11_000)


# ---------------------------------------------------------------------------
# is_low_battery — l'alerte se déclenche pour battery_pct <= threshold_pct
# (« inférieur ou égal »), donc un robot pile au seuil doit être en alerte.
# ---------------------------------------------------------------------------


def test_is_low_battery_sous_le_seuil():
    assert is_low_battery(15.0, 20.0) is True


def test_is_low_battery_au_dessus_du_seuil():
    assert is_low_battery(50.0, 20.0) is False


@pytest.mark.xfail(
    reason=(
        "bug : is_low_battery utilise `<` au lieu de `<=`, un robot exactement "
        "au seuil n'est donc pas signalé en alerte, contrairement à la docstring."
    ),
    strict=True,
)
def test_is_low_battery_pile_au_seuil():
    """« Un robot exactement au seuil est donc en alerte » (docstring)."""
    assert is_low_battery(20.0, 20.0) is True


# ---------------------------------------------------------------------------
# path_length_m — somme des distances entre positions consécutives.
# ---------------------------------------------------------------------------


def test_path_length_m_liste_vide():
    assert path_length_m([]) == 0.0


def test_path_length_m_un_seul_point():
    assert path_length_m([Position(0, 0)]) == 0.0


@pytest.mark.xfail(
    reason=(
        "bug : la boucle `range(len(positions) - 2)` saute le dernier segment "
        "du trajet, deux positions donnent donc une longueur nulle au lieu de "
        "la distance entre elles."
    ),
    strict=True,
)
def test_path_length_m_deux_points():
    assert path_length_m([Position(0, 0), Position(3, 4)]) == pytest.approx(5.0)


@pytest.mark.xfail(
    reason=(
        "bug : même cause, un trajet à trois points ne compte que le premier "
        "segment, pas la somme complète."
    ),
    strict=True,
)
def test_path_length_m_trois_points():
    trajet = [Position(0, 0), Position(3, 4), Position(3, 0)]
    # segment 1 : (0,0)->(3,4) = 5.0 ; segment 2 : (3,4)->(3,0) = 4.0
    assert path_length_m(trajet) == pytest.approx(9.0)
