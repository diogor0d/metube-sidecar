from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator


JobStatus = Literal["queued", "downloading", "complete", "failed"]

VIDEO_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".mov",
    ".webm",
    ".mkv",
}
AUDIO_EXTENSIONS = {
    ".mp3",
    ".m4a",
    ".opus",
    ".ogg",
    ".wav",
    ".flac",
    ".aac",
}
THUMBNAIL_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
TEMPORARY_SUFFIXES = {
    ".part",
    ".tmp",
    ".temp",
    ".ytdl",
    ".download",
    ".aria2",
}


class MeTubeRejectedError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    metube_url: str = "http://metube:8081"
    downloads_dir: Path = Path("/downloads")
    data_dir: Path = Path("/data")
    job_subdir: str = "sidecar"
    stable_seconds: float = 5.0
    job_timeout_seconds: float = 3600.0
    metube_timeout_seconds: float = 20.0
    api_key: str | None = None
    bridge_api_key: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            metube_url=os.getenv("METUBE_URL", cls.metube_url).rstrip("/"),
            downloads_dir=Path(os.getenv("DOWNLOADS_DIR", str(cls.downloads_dir))),
            data_dir=Path(os.getenv("DATA_DIR", str(cls.data_dir))),
            job_subdir=os.getenv("JOB_SUBDIR", cls.job_subdir).strip("/"),
            stable_seconds=float(os.getenv("STABLE_SECONDS", str(cls.stable_seconds))),
            job_timeout_seconds=float(
                os.getenv("JOB_TIMEOUT_SECONDS", str(cls.job_timeout_seconds))
            ),
            metube_timeout_seconds=float(
                os.getenv("METUBE_TIMEOUT_SECONDS", str(cls.metube_timeout_seconds))
            ),
            api_key=os.getenv("SIDECAR_API_KEY") or None,
            bridge_api_key=os.getenv("SIDECAR_BRIDGE_API_KEY") or None,
        )


class JobCreate(BaseModel):
    request_id: str | None = Field(default=None, min_length=36, max_length=36)
    url: str = Field(min_length=1, max_length=4096)
    quality: str = Field(default="best", min_length=1, max_length=64)
    format: str = Field(default="ios", min_length=1, max_length=64)
    download_type: Literal["video", "audio", "thumbnail"] = "video"
    codec: str = Field(default="h264", min_length=1, max_length=64)
    video_codec: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be an absolute HTTP or HTTPS URL")
        return value

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            parsed = UUID(value)
        except ValueError as exc:
            raise ValueError("request_id must be a canonical UUID") from exc
        if str(parsed) != value:
            raise ValueError("request_id must be a canonical UUID")
        return value

    @field_validator("quality")
    @classmethod
    def normalize_resolution_label(cls, value: str) -> str:
        match = re.fullmatch(r"(\d+)p", value, flags=re.IGNORECASE)
        return match.group(1) if match else value


class JobResponse(BaseModel):
    id: str
    status: JobStatus
    created_at: str
    updated_at: str
    error: str | None = None
    submission_unknown: bool = False
    poll_url: str
    file_url: str | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_job_id(job_id: str) -> str:
    try:
        parsed = UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    if str(parsed) != job_id:
        raise HTTPException(status_code=404, detail="job not found")
    return job_id


class JobStore:
    def __init__(self, data_dir: Path) -> None:
        self.jobs_dir = data_dir / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{canonical_job_id(job_id)}.json"

    def load(self, job_id: str) -> dict[str, Any]:
        path = self._path(job_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=500, detail="job state is unreadable") from exc

    def save(self, job: dict[str, Any]) -> None:
        path = self._path(job["id"])
        temporary_path = path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(job, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary_path, path)


