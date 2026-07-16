from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.main import Settings, create_app


def settings_for(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "metube_url": "http://metube:8081",
        "downloads_dir": tmp_path / "downloads",
        "data_dir": tmp_path / "data",
        "job_subdir": "sidecar",
        "stable_seconds": 0,
        "job_timeout_seconds": 60,
        "metube_timeout_seconds": 5,
        "api_key": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def accepting_transport(captured: dict[str, object]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request=request, json=request.read().decode("utf-8"))
        return httpx.Response(200, json={"status": "ok"})

    return httpx.MockTransport(handler)


def test_job_lifecycle_and_file_delivery(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    settings = settings_for(tmp_path)
    app = create_app(settings, accepting_transport(captured))

    with TestClient(app) as client:
        created = client.post(
            "/jobs",
            json={"url": "https://www.youtube.com/watch?v=example"},
        )
        assert created.status_code == 202
        job = created.json()
        job_id = job["id"]
        assert job["status"] == "queued"
        assert "https://www.youtube.com/watch?v=example" not in next(
            (settings.data_dir / "jobs").glob("*.json")
        ).read_text(encoding="utf-8")

        payload = str(captured["json"])
        assert f'"folder":"sidecar/{job_id}"' in payload
        assert '"format":"ios"' in payload
        assert '"codec":"h264"' in payload

        output_dir = settings.downloads_dir / "sidecar" / job_id
        output_dir.mkdir(parents=True)
        video = output_dir / "example.mp4"
        video.write_bytes(b"video-data")

        completed = client.get(f"/jobs/{job_id}")
        assert completed.status_code == 200
        assert completed.json()["status"] == "complete"
        assert completed.json()["file_url"] == f"/jobs/{job_id}/file"

        delivered = client.get(f"/jobs/{job_id}/file")
        assert delivered.status_code == 200
        assert delivered.content == b"video-data"
        assert "attachment" in delivered.headers["content-disposition"]


def test_rejects_non_http_source_url(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path), accepting_transport({}))
    with TestClient(app) as client:
        response = client.post("/jobs", json={"url": "file:///etc/passwd"})
    assert response.status_code == 422


def test_optional_api_key_protects_job_routes(tmp_path: Path) -> None:
    app = create_app(
        settings_for(tmp_path, api_key="correct-horse-battery-staple"),
        accepting_transport({}),
    )
    with TestClient(app) as client:
        denied = client.post(
            "/jobs", json={"url": "https://example.com/video"}
        )
        accepted = client.post(
            "/jobs",
            headers={"X-Sidecar-Api-Key": "correct-horse-battery-staple"},
            json={"url": "https://example.com/video"},
        )
    assert denied.status_code == 401
    assert accepted.status_code == 202


def test_temporary_file_keeps_job_downloading(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    app = create_app(settings, accepting_transport({}))
    with TestClient(app) as client:
        created = client.post(
            "/jobs", json={"url": "https://example.com/video"}
        ).json()
        output_dir = settings.downloads_dir / "sidecar" / created["id"]
        output_dir.mkdir(parents=True)
        (output_dir / "video.mp4").write_bytes(b"partial")
        (output_dir / "video.mp4.part").write_bytes(b"still-downloading")

        status_response = client.get(f"/jobs/{created['id']}")

    assert status_response.json()["status"] == "downloading"

