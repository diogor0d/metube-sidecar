# Handoff

## Objective

Deploy a secure MeTube sidecar behind Cloudflare Access so an iOS Shortcut can
submit a video, poll for completion, retrieve the resulting file, and save it to
Photos. Success requires a working container deployment on the Ubuntu server, a
Service Auth-protected Tunnel hostname, and a successful phone-to-gallery test.

## Current state

- The FastAPI sidecar, Docker packaging, Compose example, tests, and deployment/iOS
  documentation are implemented locally.
- The sidecar is deployed on `diogoserver`, reachable through the dedicated
  Cloudflare Access-protected hostname, and passed a phone-to-Photos test.
- A local, uncommitted compatibility change makes `POST /jobs` preserve the legacy
  MeTube `/add` option shape used by the existing Shortcut while retaining the
  current URL-only defaults.
- The API supports job creation, polling, persistent metadata, stable-file detection,
  optional secondary API-key authentication, and attachment delivery.
- Cloudflare credentials are not stored in the implementation.
- The baseline implementation is committed and available from the configured
  GitHub remote. The compatibility change is not committed, pushed, or deployed.

## Git state

- Repository: `C:/Users/diogo/Documents/Projetos/metube-sidecar`
- Branch: `main`
- HEAD: `6397fb5d898fd535bcc279220cf890ee0d5f0677`
- Upstream: `origin/main`; synchronized at `6397fb5d898fd535bcc279220cf890ee0d5f0677`
- Remote: `origin` is `https://github.com/diogor0d/metube-sidecar.git`
- Working tree: `app/main.py`, `tests/test_app.py`, `README.md`, and `HANDOFF.md`
  are modified; nothing is staged

## Changes

- `AGENTS.md`: durable architecture, security, development, and deployment rules.
- `app/main.py`: FastAPI job API, JSON state store, internal MeTube client, download
  detection, optional API key, safe file response, and legacy MeTube option
  forwarding.
- `tests/test_app.py`: job lifecycle, URL validation, API-key, temporary-file, and
  legacy request compatibility tests.
- `Dockerfile`: unprivileged Python 3.12 application image.
- `docker-compose.example.yml`: internal-only sidecar service, read-only downloads,
  persistent metadata volume, and shared-network example.
- `pyproject.toml`: Python package and test dependencies.
- `README.md`: architecture, Compose, Cloudflare Access, curl, iOS Shortcut, and
  security guidance.
- `.dockerignore` and `.gitignore`: local, secret, cache, and runtime exclusions.

## Verification

- `python -m pytest -q`: passed after the compatibility change on 2026-07-16,
  6 tests.
- `python -m compileall -q app tests`: passed on 2026-07-16.
- `docker compose -f docker-compose.example.yml config --quiet`: passed on
  2026-07-16.
- `git diff --check`: passed on 2026-07-16; because the implementation is
  untracked, a separate trailing-whitespace scan was also clean.
- Current upstream MeTube source review: the request schema accepts
  `download_type=video`, `codec=h264`, `format=ios`, `quality=best`, and nested
  `folder` values, and successful `/add` calls return `status=ok`.
- Production verification before the compatibility change: sidecar health, public
  Cloudflare Service Auth, job creation, polling, MP4 retrieval, and iOS Photos save
  passed. The changed image has not been built or deployed.

## Decisions and constraints

- Cloudflare Access service-token credentials remain only with the caller and must
  be sent on every Shortcut HTTP action.
- The sidecar calls MeTube over the private Docker network; it does not call MeTube
  through Cloudflare.
- MeTube's download directory is mounted read-only into the sidecar.
- Each job uses `sidecar/<UUID>` to correlate output without trusting a remote title
  or guessing a filename.
- The default output request is `format=ios`, `codec=h264`, and `quality=best`.
- Sidecar metadata deliberately excludes the submitted source URL.
- Do not commit, push, configure a remote, or change production without explicit
  user authorization.

## Risks and blockers

- The compatibility change still needs an authorized commit/push and a user-run
  pull/rebuild on `diogoserver` before the old Shortcut selectors can be retested.
- Current MeTube deduplicates a URL that is already queued or pending but still
  returns `status=ok`. A simultaneous duplicate sidecar submission would not get
  its requested job folder and would eventually time out; avoid that case until it
  is handled and tested.
- Completion detection uses filesystem stability rather than a MeTube completion
  event; tune `STABLE_SECONDS` if the deployment filesystem behaves differently.

## Next actions

1. Review the compatibility diff, then commit and push only with explicit user
   authorization.
2. On `diogoserver`, pull the authorized commit and rebuild/recreate the sidecar.
3. Restore the existing Shortcut's `quality`, `format`, and codec fields and perform
   a phone-to-Photos regression test.
4. Decide whether simultaneous duplicate-URL submissions and download retention
   need additional handling.

## Resume instructions

1. Check out `main` and obtain commit
   `6397fb5d898fd535bcc279220cf890ee0d5f0677` from `origin/main`.
2. Read `AGENTS.md`, this file, `README.md`, `app/main.py`, and
   `docker-compose.example.yml` completely.
3. Verify the branch, HEAD, remote/upstream, and working tree. Report discrepancies
   before editing.
4. Re-run the verification commands in `AGENTS.md`, then continue with the smallest
   unfinished action in **Next actions**.
