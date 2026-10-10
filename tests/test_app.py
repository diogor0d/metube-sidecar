from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

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
        "bridge_api_key": None,
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
        assert '"quality":"best"' in payload

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


def test_legacy_metube_options_are_forwarded_without_new_schema_fields(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    app = create_app(settings_for(tmp_path), accepting_transport(captured))

    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            json={
                "url": "https://example.com/video",
                "quality": "best_ios",
                "format": "mp4",
                "codec": "h264",
            },
        )

    assert response.status_code == 202
    payload = json.loads(str(captured["json"]))
    assert payload["quality"] == "best_ios"
    assert payload["format"] == "mp4"
    assert payload["video_codec"] == "h264"
    assert "download_type" not in payload
    assert "codec" not in payload
    assert payload["folder"].startswith("sidecar/")


def test_legacy_audio_format_is_left_for_metube_to_migrate(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    app = create_app(settings_for(tmp_path), accepting_transport(captured))

    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            json={
                "url": "https://example.com/video",
                "quality": "best",
                "format": "m4a",
            },
        )

    assert response.status_code == 202
    payload = json.loads(str(captured["json"]))
    assert payload["quality"] == "best"
    assert payload["format"] == "m4a"
    assert "download_type" not in payload


def test_thumbnail_job_completes_and_delivers_jpeg(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    settings = settings_for(tmp_path)
    app = create_app(settings, accepting_transport(captured))

    with TestClient(app) as client:
        created = client.post(
            "/jobs",
            json={
                "url": "https://example.com/video",
                "download_type": "thumbnail",
                "format": "jpg",
                "codec": "auto",
                "quality": "best",
            },
        )
        assert created.status_code == 202
        job_id = created.json()["id"]
        payload = json.loads(str(captured["json"]))
        assert payload["download_type"] == "thumbnail"
        assert payload["format"] == "jpg"
        assert payload["codec"] == "auto"

        metadata = next((settings.data_dir / "jobs").glob("*.json"))
        saved_job = json.loads(metadata.read_text(encoding="utf-8"))
        assert saved_job["download_type"] == "thumbnail"
        assert "https://example.com/video" not in metadata.read_text(encoding="utf-8")

        output_dir = settings.downloads_dir / "sidecar" / job_id
        output_dir.mkdir(parents=True)
        image = output_dir / "thumbnail.jpg"
        image.write_bytes(b"jpeg-data")
        (output_dir / "unrelated.mp4").write_bytes(b"video-data-that-is-larger")

        completed = client.get(f"/jobs/{job_id}")
        delivered = client.get(f"/jobs/{job_id}/file")

    assert completed.json()["status"] == "complete"
    assert delivered.content == b"jpeg-data"
    assert "image/jpeg" in delivered.headers["content-type"]


def test_video_and_audio_jobs_ignore_other_media_types(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path), accepting_transport({}))
    with TestClient(app) as client:
        video_job = client.post(
            "/jobs",
            json={"url": "https://example.com/video", "download_type": "video"},
        ).json()
        video_dir = settings_for(tmp_path).downloads_dir / "sidecar" / video_job["id"]
        video_dir.mkdir(parents=True)
        (video_dir / "thumbnail.jpg").write_bytes(b"image-is-larger")
        (video_dir / "video.mp4").write_bytes(b"video")
        video_file = client.get(f"/jobs/{video_job['id']}/file")

        audio_job = client.post(
            "/jobs",
            json={"url": "https://example.com/audio", "download_type": "audio"},
        ).json()
        audio_dir = settings_for(tmp_path).downloads_dir / "sidecar" / audio_job["id"]
        audio_dir.mkdir(parents=True)
        (audio_dir / "video.mp4").write_bytes(b"video-is-larger")
        (audio_dir / "audio.m4a").write_bytes(b"audio")
        audio_file = client.get(f"/jobs/{audio_job['id']}/file")

    assert video_file.content == b"video"
    assert audio_file.content == b"audio"


