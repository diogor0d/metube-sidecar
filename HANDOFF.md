# Handoff

## Objective

Deploy a secure MeTube sidecar behind Cloudflare Access so an iOS Shortcut can
submit a video, poll for completion, retrieve the resulting file, and save it to
Photos. Success requires a working container deployment on the Ubuntu server, a
Service Auth-protected Tunnel hostname, and a successful phone-to-gallery test.

## Current state

- The FastAPI sidecar, Docker packaging, Compose example, tests, and deployment/iOS
  documentation are implemented locally.
- The untracked implementation was reviewed on 2026-07-16. The single-video
  request fields and success response match the current upstream MeTube API.
- The API supports job creation, polling, persistent metadata, stable-file detection,
  optional secondary API-key authentication, and attachment delivery.
- Cloudflare credentials are not stored in the implementation.
- The intended GitHub remote still needs user confirmation. Deployment-specific
  Compose values, the GitHub transfer, the Ubuntu image build, Cloudflare hostname
  configuration, and the final iOS test remain.

## Git state

- Repository: `C:/Users/diogo/Documents/Projetos/metube-sidecar`
- Branch: `main`
- HEAD: `e3c1e67ac480dd5dc03cd60e8f1446424b0be96d`
- Upstream: not configured; no Git remote was present when this handoff was prepared
- Working tree: `.gitattributes` is tracked; the sidecar implementation,
  `AGENTS.md`, and this `HANDOFF.md` are untracked

## Changes

- `AGENTS.md`: durable architecture, security, development, and deployment rules.
- `app/main.py`: FastAPI job API, JSON state store, internal MeTube client, download
  detection, optional API key, and safe file response.
- `tests/test_app.py`: job lifecycle, URL validation, API-key, and temporary-file
  tests.
- `Dockerfile`: unprivileged Python 3.12 application image.
- `docker-compose.example.yml`: internal-only sidecar service, read-only downloads,
  persistent metadata volume, and shared-network example.
- `pyproject.toml`: Python package and test dependencies.
- `README.md`: architecture, Compose, Cloudflare Access, curl, iOS Shortcut, and
  security guidance.
- `.dockerignore` and `.gitignore`: local, secret, cache, and runtime exclusions.

## Verification

- `python -m pytest -q`: passed on 2026-07-16, 4 tests.
- `python -m compileall -q app tests`: passed on 2026-07-16.
- `docker compose -f docker-compose.example.yml config --quiet`: passed on
  2026-07-16.
- `git diff --check`: passed on 2026-07-16; because the implementation is
  untracked, a separate trailing-whitespace scan was also clean.
- Current upstream MeTube source review: the request schema accepts
  `download_type=video`, `codec=h264`, `format=ios`, `quality=best`, and nested
  `folder` values, and successful `/add` calls return `status=ok`.
- Container image build: not run because the Docker Desktop Linux daemon was not
  running on the Windows resume machine.

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

- No Git remote or upstream is configured, and all implementation files are
  untracked. They cannot reach another Codex project through Git until the user
  authorizes a commit, configures the intended remote, and pushes.
- The Compose download path is a placeholder until reconciled with the existing
  MeTube deployment on the Ubuntu server.
- The container image has not yet been built or exercised against the user's actual
  MeTube version, configuration, and filesystem permissions. Compatibility with
  upstream MeTube does not establish compatibility with the deployed version.
- Current MeTube deduplicates a URL that is already queued or pending but still
  returns `status=ok`. A simultaneous duplicate sidecar submission would not get
  its requested job folder and would eventually time out; avoid that case until it
  is handled and tested.
- Completion detection uses filesystem stability rather than a MeTube completion
  event; tune `STABLE_SECONDS` if the deployment filesystem behaves differently.

## Next actions

1. Confirm the intended GitHub remote.
2. Decide whether simultaneous duplicate-URL submissions must be handled before the
   first deployment.
3. With explicit authorization, add the remote if needed, commit the files, and push
   `main` so the repository-backed Codex project can obtain them.
4. On Ubuntu, reconcile `docker-compose.example.yml` with the existing MeTube
   service name, Docker network, and exact host download path.
5. Build and start the sidecar; verify `/healthz`, a submitted job, polling, and file
   retrieval over the internal network.
6. Add the dedicated Cloudflare Tunnel hostname and an Access **Service Auth** policy
   for the Shortcut's dedicated service token.
7. Update the iOS Shortcut to create a job, poll it, fetch `file_url` with the same
   Access headers, and pass the returned file to **Save to Photo Album**.
8. Perform one end-to-end test, then decide on download retention and cleanup.

## Resume instructions

1. Check out `main` and obtain commit
   `e3c1e67ac480dd5dc03cd60e8f1446424b0be96d` plus the implementation changes. The
   changes described here were untracked when prepared and will not transfer unless
   they are committed and pushed or copied by another approved method.
2. Read `AGENTS.md`, this file, `README.md`, `app/main.py`, and
   `docker-compose.example.yml` completely.
3. Verify the branch, HEAD, remote/upstream, and working tree. Report discrepancies
   before editing.
4. Re-run the verification commands in `AGENTS.md`, then continue with the smallest
   unfinished action in **Next actions**.
