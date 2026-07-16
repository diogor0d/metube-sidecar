# MeTube Sidecar

MeTube Sidecar turns a MeTube download into a pollable job and, when the file is
finished, serves that file back to the caller. It is intended for an iOS Shortcut
that should download a video through Cloudflare Access and then save it to Photos.

The sidecar does **not** contain or persist Cloudflare credentials. The Shortcut
sends its Cloudflare Access service-token headers on every request, and Cloudflare
validates them before proxying traffic to this service.

## How it works

1. `POST /jobs` submits a URL to MeTube's internal `/add` endpoint.
2. The sidecar assigns a unique MeTube folder: `sidecar/<job-id>`.
3. `GET /jobs/<job-id>` watches that folder through a read-only download mount.
4. Once the output file stops changing, `GET /jobs/<job-id>/file` returns it as an
   attachment.

Job metadata is persisted in `/data/jobs`. Source URLs are intentionally not
written to that metadata. Downloaded files remain managed by MeTube in its normal
download directory.

## Run with Docker Compose

The simplest setup is to add the sidecar service to the same Compose project as
MeTube. They must share:

- a Docker network, so `METUBE_URL=http://metube:8081` resolves; and
- the same download directory, writable in MeTube and read-only in the sidecar.

Copy `docker-compose.example.yml` and replace `/path/to/metube/downloads` with the
host directory already mounted at `/downloads` in MeTube. If both services are in
one Compose file, remove `external: true` and let Compose create the network.

```bash
docker compose up -d --build
docker compose logs -f metube-sidecar
```

Do not publish port 8080 to the host unless you explicitly need direct LAN access.
The example uses `expose`, which keeps it available only to connected containers.

### Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `METUBE_URL` | `http://metube:8081` | Internal MeTube base URL |
| `DOWNLOADS_DIR` | `/downloads` | Read-only view of MeTube downloads |
| `DATA_DIR` | `/data` | Persistent job metadata (use the named volume) |
| `JOB_SUBDIR` | `sidecar` | Folder reserved for sidecar jobs |
| `STABLE_SECONDS` | `5` | Time an output file must remain unchanged |
| `JOB_TIMEOUT_SECONDS` | `3600` | Time before an unfinished job fails |
| `METUBE_TIMEOUT_SECONDS` | `20` | Timeout when submitting to MeTube |
| `SIDECAR_API_KEY` | unset | Optional second authentication layer |

If `SIDECAR_API_KEY` is set, every `/jobs` request must also contain
`X-Sidecar-Api-Key`. Cloudflare Access is still the primary control.

## Cloudflare Tunnel and Access

Create a dedicated hostname such as `download-api.example.com` in the existing
Cloudflare Tunnel and point it to:

```text
http://metube-sidecar:8080
```

Create a Cloudflare Access self-hosted application for that hostname. Its token
policy must use:

- Action: **Service Auth**
- Include: **Service Token** → the token dedicated to this Shortcut

Do not use an `Allow` action for a service-token-only policy. Keep the service-token
ID and secret only in the iOS Shortcut (or another secret store), never in Git,
Compose, or the sidecar.

## API check

```bash
export CF_ID='your-client-id.access'
export CF_SECRET='your-client-secret'

curl -sS -X POST 'https://download-api.example.com/jobs' \
  -H "CF-Access-Client-Id: ${CF_ID}" \
  -H "CF-Access-Client-Secret: ${CF_SECRET}" \
  -H 'Content-Type: application/json' \
  --data '{"url":"https://www.youtube.com/watch?v=JsdjnlsSaw4"}'
```

The response resembles:

```json
{
  "id": "48b49c4e-676e-45a8-95aa-0cfb1f26780a",
  "status": "queued",
  "poll_url": "/jobs/48b49c4e-676e-45a8-95aa-0cfb1f26780a",
  "file_url": null
}
```

Poll the returned `poll_url`. When `status` becomes `complete`, request `file_url`
with the same Cloudflare headers.

### Existing MeTube Shortcut compatibility

`POST /jobs` also accepts the legacy option shape used by Shortcuts that previously
posted directly to MeTube's `/add` endpoint. When `quality`, `format`, or
`video_codec` is supplied without `download_type`, the sidecar forwards those
values using MeTube's legacy schema and adds only its controlled per-job folder.
For example:

```json
{
  "url": "https://example.com/video",
  "quality": "best_ios",
  "format": "mp4",
  "video_codec": "h264"
}
```

For compatibility with existing sidecar-oriented Shortcuts, `codec` in a
legacy-shaped body is translated to MeTube's legacy `video_codec` field. Requests
that explicitly provide `download_type` continue to use MeTube's current schema.
Omitted legacy fields and URL-only requests default to `format=ios`, `codec=h264`,
and `quality=best`.

## iOS Shortcut flow

Use the remote sidecar address as `server_address`, without a trailing slash.

1. **Get Contents of URL**: `server_address/jobs`
   - Method: `POST`
   - Headers: `CF-Access-Client-Id`, `CF-Access-Client-Secret`,
     `Content-Type: application/json`
   - JSON body: `url` = the shared video URL. The defaults are `format=ios`,
     `codec=h264`, and `quality=best`. Existing direct-MeTube `quality`, `format`,
     and `video_codec` selections can be retained unchanged.
2. Get dictionary value `id` from the response and store it as `job_id`.
3. Repeat up to 120 times:
   - Wait 5 seconds.
   - GET `server_address/jobs/job_id`, including both Cloudflare headers.
   - If `status` is `complete`, GET `server_address` + `file_url`, again including
     both Cloudflare headers.
   - Pass the result to **Save to Photo Album**, show a success notification, and
     stop the Shortcut.
   - If `status` is `failed`, show `error` and stop the Shortcut.
4. If the loop finishes, show a timeout notification.

Every HTTP action needs the Cloudflare headers; authentication is not automatically
carried from the first request. iOS may ask for Photos permission the first time the
Shortcut runs.

## Security notes

- Keep the sidecar behind Cloudflare Access and do not publish its container port.
- Give the Shortcut a dedicated, revocable service token.
- The download mount is read-only, so the sidecar cannot modify MeTube files.
- `/healthz` is unauthenticated inside the application for container health checks;
  Cloudflare Access still protects it externally.
- Download folders are not automatically deleted. Apply your normal retention or
  cleanup policy to MeTube's `sidecar/` directory.
