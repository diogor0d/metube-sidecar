#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import plistlib
import sys
from pathlib import Path
from urllib.parse import urlsplit

from finalize import load_shortcut, parameters, validate_shortcut, write_shortcut


ROOT = Path(__file__).resolve().parent
PUBLIC_ARTIFACT = ROOT / "MeTube Download_unsigned.shortcut"
PRIVATE_DIR = ROOT / "private"
CONFIG_PATH = PRIVATE_DIR / "config.json"
PRIVATE_ARTIFACT = PRIVATE_DIR / "MeTube Download Configured_unsigned.shortcut"
PRIVATE_SIGNED = PRIVATE_DIR / "MeTube Download Configured.shortcut"
REQUIRED_KEYS = {
    "server_url",
    "cf_access_client_id",
    "cf_access_client_secret",
    "sidecar_api_key",
}
OUTPUT_NAMES = {
    "serverAddress": "server_url",
    "clientID": "cf_access_client_id",
    "clientSecret": "cf_access_client_secret",
    "sidecarAPIKey": "sidecar_api_key",
}


def validate_config(config: object) -> dict[str, str]:
    if not isinstance(config, dict) or set(config) != REQUIRED_KEYS:
        raise ValueError(f"config.json must contain exactly {sorted(REQUIRED_KEYS)}")
    if not all(isinstance(value, str) for value in config.values()):
        raise ValueError("every configuration value must be a string")
    parsed = urlsplit(config["server_url"])
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("server_url must be an HTTPS origin without credentials, path, query, or fragment")
    config["server_url"] = config["server_url"].rstrip("/")
    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an ignored, configured MeTube Shortcut artifact."
    )
    parser.add_argument(
        "--prompt-credentials",
        action="store_true",
        help="prompt locally for credentials and remove all setup questions",
    )
    parser.add_argument(
        "--from-env",
        action="store_true",
        help="read CF_ID, CF_SECRET, and optional SIDECAR_API_KEY from the environment",
    )
    return parser.parse_args()


def prompted_config(config: dict[str, str]) -> dict[str, str]:
    configured = dict(config)
    configured["cf_access_client_id"] = input(
        "Cloudflare Access client ID: "
    ).strip()
    configured["cf_access_client_secret"] = getpass.getpass(
        "Cloudflare Access client secret (hidden): "
    )
    configured["sidecar_api_key"] = getpass.getpass(
        "Optional sidecar API key (hidden; press Enter if disabled): "
    )
    if not configured["cf_access_client_id"] or not configured["cf_access_client_secret"]:
        raise ValueError("Cloudflare Access client ID and secret are required")
    return configured


def environment_config(config: dict[str, str]) -> dict[str, str]:
    configured = dict(config)
    configured["cf_access_client_id"] = os.environ.get("CF_ID", "").strip()
    configured["cf_access_client_secret"] = os.environ.get("CF_SECRET", "")
    configured["sidecar_api_key"] = os.environ.get("SIDECAR_API_KEY", "")
    if not configured["cf_access_client_id"] or not configured["cf_access_client_secret"]:
        raise ValueError("CF_ID and CF_SECRET environment variables are required")
    return configured


def main() -> int:
    args = parse_args()
    if args.prompt_credentials and args.from_env:
        print("choose only one of --prompt-credentials or --from-env", file=sys.stderr)
        return 2
    if not CONFIG_PATH.exists():
        PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
        template = {key: "" for key in sorted(REQUIRED_KEYS)}
        CONFIG_PATH.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
        print(f"created {CONFIG_PATH}; fill it with disposable test configuration", file=sys.stderr)
        return 2

    try:
        config = validate_config(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        prompted_outputs: set[str] = set()
        if args.prompt_credentials:
            config = prompted_config(config)
            prompted_outputs = {"clientID", "clientSecret", "sidecarAPIKey"}
        elif args.from_env:
            config = environment_config(config)
            prompted_outputs = {"clientID", "clientSecret", "sidecarAPIKey"}
        shortcut = load_shortcut(PUBLIC_ARTIFACT)
        validate_shortcut(shortcut)
        found: set[str] = set()
        configured_outputs: set[str] = set()
        for action in shortcut["WFWorkflowActions"]:
            params = parameters(action)
            output_name = params.get("CustomOutputName")
            if output_name in OUTPUT_NAMES:
                value = config[OUTPUT_NAMES[output_name]]
                if value or output_name in prompted_outputs:
                    params["WFTextActionText"] = value
                    configured_outputs.add(output_name)
                found.add(output_name)
        if found != set(OUTPUT_NAMES):
            raise ValueError("public artifact is missing configuration actions")
        normalized = next(
            (
                action
                for action in shortcut["WFWorkflowActions"]
                if parameters(action).get("CustomOutputName")
                == "normalizedServerAddress"
            ),
            None,
        )
        if normalized is None:
            raise ValueError("public artifact is missing address normalization")
        matched = next(
            (
                action
                for action in shortcut["WFWorkflowActions"]
                if parameters(action).get("CustomOutputName") == "serverMatch"
            ),
            None,
        )
        if matched is None:
            raise ValueError("public artifact is missing address validation")
        # The origin was validated above, and the runner already checked /healthz.
        # Keep action output names and UUIDs so all later references remain intact,
        # but avoid iOS text transformations that can fail on a valid origin.
        for action, value in ((normalized, config["server_url"]), (matched, "validated")):
            params = parameters(action)
            output_name, output_uuid = params["CustomOutputName"], params["UUID"]
            action["WFWorkflowActionIdentifier"] = "is.workflow.actions.gettext"
            action["WFWorkflowActionParameters"] = {
                "CustomOutputName": output_name,
                "UUID": output_uuid,
                "WFTextActionText": value,
            }
        shortcut["WFWorkflowImportQuestions"] = [
            question
            for question in shortcut["WFWorkflowImportQuestions"]
            if parameters(shortcut["WFWorkflowActions"][question["ActionIndex"]]).get(
                "CustomOutputName"
            )
            not in configured_outputs
        ]
        validate_shortcut(shortcut, public=False)
        PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
        write_shortcut(PRIVATE_ARTIFACT, shortcut)
        sign_script = """#!/bin/sh
set -eu
test "$(uname -s)" = "Darwin" || { echo "Apple shortcuts CLI requires macOS" >&2; exit 1; }
command -v shortcuts >/dev/null 2>&1 || { echo "shortcuts CLI not found" >&2; exit 1; }
shortcuts sign --mode anyone \\
  --input "MeTube Download Configured_unsigned.shortcut" \\
  --output "MeTube Download Configured.shortcut"
"""
        sign_path = PRIVATE_DIR / "sign-private.sh"
        with sign_path.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(sign_script)
        sign_path.chmod(0o700)
    except (OSError, json.JSONDecodeError, plistlib.InvalidFileException, ValueError) as exc:
        print(f"private preparation failed: {exc}", file=sys.stderr)
        return 1

    print(f"created {PRIVATE_ARTIFACT}")
    print(f"on macOS, run {PRIVATE_DIR / 'sign-private.sh'} to create {PRIVATE_SIGNED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