def public_job(job: dict[str, Any]) -> JobResponse:
    complete = job["status"] == "complete"
    return JobResponse(
        id=job["id"],
        status=job["status"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        error=job.get("error"),
        submission_unknown=bool(
            job.get("submission_unknown") or job.get("submission_state") == "unknown"
        ),
        poll_url=f"/jobs/{job['id']}",
        file_url=f"/jobs/{job['id']}/file" if complete else None,
    )


def job_directory(settings: Settings, job_id: str) -> Path:
    return settings.downloads_dir / settings.job_subdir / job_id


def metube_payload(
    request: JobCreate,
    settings: Settings,
    job_id: str,
) -> dict[str, str]:
    supplied_fields = request.model_fields_set
    folder = f"{settings.job_subdir}/{job_id}"

    # MeTube's legacy /add schema infers download_type, codec, and output format
    # from quality/format/video_codec. Preserve those semantics for existing
    # Shortcuts that previously posted directly to MeTube. The job folder remains
    # sidecar-controlled so the resulting file can be correlated safely.
    legacy_fields = {"quality", "format", "codec", "video_codec"}
    if "download_type" not in supplied_fields and supplied_fields & legacy_fields:
        return {
            "url": request.url,
            "quality": request.quality,
            "format": request.format,
            "video_codec": request.video_codec or request.codec,
            "folder": folder,
        }

    return {
        "url": request.url,
        "quality": request.quality,
        "format": request.format,
        "download_type": request.download_type,
        "codec": request.codec,
        "folder": folder,
    }


def requested_download_type(request: JobCreate) -> str:
    if "download_type" in request.model_fields_set:
        return request.download_type
    # Legacy MeTube requests used the output format to select audio downloads.
    if request.format.lower() in {"auto", "m4a", "mp3", "opus", "wav", "flac"}:
        return "audio"
    return "video"


def output_extensions(job: dict[str, Any]) -> set[str]:
    download_type = job.get("download_type")
    if download_type == "video":
        return VIDEO_EXTENSIONS
    if download_type == "audio":
        return AUDIO_EXTENSIONS
    if download_type == "thumbnail":
        return THUMBNAIL_EXTENSIONS
    # Older persisted records have no download_type and used the combined
    # video/audio extension set. Keep accepting those records after upgrade.
    return VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


def is_temporary(path: Path) -> bool:
    lower_name = path.name.lower()
    return any(lower_name.endswith(suffix) for suffix in TEMPORARY_SUFFIXES)


def fail_job(job: dict[str, Any], message: str) -> bool:
    job.update(status="failed", error=message, updated_at=utc_now_iso())
    return True


def mark_submission_accepted_from_output(job: dict[str, Any]) -> None:
    # A stable, supported output in this job's UUID-scoped directory is evidence;
    # directory existence alone can be stale and never clears submission_unknown.
    if job.get("submission_state") in {"submitting", "unknown"}:
        job.update(submission_state="accepted", submission_unknown=False)


def refresh_job(job: dict[str, Any], settings: Settings) -> bool:
    if job["status"] in {"complete", "failed"}:
        return False

    now = time.time()
    created_at = datetime.fromisoformat(job["created_at"]).timestamp()
    if now - created_at > settings.job_timeout_seconds:
        if job.get("submission_state") in {"submitting", "unknown"}:
            job.update(
                status="failed",
                error="Submission could not be confirmed before timeout",
                submission_state="unknown",
                submission_unknown=True,
                updated_at=utc_now_iso(),
            )
            return True
        return fail_job(job, "download timed out")

    directory = job_directory(settings, job["id"])
    if not directory.is_dir():
        return False

    files = [path for path in directory.rglob("*") if path.is_file()]
    if any(is_temporary(path) for path in files):
        had_observation = any(
            key in job
            for key in (
                "observed_path",
                "observed_size",
                "observed_mtime_ns",
                "stable_since",
            )
        )
        job.pop("observed_path", None)
        job.pop("observed_size", None)
        job.pop("observed_mtime_ns", None)
        job.pop("stable_since", None)
        changed = job.get("status") != "downloading"
        if changed:
            job.update(status="downloading", updated_at=utc_now_iso())
        return changed or had_observation

    candidates = [
        path for path in files if path.suffix.lower() in output_extensions(job)
    ]
    if not candidates:
        if job["status"] != "downloading":
            job.update(status="downloading", updated_at=utc_now_iso())
            return True
        had_observation = any(
            key in job
            for key in (
                "observed_path",
                "observed_size",
                "observed_mtime_ns",
                "stable_since",
            )
        )
        for key in (
            "observed_path",
            "observed_size",
            "observed_mtime_ns",
            "stable_since",
        ):
            job.pop(key, None)
        return had_observation

    candidate = max(candidates, key=lambda path: path.stat().st_size)
    candidate_stat = candidate.stat()
    relative_path = str(candidate.relative_to(directory))
    unchanged = (
        job.get("observed_path") == relative_path
        and job.get("observed_size") == candidate_stat.st_size
        and job.get("observed_mtime_ns") == candidate_stat.st_mtime_ns
    )

    if not unchanged:
        job.update(
            status="downloading",
            observed_path=relative_path,
            observed_size=candidate_stat.st_size,
            observed_mtime_ns=candidate_stat.st_mtime_ns,
            stable_since=now,
            updated_at=utc_now_iso(),
        )
        if settings.stable_seconds <= 0:
            job.update(status="complete", filename=relative_path, updated_at=utc_now_iso())
            mark_submission_accepted_from_output(job)
        return True

    if now - float(job["stable_since"]) >= settings.stable_seconds:
        job.update(
            status="complete",
            filename=relative_path,
            updated_at=utc_now_iso(),
        )
        mark_submission_accepted_from_output(job)
        return True

    return False


def resolved_file(job: dict[str, Any], settings: Settings) -> Path:
    directory = job_directory(settings, job["id"]).resolve()
    path = (directory / job["filename"]).resolve()
    try:
        path.relative_to(directory)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="unsafe stored file path") from exc
    if not path.is_file():
        raise HTTPException(status_code=410, detail="downloaded file is no longer available")
    return path