def test_job_type_persists_across_app_restart_and_old_jobs_fallback(
    tmp_path: Path,
) -> None:
    settings = settings_for(tmp_path)
    with TestClient(create_app(settings, accepting_transport({}))) as client:
        created = client.post(
            "/jobs",
            json={"url": "https://example.com/audio", "download_type": "audio"},
        ).json()
    output_dir = settings.downloads_dir / "sidecar" / created["id"]
    output_dir.mkdir(parents=True)
    (output_dir / "audio.m4a").write_bytes(b"audio")

    with TestClient(create_app(settings, accepting_transport({}))) as client:
        restored = client.get(f"/jobs/{created['id']}")
        assert restored.json()["status"] == "complete"
        assert client.get(f"/jobs/{created['id']}/file").content == b"audio"

        old_id = str(uuid4())
        old_created_at = datetime.now(timezone.utc).isoformat()
        old_dir = settings.downloads_dir / "sidecar" / old_id
        old_dir.mkdir(parents=True)
        (old_dir / "old-audio.mp3").write_bytes(b"old-audio")
        old_record = {
            "id": old_id,
            "status": "queued",
            "created_at": old_created_at,
            "updated_at": old_created_at,
            "error": None,
        }
        (settings.data_dir / "jobs" / f"{old_id}.json").write_text(
            json.dumps(old_record), encoding="utf-8"
        )
        old_response = client.get(f"/jobs/{old_id}")

    assert old_response.json()["status"] == "complete"


def test_video_resolution_label_is_normalized(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    app = create_app(settings_for(tmp_path), accepting_transport(captured))
    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            json={
                "url": "https://example.com/video",
                "download_type": "video",
                "quality": "1080p",
            },
        )

    assert response.status_code == 202
    assert json.loads(str(captured["json"]))["quality"] == "1080"


def test_video_quality_aliases_are_preserved(tmp_path: Path) -> None:
    for quality in ("best_ios", "best", "1080"):
        captured: dict[str, object] = {}
        app = create_app(settings_for(tmp_path / quality), accepting_transport(captured))
        with TestClient(app) as client:
            response = client.post(
                "/jobs",
                json={"url": "https://example.com/video", "quality": quality},
            )
        assert response.status_code == 202
        assert json.loads(str(captured["json"]))["quality"] == quality


def test_temporary_file_resets_stability_observation(
    tmp_path: Path, monkeypatch
) -> None:
    settings = settings_for(tmp_path, stable_seconds=5)
    app = create_app(settings, accepting_transport({}))
    with TestClient(app) as client:
        created = client.post(
            "/jobs", json={"url": "https://example.com/video"}
        ).json()
        created_at = datetime.fromisoformat(created["created_at"]).timestamp()
        current_time = [created_at]
        monkeypatch.setattr("app.main.time.time", lambda: current_time[0])
        output_dir = settings.downloads_dir / "sidecar" / created["id"]
        output_dir.mkdir(parents=True)
        (output_dir / "video.mp4").write_bytes(b"stable")

        assert client.get(f"/jobs/{created['id']}").json()["status"] == "downloading"
        current_time[0] = created_at + 4
        assert client.get(f"/jobs/{created['id']}").json()["status"] == "downloading"

        (output_dir / "video.mp4.part").write_bytes(b"still-writing")
        current_time[0] = created_at + 6
        assert client.get(f"/jobs/{created['id']}").json()["status"] == "downloading"
        (output_dir / "video.mp4.part").unlink()

        current_time[0] = created_at + 10
        assert client.get(f"/jobs/{created['id']}").json()["status"] == "downloading"
        current_time[0] = created_at + 14
        assert client.get(f"/jobs/{created['id']}").json()["status"] == "downloading"
        current_time[0] = created_at + 15
        assert client.get(f"/jobs/{created['id']}").json()["status"] == "complete"


def test_legacy_partial_options_use_sidecar_defaults(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    app = create_app(settings_for(tmp_path), accepting_transport(captured))

    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            json={
                "url": "https://example.com/video",
                "quality": "1080",
            },
        )

    assert response.status_code == 202
    payload = json.loads(str(captured["json"]))
    assert payload["quality"] == "1080"
    assert payload["format"] == "ios"
    assert payload["video_codec"] == "h264"
    assert "download_type" not in payload


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


