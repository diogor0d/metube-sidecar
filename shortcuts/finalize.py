#!/usr/bin/env python3
from __future__ import annotations

import plistlib
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5


IMPORT_QUESTIONS = (
    ("HTTPS sidecar address", "serverAddress"),
    ("Cloudflare Access client ID", "clientID"),
    ("Cloudflare Access client secret", "clientSecret"),
    ("Optional sidecar API key (leave blank if disabled)", "sidecarAPIKey"),
)
MATCH_TEXT = "is.workflow.actions.text.match"
DOWNLOAD_URL = "is.workflow.actions.downloadurl"
RAW_ACTION = "is.workflow.actions.rawaction"
RUN_SHORTCUT = "is.workflow.actions.runworkflow"
UUID_SCOPE = "https://github.com/example/metube-sidecar/shortcuts/"


class ShortcutValidationError(ValueError):
    pass


def actions(shortcut: dict[str, Any]) -> list[dict[str, Any]]:
    value = shortcut.get("WFWorkflowActions")
    if not isinstance(value, list):
        raise ShortcutValidationError("WFWorkflowActions must be a list")
    return value


def parameters(action: dict[str, Any]) -> dict[str, Any]:
    value = action.setdefault("WFWorkflowActionParameters", {})
    if not isinstance(value, dict):
        raise ShortcutValidationError("action parameters must be a dictionary")
    return value


def walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def token_string(value: Any) -> tuple[str, list[dict[str, Any]]]:
    if isinstance(value, str):
        return value, []
    if not isinstance(value, dict):
        return "", []
    payload = value.get("Value", value)
    if not isinstance(payload, dict):
        return "", []
    attachments = payload.get("attachmentsByRange", {})
    ordered = []
    if isinstance(attachments, dict):
        ordered = [attachments[key] for key in sorted(attachments)]
    return str(payload.get("string", "")), ordered