def create_app(
    settings: Settings | None = None,
    metube_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()
    store = JobStore(active_settings.data_dir)
    lock = asyncio.Lock()

    application = FastAPI(title="MeTube Sidecar", version="0.1.0")

    async def require_api_key(
        x_sidecar_api_key: str | None = Header(default=None),
    ) -> None:
        expected = active_settings.api_key
        if expected is None:
            return
        if x_sidecar_api_key is None or not secrets.compare_digest(
            x_sidecar_api_key, expected
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid sidecar API key",
            )

    async def require_bridge_api_key(
        x_sidecar_bridge_key: str | None = Header(
            default=None, alias="X-Sidecar-Bridge-Key"
        ),
    ) -> None:
        expected = active_settings.bridge_api_key
        if expected is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        if x_sidecar_bridge_key is None or not secrets.compare_digest(
            x_sidecar_bridge_key, expected
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid sidecar API key",
            )

    @application.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    async def latest_public_job(job_id: str) -> JobResponse:
        async with lock:
            current = store.load(job_id)
            changed = False
            if current.get("submission_state") == "submitting":
                current.update(
                    submission_state="unknown",
                    submission_unknown=True,
                    updated_at=utc_now_iso(),
                )
                changed = True
            if refresh_job(current, active_settings):
                changed = True
            if changed:
                store.save(current)
            return public_job(current)

    @application.post(
        "/internal/jobs",
        response_model=JobResponse,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_bridge_api_key)],
    )
    @application.post(
        "/jobs",
        response_model=JobResponse,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_api_key)],
    )
    async def create_job(request: JobCreate) -> JobResponse:
        job_id = request.request_id or str(uuid4())
        now = utc_now_iso()
        job: dict[str, Any] = {
            "id": job_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "error": None,
            "download_type": requested_download_type(request),
            "submission_state": "submitting",
            "submission_unknown": False,
        }
        async with lock:
            if request.request_id:
                try:
                    existing = store.load(job_id)
                except HTTPException as exc:
                    if exc.status_code != 404:
                        raise
                else:
                    if existing.get("submission_state") == "submitting":
                        existing.update(
                            submission_state="unknown",
                            submission_unknown=True,
                            updated_at=utc_now_iso(),
                        )
                    if refresh_job(existing, active_settings):
                        store.save(existing)
                    elif existing.get("submission_state") == "unknown":
                        store.save(existing)
                    return public_job(existing)
            payload = metube_payload(request, active_settings, job_id)
            store.save(job)

        try:
            async with httpx.AsyncClient(
                transport=metube_transport,
                timeout=active_settings.metube_timeout_seconds,
            ) as client:
                response = await client.post(
                    f"{active_settings.metube_url}/add", json=payload
                )
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict) or result.get("status") != "ok":
                    raise MeTubeRejectedError
            async with lock:
                current = store.load(job_id)
                current.update(
                    submission_state="accepted",
                    submission_unknown=False,
                    updated_at=utc_now_iso(),
                )
                store.save(current)
        except MeTubeRejectedError as exc:
            async with lock:
                current = store.load(job_id)
                fail_job(current, "MeTube rejected the download request")
                current.update(submission_state="rejected", submission_unknown=False)
                store.save(current)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="MeTube rejected the download request",
            ) from exc
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            async with lock:
                current = store.load(job_id)
                fail_job(current, "MeTube could not be reached")
                current.update(submission_state="not_submitted", submission_unknown=False)
                store.save(current)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="MeTube could not be reached",
            ) from exc
        except httpx.HTTPStatusError as exc:
            if 400 <= exc.response.status_code < 500:
                async with lock:
                    current = store.load(job_id)
                    fail_job(current, "MeTube rejected the download request")
                    current.update(submission_state="rejected", submission_unknown=False)
                    store.save(current)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="MeTube rejected the download request",
                ) from exc
            async with lock:
                current = store.load(job_id)
                current.update(
                    status="queued",
                    error=None,
                    submission_state="unknown",
                    submission_unknown=True,
                    updated_at=utc_now_iso(),
                )
                store.save(current)
        except (httpx.HTTPError, ValueError):
            async with lock:
                current = store.load(job_id)
                current.update(
                    status="queued",
                    error=None,
                    submission_state="unknown",
                    submission_unknown=True,
                    updated_at=utc_now_iso(),
                )
                store.save(current)

        return await latest_public_job(job_id)

    @application.get(
        "/internal/jobs/{job_id}",
        response_model=JobResponse,
        dependencies=[Depends(require_bridge_api_key)],
    )
    @application.get(
        "/jobs/{job_id}",
        response_model=JobResponse,
        dependencies=[Depends(require_api_key)],
    )
    async def get_job(job_id: str) -> JobResponse:
        return await latest_public_job(job_id)

    @application.get(
        "/internal/jobs/{job_id}/download",
        response_class=FileResponse,
        dependencies=[Depends(require_bridge_api_key)],
    )
    @application.get(
        "/jobs/{job_id}/file",
        response_class=FileResponse,
        dependencies=[Depends(require_api_key)],
    )
    async def get_file(job_id: str) -> FileResponse:
        async with lock:
            job = store.load(job_id)
            if refresh_job(job, active_settings):
                store.save(job)
        if job["status"] != "complete":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"download is {job['status']}",
            )
        path = resolved_file(job, active_settings)
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, filename=path.name, media_type=media_type)

    return application


app = create_app()