def test_internal_bridge_routes_require_bridge_key_and_serve_job_content(
    tmp_path: Path,
) -> None:
    settings = settings_for(tmp_path, bridge_api_key="bridge-secret")
    app = create_app(settings, accepting_transport({}))
    request = {"url": "https://example.com/video"}

    with TestClient(app) as client:
        missing = client.post("/internal/jobs", json=request)
        wrong = client.post(
            "/internal/jobs",
            headers={"X-Sidecar-Bridge-Key": "wrong"},
            json=request,
        )
        headers = {"X-Sidecar-Bridge-Key": "bridge-secret"}
        created = client.post("/internal/jobs", headers=headers, json=request)
        assert created.status_code == 202
        job_id = created.json()["id"]

        output_dir = settings.downloads_dir / "sidecar" / job_id
        output_dir.mkdir(parents=True)
        (output_dir / "video.mp4").write_bytes(b"bridge-video")

        status_response = client.get(f"/internal/jobs/{job_id}", headers=headers)
        content = client.get(f"/internal/jobs/{job_id}/download", headers=headers)
        denied_status = client.get(f"/internal/jobs/{job_id}")
        denied_content = client.get(f"/internal/jobs/{job_id}/download")

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert status_response.json()["status"] == "complete"
    assert content.status_code == 200
    assert content.content == b"bridge-video"
    assert denied_status.status_code == 401
    assert denied_content.status_code == 401


def test_internal_bridge_routes_are_unavailable_without_bridge_key(tmp_path: Path) -> None:
    app = create_app(settings_for(tmp_path), accepting_transport({}))
    with TestClient(app) as client:
        created = client.post("/internal/jobs", json={"url": "https://example.com/video"})
        status_response = client.get(f"/internal/jobs/{uuid4()}")
        content = client.get(f"/internal/jobs/{uuid4()}/download")
    assert created.status_code == 404
    assert status_response.status_code == 404
    assert content.status_code == 404


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


def test_request_id_is_canonical_and_duplicate_does_not_resubmit(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    submission_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submission_count
        submission_count += 1
        captured.update(request=request, json=request.read().decode("utf-8"))
        return httpx.Response(200, json={"status": "ok"})

    settings = settings_for(tmp_path)
    app = create_app(settings, httpx.MockTransport(handler))
    request_id = str(uuid4())
    request = {
        "request_id": request_id,
        "url": "https://example.com/synthetic-source",
    }

    with TestClient(app) as client:
        first = client.post("/jobs", json=request)
        output_dir = settings.downloads_dir / "sidecar" / request_id
        output_dir.mkdir(parents=True)
        (output_dir / "output.mp4").write_bytes(b"finished")
        duplicate = client.post(
            "/jobs",
            json={**request, "url": "https://example.com/different-source"},
        )

    assert first.status_code == 202
    assert first.json()["id"] == request_id
    assert duplicate.status_code == 202
    assert duplicate.json()["id"] == request_id
    assert duplicate.json()["status"] == "complete"
    assert duplicate.json()["submission_unknown"] is False
    assert submission_count == 1
    metadata = settings.data_dir / "jobs" / f"{request_id}.json"
    saved = metadata.read_text(encoding="utf-8")
    assert "synthetic-source" not in saved
    assert "different-source" not in saved


def test_concurrent_request_id_posts_reserve_before_me_tube_add(tmp_path: Path) -> None:
    async def run() -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        submission_count = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal submission_count
            submission_count += 1
            started.set()
            await release.wait()
            return httpx.Response(200, json={"status": "ok"})

        settings = settings_for(tmp_path)
        app = create_app(settings, httpx.MockTransport(handler))
        request_id = str(uuid4())
        body = {
            "request_id": request_id,
            "url": "https://example.com/synthetic-source",
        }
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://sidecar") as client:
            original = asyncio.create_task(client.post("/jobs", json=body))
            await asyncio.wait_for(started.wait(), timeout=2)
            duplicate = await client.post("/jobs", json=body)
            assert duplicate.status_code == 202
            assert duplicate.json()["id"] == request_id
            assert duplicate.json()["status"] == "queued"
            assert duplicate.json()["submission_unknown"] is True
            assert submission_count == 1
            release.set()
            accepted = await original
        assert accepted.status_code == 202
        assert accepted.json()["submission_unknown"] is False
        assert submission_count == 1

    asyncio.run(run())


def test_ambiguous_add_timeout_stays_pending_and_duplicate_never_resubmits(
    tmp_path: Path,
) -> None:
    submission_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submission_count
        submission_count += 1
        raise httpx.ReadTimeout("synthetic response timeout", request=request)

    settings = settings_for(tmp_path, job_timeout_seconds=60)
    app = create_app(settings, httpx.MockTransport(handler))
    request_id = str(uuid4())
    body = {"request_id": request_id, "url": "https://example.com/synthetic-source"}

    with TestClient(app) as client:
        created = client.post("/jobs", json=body)
        assert created.status_code == 202
        assert created.json()["status"] == "queued"
        assert created.json()["submission_unknown"] is True

        duplicate = client.post("/jobs", json=body)
        assert duplicate.status_code == 202
        assert duplicate.json()["id"] == request_id
        assert duplicate.json()["submission_unknown"] is True

        output_dir = settings.downloads_dir / "sidecar" / request_id
        output_dir.mkdir(parents=True)
        still_pending = client.get(f"/jobs/{request_id}")
        assert still_pending.json()["status"] == "downloading"
        assert still_pending.json()["submission_unknown"] is True

        (output_dir / "late-output.mp4").write_bytes(b"late-output")
        completed = client.get(f"/jobs/{request_id}")

    assert completed.json()["status"] == "complete"
    assert completed.json()["submission_unknown"] is False
    assert submission_count == 1


def test_orphaned_submission_reservation_recovers_as_unknown_without_retry(
    tmp_path: Path,
) -> None:
    submission_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submission_count
        submission_count += 1
        return httpx.Response(200, json={"status": "ok"})

    settings = settings_for(tmp_path, job_timeout_seconds=60)
    request_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    metadata = settings.data_dir / "jobs" / f"{request_id}.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        json.dumps(
            {
                "id": request_id,
                "status": "queued",
                "created_at": created_at,
                "updated_at": created_at,
                "error": None,
                "submission_state": "submitting",
                "submission_unknown": False,
            }
        ),
        encoding="utf-8",
    )
    app = create_app(settings, httpx.MockTransport(handler))

    with TestClient(app) as client:
        recovered = client.get(f"/jobs/{request_id}")
        duplicate = client.post(
            "/jobs",
            json={"request_id": request_id, "url": "https://example.com/video"},
        )

    assert recovered.status_code == 200
    assert recovered.json()["status"] == "queued"
    assert recovered.json()["submission_unknown"] is True
    assert duplicate.status_code == 202
    assert duplicate.json()["submission_unknown"] is True
    assert submission_count == 0


