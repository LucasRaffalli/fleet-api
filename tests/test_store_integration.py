"""Tests d'intégration de PostgresStore — séance 5.

Ils parlent à une vraie base PostgreSQL. Sans `DATABASE_URL`, le module est
ignoré : la suite unitaire tourne sans infrastructure.

    docker compose up -d db
    DATABASE_URL=postgresql://app:app@localhost:5432/fleet \
        uv run pytest -m integration -v
"""

import os

import pytest

from fleet_api.models import Position, Reading

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    pytest.skip("DATABASE_URL non définie", allow_module_level=True)

from fleet_api.store import PostgresStore  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture
def store() -> PostgresStore:
    s = PostgresStore(DATABASE_URL)
    with s._connect() as conn:
        conn.execute("TRUNCATE readings")
    return s


def reading(
    robot_id: str = "r1",
    ts: float = 1_730_000_000.0,
    voltage_mv: int = 11_550,
    x: float = 0.0,
    y: float = 0.0,
    charging: bool = False,
) -> Reading:
    return Reading(
        robot_id=robot_id,
        timestamp_s=ts,
        voltage_mv=voltage_mv,
        position=Position(x=x, y=y),
        is_charging=charging,
    )


def test_ping(store: PostgresStore) -> None:
    assert store.ping() is True


def test_latest_inconnu_renvoie_none(store: PostgresStore) -> None:
    assert store.latest("fantome") is None


def test_aller_retour_conserve_tous_les_champs(store: PostgresStore) -> None:
    envoyee = reading(voltage_mv=10_200, x=3.5, y=-1.25, charging=True)
    store.add(envoyee)
    assert store.latest("r1") == envoyee


def test_latest_renvoie_la_plus_recente(store: PostgresStore) -> None:
    store.add(reading(ts=100.0, voltage_mv=11_000))
    store.add(reading(ts=300.0, voltage_mv=9_000))
    store.add(reading(ts=200.0, voltage_mv=10_000))
    derniere = store.latest("r1")
    assert derniere is not None
    assert derniere.timestamp_s == 300.0


def test_latest_all_une_mesure_par_robot(store: PostgresStore) -> None:
    store.add(reading("r1", ts=100.0))
    store.add(reading("r1", ts=200.0))
    store.add(reading("r2", ts=150.0))
    par_robot = {r.robot_id: r.timestamp_s for r in store.latest_all()}
    assert par_robot == {"r1": 200.0, "r2": 150.0}


def test_history_du_plus_recent_au_plus_ancien(store: PostgresStore) -> None:
    for ts in (100.0, 300.0, 200.0):
        store.add(reading(ts=ts))
    assert [r.timestamp_s for r in store.history("r1")] == [300.0, 200.0, 100.0]


def test_history_respecte_la_limite(store: PostgresStore) -> None:
    for ts in range(10):
        store.add(reading(ts=float(ts)))
    assert len(store.history("r1", limit=3)) == 3


def test_history_isole_les_robots(store: PostgresStore) -> None:
    store.add(reading("r1"))
    store.add(reading("r2"))
    assert {r.robot_id for r in store.history("r1")} == {"r1"}