def dictionary_items(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    payload = value.get("Value", value)
    if not isinstance(payload, dict):
        return {}
    items = payload.get("WFDictionaryFieldValueItems", [])
    result: dict[str, Any] = {}
    for item in items:
        key, _ = token_string(item.get("WFKey"))
        result[key] = item.get("WFValue")
    return result


def reference_name(value: Any) -> str | None:
    _, refs = token_string(value)
    if len(refs) == 1:
        return refs[0].get("OutputName") or refs[0].get("VariableName")
    if isinstance(value, dict):
        payload = value.get("Value")
        if isinstance(payload, dict):
            return payload.get("OutputName") or payload.get("VariableName")
    return None


def repair_raw_actions(shortcut: dict[str, Any]) -> None:
    for action in actions(shortcut):
        if action.get("WFWorkflowActionIdentifier") != RAW_ACTION:
            continue
        params = parameters(action)
        target = next(
            (
                params.pop(key)
                for key in (
                    "WFWorkflowActionIdentifier",
                    "ActionIdentifier",
                    "Identifier",
                )
                if isinstance(params.get(key), str)
            ),
            None,
        )
        if not target or target == RAW_ACTION:
            raise ShortcutValidationError("raw placeholder action has no native target")
        action["WFWorkflowActionIdentifier"] = target


def repair_match_text(shortcut: dict[str, Any]) -> None:
    for action in actions(shortcut):
        if action.get("WFWorkflowActionIdentifier") != MATCH_TEXT:
            continue
        params = parameters(action)
        if "WFInput" not in params and "text" in params:
            params["WFInput"] = params.pop("text")
        if "WFInput" not in params:
            raise ShortcutValidationError("Match Text action has no explicit WFInput")


def action_output_text(output_name: str, output_uuid: str) -> dict[str, Any]:
    return {
        "Value": {
            "string": "\ufffc",
            "attachmentsByRange": {"{0, 1}": {
                "OutputName": output_name,
                "OutputUUID": output_uuid,
                "Type": "ActionOutput",
            }},
        },
        "WFSerializationType": "WFTextTokenString",
    }


def repair_address_inputs(shortcut: dict[str, Any]) -> None:
    by_output = {
        parameters(action).get("CustomOutputName"): parameters(action)
        for action in actions(shortcut)
    }
    server = by_output.get("serverAddress")
    normalized = by_output.get("normalizedServerAddress")
    matched = by_output.get("serverMatch")
    if not all(isinstance(value, dict) for value in (server, normalized, matched)):
        raise ShortcutValidationError("sidecar address actions are missing")
    server_uuid = server.get("UUID")
    normalized_uuid = normalized.get("UUID")
    if not isinstance(server_uuid, str) or not isinstance(normalized_uuid, str):
        raise ShortcutValidationError("sidecar address actions have no UUID")
    normalized["WFInput"] = action_output_text("serverAddress", server_uuid)
    matched["WFInput"] = action_output_text(
        "normalizedServerAddress", normalized_uuid
    )


def repair_shared_url_inputs(shortcut: dict[str, Any]) -> None:
    workflow_actions = actions(shortcut)
    link_actions = [action for action in workflow_actions
                    if action.get("WFWorkflowActionIdentifier") == "is.workflow.actions.detect.link"]
    text_actions = [action for action in workflow_actions
                    if action.get("WFWorkflowActionIdentifier") == "is.workflow.actions.detect.text"]
    prompts = [action for action in workflow_actions
               if action.get("WFWorkflowActionIdentifier") == "is.workflow.actions.ask"]
    if len(link_actions) != 3 or len(text_actions) != 1 or len(prompts) != 1:
        raise ShortcutValidationError(
            "expected direct, text-fallback, and prompted URL extraction actions"
        )
    text_params = parameters(text_actions[0])
    prompt_params = parameters(prompts[0])
    text_name, text_uuid = text_params.get("CustomOutputName"), text_params.get("UUID")
    prompt_name, prompt_uuid = prompt_params.get("CustomOutputName"), prompt_params.get("UUID")
    if not all(isinstance(value, str) and value for value in
               (text_name, text_uuid, prompt_name, prompt_uuid)):
        raise ShortcutValidationError("URL fallback actions must have output names and UUIDs")
    prompt_params["WFAllowsMultilineText"] = False
    # Get Text consumes the native ExtensionInput attachment. Get URLs declares
    # text input and needs a WFTextTokenString; bare attachments resolve empty.
    text_params["WFInput"] = {
        "Value": {"Type": "ExtensionInput"},
        "WFSerializationType": "WFTextTokenAttachment",
    }
    link_params = [parameters(action) for action in link_actions]
    link_params[0]["WFInput"] = {
        "Value": {
            "string": "\ufffc",
            "attachmentsByRange": {"{0, 1}": {"Type": "ExtensionInput"}},
        },
        "WFSerializationType": "WFTextTokenString",
    }
    link_params[1]["WFInput"] = action_output_text(text_name, text_uuid)
    link_params[2]["WFInput"] = action_output_text(prompt_name, prompt_uuid)


def repair_import_questions(shortcut: dict[str, Any]) -> None:
    workflow_actions = actions(shortcut)
    indexes: dict[str, int] = {}
    for index, action in enumerate(workflow_actions):
        output_name = parameters(action).get("CustomOutputName")
        if isinstance(output_name, str):
            indexes[output_name] = index

    questions = shortcut.get("WFWorkflowImportQuestions")
    if not isinstance(questions, list):
        questions = []
        shortcut["WFWorkflowImportQuestions"] = questions
    by_text = {
        question.get("Text"): question
        for question in questions
        if isinstance(question, dict)
    }
    repaired = []
    for prompt, output_name in IMPORT_QUESTIONS:
        if output_name not in indexes:
            raise ShortcutValidationError(f"missing configuration action {output_name}")
        question = by_text.get(prompt, {})
        question.update(
            {
                "ActionIndex": indexes[output_name],
                "Category": "Parameter",
                "DefaultValue": "",
                "ParameterKey": "WFTextActionText",
                "Text": prompt,
            }
        )
        repaired.append(question)
    shortcut["WFWorkflowImportQuestions"] = repaired


def derive_uuids(shortcut: dict[str, Any]) -> None:
    workflow_actions = actions(shortcut)
    group_order: dict[str, int] = {}
    for action in workflow_actions:
        group = parameters(action).get("GroupingIdentifier")
        if isinstance(group, str) and group not in group_order:
            group_order[group] = len(group_order)
    group_map = {
        old: str(uuid5(NAMESPACE_URL, f"{UUID_SCOPE}group/{order}"))
        for old, order in group_order.items()
    }

    action_map: dict[str, str] = {}
    for index, action in enumerate(workflow_actions):
        params = parameters(action)
        old = params.get("UUID")
        if isinstance(old, str) and old not in group_map:
            action_map[old] = str(uuid5(NAMESPACE_URL, f"{UUID_SCOPE}action/{index}"))

    for index, action in enumerate(workflow_actions):
        params = parameters(action)
        group = params.get("GroupingIdentifier")
        if isinstance(group, str):
            params["GroupingIdentifier"] = group_map[group]
        old_uuid = params.get("UUID")
        if isinstance(old_uuid, str):
            params["UUID"] = group_map.get(
                old_uuid,
                action_map.get(
                    old_uuid,
                    str(uuid5(NAMESPACE_URL, f"{UUID_SCOPE}action/{index}")),
                ),
            )
        for node in walk(params):
            old_output = node.get("OutputUUID")
            if isinstance(old_output, str) and old_output in action_map:
                node["OutputUUID"] = action_map[old_output]


def canonicalize_dictionaries(value: Any) -> None:
    if isinstance(value, dict):
        items = value.get("WFDictionaryFieldValueItems")
        if isinstance(items, list):
            items.sort(key=lambda item: token_string(item.get("WFKey"))[0])
        for child in value.values():
            canonicalize_dictionaries(child)
    elif isinstance(value, list):
        for child in value:
            canonicalize_dictionaries(child)


def _validate_action_outputs(shortcut: dict[str, Any], errors: list[str]) -> None:
    seen: set[str] = set()
    for index, action in enumerate(actions(shortcut)):
        params = parameters(action)
        for node in walk(params):
            output_uuid = node.get("OutputUUID")
            if isinstance(output_uuid, str) and output_uuid not in seen:
                errors.append(
                    f"action {index} references missing or later ActionOutput {output_uuid}"
                )
        own_uuid = params.get("UUID")
        if isinstance(own_uuid, str):
            seen.add(own_uuid)


def _validate_questions(shortcut: dict[str, Any], errors: list[str], public: bool) -> None:
    workflow_actions = actions(shortcut)
    questions = shortcut.get("WFWorkflowImportQuestions", [])
    expected = {prompt: output for prompt, output in IMPORT_QUESTIONS}
    if public and len(questions) != len(expected):
        errors.append("public artifact must contain exactly four import questions")
    for question in questions:
        prompt = question.get("Text")
        if prompt not in expected:
            errors.append(f"unexpected import question {prompt!r}")
            continue
        index = question.get("ActionIndex")
        if not isinstance(index, int) or not 0 <= index < len(workflow_actions):
            errors.append(f"import question {prompt!r} has an invalid ActionIndex")
            continue
        params = parameters(workflow_actions[index])
        if params.get("CustomOutputName") != expected[prompt]:
            errors.append(f"import question {prompt!r} targets the wrong action")
        if question.get("ParameterKey") != "WFTextActionText":
            errors.append(f"import question {prompt!r} targets the wrong parameter")
        if public and question.get("DefaultValue") != "":
            errors.append(f"import question {prompt!r} has a non-blank default")
        if public and params.get("WFTextActionText") != "":
            errors.append(f"configuration action {expected[prompt]} is not blank")


def _validate_http(shortcut: dict[str, Any], errors: list[str]) -> None:
    http = [
        action
        for action in actions(shortcut)
        if action.get("WFWorkflowActionIdentifier") == DOWNLOAD_URL
    ]
    if len(http) != 3:
        errors.append(f"expected three HTTP actions, found {len(http)}")
        return
    expected_methods = ("POST", "GET", "GET")
    expected_url_refs = (
        ("normalizedServerAddress",),
        ("normalizedServerAddress", "expectedPollPath"),
        ("normalizedServerAddress", "expectedFilePath"),
    )
    for position, (action, method, url_refs) in enumerate(
        zip(http, expected_methods, expected_url_refs)
    ):
        params = parameters(action)
        if params.get("WFHTTPMethod") != method:
            errors.append(f"HTTP action {position} must use {method}")
        _, refs = token_string(params.get("WFURL"))
        names = tuple(
            ref.get("OutputName") or ref.get("VariableName") for ref in refs
        )
        if names != url_refs:
            errors.append(f"HTTP action {position} has unexpected URL references {names}")

        headers = dictionary_items(params.get("WFHTTPHeaders"))
        required = {
            "CF-Access-Client-Id": "clientID",
            "CF-Access-Client-Secret": "clientSecret",
            "X-Sidecar-Api-Key": "sidecarAPIKey",
        }
        allowed_keys = set(required)
        if method == "POST":
            allowed_keys.add("Content-Type")
        if set(headers) != allowed_keys:
            errors.append(f"HTTP action {position} has unexpected headers")
        for header, output_name in required.items():
            if reference_name(headers.get(header)) != output_name:
                errors.append(f"header {header} must reference {output_name}")
        if method == "POST":
            content_type, refs = token_string(headers.get("Content-Type"))
            if content_type != "application/json" or refs:
                errors.append("POST Content-Type must be literal application/json")
            if params.get("WFHTTPBodyType") != "JSON":
                errors.append("POST body type must be JSON")
            body = dictionary_items(params.get("WFJSONValues"))
            if set(body) != {"url", "quality", "format", "download_type", "codec"}:
                errors.append("POST JSON body fields are not exact")
            quality, quality_refs = token_string(body.get("quality"))
            if quality != "best" or quality_refs:
                errors.append("POST quality must be literal best")


def _valid_https_origin(value: Any) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and not any(char.isspace() for char in parsed.netloc)
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


def _validate_control_and_outputs(shortcut: dict[str, Any], errors: list[str],
                                  *, public: bool) -> None:
    workflow_actions = actions(shortcut)
    identifiers = [action.get("WFWorkflowActionIdentifier") for action in workflow_actions]
    link_actions = [action for action in workflow_actions
                    if action.get("WFWorkflowActionIdentifier") == "is.workflow.actions.detect.link"]
    text_actions = [action for action in workflow_actions
                    if action.get("WFWorkflowActionIdentifier") == "is.workflow.actions.detect.text"]
    prompts = [action for action in workflow_actions
               if action.get("WFWorkflowActionIdentifier") == "is.workflow.actions.ask"]
    if len(link_actions) != 3 or len(text_actions) != 1 or len(prompts) != 1:
        errors.append("URL extraction must include direct, text-fallback, and prompted actions")
    else:
        link_params = [parameters(action) for action in link_actions]
        text_params = parameters(text_actions[0])
        prompt_params = parameters(prompts[0])
        direct_input = {
            "Value": {
                "string": "\ufffc",
                "attachmentsByRange": {"{0, 1}": {"Type": "ExtensionInput"}},
            },
            "WFSerializationType": "WFTextTokenString",
        }
        if link_params[0].get("WFInput") != direct_input:
            errors.append("primary Get URLs must receive direct ExtensionInput")
        if text_params.get("WFInput") != {
            "Value": {"Type": "ExtensionInput"},
            "WFSerializationType": "WFTextTokenAttachment",
        }:
            errors.append("Get Text fallback must receive the raw ExtensionInput attachment")
        text_name, text_uuid = text_params.get("CustomOutputName"), text_params.get("UUID")
        prompt_name, prompt_uuid = prompt_params.get("CustomOutputName"), prompt_params.get("UUID")
        if link_params[1].get("WFInput") != action_output_text(text_name, text_uuid):
            errors.append("text-fallback Get URLs must receive Get Text as a text token string")
        if link_params[2].get("WFInput") != action_output_text(prompt_name, prompt_uuid):
            errors.append("prompted Get URLs must receive the entered URL as a text token string")
        if (
            prompt_params.get("WFInputType") != "Text"
            or prompt_params.get("WFAskActionDefaultAnswer") != ""
            or prompt_params.get("WFAllowsMultilineText") is not False
        ):
            errors.append("URL prompt must be empty-default, text-typed, and single-line")
        link_indexes = [workflow_actions.index(action) for action in link_actions]
        text_index = workflow_actions.index(text_actions[0])
        prompt_index = workflow_actions.index(prompts[0])
        if not (link_indexes[0] < text_index < link_indexes[1] < prompt_index < link_indexes[2]):
            errors.append("URL extraction actions are out of direct-to-fallback order")
        # The text and URL-prompt branches are guarded by empty inputURLs checks.
        missing_input_conditions = [
            index for index, action in enumerate(workflow_actions)
            if action.get("WFWorkflowActionIdentifier") == "is.workflow.actions.conditional"
            and parameters(action).get("WFCondition") == 101
            and any(node.get("VariableName") == "inputURLs"
                    for node in walk(parameters(action).get("WFInput", {})))
        ]
        if len(missing_input_conditions) < 2:
            errors.append("text and URL prompt fallbacks must be guarded by empty URL checks")
        else:
            for start, target in zip(missing_input_conditions[:2],
                                     (text_index, prompt_index)):
                group = parameters(workflow_actions[start]).get("GroupingIdentifier")
                end = next((index for index in range(start + 1, len(workflow_actions))
                            if workflow_actions[index].get("WFWorkflowActionIdentifier")
                            == "is.workflow.actions.conditional"
                            and parameters(workflow_actions[index]).get("WFControlFlowMode") == 2
                            and parameters(workflow_actions[index]).get("GroupingIdentifier") == group),
                           None)
                if end is None or not start < target < end:
                    errors.append("URL fallback action is outside its empty-input branch")
    output_actions = {
        parameters(action).get("CustomOutputName"): action
        for action in workflow_actions
    }
    outputs = {name: parameters(action) for name, action in output_actions.items()}
    if public:
        for input_name, source_name in (
            ("normalizedServerAddress", "serverAddress"),
            ("serverMatch", "normalizedServerAddress"),
        ):
            target = outputs.get(input_name)
            source = outputs.get(source_name)
            if not isinstance(target, dict) or not isinstance(source, dict):
                errors.append(f"{input_name} text input action is missing")
            elif target.get("WFInput") != action_output_text(source_name, source.get("UUID", "")):
                errors.append(f"{input_name} must receive {source_name} as a text token string")
    else:
        server = outputs.get("serverAddress")
        normalized = outputs.get("normalizedServerAddress")
        matched = outputs.get("serverMatch")
        if not all(isinstance(value, dict) for value in (server, normalized, matched)):
            errors.append("private address validation actions are missing")
        else:
            origin = server.get("WFTextActionText")
            if (
                output_actions["serverAddress"].get("WFWorkflowActionIdentifier")
                != "is.workflow.actions.gettext"
                or not _valid_https_origin(origin)
                or server.get("CustomOutputName") != "serverAddress"
            ):
                errors.append("private serverAddress must be a literal HTTPS origin")
            for action, output_name in ((normalized, "normalizedServerAddress"),
                                        (matched, "serverMatch")):
                if (
                    output_actions[output_name].get("WFWorkflowActionIdentifier")
                    != "is.workflow.actions.gettext"
                    or action.get("CustomOutputName") != output_name
                    or not isinstance(action.get("WFTextActionText"), str)
                ):
                    errors.append(f"private {output_name} must be a literal text action")
            if normalized.get("WFTextActionText") != origin or not _valid_https_origin(
                normalized.get("WFTextActionText")
            ):
                errors.append("private normalizedServerAddress must match a valid HTTPS origin")
            if matched.get("WFTextActionText") != "validated":
                errors.append("private serverMatch must contain the validated marker")
    if RAW_ACTION in identifiers:
        errors.append("raw placeholder action remains")
    if RUN_SHORTCUT in identifiers:
        errors.append("unexpected Run Shortcut self-invocation")

    repeats = [parameters(action) for action in workflow_actions if action.get("WFWorkflowActionIdentifier") == "is.workflow.actions.repeat.count" and parameters(action).get("WFControlFlowMode") == 0]
    waits = [parameters(action).get("WFDelayTime") for action in workflow_actions if action.get("WFWorkflowActionIdentifier") == "is.workflow.actions.delay"]
    if len(repeats) != 1 or repeats[0].get("WFRepeatCount") != 120:
        errors.append("polling must use one 120-iteration repeat")
    if waits != [5]:
        errors.append("polling must contain one five-second wait")

    for index, action in enumerate(workflow_actions):
        identifier = action.get("WFWorkflowActionIdentifier")
        params = parameters(action)
        if identifier == MATCH_TEXT and "WFInput" not in params:
            errors.append(f"Match Text action {index} has no explicit input")
        if identifier == "is.workflow.actions.math":
            for key in ("WFMathOperation", "WFInput", "WFMathOperand"):
                if key not in params:
                    errors.append(f"Math action {index} is missing {key}")
        if identifier == "is.workflow.actions.exit":
            previous = workflow_actions[index - 1] if index else {}
            if previous.get("WFWorkflowActionIdentifier") != "is.workflow.actions.nothing":
                errors.append(f"terminal exit at action {index} lacks cleanup")

    file_download = next(
        (i for i, action in enumerate(workflow_actions) if parameters(action).get("CustomOutputName") == "DownloadURL"),
        None,
    )
    output_ids = {
        "is.workflow.actions.savetocameraroll",
        "is.workflow.actions.documentpicker.save",
        "is.workflow.actions.share",
    }
    output_indexes = [i for i, identifier in enumerate(identifiers) if identifier in output_ids]
    rename_indexes = [i for i, identifier in enumerate(identifiers) if identifier == "is.workflow.actions.setitemname"]
    if file_download is None or not output_indexes or not rename_indexes:
        errors.append("download, rename, and output actions must exist")
    elif not (file_download < min(rename_indexes) < min(output_indexes)):
        errors.append("file must be downloaded, then renamed, then output")
    for index in output_indexes:
        if reference_name(parameters(workflow_actions[index]).get("WFInput")) != "finalFile":
            errors.append(f"output action {index} must receive finalFile")
        if index + 1 >= len(workflow_actions) or identifiers[index + 1] != "is.workflow.actions.nothing":
            errors.append(f"output action {index} lacks cleanup")


def validate_shortcut(shortcut: dict[str, Any], *, public: bool = True) -> None:
    errors: list[str] = []
    _validate_action_outputs(shortcut, errors)
    _validate_questions(shortcut, errors, public)
    _validate_http(shortcut, errors)
    _validate_control_and_outputs(shortcut, errors, public=public)
    if errors:
        raise ShortcutValidationError("\n".join(errors))


def load_shortcut(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        value = plistlib.load(stream)
    if not isinstance(value, dict):
        raise ShortcutValidationError("Shortcut plist root must be a dictionary")
    return value


def write_shortcut(path: Path, shortcut: dict[str, Any]) -> None:
    with path.open("wb") as stream:
        plistlib.dump(shortcut, stream, fmt=plistlib.FMT_BINARY, sort_keys=True)


def finalize(path: Path) -> None:
    shortcut = load_shortcut(path)
    repair_raw_actions(shortcut)
    repair_match_text(shortcut)
    repair_import_questions(shortcut)
    repair_address_inputs(shortcut)
    repair_shared_url_inputs(shortcut)
    derive_uuids(shortcut)
    canonicalize_dictionaries(shortcut)
    validate_shortcut(shortcut)
    write_shortcut(path, shortcut)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {Path(argv[0]).name} SHORTCUT_unsigned.shortcut", file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        finalize(path)
    except (OSError, plistlib.InvalidFileException, ShortcutValidationError) as exc:
        print(f"finalize failed: {exc}", file=sys.stderr)
        return 1
    print(f"finalized and validated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