def test_orphaned_uncertain_submission_fails_safely_after_deadline(
    tmp_path: Path, monkeypatch
) -> None:
    submission_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submission_count
        submission_count += 1
        raise httpx.ReadTimeout("synthetic response timeout", request=request)

    settings = settings_for(tmp_path, job_timeout_seconds=1)
    app = create_app(settings, httpx.MockTransport(handler))
    request_id = str(uuid4())
    body = {"request_id": request_id, "url": "https://example.com/synthetic-source"}
    with TestClient(app) as client:
        created = client.post("/jobs", json=body)
        assert created.status_code == 202
        assert created.json()["submission_unknown"] is True

        created_at = datetime.fromisoformat(created.json()["created_at"]).timestamp()
        monkeypatch.setattr("app.main.time.time", lambda: created_at + 60)
        expired = client.get(f"/jobs/{request_id}")
        duplicate = client.post("/jobs", json=body)

    assert expired.json()["status"] == "failed"
    assert expired.json()["error"] == "Submission could not be confirmed before timeout"
    assert expired.json()["submission_unknown"] is True
    assert duplicate.json()["status"] == "failed"
    assert duplicate.json()["error"] == "Submission could not be confirmed before timeout"
    assert submission_count == 1


def test_confirmed_me_tube_rejection_is_saved_failed_and_not_retried(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def reject(request: httpx.Request) -> httpx.Response:
        captured["called"] = captured.get("called", 0) + 1
        return httpx.Response(400, json={"detail": "rejected"})

    request_id = str(uuid4())
    app = create_app(settings_for(tmp_path), httpx.MockTransport(reject))
    with TestClient(app) as client:
        rejected = client.post(
            "/jobs",
            json={"request_id": request_id, "url": "https://example.com/video"},
        )
        duplicate = client.post(
            "/jobs",
            json={"request_id": request_id, "url": "https://example.com/video"},
        )

    assert rejected.status_code == 502
    assert duplicate.status_code == 202
    assert duplicate.json()["status"] == "failed"
    assert duplicate.json()["submission_unknown"] is False
    assert captured["called"] == 1


def test_request_id_rejects_noncanonical_uuid_before_submission(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    app = create_app(settings_for(tmp_path), accepting_transport(captured))
    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            json={"request_id": str(uuid4()).upper(), "url": "https://example.com/video"},
        )
    assert response.status_code == 422
    assert captured == {}
