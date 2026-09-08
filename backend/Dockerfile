# GShare backend image — shared by `api` and `worker` processes
# Multi-stage: base (shared sources) branches into test (dev dependencies plus pytest) and runtime.
# runtime is the default target.
#   Runtime: docker build -t gshare-backend .
#   Tests:   docker build --target test -t gshare-backend-test . && docker run --rm gshare-backend-test
#            pytest caches and coverage data land only in the container's writable layer, so --rm
#            removes them.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# ── test: dev dependencies plus the test suite, run entirely inside the container ──
# Installing dependencies before copying tests means a test-only change rebuilds just the cheap
# COPY layer.
FROM base AS test
RUN pip install --upgrade pip && pip install ".[dev]"
COPY tests ./tests
# Unit and functional tests with a coverage summary, excluding the real-GPU e2e tests.
CMD ["pytest", "-m", "not realgpu", "--cov=app", "--cov-report=term-missing"]

# ── runtime: production dependencies only; the default build target ──
FROM base AS runtime
# Install the application, then take the installer out of the runtime image. Nothing here imports
# pip, setuptools or pkg_resources — uvicorn just needs the app and its dependencies — and leaving
# them behind is what put two fixed CVEs in the published image: setuptools pulled in as a build
# dependency, and the msgpack copy vendored inside pip itself.
RUN pip install --upgrade pip && pip install . \
    && python -m pip uninstall -y setuptools wheel 2>/dev/null || true \
    && python -m pip uninstall -y pip 2>/dev/null || true

EXPOSE 8000

# Default to the API; docker-compose overrides `command` for the worker.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# The chart pins runAsUser 1000; matching it here keeps `docker run` and the cluster identical
# and satisfies the "image must not default to root" scanner rule.
USER 1000
