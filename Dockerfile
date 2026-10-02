# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Étage 1 : construction de l'environnement virtuel
# ---------------------------------------------------------------------------
FROM python:3.14-slim-trixie AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_NO_DEV=1

WORKDIR /app

# (1) Les dépendances seules : la couche lourde, qui ne dépend que de uv.lock
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable

# (2) Le code, puis le projet — quelques millisecondes
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

# ---------------------------------------------------------------------------
# Étage 2 : l'image d'exécution, sans uv ni cache
# ---------------------------------------------------------------------------
FROM python:3.14-slim-trixie

# Correctifs de sécurité Debian publiés depuis la construction de l'image de
# base. Compromis assumé : le contenu dépend de la date de build.
RUN apt-get update && apt-get upgrade -y \
 && rm -rf /var/lib/apt/lists/*

# Une image d'exécution n'installe rien : pip est inutile et embarque ses
# propres dépendances vendorisées.
RUN python -m pip uninstall -y pip

RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app \
      --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001:10001
EXPOSE 8000

# Pas de curl dans une image slim : urllib fait le travail sans paquet en plus.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status==200 else 1)"]

# Forme exec : fastapi est PID 1 et reçoit directement le SIGTERM de docker stop.
CMD ["fastapi", "run", "src/fleet_api/api.py", "--host", "0.0.0.0", "--port", "8000"]
