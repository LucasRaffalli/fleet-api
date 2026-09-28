"""API HTTP du service de supervision de flotte."""

from __future__ import annotations

import time

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from fleet_api import __version__
from fleet_api.models import Position, Reading
from fleet_api.store import Store, build_store
from fleet_api.telemetry import (
    battery_percentage,
    fleet_summary,
    path_length_m,
    robot_state,
)

app = FastAPI(
    title="fleet-api",
    version=__version__,
    summary="Supervision d'une flotte de robots d'entrepôt",
)

# CORS ouvert sur localhost : sert uniquement la page de démo statique
# (demo/fleet-floor.html), servie sur un autre port (Go Live, file://) en dev.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_store: Store = build_store()


def get_store() -> Store:
    """Dépendance injectable — permet de substituer le stockage dans les tests."""
    return _store


# --------------------------------------------------------------------------
# Schémas d'entrée et de sortie
# --------------------------------------------------------------------------


class TelemetryIn(BaseModel):
    """Une mesure envoyée par un robot."""

    timestamp_s: float = Field(description="Horodatage, en secondes Unix")
    voltage_mv: int = Field(ge=0, le=20_000, description="Tension batterie, en mV")
    x: float = Field(description="Abscisse, en mètres")
    y: float = Field(description="Ordonnée, en mètres")
    is_charging: bool = False


class RobotOut(BaseModel):
    robot_id: str
    state: str
    battery_pct: float
    last_seen_s: float
    distance_travelled_m: float


class HealthOut(BaseModel):
    status: str
    storage: str


# --------------------------------------------------------------------------
# Endpoints d'exploitation
# --------------------------------------------------------------------------


@app.get("/health", response_model=HealthOut, tags=["exploitation"])
def health(response: Response, store: Store = Depends(get_store)) -> HealthOut:
    """Sonde de santé.

    Renvoie 200 si le service **et** son stockage répondent, 503 sinon. C'est
    cette réponse qui pilote la bascule et le retour arrière de la séance 7 :
    un service qui ne se déclare pas sain ne reçoit pas de trafic.
    """
    ok = store.ping()
    if not ok:
        response.status_code = 503
    return HealthOut(status="ok" if ok else "degraded", storage="ok" if ok else "down")


@app.get("/version", tags=["exploitation"])
def version() -> dict[str, str]:
    """Version déployée. Permet de vérifier *ce qui tourne réellement*."""
    return {"version": __version__}


# --------------------------------------------------------------------------
# Endpoints métier
# --------------------------------------------------------------------------


@app.post("/robots/{robot_id}/telemetry", status_code=201, tags=["télémétrie"])
def ingest(
    robot_id: str, payload: TelemetryIn, store: Store = Depends(get_store)
) -> dict[str, str]:
    """Enregistre une mesure de télémétrie pour un robot."""
    store.add(
        Reading(
            robot_id=robot_id,
            timestamp_s=payload.timestamp_s,
            voltage_mv=payload.voltage_mv,
            position=Position(x=payload.x, y=payload.y),
            is_charging=payload.is_charging,
        )
    )
    return {"status": "accepted"}


@app.get("/robots/{robot_id}", response_model=RobotOut, tags=["télémétrie"])
def robot(robot_id: str, store: Store = Depends(get_store)) -> RobotOut:
    """État courant d'un robot, calculé à partir de sa dernière mesure."""
    derniere = store.latest(robot_id)
    if derniere is None:
        raise HTTPException(status_code=404, detail=f"Robot inconnu : {robot_id}")

    trajet = [r.position for r in reversed(store.history(robot_id, limit=1000))]
    return RobotOut(
        robot_id=robot_id,
        state=robot_state(derniere, now_s=time.time()).value,
        battery_pct=battery_percentage(derniere.voltage_mv),
        last_seen_s=derniere.timestamp_s,
        distance_travelled_m=round(path_length_m(trajet), 2),
    )


@app.get("/fleet", tags=["télémétrie"])
def fleet(store: Store = Depends(get_store)) -> dict[str, float | int]:
    """Agrégats sur l'ensemble de la flotte."""
    return fleet_summary(store.latest_all())
