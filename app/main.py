from __future__ import annotations

import asyncio
import json
import mimetypes
import os
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

OUTPUT_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".mov",
    ".webm",
    ".mkv",
    ".mp3",
    ".m4a",
    ".opus",
    ".ogg",
    ".wav",
    ".flac",
    ".aac",
}
TEMPORARY_SUFFIXES = {
    ".part",
    ".tmp",
    ".temp",
    ".ytdl",
    ".download",
    ".aria2",
}


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
        )


class JobCreate(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    quality: str = Field(default="best", min_length=1, max_length=64)
    format: str = Field(default="ios", min_length=1, max_length=64)
    download_type: Literal["video", "audio"] = "video"
    codec: str = Field(default="h264", min_length=1, max_length=64)
    video_codec: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be an absolute HTTP or HTTPS URL")
        return value


class JobResponse(BaseModel):
    id: str
    status: JobStatus
    created_at: str
    updated_at: str
    error: str | None = None
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
    legacy_fields = {"quality", "format", "video_codec"}
    if "download_type" not in supplied_fields and supplied_fields & legacy_fields:
        payload = {"url": request.url, "folder": folder}
        for field in ("quality", "format", "video_codec"):
            value = getattr(request, field)
            if field in supplied_fields and value is not None:
                payload[field] = value

        # Accept the newer field name as a convenience for legacy-shaped bodies.
        if "codec" in supplied_fields and "video_codec" not in payload:
            payload["video_codec"] = request.codec
        return payload

    return {
        "url": request.url,
        "quality": request.quality,
        "format": request.format,
        "download_type": request.download_type,
        "codec": request.codec,
        "folder": folder,
    }


def is_temporary(path: Path) -> bool:
    lower_name = path.name.lower()
    return any(lower_name.endswith(suffix) for suffix in TEMPORARY_SUFFIXES)


def fail_job(job: dict[str, Any], message: str) -> bool:
    job.update(status="failed", error=message, updated_at=utc_now_iso())
    return True


def refresh_job(job: dict[str, Any], settings: Settings) -> bool:
    if job["status"] in {"complete", "failed"}:
        return False

    now = time.time()
    created_at = datetime.fromisoformat(job["created_at"]).timestamp()
    if now - created_at > settings.job_timeout_seconds:
        return fail_job(job, "download timed out")

    directory = job_directory(settings, job["id"])
    if not directory.is_dir():
        return False

    files = [path for path in directory.rglob("*") if path.is_file()]
    if any(is_temporary(path) for path in files):
        if job["status"] != "downloading":
            job.update(status="downloading", updated_at=utc_now_iso())
            return True
        return False

    candidates = [
        path for path in files if path.suffix.lower() in OUTPUT_EXTENSIONS
    ]
    if not candidates:
        if job["status"] != "downloading":
            job.update(status="downloading", updated_at=utc_now_iso())
            return True
        return False

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
        return True

    if now - float(job["stable_since"]) >= settings.stable_seconds:
        job.update(
            status="complete",
            filename=relative_path,
            updated_at=utc_now_iso(),
        )
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

    @application.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post(
        "/jobs",
        response_model=JobResponse,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_api_key)],
    )
    async def create_job(request: JobCreate) -> JobResponse:
        job_id = str(uuid4())
        payload = metube_payload(request, active_settings, job_id)
        now = utc_now_iso()
        job: dict[str, Any] = {
            "id": job_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "error": None,
        }
        async with lock:
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
                    raise ValueError("MeTube did not accept the download")
        except (httpx.HTTPError, ValueError) as exc:
            async with lock:
                current = store.load(job_id)
                fail_job(current, "MeTube rejected the download request")
                store.save(current)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="MeTube rejected the download request",
            ) from exc

        return public_job(job)

    @application.get(
        "/jobs/{job_id}",
        response_model=JobResponse,
        dependencies=[Depends(require_api_key)],
    )
    async def get_job(job_id: str) -> JobResponse:
        async with lock:
            job = store.load(job_id)
            if refresh_job(job, active_settings):
                store.save(job)
        return public_job(job)

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
