#!/usr/bin/env python3
"""Run the synthetic video, thumbnail, and resolution MeTube integration check.

Expected to run inside the sidecar image on the disposable integration network,
with `/fixtures` and the read-only job metadata volume mounted at `/state`.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx


METUBE_URL = "http://metube:8081"
FIXTURE_URL = "http://fixture:8082"
SIDECAR_URL = "http://sidecar:8080"
API_KEY = "synthetic-local-integration-key"
STATE_DIR = Path("/state/jobs")
READY_TIMEOUT_SECONDS = 30
CASE_TIMEOUT_SECONDS = 30
POLL_INTERVAL_SECONDS = 0.5

CASES = (
    {
        "name": "video",
        "download_type": "video",
        "format": "ios",
        "codec": "h264",
        "quality": "best",
        "fixture": "fixture.mp4",
        "content_type": "video/mp4",
    },
    {
        "name": "thumbnail",
        "download_type": "thumbnail",
        "format": "jpg",
        "codec": "auto",
        "quality": "best",
        "fixture": "fixture.jpg",
        "content_type": "image/jpeg",
    },
    {
        "name": "resolution",
        "download_type": "video",
        "format": "ios",
        "codec": "h264",
        "quality": "1080p",
        "fixture": "fixture.mp4",
        "content_type": "video/mp4",
    },
)


class IntegrationCheckError(RuntimeError):
    """A synthetic integration check failed without exposing request data."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise IntegrationCheckError(message)


def response_json(response: httpx.Response, message: str) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError as exc:
        raise IntegrationCheckError(message) from exc
    require(isinstance(value, dict), message)
    return value


def wait_until_ready(client: httpx.Client) -> None:
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    ready: set[str] = set()
    checks = {
        "metube": (f"{METUBE_URL}/", 200),
        "fixture": (f"{FIXTURE_URL}/index.html", 200),
        "sidecar": (f"{SIDECAR_URL}/healthz", 200),
    }
    while time.monotonic() < deadline:
        for name, (url, expected_status) in checks.items():
            if name in ready:
                continue
            try:
                response = client.get(url)
            except httpx.HTTPError:
                continue
            if response.status_code == expected_status:
                ready.add(name)
        if len(ready) == len(checks):
            return
        time.sleep(0.5)
    missing = sorted(set(checks) - ready)
    raise IntegrationCheckError(
        f"services did not become ready within {READY_TIMEOUT_SECONDS}s: "
        + ", ".join(missing)
    )


def check_case(client: httpx.Client, case: dict[str, str]) -> dict[str, Any]:
    fixture_path = Path("/fixtures") / case["fixture"]
    try:
        expected_bytes = fixture_path.read_bytes()
    except OSError as exc:
        raise IntegrationCheckError(
            f"expected fixture is unavailable: {fixture_path.name}"
        ) from exc
    expected_hash = hashlib.sha256(expected_bytes).hexdigest()

    source_url = f"{FIXTURE_URL}/index.html?case={case['name']}"
    payload = {
        "url": source_url,
        "download_type": case["download_type"],
        "format": case["format"],
        "codec": case["codec"],
        "quality": case["quality"],
    }
    headers = {"X-Sidecar-Api-Key": API_KEY}
    try:
        created_response = client.post(
            f"{SIDECAR_URL}/jobs", headers=headers, json=payload
        )
    except httpx.HTTPError as exc:
        raise IntegrationCheckError(f"{case['name']} submission request failed") from exc
    require(
        created_response.status_code == 202,
        f"{case['name']} submission returned HTTP {created_response.status_code}",
    )
    created = response_json(created_response, f"{case['name']} submission was not JSON")
    job_id = created.get("id")
    require(isinstance(job_id, str) and job_id, f"{case['name']} response has no job ID")
    try:
        UUID(job_id)
    except ValueError as exc:
        raise IntegrationCheckError(f"{case['name']} response has an invalid job ID") from exc
    expected_poll_path = f"/jobs/{job_id}"
    require(
        created.get("poll_url") == expected_poll_path,
        f"{case['name']} response poll path is incorrect",
    )

    deadline = time.monotonic() + CASE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            polled_response = client.get(
                f"{SIDECAR_URL}{expected_poll_path}", headers=headers
            )
        except httpx.HTTPError as exc:
            raise IntegrationCheckError(f"{case['name']} poll request failed") from exc
        require(
            polled_response.status_code == 200,
            f"{case['name']} poll returned HTTP {polled_response.status_code}",
        )
        polled = response_json(polled_response, f"{case['name']} poll was not JSON")
        require(polled.get("status") in {"queued", "downloading", "complete", "failed"},
                f"{case['name']} poll returned an unknown job state")
        if polled.get("status") in {"complete", "failed"}:
            break
        time.sleep(POLL_INTERVAL_SECONDS)
    else:
        raise IntegrationCheckError(
            f"{case['name']} job did not finish within {CASE_TIMEOUT_SECONDS}s"
        )

    require(
        polled.get("status") == "complete",
        f"{case['name']} job ended in {polled.get('status', 'unknown')} state",
    )
    expected_file_path = f"/jobs/{job_id}/file"
    require(
        polled.get("file_url") == expected_file_path,
        f"{case['name']} response file path is incorrect",
    )
    try:
        file_response = client.get(
            f"{SIDECAR_URL}{expected_file_path}", headers=headers
        )
    except httpx.HTTPError as exc:
        raise IntegrationCheckError(f"{case['name']} file request failed") from exc
    require(
        file_response.status_code == 200,
        f"{case['name']} file request returned HTTP {file_response.status_code}",
    )
    require(
        file_response.headers.get("content-type", "").split(";", 1)[0]
        == case["content_type"],
        f"{case['name']} file has an unexpected MIME type",
    )
    actual_hash = hashlib.sha256(file_response.content).hexdigest()
    require(
        actual_hash == expected_hash,
        f"{case['name']} downloaded bytes do not match the synthetic fixture",
    )

    metadata_path = STATE_DIR / f"{job_id}.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrationCheckError(
            f"{case['name']} persisted job metadata is unavailable or invalid"
        ) from exc
    require(
        isinstance(metadata, dict),
        f"{case['name']} persisted metadata is not an object",
    )
    require(
        metadata.get("download_type") == case["download_type"],
        f"{case['name']} persisted download type is incorrect",
    )
    require(
        source_url not in metadata_path.read_text(encoding="utf-8"),
        f"{case['name']} persisted metadata contains the submitted URL",
    )

    return {
        "case": case["name"],
        "status": polled["status"],
        "content_type": case["content_type"],
        "bytes": len(file_response.content),
        "sha256": actual_hash,
        "metadata_type": metadata["download_type"],
        "url_persisted": False,
    }


def main() -> int:
    try:
        with httpx.Client(timeout=5) as client:
            wait_until_ready(client)
            print(
                json.dumps(
                    {"phase": "ready", "services": ["metube", "fixture", "sidecar"]},
                    sort_keys=True,
                ),
                flush=True,
            )
            for case in CASES:
                evidence = check_case(client, case)
                print(json.dumps(evidence, sort_keys=True), flush=True)
    except IntegrationCheckError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True))
        return 1
    except httpx.HTTPError as exc:
        print(
            json.dumps(
                {"status": "failed", "error": f"HTTP client failure: {type(exc).__name__}"},
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps({"status": "passed", "cases": len(CASES)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
