# Handoff

## Objective

Operate a secure MeTube sidecar behind Cloudflare Access so an iOS Shortcut can
submit media, poll for completion, retrieve the resulting file, and save supported
video/image results to Photos.

## Current state

- The FastAPI sidecar, Docker packaging, Compose example, tests, and deployment/iOS
  documentation are implemented locally.
- The sidecar is deployed on `server-1`, reachable through a dedicated
  Cloudflare Access-protected hostname, and passed a phone-to-Photos test.
- Commit `99b510a` preserves the legacy MeTube `/add` option shape and fills omitted
  request fields with the sidecar defaults.
- The API supports job creation, polling, persistent metadata, stable-file detection,
  optional secondary API-key authentication, and attachment delivery.
- Cloudflare credentials are not stored in the implementation.
- The source is committed and synchronized with the configured upstream. The exact
  revision deployed on `server-1` has not been recorded.

## Git state

- Repository: repository root
- Branch: `main`
- HEAD: `99b510ae7c53bc329cf96eb79ea9a8619e9e0b2d`
- Upstream: `origin/main`; synchronized at the same commit
- Working tree: `AGENTS.md` and `HANDOFF.md` contain the uncommitted public-disclosure
  documentation update; nothing is staged

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
- `HANDOFF.md`: public-safe continuity state using aliases and placeholders.

## Verification

- `python -m pytest -q`: passed after the compatibility/default change on
  2026-07-16, 7 tests.
- `python -m compileall -q app tests`: passed on 2026-07-16.
- `docker compose -f docker-compose.example.yml config --quiet`: passed on
  2026-07-16.
- `git diff --check`: passed on 2026-07-16.
- Current upstream MeTube source review: the request schema accepts
  `download_type=video`, `codec=h264`, `format=ios`, `quality=best`, and nested
  `folder` values, and successful `/add` calls return `status=ok`.
- Production evidence: sidecar health, public Cloudflare Service Auth, job creation,
  polling, MP4 retrieval, and iOS Photos save passed. The exact deployed source
  revision remains unverified.

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
- Treat every tracked file and all reachable history as public. `HANDOFF.md` remains
  tracked but must use aliases/placeholders and contain no sensitive information.

## Risks and blockers

- Specific resolution selections can cause MeTube rejection when display labels
  such as `1080p` are sent instead of API values such as `1080`; the resulting
  Cloudflare HTML error cannot be parsed as a Shortcut dictionary.
- Thumbnail jobs can be accepted by MeTube but are not completed by the sidecar
  because image extensions are not yet part of type-aware output detection.
- Audio files are detectable by the sidecar but require a Shortcut **Save File**
  branch rather than **Save to Photo Album**.
- Current MeTube deduplicates a URL that is already queued or pending but still
  returns `status=ok`. A simultaneous duplicate sidecar submission would not get
  its requested job folder and would eventually time out; avoid that case until it
  is handled and tested.
- Completion detection uses filesystem stability rather than a MeTube completion
  event; tune `STABLE_SECONDS` if the deployment filesystem behaves differently.

## Next actions

1. Add type-aware thumbnail output detection and JSON validation/normalization for
   resolution selections, with tests and synchronized documentation.
2. Add separate Shortcut save branches for Photos-compatible media and audio/files.
3. Record the deployed source revision during the next authorized rebuild and run
   video, thumbnail, resolution, and audio regression tests.
4. Decide whether simultaneous duplicate-URL submissions and download retention
   need additional handling.

## Resume instructions

1. Check out `main` and obtain commit
   `99b510ae7c53bc329cf96eb79ea9a8619e9e0b2d` from `origin/main`, plus the
   uncommitted documentation update described above.
2. Read `AGENTS.md`, this file, `README.md`, `app/main.py`, and
   `docker-compose.example.yml` completely.
3. Verify the branch, HEAD, remote/upstream, and working tree. Report discrepancies
   before editing.
4. Re-run the verification commands in `AGENTS.md`, then continue with the smallest
   unfinished action in **Next actions**.
