from __future__ import annotations

import asyncio
import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import httpx


SHORTCUTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHORTCUTS_DIR))

import native_test  # noqa: E402


class PrepareNativeShortcutsTests(unittest.TestCase):
    def test_prepare_copies_synthetic_fixtures_only_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            work_dir = Path(temp)
            existing = work_dir / "fixture.jpg"
            existing.write_bytes(b"preserve-existing-fixture")
            native_test.copy_fixtures(work_dir)
            self.assertEqual(existing.read_bytes(), b"preserve-existing-fixture")
            self.assertEqual((work_dir / "fixture.mp4").read_bytes(),
                             (native_test.FIXTURES_DIR / "fixture.mp4").read_bytes())

    def test_prepares_unsigned_variants_without_mutating_public_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            work_dir = Path(temp)
            for mode, expected_type in (("Video", "video"), ("Image", "thumbnail")):
                target = work_dir / f"{mode}.shortcut"
                workflow = native_test.prepare_shortcut(
                    native_test.SOURCE_SHORTCUT, target, port=9912,
                    media_mode=mode,
                )
                self.assertEqual(workflow["WFWorkflowName"],
                                 f"MeTube Local Test {mode}")
                self.assertEqual(workflow["WFWorkflowImportQuestions"], [])
                self.assertEqual(workflow["WFWorkflowTypes"], ["ActionExtension"])
                actions = workflow["WFWorkflowActions"]
                outputs = {
                    action.get("WFWorkflowActionParameters", {}).get("CustomOutputName"):
                    action for action in actions
                }
                self.assertEqual(
                    outputs["serverAddress"]["WFWorkflowActionParameters"]["WFTextActionText"],
                    "http://127.0.0.1:9912",
                )
                self.assertEqual(
                    outputs["normalizedServerAddress"]["WFWorkflowActionParameters"]["WFTextActionText"],
                    "http://127.0.0.1:9912",
                )
                self.assertEqual(
                    outputs["serverMatch"]["WFWorkflowActionParameters"]["WFTextActionText"],
                    "validated",
                )
                self.assertEqual(
                    outputs["modeChoice"]["WFWorkflowActionParameters"]["WFTextActionText"],
                    mode,
                )
                identifiers = [a["WFWorkflowActionIdentifier"] for a in actions]
                self.assertEqual(identifiers[-1], "is.workflow.actions.output")
                self.assertEqual(actions[-1]["WFWorkflowActionParameters"]["WFOutput"], {
                    "Value": {"string": "\ufffc", "attachmentsByRange": {"{0, 1}": {
                        "Type": "Variable", "VariableName": "finalFile",
                    }}},
                    "WFSerializationType": "WFTextTokenString",
                })
                self.assertNotIn("is.workflow.actions.notification", identifiers)
                delays = [a["WFWorkflowActionParameters"].get("WFDelayTime")
                          for a in actions
                          if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.delay"]
                self.assertEqual(delays, [1])
                self.assertEqual(sum(i == "is.workflow.actions.downloadurl"
                                     for i in identifiers), 3)
                self.assertIn("is.workflow.actions.detect.link", identifiers)
                self.assertIn("is.workflow.actions.setitemname", identifiers)
                self.assertEqual(outputs["serverAddress"]["WFWorkflowActionParameters"]["UUID"],
                                 self._source_action_uuid("serverAddress"))
                with target.open("rb") as stream:
                    saved = plistlib.load(stream)
                self.assertEqual(saved["WFWorkflowActions"][-1], actions[-1])
            self.assertFalse((work_dir / "Video.shortcut").read_bytes() ==
                             native_test.SOURCE_SHORTCUT.read_bytes())

    def test_test_failures_emit_only_stage_title_then_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workflow = native_test.prepare_shortcut(
                native_test.SOURCE_SHORTCUT, Path(temp) / "Video.shortcut",
                port=9912, media_mode="Video",
            )
        actions = workflow["WFWorkflowActions"]
        self.assertFalse(any(a["WFWorkflowActionIdentifier"] == "is.workflow.actions.alert"
                             for a in actions))
        receipts = [a for a in actions
                    if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.gettext"
                    and str(a["WFWorkflowActionParameters"].get("CustomOutputName", ""))
                    .startswith("NativeTestErrorReceipt")]
        self.assertGreater(len(receipts), 0)
        for receipt in receipts:
            params = receipt["WFWorkflowActionParameters"]
            title = params["WFTextActionText"]
            self.assertTrue(title.strip())
            self.assertNotRegex(title, r"^D\d{2}/\d{2}")
            self.assertEqual(set(params), {"CustomOutputName", "UUID", "WFTextActionText"})
            index = actions.index(receipt)
            self.assertEqual(actions[index + 1]["WFWorkflowActionIdentifier"],
                             "is.workflow.actions.output")
            output = actions[index + 1]["WFWorkflowActionParameters"]["WFOutput"]
            self.assertEqual(output["WFSerializationType"], "WFTextTokenString")
            self.assertEqual(output["Value"]["string"], "\ufffc")
            self.assertEqual(output["Value"]["attachmentsByRange"]["{0, 1}"], {
                "OutputName": params["CustomOutputName"],
                "OutputUUID": params["UUID"],
                "Type": "ActionOutput",
            })
            self.assertEqual(actions[index + 2]["WFWorkflowActionIdentifier"],
                             "is.workflow.actions.nothing")
            self.assertEqual(actions[index + 3]["WFWorkflowActionIdentifier"],
                             "is.workflow.actions.exit")

    def test_direct_cli_adapter_uses_the_production_three_stage_url_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            for mode in ("Video", "Image"):
                path = Path(temp) / f"Direct-{mode}.shortcut"
                workflow = native_test.prepare_shortcut(
                    native_test.SOURCE_SHORTCUT, path, port=9912,
                    media_mode=mode, direct_cli=True,
                )
                self.assertEqual(workflow["WFWorkflowName"],
                                 f"MeTube Local Direct {mode}")
                actions = workflow["WFWorkflowActions"]
                text_index = next(i for i, a in enumerate(actions)
                                  if a["WFWorkflowActionIdentifier"] ==
                                  "is.workflow.actions.detect.text")
                prompt_index = next(i for i, a in enumerate(actions)
                                    if a["WFWorkflowActionIdentifier"] ==
                                    "is.workflow.actions.gettext"
                                    and a["WFWorkflowActionParameters"].get(
                                        "CustomOutputName") == "enteredURL")
                link_indexes = [i for i, a in enumerate(actions)
                                if a["WFWorkflowActionIdentifier"] ==
                                "is.workflow.actions.detect.link"]
                self.assertEqual(len(link_indexes), 3)
                self.assertLess(link_indexes[0], text_index)
                self.assertLess(text_index, link_indexes[1])
                self.assertLess(link_indexes[1], prompt_index)
                self.assertLess(prompt_index, link_indexes[2])
                text_params = actions[text_index]["WFWorkflowActionParameters"]
                self.assertEqual(text_params["WFInput"]["Value"],
                                 {"Type": "ExtensionInput"})
                link_input = actions[link_indexes[1]]["WFWorkflowActionParameters"]["WFInput"]
                self.assertEqual(link_input["Value"], {
                    "string": "\ufffc",
                    "attachmentsByRange": {"{0, 1}": {
                        "OutputName": "inputText",
                        "OutputUUID": text_params["UUID"],
                        "Type": "ActionOutput",
                    }},
                })
                self.assertEqual(link_input["WFSerializationType"],
                                 "WFTextTokenString")
                prompt_params = actions[prompt_index]["WFWorkflowActionParameters"]
                self.assertEqual(prompt_params["WFTextActionText"],
                                 "D05/15 - URL prompt bypassed in headless test")
                self.assertEqual(
                    actions[link_indexes[2]]["WFWorkflowActionParameters"]["WFInput"][
                        "Value"]["attachmentsByRange"]["{0, 1}"],
                    {
                        "OutputName": "enteredURL",
                        "OutputUUID": prompt_params["UUID"],
                        "Type": "ActionOutput",
                    },
                )
                self.assertFalse(any(a["WFWorkflowActionIdentifier"] ==
                                     "is.workflow.actions.ask" for a in actions))

    @staticmethod
    def _source_action_uuid(output_name: str) -> str:
        with native_test.SOURCE_SHORTCUT.open("rb") as stream:
            source = plistlib.load(stream)
        for action in source["WFWorkflowActions"]:
            params = action["WFWorkflowActionParameters"]
            if params.get("CustomOutputName") == output_name:
                return params["UUID"]
        raise AssertionError(f"source action {output_name} missing")

    def test_driver_passes_literal_url_text_to_matching_shortcut(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            for mode in ("Video", "Image"):
                driver = native_test.prepare_driver(
                    Path(temp) / f"MeTube Local Driver {mode}_unsigned.shortcut",
                    media_mode=mode,
                )
                actions = driver["WFWorkflowActions"]
                self.assertEqual([a["WFWorkflowActionIdentifier"] for a in actions], [
                "is.workflow.actions.gettext", "is.workflow.actions.runworkflow",
                ])
                text_params = actions[0]["WFWorkflowActionParameters"]
                run_params = actions[1]["WFWorkflowActionParameters"]
                self.assertEqual(text_params["WFTextActionText"],
                                 "https://example.com/watch?v=native-test")
                self.assertEqual(run_params["WFWorkflowName"],
                                 f"MeTube Local Test {mode}")
                self.assertEqual(run_params["WFInput"]["Value"], {
                    "OutputName": "DriverURL",
                    "OutputUUID": text_params["UUID"],
                    "Type": "ActionOutput",
                })


class NativeMockServiceTests(unittest.TestCase):
    def test_real_sidecar_uses_only_mock_metube_and_enforces_synthetic_auth(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            work_dir = Path(temp)
            (work_dir / "fixture.mp4").write_bytes(b"synthetic mp4 data")
            (work_dir / "fixture.jpg").write_bytes(b"synthetic jpg data")
            counts = native_test.RequestCounts()
            app = native_test.create_test_app(work_dir, counts)

            async def exercise() -> None:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport,
                        base_url="http://127.0.0.1:9912") as client:
                    headers = {
                        "CF-Access-Client-Id": native_test.SYNTHETIC_CLIENT_ID,
                        "CF-Access-Client-Secret": native_test.SYNTHETIC_CLIENT_SECRET,
                        "X-Sidecar-Api-Key": native_test.SYNTHETIC_API_KEY,
                    }
                    denied = await client.post("/jobs", json={"url": "https://example.com/x"})
                    self.assertEqual(denied.status_code, 401)
                    for media_type, fmt, codec in (("video", "ios", "h264"),
                                                   ("thumbnail", "jpg", "auto")):
                        response = await client.post("/jobs", headers=headers, json={
                            "url": "https://example.com/native-test",
                            "quality": "best", "format": fmt,
                            "download_type": media_type, "codec": codec,
                        })
                        self.assertEqual(response.status_code, 202, response.text)
                        job = response.json()
                        self.assertEqual(job["poll_url"], f"/jobs/{job['id']}")
                        for attempt in range(12):
                            status_response = await client.get(job["poll_url"], headers=headers)
                            self.assertEqual(status_response.status_code, 200)
                            if status_response.json()["status"] == "complete":
                                break
                            await asyncio.sleep(0.15)
                        self.assertEqual(status_response.json()["status"], "complete")
                        file_response = await client.get(
                            status_response.json()["file_url"], headers=headers)
                        self.assertEqual(file_response.status_code, 200)
                        suffix = ".mp4" if media_type == "video" else ".jpg"
                        self.assertTrue(file_response.headers["content-disposition"].endswith(
                            f'filename="fixture{suffix}"'))
                    denied_poll = await client.get("/jobs/not-a-job")
                    self.assertEqual(denied_poll.status_code, 401)

            asyncio.run(exercise())
            self.assertEqual(counts.submit, 2)
            self.assertEqual(counts.file, 2)
            self.assertEqual(counts.by_type["video"]["submit"], 1)
            self.assertEqual(counts.by_type["thumbnail"]["file"], 1)
            report = json.loads(json.dumps(counts.report()))
            self.assertEqual(report["submit"], 2)
            self.assertEqual(report["file"], 2)
            self.assertTrue((work_dir / "report.json").is_file())


class BoundedNativeRunnerTests(unittest.TestCase):
    INSTALLED = "\n".join(f"MeTube Local {role} {mode}"
                          for role in ("Test", "Driver")
                          for mode in ("Video", "Image"))
    DIRECT_INSTALLED = "MeTube Local Direct Video\nMeTube Local Direct Image"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp.name) / "work"
        native_test.copy_fixtures(self.work_dir)
        self.lock = Path(self.temp.name) / "ui-lock"
        self.report = self.work_dir / "report.json"
        self.report.write_text(json.dumps({"submit": 0, "poll": 0, "file": 0, "by_type": {}}))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def successful_process(self, command, **kwargs):
        is_video = command[2].endswith("Video")
        mode = "video" if is_video else "thumbnail"
        fixture = self.work_dir / ("fixture.mp4" if is_video else "fixture.jpg")
        Path(command[4]).write_bytes(fixture.read_bytes())
        counts = json.loads(self.report.read_text())
        counts["by_type"][mode] = {"submit": 1, "poll": 1, "file": 1}
        for kind in ("submit", "poll", "file"):
            counts[kind] += 1
        self.report.write_text(json.dumps(counts))
        return subprocess.CompletedProcess(command, 0)

    def run_with(self, process, *, direct_cli=False, installed=None):
        with patch.object(native_test.httpx, "get", return_value=httpx.Response(
                200, json={"status": "ok"})) as health, \
                patch.object(native_test.subprocess, "check_output",
                             return_value=installed or self.INSTALLED), \
                patch.object(native_test.subprocess, "run", side_effect=process) as runner:
            result = native_test.run_native(self.work_dir, 9912, 4, self.lock,
                                            direct_cli=direct_cli)
        return result, health, runner

    def direct_successful_process(self, command, **kwargs):
        mode = "video" if command[2].endswith("Video") else "thumbnail"
        fixture = self.work_dir / ("fixture.mp4" if mode == "video" else "fixture.jpg")
        Path(command[command.index("--output-path") + 1]).write_bytes(fixture.read_bytes())
        counts = json.loads(self.report.read_text())
        counts["by_type"][mode] = {"submit": 1, "poll": 1, "file": 1}
        for kind in ("submit", "poll", "file"):
            counts[kind] += 1
        self.report.write_text(json.dumps(counts))
        return subprocess.CompletedProcess(command, 0)

    def test_direct_cli_runs_named_shortcuts_with_text_input_and_verifies_bytes(self) -> None:
        input_path = self.work_dir / "url-input.txt"
        input_path.write_text("https://example.com/watch?v=native-test\n")
        result, health, runner = self.run_with(
            self.direct_successful_process, direct_cli=True,
            installed=self.DIRECT_INSTALLED,
        )
        self.assertTrue(result["verified"])
        self.assertTrue(result["native_direct_shortcut_execution_succeeded"])
        self.assertFalse(result["native_driver_execution_succeeded"])
        self.assertEqual(result["completed_drivers"], ["Video", "Image"])
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(runner.call_args_list[0].args[0], [
            "shortcuts", "run", "MeTube Local Direct Video",
            "--input-path", str(input_path),
            "--output-path", str(self.work_dir / "video-result.mp4"),
        ])
        self.assertEqual(runner.call_args_list[1].args[0], [
            "shortcuts", "run", "MeTube Local Direct Image",
            "--input-path", str(input_path),
            "--output-path", str(self.work_dir / "image-result.jpg"),
        ])
        self.assertEqual(health.call_count, 1)
        self.assertFalse(self.lock.exists())

    def test_direct_cli_failure_stops_before_second_shortcut(self) -> None:
        input_path = self.work_dir / "url-input.txt"
        input_path.write_text("https://example.com/watch?v=native-test\n")
        result, _, runner = self.run_with(
            lambda command, **kwargs: subprocess.CompletedProcess(command, 1),
            direct_cli=True, installed=self.DIRECT_INSTALLED,
        )
        self.assertEqual(result["reason"], "native_direct_shortcut_failed")
        self.assertEqual(runner.call_count, 1)
        self.assertFalse(self.lock.exists())

    def test_direct_cli_missing_input_fails_before_health_or_invocation(self) -> None:
        result, health, runner = self.run_with(
            self.direct_successful_process, direct_cli=True,
            installed=self.DIRECT_INSTALLED,
        )
        self.assertEqual(result["reason"], "loopback_test_setup_failed")
        self.assertEqual(result["detail"], "direct_input_file_missing")
        health.assert_not_called()
        runner.assert_not_called()
        self.assertFalse(self.lock.exists())

    def test_success_runs_both_drivers_and_verifies_this_runs_bytes(self) -> None:
        result, health, runner = self.run_with(self.successful_process)
        self.assertTrue(result["verified"])
        self.assertTrue(result["native_driver_execution_succeeded"])
        self.assertEqual(result["completed_drivers"], ["Video", "Image"])
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(health.call_args.args[0], "http://127.0.0.1:9912/healthz")
        self.assertEqual(runner.call_args.kwargs["timeout"], 4)
        self.assertFalse(self.lock.exists())
        self.assertTrue(json.loads((self.work_dir / "native-run.json").read_text())["verified"])

    def test_timeout_stops_before_second_driver_and_releases_lock(self) -> None:
        result, _, runner = self.run_with(subprocess.TimeoutExpired("shortcuts", 4))
        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "native_timeout_or_pending_dialog")
        self.assertEqual(runner.call_count, 1)
        self.assertFalse(self.lock.exists())

    def test_failed_driver_stops_before_second_driver(self) -> None:
        result, _, runner = self.run_with(lambda *args, **kwargs: subprocess.CompletedProcess(args, 1))
        self.assertEqual(result["reason"], "native_driver_failed")
        self.assertEqual(runner.call_count, 1)
        self.assertFalse(self.lock.exists())

    def test_busy_ui_preserves_other_owner_and_never_launches(self) -> None:
        self.lock.mkdir()
        owner = self.lock / "owner.txt"
        owner.write_text("other-owner")
        result, health, runner = self.run_with(self.successful_process)
        self.assertEqual(result["reason"], "shortcuts_ui_busy")
        health.assert_not_called()
        runner.assert_not_called()
        self.assertEqual(owner.read_text(), "other-owner")

    def test_old_output_is_preserved_and_never_used(self) -> None:
        output = self.work_dir / "video-result.mp4"
        output.write_bytes(b"old result")
        result, health, runner = self.run_with(self.successful_process)
        self.assertEqual(result["reason"], "stale_test_evidence")
        health.assert_not_called()
        runner.assert_not_called()
        self.assertEqual(output.read_bytes(), b"old result")

    def test_previous_server_requests_prevent_launch(self) -> None:
        counts = json.loads(self.report.read_text())
        counts["submit"] = 1
        self.report.write_text(json.dumps(counts))
        result, _, runner = self.run_with(self.successful_process)
        self.assertEqual(result["reason"], "fresh_server_required")
        runner.assert_not_called()
        self.assertFalse(self.lock.exists())

    def test_unavailable_loopback_server_releases_lock_without_launch(self) -> None:
        with patch.object(native_test.httpx, "get", side_effect=httpx.ConnectError("test")), \
                patch.object(native_test.subprocess, "check_output", return_value=self.INSTALLED), \
                patch.object(native_test.subprocess, "run") as runner:
            result = native_test.run_native(self.work_dir, 9912, 4, self.lock)
        self.assertEqual(result["reason"], "loopback_test_setup_failed")
        runner.assert_not_called()
        self.assertFalse(self.lock.exists())

    def test_missing_image_registration_stops_before_network_or_execution(self) -> None:
        with patch.object(native_test.subprocess, "check_output", return_value=
                          "MeTube Local Test Video\nMeTube Local Driver Video"), \
                patch.object(native_test.httpx, "get") as health, \
                patch.object(native_test.subprocess, "run") as runner:
            result = native_test.run_native(self.work_dir, 9912, 4, self.lock)
        self.assertEqual(result["reason"], "native_shortcuts_not_registered")
        self.assertEqual(result["missing_media"], ["Image"])
        health.assert_not_called()
        runner.assert_not_called()
        self.assertFalse(self.lock.exists())

    def test_registration_timeout_stops_without_launching_driver(self) -> None:
        with patch.object(native_test.subprocess, "check_output", side_effect=
                          subprocess.TimeoutExpired("shortcuts list", 5)), \
                patch.object(native_test.subprocess, "run") as runner:
            result = native_test.run_native(self.work_dir, 9912, 4, self.lock)
        self.assertEqual(result["reason"], "native_registration_check_failed")
        runner.assert_not_called()
        self.assertFalse(self.lock.exists())


class NativeEvidenceVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp.name)
        self.fixtures = {
            "video": (native_test.FIXTURES_DIR / "fixture.mp4", "video-result.mp4"),
            "thumbnail": (native_test.FIXTURES_DIR / "fixture.jpg", "image-result.jpg"),
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_valid_evidence(self) -> None:
        for source, name in self.fixtures.values():
            fixture_name = "fixture.mp4" if name == "video-result.mp4" else "fixture.jpg"
            (self.work_dir / fixture_name).write_bytes(source.read_bytes())
            (self.work_dir / name).write_bytes(source.read_bytes())
        (self.work_dir / "report.json").write_text(json.dumps({
            "by_type": {
                media_type: {"submit": 1, "poll": 1, "file": 1}
                for media_type in ("video", "thumbnail")
            }
        }), encoding="utf-8")

    def test_matching_outputs_and_complete_counts_verify_as_evidence_only(self) -> None:
        self.write_valid_evidence()
        evidence = native_test.verify_work_dir(self.work_dir)
        self.assertTrue(evidence["verified"])
        self.assertFalse(evidence["native_shortcut_success_established"])

    def test_missing_outputs_fail(self) -> None:
        self.write_valid_evidence()
        (self.work_dir / "image-result.jpg").unlink()
        self.assertFalse(native_test.verify_work_dir(self.work_dir)["verified"])

    def test_byte_mismatch_fails(self) -> None:
        self.write_valid_evidence()
        (self.work_dir / "video-result.mp4").write_bytes(b"different bytes")
        self.assertFalse(native_test.verify_work_dir(self.work_dir)["verified"])

    def test_missing_request_lifecycle_count_fails(self) -> None:
        self.write_valid_evidence()
        report_path = self.work_dir / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["by_type"]["thumbnail"]["poll"] = 0
        report_path.write_text(json.dumps(report), encoding="utf-8")
        self.assertFalse(native_test.verify_work_dir(self.work_dir)["verified"])

    def test_missing_work_dir_fixture_fails_without_raising(self) -> None:
        self.write_valid_evidence()
        (self.work_dir / "fixture.jpg").unlink()
        evidence = native_test.verify_work_dir(self.work_dir)
        self.assertFalse(evidence["verified"])
        self.assertFalse(evidence["results"]["thumbnail"]["fixture_present"])

    def test_non_integer_request_counts_fail_cleanly(self) -> None:
        invalid_values = ("1", None, {"count": 1}, True)
        for value in invalid_values:
            with self.subTest(value=value):
                self.write_valid_evidence()
                report_path = self.work_dir / "report.json"
                report = json.loads(report_path.read_text(encoding="utf-8"))
                report["by_type"]["video"]["poll"] = value
                report_path.write_text(json.dumps(report), encoding="utf-8")
                evidence = native_test.verify_work_dir(self.work_dir)
                self.assertFalse(evidence["verified"])
                self.assertFalse(
                    evidence["request_lifecycle_present"]["video"]["poll"]
                )

    def test_malformed_by_type_container_fails_cleanly(self) -> None:
        self.write_valid_evidence()
        (self.work_dir / "report.json").write_text(
            json.dumps({"by_type": [1, 2]}), encoding="utf-8")
        evidence = native_test.verify_work_dir(self.work_dir)
        self.assertFalse(evidence["verified"])
        self.assertFalse(evidence["request_lifecycle_present"]["video"]["submit"])


if __name__ == "__main__":
    unittest.main()
