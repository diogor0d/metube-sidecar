#!/usr/bin/env python3
"""Prepare native macOS Shortcut tests and a loopback-only sidecar mock.

The transformations here are deliberately test-only. They start from the
finalized public artifact and replace its blank import configuration/runtime
origin validation, output picker, notifications, poll delay, and destination
actions. The public ``validate_shortcut`` rules remain unchanged.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import plistlib
import subprocess
import sys
from uuid import NAMESPACE_URL, uuid4, uuid5
from pathlib import Path
from typing import Any

import httpx


SHORTCUTS_DIR = Path(__file__).resolve().parent
REPOSITORY_DIR = SHORTCUTS_DIR.parent
SOURCE_SHORTCUT = SHORTCUTS_DIR / "MeTube Download_unsigned.shortcut"
SYNTHETIC_CLIENT_ID = "native-test-id.access"
SYNTHETIC_CLIENT_SECRET = "native-test-secret"
SYNTHETIC_API_KEY = "native-test-api-key"
MOCK_METUBE_URL = "http://metube-mock.invalid"
FIXTURES_DIR = SHORTCUTS_DIR / "tests" / "fixtures"


def _action(action_id: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"WFWorkflowActionIdentifier": action_id,
            "WFWorkflowActionParameters": params}


def _replace_action(action: dict[str, Any], action_id: str,
                    new_values: dict[str, Any]) -> None:
    params = action.setdefault("WFWorkflowActionParameters", {})
    kept = {key: params[key] for key in ("UUID", "GroupingIdentifier")
            if key in params}
    kept.update(new_values)
    action["WFWorkflowActionIdentifier"] = action_id
    action["WFWorkflowActionParameters"] = kept


def prepare_shortcut(source: Path, target: Path, *, port: int,
                     media_mode: str, direct_cli: bool = False) -> dict[str, Any]:
    with source.open("rb") as stream:
        workflow = plistlib.load(stream)
    workflow = copy.deepcopy(workflow)
    workflow["WFWorkflowName"] = (
        f"MeTube Local Direct {media_mode}" if direct_cli
        else f"MeTube Local Test {media_mode}"
    )
    workflow["WFWorkflowImportQuestions"] = []
    workflow["WFWorkflowTypes"] = ["ActionExtension"]

    actions = workflow.get("WFWorkflowActions")
    if not isinstance(actions, list):
        raise ValueError("finalized Shortcut has no action list")
    by_output = {
        action.get("WFWorkflowActionParameters", {}).get("CustomOutputName"): action
        for action in actions
    }
    origin = f"http://127.0.0.1:{port}"
    literals = {
        "serverAddress": origin,
        "clientID": SYNTHETIC_CLIENT_ID,
        "clientSecret": SYNTHETIC_CLIENT_SECRET,
        "sidecarAPIKey": SYNTHETIC_API_KEY,
    }
    for output, literal in literals.items():
        if output not in by_output:
            raise ValueError(f"finalized Shortcut is missing {output}")
        _replace_action(by_output[output], "is.workflow.actions.gettext",
                        {"CustomOutputName": output, "WFTextActionText": literal})

    for output, literal in (("normalizedServerAddress", origin),
                            ("serverMatch", "validated")):
        if output not in by_output:
            raise ValueError(f"finalized Shortcut is missing {output}")
        _replace_action(by_output[output], "is.workflow.actions.gettext",
                        {"CustomOutputName": output, "WFTextActionText": literal})

    mode_picker = by_output.get("modeChoice")
    if mode_picker is None:
        raise ValueError("finalized Shortcut is missing modeChoice")
    _replace_action(mode_picker, "is.workflow.actions.gettext", {
        "CustomOutputName": "modeChoice", "WFTextActionText": media_mode,
    })

    delay_count = 0
    for action in actions:
        identifier = action.get("WFWorkflowActionIdentifier")
        params = action.setdefault("WFWorkflowActionParameters", {})
        if identifier == "is.workflow.actions.notification":
            _replace_action(action, "is.workflow.actions.nothing", {})
        elif identifier == "is.workflow.actions.delay":
            params["WFDelayTime"] = 1
            delay_count += 1
    if delay_count != 1:
        raise ValueError("expected exactly one polling delay")

    # Replace interactive alerts only in this disposable native test artifact.
    # The title is the fixed failure receipt; alert messages are deliberately
    # discarded so runtime response content can never reach the output.
    index = 0
    failure_count = 0
    while index < len(actions):
        action = actions[index]
        identifier = action.get("WFWorkflowActionIdentifier")
        if identifier == "is.workflow.actions.ask":
            params = action.get("WFWorkflowActionParameters", {})
            output_name = params.get("CustomOutputName")
            output_uuid = params.get("UUID")
            if not isinstance(output_name, str) or not isinstance(output_uuid, str):
                raise ValueError("URL prompt has no stable output for headless test")
            _replace_action(action, "is.workflow.actions.gettext", {
                "CustomOutputName": output_name,
                "UUID": output_uuid,
                "WFTextActionText": "D05/15 - URL prompt bypassed in headless test",
            })
            actions[index + 1:index + 1] = [
                _action("is.workflow.actions.output", {
                    "WFOutput": {
                        "Value": {
                            "string": "\ufffc",
                            "attachmentsByRange": {"{0, 1}": {
                                "OutputName": output_name,
                                "OutputUUID": output_uuid,
                                "Type": "ActionOutput",
                            }},
                        },
                        "WFSerializationType": "WFTextTokenString",
                    },
                }),
                _action("is.workflow.actions.nothing", {}),
                _action("is.workflow.actions.exit", {}),
            ]
            failure_count += 1
            index += 4
            continue
        if identifier != "is.workflow.actions.alert":
            index += 1
            continue
        params = action.get("WFWorkflowActionParameters", {})
        title = params.get("WFAlertActionTitle")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("failure alert has no deterministic title")
        output_name = f"NativeTestErrorReceipt{failure_count}"
        receipt_uuid = str(uuid5(NAMESPACE_URL, f"native-test/{title}"))
        _replace_action(action, "is.workflow.actions.gettext", {
            "CustomOutputName": output_name,
            "UUID": receipt_uuid,
            "WFTextActionText": title,
        })
        actions[index + 1:index + 1] = [
            _action("is.workflow.actions.output", {
                "WFOutput": {
                    "Value": {
                        "string": "\ufffc",
                        "attachmentsByRange": {"{0, 1}": {
                            "OutputName": output_name,
                            "OutputUUID": receipt_uuid,
                            "Type": "ActionOutput",
                        }},
                    },
                    "WFSerializationType": "WFTextTokenString",
                },
            }),
            _action("is.workflow.actions.nothing", {}),
            _action("is.workflow.actions.exit", {}),
        ]
        failure_count += 1
        index += 4
    if failure_count == 0:
        raise ValueError("finalized Shortcut has no failure alerts")

    if direct_cli:
        links = [action for action in actions
                 if action.get("WFWorkflowActionIdentifier") == "is.workflow.actions.detect.link"]
        text_actions = [action for action in actions
                        if action.get("WFWorkflowActionIdentifier") == "is.workflow.actions.detect.text"]
        if len(links) != 3 or len(text_actions) != 1:
            raise ValueError("direct CLI test requires the production three-stage URL path")
        text_params = text_actions[0]["WFWorkflowActionParameters"]
        if text_params.get("WFInput") != {
            "Value": {"Type": "ExtensionInput"},
            "WFSerializationType": "WFTextTokenAttachment",
        }:
            raise ValueError("direct CLI fallback must read the raw extension input")

    destination_index = next((index for index, action in enumerate(actions)
        if action.get("WFWorkflowActionParameters", {}).get("CustomOutputName")
        == "destinationOptions"), None)
    if destination_index is None:
        raise ValueError("finalized Shortcut is missing destination selection")
    del actions[destination_index:]
    actions.append(_action("is.workflow.actions.output", {
        "WFOutput": {
            "Value": {"string": "\ufffc", "attachmentsByRange": {"{0, 1}": {
                "Type": "Variable", "VariableName": "finalFile",
            }}},
            "WFSerializationType": "WFTextTokenString",
        },
    }))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as stream:
        plistlib.dump(workflow, stream, sort_keys=False)
    return workflow


def prepare_driver(target: Path, *, media_mode: str) -> dict[str, Any]:
    """Build a native test driver that supplies URL text to the target shortcut."""
    shortcut_name = f"MeTube Local Test {media_mode}"
    driver_name = f"MeTube Local Driver {media_mode}"
    text_uuid = str(uuid5(NAMESPACE_URL, f"native-test/{driver_name}/url"))
    run_uuid = str(uuid5(NAMESPACE_URL, f"native-test/{driver_name}/run"))
    input_attachment = {
        "Value": {
            "OutputName": "DriverURL",
            "OutputUUID": text_uuid,
            "Type": "ActionOutput",
        },
        "WFSerializationType": "WFTextTokenAttachment",
    }
    workflow = {
        "WFWorkflowName": driver_name,
        "WFWorkflowImportQuestions": [],
        "WFWorkflowTypes": [],
        "WFWorkflowActions": [
            _action("is.workflow.actions.gettext", {
                "CustomOutputName": "DriverURL",
                "UUID": text_uuid,
                "WFTextActionText": "https://example.com/watch?v=native-test",
            }),
            _action("is.workflow.actions.runworkflow", {
                "UUID": run_uuid,
                "WFInput": input_attachment,
                "WFWorkflowName": shortcut_name,
            }),
        ],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as stream:
        plistlib.dump(workflow, stream, sort_keys=False)
    return workflow


def copy_fixtures(work_dir: Path) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    for name in ("fixture.mp4", "fixture.jpg"):
        destination = work_dir / name
        if not destination.exists():
            destination.write_bytes((FIXTURES_DIR / name).read_bytes())


def verify_work_dir(work_dir: Path) -> dict[str, Any]:
    """Check synthetic artifact hashes and request lifecycle evidence only."""
    expected = {
        "video": (work_dir / "fixture.mp4", work_dir / "video-result.mp4"),
        "thumbnail": (work_dir / "fixture.jpg", work_dir / "image-result.jpg"),
    }
    result_checks: dict[str, Any] = {}
    for media_type, (fixture, output) in expected.items():
        fixture_present = fixture.is_file()
        fixture_hash = (hashlib.sha256(fixture.read_bytes()).hexdigest()
                        if fixture_present else None)
        output_hash = (hashlib.sha256(output.read_bytes()).hexdigest()
                       if output.is_file() else None)
        result_checks[media_type] = {
            "fixture_present": fixture_present,
            "output_present": output.is_file(),
            "sha256_matches_fixture": (
                fixture_present and output.is_file() and output_hash == fixture_hash
            ),
            "sha256": output_hash,
        }

    try:
        report = json.loads((work_dir / "report.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        report = {}
    by_type = report.get("by_type", {}) if isinstance(report, dict) else {}
    if not isinstance(by_type, dict):
        by_type = {}
    request_checks: dict[str, dict[str, bool]] = {}
    for media_type in ("video", "thumbnail"):
        media_counts = by_type.get(media_type)
        if not isinstance(media_counts, dict):
            media_counts = {}
        request_checks[media_type] = {
            kind: type(media_counts.get(kind)) is int and media_counts[kind] >= 1
            for kind in ("submit", "poll", "file")
        }
    verified = (
        all(item["fixture_present"] and item["output_present"]
            and item["sha256_matches_fixture"]
            for item in result_checks.values())
        and all(all(counts.values()) for counts in request_checks.values())
    )
    return {
        "verified": verified,
        "native_shortcut_success_established": False,
        "results": result_checks,
        "request_lifecycle_present": request_checks,
    }


def run_native(work_dir: Path, port: int, timeout: float,
               lock_dir: Path = Path("/tmp/codex-shortcuts-ui.lock"), *,
               direct_cli: bool = False) -> dict[str, Any]:
    """Run imported native test Shortcuts with bounded waits.

    This never imports a Shortcut or interacts with a dialog. A timeout cancels
    only the CLI subprocess it started. The user may still need to close its
    permission dialog in Shortcuts.
    """
    if any((work_dir / name).exists() for name in
           ("video-result.mp4", "image-result.jpg", "native-run.json")):
        return {"verified": False, "reason": "stale_test_evidence"}
    owner = f"metube-sidecar-native-test {os.getpid()} {uuid4()}"
    try:
        lock_dir.mkdir()
    except FileExistsError:
        return {"verified": False, "reason": "shortcuts_ui_busy"}
    owner_file = lock_dir / "owner.txt"
    completed: list[str] = []
    outcome: dict[str, Any] = {"verified": False}
    try:
        owner_file.write_text(owner + "\n", encoding="utf-8")
        try:
            installed = set(subprocess.check_output(
                ["shortcuts", "list"], text=True, timeout=5,
                stderr=subprocess.DEVNULL,
            ).splitlines())
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            outcome["reason"] = "native_registration_check_failed"
            return outcome
        if direct_cli:
            missing = [mode for mode in ("Video", "Image")
                       if f"MeTube Local Direct {mode}" not in installed]
            shortcut_names = {mode: f"MeTube Local Direct {mode}"
                              for mode in ("Video", "Image")}
            if not (work_dir / "url-input.txt").is_file():
                outcome["reason"] = "loopback_test_setup_failed"
                outcome["detail"] = "direct_input_file_missing"
                return outcome
        else:
            missing = [mode for mode in ("Video", "Image") if any(
                f"MeTube Local {role} {mode}" not in installed
                for role in ("Test", "Driver")
            )]
            shortcut_names = {mode: f"MeTube Local Driver {mode}"
                              for mode in ("Video", "Image")}
        if missing:
            outcome.update(reason="native_shortcuts_not_registered", missing_media=missing)
            return outcome
        health = httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=3,
                          headers={"CF-Access-Client-Id": SYNTHETIC_CLIENT_ID,
                                   "CF-Access-Client-Secret": SYNTHETIC_CLIENT_SECRET,
                                   "X-Sidecar-Api-Key": SYNTHETIC_API_KEY})
        if health.status_code != 200 or health.json() != {"status": "ok"}:
            outcome["reason"] = "loopback_server_unavailable"
            return outcome
        counts = json.loads((work_dir / "report.json").read_text(encoding="utf-8"))
        if not isinstance(counts, dict) or counts.get("by_type") != {} or any(type(counts.get(kind)) is not int
                                             or counts[kind] != 0
                                             for kind in ("submit", "poll", "file")):
            outcome["reason"] = "fresh_server_required"
            return outcome
        for mode, filename in (("Video", "video-result.mp4"),
                               ("Image", "image-result.jpg")):
            print(json.dumps({"phase": "running_native_shortcut", "media": mode}), flush=True)
            try:
                command = ["shortcuts", "run", shortcut_names[mode]]
                if direct_cli:
                    command.extend(["--input-path", str(work_dir / "url-input.txt")])
                command.extend(["--output-path", str(work_dir / filename)])
                process = subprocess.run(
                    command,
                    timeout=timeout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                outcome["reason"] = "native_timeout_or_pending_dialog"
                return outcome
            if process.returncode != 0:
                outcome["reason"] = (
                    "native_direct_shortcut_failed" if direct_cli
                    else "native_driver_failed"
                )
                return outcome
            completed.append(mode)
        outcome.update(verify_work_dir(work_dir))
        outcome["native_driver_execution_succeeded"] = not direct_cli
        if direct_cli:
            outcome["native_direct_shortcut_execution_succeeded"] = True
        return outcome
    except (OSError, ValueError, httpx.HTTPError):
        outcome["reason"] = "loopback_test_setup_failed"
        return outcome
    finally:
        outcome["completed_drivers"] = completed
        try:
            if work_dir.is_dir() and (completed or "reason" in outcome):
                (work_dir / "native-run.json").write_text(json.dumps(outcome, indent=2) + "\n")
        except OSError:
            outcome.update(verified=False, evidence_write_failed=True)
        finally:
            if owner_file.exists() and owner_file.read_text().strip() == owner:
                owner_file.unlink()
                lock_dir.rmdir()


class RequestCounts:
    def __init__(self) -> None:
        self.submit = 0
        self.poll = 0
        self.file = 0
        self.by_type: dict[str, dict[str, int]] = {}

    def record(self, kind: str, media_type: str | None = None) -> None:
        setattr(self, kind, getattr(self, kind) + 1)
        if media_type:
            bucket = self.by_type.setdefault(media_type,
                {"submit": 0, "poll": 0, "file": 0})
            bucket[kind] += 1

    def report(self) -> dict[str, Any]:
        return {"submit": self.submit, "poll": self.poll, "file": self.file,
                "by_type": self.by_type}


def create_test_app(work_dir: Path, counts: RequestCounts | None = None):
    """Build the real sidecar app with an in-memory, non-network MeTube mock."""
    counts = counts or RequestCounts()
    fixture_paths = {"video": work_dir / "fixture.mp4",
                     "thumbnail": work_dir / "fixture.jpg"}
    for fixture in fixture_paths.values():
        if not fixture.is_file():
            raise FileNotFoundError(f"required test fixture is missing: {fixture.name}")
    downloads_dir = work_dir / "downloads"
    data_dir = work_dir / "jobs-data"

    async def metube_mock(request: httpx.Request) -> httpx.Response:
        if request.url.host != "metube-mock.invalid" or request.url.path != "/add":
            return httpx.Response(502, json={"error": "unexpected mock upstream"})
        payload = json.loads(request.content)
        media_type = payload.get("download_type")
        expected = {
            "video": {"format": "ios", "codec": "h264", "quality": "best"},
            "thumbnail": {"format": "jpg", "codec": "auto", "quality": "best"},
        }
        if media_type not in expected or any(
            payload.get(key) != value for key, value in expected[media_type].items()
        ):
            return httpx.Response(400, json={"status": "error"})
        folder = payload.get("folder", "")
        prefix = "sidecar/"
        job_id = folder.removeprefix(prefix)
        if not job_id or "/" in job_id or folder != prefix + job_id:
            return httpx.Response(400, json={"status": "error"})
        destination = downloads_dir / folder
        destination.mkdir(parents=True, exist_ok=True)
        fixture = fixture_paths[media_type]
        (destination / fixture.name).write_bytes(fixture.read_bytes())
        return httpx.Response(200, json={"status": "ok"})

    # Prevent importing app.main from creating its module-level default app
    # under /data if this is the first import in this process.
    env_names = ("DATA_DIR", "DOWNLOADS_DIR", "METUBE_URL", "SIDECAR_API_KEY")
    previous = {name: os.environ.get(name) for name in env_names}
    os.environ.update({"DATA_DIR": str(data_dir), "DOWNLOADS_DIR": str(downloads_dir),
        "METUBE_URL": MOCK_METUBE_URL, "SIDECAR_API_KEY": SYNTHETIC_API_KEY})
    try:
        if str(REPOSITORY_DIR) not in sys.path:
            sys.path.insert(0, str(REPOSITORY_DIR))
        from app.main import Settings, create_app  # local import, after safe env
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    settings = Settings(metube_url=MOCK_METUBE_URL, downloads_dir=downloads_dir,
        data_dir=data_dir, job_subdir="sidecar", stable_seconds=1,
        api_key=SYNTHETIC_API_KEY)
    application = create_app(settings, metube_transport=httpx.MockTransport(metube_mock))
    from fastapi.responses import JSONResponse
    report_path = work_dir / "report.json"

    def save_report() -> None:
        report_path.write_text(json.dumps(counts.report(), indent=2) + "\n",
                               encoding="utf-8")

    @application.middleware("http")
    async def require_synthetic_auth_and_count(request, call_next):
        expected_headers = {
            "cf-access-client-id": SYNTHETIC_CLIENT_ID,
            "cf-access-client-secret": SYNTHETIC_CLIENT_SECRET,
            "x-sidecar-api-key": SYNTHETIC_API_KEY,
        }
        if any(request.headers.get(key) != value
               for key, value in expected_headers.items()):
            return JSONResponse(status_code=401,
                                content={"detail": "synthetic auth required"})
        media_type = None
        if request.method == "POST" and request.url.path == "/jobs":
            try:
                body = await request.json()
                media_type = body.get("download_type")
                if media_type not in {"video", "thumbnail"}:
                    media_type = "unknown"
            except Exception:
                media_type = "unknown"
        response = await call_next(request)
        path = request.url.path
        if request.method == "POST" and path == "/jobs":
            counts.record("submit", media_type)
        elif request.method == "GET" and path.startswith("/jobs/"):
            media_type = _media_type_from_job(data_dir, path)
            if path.endswith("/file"):
                counts.record("file", media_type)
            else:
                counts.record("poll", media_type)
        save_report()
        return response

    application.state.native_test_counts = counts
    return application


def _media_type_from_job(data_dir: Path, path: str) -> str | None:
    parts = path.split("/")
    if len(parts) < 3:
        return None
    try:
        job = json.loads((data_dir / "jobs" / f"{parts[2]}.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return job.get("download_type")


def serve(work_dir: Path, port: int) -> None:
    import uvicorn

    counts = RequestCounts()
    application = create_test_app(work_dir, counts)
    report_path = work_dir / "report.json"
    config = uvicorn.Config(application, host="127.0.0.1", port=port,
                            log_level="info", access_log=True)
    server = uvicorn.Server(config)
    try:
        asyncio.run(server.serve())
    except KeyboardInterrupt:
        pass
    finally:
        report_path.write_text(json.dumps(counts.report(), indent=2) + "\n",
                               encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="write Video and Image test Shortcuts")
    prepare.add_argument("--work-dir", type=Path, required=True)
    prepare.add_argument("--port", type=int, required=True)
    prepare.add_argument("--direct-cli", action="store_true",
                         help="also write direct text-file input adapter Shortcuts")
    server = commands.add_parser("serve", help="run the loopback sidecar mock")
    server.add_argument("--work-dir", type=Path, required=True)
    server.add_argument("--port", type=int, required=True)
    verify_parser = commands.add_parser(
        "verify", help="check synthetic outputs and request lifecycle evidence")
    verify_parser.add_argument("--work-dir", type=Path, required=True)
    run_parser = commands.add_parser("run", help="run already-imported native drivers and verify")
    run_parser.add_argument("--work-dir", type=Path, required=True)
    run_parser.add_argument("--port", type=int, required=True)
    run_parser.add_argument("--timeout", type=float, default=45,
                            help="seconds allowed per synthetic driver (1-60; default 45)")
    run_parser.add_argument("--direct-cli", action="store_true",
                            help="run direct-input adapters instead of native drivers")
    args = parser.parse_args(argv)
    if args.command != "verify" and not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.command == "run":
        if sys.platform != "darwin":
            parser.error("native execution requires macOS")
        if not 1 <= args.timeout <= 60:
            parser.error("--timeout must be between 1 and 60 seconds")
        evidence = run_native(args.work_dir, args.port, args.timeout,
                              direct_cli=args.direct_cli)
        print(json.dumps(evidence, sort_keys=True))
        return 0 if evidence["verified"] else 1
    if args.command == "prepare":
        if not SOURCE_SHORTCUT.is_file():
            parser.error(f"finalized source shortcut missing: {SOURCE_SHORTCUT.name}")
        for mode in ("Video", "Image"):
            output = args.work_dir / f"MeTube Local Test {mode}_unsigned.shortcut"
            prepare_shortcut(SOURCE_SHORTCUT, output, port=args.port,
                             media_mode=mode)
            driver = args.work_dir / f"MeTube Local Driver {mode}_unsigned.shortcut"
            prepare_driver(driver, media_mode=mode)
            if args.direct_cli:
                direct = args.work_dir / f"MeTube Local Direct {mode}_unsigned.shortcut"
                prepare_shortcut(SOURCE_SHORTCUT, direct, port=args.port,
                                 media_mode=mode, direct_cli=True)
        (args.work_dir / "url-input.txt").write_text(
            "https://example.com/watch?v=native-test\n", encoding="utf-8")
        copy_fixtures(args.work_dir)
        return 0
    if args.command == "verify":
        evidence = verify_work_dir(args.work_dir)
        print(json.dumps(evidence, sort_keys=True))
        return 0 if evidence["verified"] else 1
    args.work_dir.mkdir(parents=True, exist_ok=True)
    serve(args.work_dir, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
