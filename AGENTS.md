# Repository Instructions

## Purpose

This repository contains a small FastAPI sidecar for MeTube. It converts a MeTube
download request into a pollable job and serves the completed file to an authorized
caller, primarily an iOS Shortcut that saves the result to Photos.

## Architecture

- `app/main.py` owns the HTTP API, job persistence, MeTube submission, download
  detection, and file delivery.
- `POST /jobs` submits a URL to MeTube's internal `/add` endpoint.
- `GET /jobs/{id}` refreshes and returns job status.
- `GET /jobs/{id}/file` returns the completed output as an attachment.
- Job metadata lives under `DATA_DIR/jobs` and must survive container restarts.
- MeTube writes each job into `JOB_SUBDIR/<job-id>` inside its download directory.
  The sidecar receives the same directory as a read-only mount.
- The application currently assumes one Uvicorn worker. Its in-process lock is not
  a distributed lock; do not enable multiple workers without redesigning state
  coordination.

## Security boundaries

- Never store Cloudflare Access client IDs, client secrets, tokens, API keys, real
  `.env` values, production URLs containing credentials, or user download data in
  Git.
- Cloudflare Access authentication happens at the edge. The caller must send the
  Access service-token headers on every request; the sidecar must not proxy or
  persist them.
- `SIDECAR_API_KEY` is optional defense in depth. If used, inject it at deployment
  time and send it as `X-Sidecar-Api-Key`; never hard-code it.
- Keep the container port internal by default. Use Compose `expose`, not `ports`,
  unless the user explicitly authorizes direct host or LAN exposure.
- Preserve the read-only `/downloads` mount and the resolved-path containment check
  in the file endpoint.
- Do not persist submitted source URLs in sidecar job metadata. MeTube itself may
  still retain operational information according to its own configuration.
- A file is complete only after temporary download files disappear and the selected
  output remains unchanged for `STABLE_SECONDS`.

## Development workflow

- Target Python 3.12 or newer.
- Keep API behavior, tests, `README.md`, and the Compose example synchronized.
- Prefer small dependencies and standard-library implementations where practical.
- Add or update tests for API, persistence, authentication, path-safety, or download
  detection changes.
- Run before handing off a change:

  ```bash
  python -m compileall -q app tests
  python -m pytest -q
  docker compose -f docker-compose.example.yml config --quiet
  git diff --check
  ```

- When Docker is available, also build the image and exercise `/healthz` plus one
  mocked or disposable end-to-end job.

## Deployment assumptions

- `METUBE_URL` is an internal Docker-network URL such as `http://metube:8081`.
- The download path in `docker-compose.example.yml` is a placeholder and must match
  the exact host directory mounted into MeTube at `/downloads`.
- The sidecar and MeTube must share a Docker network.
- The recommended public entry point is a dedicated Cloudflare Tunnel hostname with
  an Access policy whose action is **Service Auth** and whose include selector is the
  Shortcut's dedicated service token.
- Never mutate a production deployment, Cloudflare configuration, Git history, or a
  remote repository without explicit authorization.

