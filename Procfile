# Single worker: run output is stored in process memory (RESULTS). With 2+ workers,
# /api/run/* and /api/download/<id> can hit different processes → export 404 / flaky behavior.
web: gunicorn app_backend:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
