from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SHORTCUTS_DIR = Path(__file__).resolve().parents[1]
RUNNER = SHORTCUTS_DIR / "run-on-mac.sh"
ARTIFACT = SHORTCUTS_DIR / "MeTube Download_unsigned.shortcut"


@unittest.skipUnless(shutil.which("sh"), "requires a POSIX shell")
class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        (self.bundle / "private").mkdir()
        for name in ("run-on-mac.sh", "prepare-private.py", "finalize.py"):
            shutil.copy2(SHORTCUTS_DIR / name, self.bundle / name)
        shutil.copy2(ARTIFACT, self.bundle / ARTIFACT.name)
        (self.bundle / "private" / "config.json").write_text(
            '{\n'
            '  "cf_access_client_id": "",\n'
            '  "cf_access_client_secret": "",\n'
            '  "server_url": "https://download-api.example.com",\n'
            '  "sidecar_api_key": ""\n'
            '}\n',
            encoding="utf-8",
        )
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.security_log = self.root / "security.log"
        self._write_command("uname", "printf '%s\\n' Darwin\n")
        self._write_command(
            "security",
            """case "$1" in
find-generic-password) exit 1 ;;
add-generic-password) printf '%s\\n' "$*" >> "$SECURITY_LOG" ;;
delete-generic-password) ;;
esac
""",
        )
        self._write_command(
            "shortcuts",
            """input=''
output=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --input) input=$2; shift 2 ;;
    --output) output=$2; shift 2 ;;
    *) shift ;;
  esac
done
cp "$input" "$output"
""",
        )
        self._write_command("open", "exit 0\n")
        self._write_command(
            "curl",
            """agent=''
output=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) output=$2; shift 2 ;;
    --user-agent) agent=$2; shift 2 ;;
    *) shift ;;
  esac
done
headers=$(cat)
case "$agent" in Python-urllib*) exit 98 ;; esac
case "$headers" in
  *'CF-Access-Client-Id: test-id.access'*'CF-Access-Client-Secret: test-secret'*) ;;
  *) exit 99 ;;
esac
printf '%s' '{"status":"ok"}' > "$output"
printf '%s' "${CURL_STATUS:-200}"
""",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_command(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(f"#!/bin/sh\nset -eu\n{body}", encoding="utf-8")
        path.chmod(0o700)

    def run_runner(self, *, status: str = "200") -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.bin}{os.pathsep}{environment['PATH']}",
                "HOME": str(self.root / "home"),
                "SECURITY_LOG": str(self.security_log),
                "CF_SECRET": "test-secret",
                "CURL_STATUS": status,
            }
        )
        return subprocess.run(
            ["sh", "./run-on-mac.sh"],
            cwd=self.bundle,
            env=environment,
            input="test-id.access\n",
            text=True,
            capture_output=True,
            check=False,
        )

    def test_validates_before_saving_and_signs_after_success(self) -> None:
        result = self.run_runner()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Cloudflare Access credentials validated", result.stdout)
        self.assertTrue(
            (self.root / "home/Library/Application Support/MeTube Sidecar/private/MeTube Download Configured.shortcut").exists()
        )
        configured_path = self.root / "home/Library/Application Support/MeTube Sidecar/private/MeTube Download Configured_unsigned.shortcut"
        with configured_path.open("rb") as stream:
            configured = plistlib.load(stream)
        self.assertEqual(configured["WFWorkflowImportQuestions"], [])
        self.assertNotIn("WFWorkflowNoInputBehavior", configured)
        prompts = [action for action in configured["WFWorkflowActions"]
                   if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.ask"]
        self.assertEqual(len(prompts), 1)
        address_actions = {
            action["WFWorkflowActionParameters"].get("CustomOutputName"): action
            for action in configured["WFWorkflowActions"]
        }
        for name, expected in (
            ("normalizedServerAddress", "https://download-api.example.com"),
            ("serverMatch", "validated"),
        ):
            action = address_actions[name]
            self.assertEqual(action["WFWorkflowActionIdentifier"], "is.workflow.actions.gettext")
            self.assertEqual(action["WFWorkflowActionParameters"]["WFTextActionText"], expected)
        actions = configured["WFWorkflowActions"]
        get_urls = [
            action for action in actions
            if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.detect.link"
        ]
        self.assertEqual(len(get_urls), 3)
        self.assertEqual(get_urls[0]["WFWorkflowActionParameters"]["WFInput"]["Value"], {
            "string": "\ufffc",
            "attachmentsByRange": {"{0, 1}": {"Type": "ExtensionInput"}},
        })
        self.assertFalse(any(
            action["WFWorkflowActionIdentifier"] == "is.workflow.actions.text.match"
            for action in actions
        ))
        self.assertFalse(any(
            action["WFWorkflowActionIdentifier"] == "is.workflow.actions.notification"
            for action in configured["WFWorkflowActions"]
        ))
        self.assertIn("add-generic-password", self.security_log.read_text(encoding="utf-8"))

    def test_rejected_credentials_are_not_saved_or_signed(self) -> None:
        result = self.run_runner(status="403")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("returned HTTP 403", result.stderr)
        self.assertFalse((self.root / "home/Library/Application Support/MeTube Sidecar").exists())
        self.assertFalse(self.security_log.exists())

    def test_invalid_server_origin_is_rejected_before_network_request(self) -> None:
        config = self.bundle / "private/config.json"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                "https://download-api.example.com", "http://download-api.example.com"
            ),
            encoding="utf-8",
        )

        result = self.run_runner()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid private server URL", result.stderr)
        self.assertFalse(self.security_log.exists())


if __name__ == "__main__":
    unittest.main()
