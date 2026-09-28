"""Tests du module de télémétrie.

Deux tests vous sont fournis en exemple : ils montrent le style attendu.
Tout le reste est à écrire — voir le TD 1.
"""

import pytest

from fleet_api.models import Position, Reading, RobotState
from fleet_api.telemetry import (
    average_speed_mps,
    battery_percentage,
    detect_voltage_dropouts,
    distance_m,
    estimate_runtime_minutes,
    is_low_battery,
    median_voltage_mv,
    path_length_m,
    robot_state,
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


# ---------------------------------------------------------------------------
# average_speed_mps
# ---------------------------------------------------------------------------


def test_average_speed_mps_cas_nominal():
    assert average_speed_mps(10.0, 5.0) == pytest.approx(2.0)


@pytest.mark.parametrize("elapsed_s", [0.0, -5.0])
def test_average_speed_mps_duree_non_positive(elapsed_s):
    assert average_speed_mps(10.0, elapsed_s) is None


# ---------------------------------------------------------------------------
# estimate_runtime_minutes
# ---------------------------------------------------------------------------


def test_estimate_runtime_minutes_cas_nominal():
    assert estimate_runtime_minutes(50.0, 2.0) == pytest.approx(25.0)


@pytest.mark.parametrize("drain_pct_per_min", [0.0, -1.0])
def test_estimate_runtime_minutes_pas_de_decharge(drain_pct_per_min):
    assert estimate_runtime_minutes(50.0, drain_pct_per_min) is None


# ---------------------------------------------------------------------------
# median_voltage_mv
# ---------------------------------------------------------------------------


def _reading(robot_id="r1", timestamp_s=0.0, voltage_mv=12_000, is_charging=False):
    return Reading(
        robot_id=robot_id,
        timestamp_s=timestamp_s,
        voltage_mv=voltage_mv,
        position=Position(0, 0),
        is_charging=is_charging,
    )


def test_median_voltage_mv_liste_vide():
    assert median_voltage_mv([]) is None


def test_median_voltage_mv_nombre_impair():
    readings = [_reading(voltage_mv=v) for v in (11_000, 12_000, 10_000)]
    assert median_voltage_mv(readings) == 11_000


def test_median_voltage_mv_nombre_pair():
    """Sur un nombre pair de mesures, la médiane moyenne les deux valeurs centrales."""
    readings = [_reading(voltage_mv=v) for v in (10_000, 11_000, 12_000, 13_000)]
    assert median_voltage_mv(readings) == pytest.approx(11_500)


# ---------------------------------------------------------------------------
# robot_state — priorité OFFLINE > CHARGING > LOW_BATTERY > OPERATIONAL.
# ---------------------------------------------------------------------------


def test_robot_state_offline_prime_sur_batterie_basse():
    """Un robot silencieux est hors ligne même si sa dernière batterie était basse."""
    reading = _reading(timestamp_s=0.0, voltage_mv=10_500)  # 0 %, en dessous du seuil
    assert robot_state(reading, now_s=200.0) == RobotState.OFFLINE


def test_robot_state_charging_prime_sur_batterie_basse():
    reading = _reading(timestamp_s=0.0, voltage_mv=10_500, is_charging=True)
    assert robot_state(reading, now_s=0.0) == RobotState.CHARGING


def test_robot_state_low_battery():
    reading = _reading(timestamp_s=0.0, voltage_mv=10_500)  # 0 %
    assert robot_state(reading, now_s=0.0) == RobotState.LOW_BATTERY


def test_robot_state_operational():
    reading = _reading(timestamp_s=0.0, voltage_mv=12_600)  # 100 %
    assert robot_state(reading, now_s=0.0) == RobotState.OPERATIONAL


def test_robot_state_juste_avant_le_delai_de_grace():
    reading = _reading(timestamp_s=0.0, voltage_mv=12_600)
    assert robot_state(reading, now_s=120.0, grace_s=120.0) == RobotState.OPERATIONAL


# ---------------------------------------------------------------------------
# detect_voltage_dropouts — indices d'arrivée des chutes strictement > seuil.
# ---------------------------------------------------------------------------


def test_detect_voltage_dropouts_aucune_chute():
    readings = [_reading(voltage_mv=v) for v in (12_000, 11_900, 11_950)]
    assert detect_voltage_dropouts(readings, max_drop_mv=200) == []


def test_detect_voltage_dropouts_chute_detectee():
    readings = [_reading(voltage_mv=v) for v in (12_000, 11_000, 10_900)]
    assert detect_voltage_dropouts(readings, max_drop_mv=500) == [1]


def test_detect_voltage_dropouts_remontee_non_signalee():
    """Une remontée de tension n'est jamais une chute."""
    readings = [_reading(voltage_mv=v) for v in (11_000, 12_000)]
    assert detect_voltage_dropouts(readings, max_drop_mv=100) == []


def test_detect_voltage_dropouts_egal_au_seuil_non_signale():
    """La chute doit être strictement supérieure au seuil pour être signalée."""
    readings = [_reading(voltage_mv=v) for v in (12_000, 11_800)]
    assert detect_voltage_dropouts(readings, max_drop_mv=200) == []
