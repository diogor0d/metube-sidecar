from __future__ import annotations

import copy
import plistlib
import sys
import unittest
from pathlib import Path
from typing import Any, Iterable


SHORTCUTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHORTCUTS_DIR))

from finalize import (  # noqa: E402
    IMPORT_QUESTIONS,
    ShortcutValidationError,
    action_output_text,
    dictionary_items,
    parameters,
    reference_name,
    token_string,
    validate_shortcut,
    walk,
)


ARTIFACT = SHORTCUTS_DIR / "MeTube Download_unsigned.shortcut"


class ShortcutStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not ARTIFACT.exists():
            raise FileNotFoundError(
                f"{ARTIFACT.name} is missing; compile and finalize it before testing"
            )
        with ARTIFACT.open("rb") as stream:
            cls.shortcut = plistlib.load(stream)
        cls.actions = cls.shortcut["WFWorkflowActions"]

    def matching(self, identifier: str) -> list[dict[str, Any]]:
        return [
            action
            for action in self.actions
            if action["WFWorkflowActionIdentifier"] == identifier
        ]

    def index_with_output(self, output_name: str) -> int:
        return next(
            index
            for index, action in enumerate(self.actions)
            if parameters(action).get("CustomOutputName") == output_name
        )

    def guard_for_variable(self, variable_name: str) -> tuple[int, int]:
        start = next(
            index
            for index, action in enumerate(self.actions)
            if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.conditional"
            and any(
                node.get("VariableName") == variable_name
                or node.get("OutputName") == variable_name
                for node in walk(parameters(action).get("WFInput", {}))
            )
            and parameters(action).get("WFControlFlowMode") == 0
        )
        end = next(
            index
            for index in range(start + 1, len(self.actions))
            if self.actions[index]["WFWorkflowActionIdentifier"]
            == "is.workflow.actions.conditional"
            and parameters(self.actions[index]).get("WFControlFlowMode") == 2
        )
        return start, end

    def test_finalizer_validation_passes(self) -> None:
        try:
            validate_shortcut(self.shortcut)
        except ShortcutValidationError as exc:
            self.fail(str(exc))

    def test_rejects_named_global_input_that_lost_urls_in_native_probe(self) -> None:
        broken = copy.deepcopy(self.shortcut)
        extractor = next(action for action in broken["WFWorkflowActions"]
                         if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.detect.link")
        parameters(extractor)["WFInput"]["Value"]["VariableName"] = "ShortcutInput"
        with self.assertRaisesRegex(ShortcutValidationError, "ExtensionInput"):
            validate_shortcut(broken)

    def test_rejects_bare_action_output_attachments_for_text_address_inputs(self) -> None:
        for output_name in ("normalizedServerAddress", "serverMatch"):
            with self.subTest(output_name=output_name):
                broken = copy.deepcopy(self.shortcut)
                action = next(a for a in broken["WFWorkflowActions"]
                              if parameters(a).get("CustomOutputName") == output_name)
                _, references = token_string(parameters(action)["WFInput"])
                self.assertEqual(len(references), 1)
                parameters(action)["WFInput"] = {
                    "Value": references[0],
                    "WFSerializationType": "WFTextTokenAttachment",
                }
                with self.assertRaisesRegex(ShortcutValidationError,
                                            "text token string"):
                    validate_shortcut(broken)

    def configured_private_shortcut(self, origin: str,
                                    marker: str = "validated") -> dict[str, Any]:
        configured = copy.deepcopy(self.shortcut)
        named = {
            parameters(action).get("CustomOutputName"): action
            for action in configured["WFWorkflowActions"]
        }
        for output_name, value in (("serverAddress", origin),
                                   ("normalizedServerAddress", origin),
                                   ("serverMatch", marker)):
            action = named[output_name]
            params = action["WFWorkflowActionParameters"]
            action["WFWorkflowActionIdentifier"] = "is.workflow.actions.gettext"
            action["WFWorkflowActionParameters"] = {
                "CustomOutputName": output_name,
                "UUID": params["UUID"],
                "WFTextActionText": value,
            }
        configured["WFWorkflowImportQuestions"] = []
        return configured

    def test_accepts_safe_prevalidated_private_address_literals(self) -> None:
        try:
            validate_shortcut(
                self.configured_private_shortcut("https://download-api.example.com"),
                public=False,
            )
        except ShortcutValidationError as exc:
            self.fail(str(exc))

    def test_rejects_invalid_private_address_literals_and_marker(self) -> None:
        for origin in (
            "",
            "http://download-api.example.com",
            "https://user:pass@download-api.example.com",
            "https://download-api.example.com/path",
            "https://download-api.example.com?token=x",
            "https://download-api.example.com#fragment",
        ):
            with self.subTest(origin=origin):
                with self.assertRaisesRegex(ShortcutValidationError,
                                            "HTTPS origin"):
                    validate_shortcut(self.configured_private_shortcut(origin),
                                      public=False)
        with self.assertRaisesRegex(ShortcutValidationError, "validated marker"):
            validate_shortcut(
                self.configured_private_shortcut(
                    "https://download-api.example.com", marker="no"
                ),
                public=False,
            )

    def test_public_validation_rejects_private_literal_address_bypass(self) -> None:
        with self.assertRaisesRegex(ShortcutValidationError,
                                    "text token string"):
            validate_shortcut(
                self.configured_private_shortcut("https://download-api.example.com"),
                public=True,
            )

    def test_action_outputs_exist_and_precede_references(self) -> None:
        seen: set[str] = set()
        for index, action in enumerate(self.actions):
            params = parameters(action)
            for node in walk(params):
                output_uuid = node.get("OutputUUID")
                if output_uuid is not None:
                    self.assertIn(output_uuid, seen, f"bad reference at action {index}")
            own_uuid = params.get("UUID")
            if own_uuid:
                seen.add(own_uuid)

    def test_import_questions_are_blank_and_target_configuration_text(self) -> None:
        questions = self.shortcut["WFWorkflowImportQuestions"]
        self.assertEqual(len(questions), len(IMPORT_QUESTIONS))
        expected = dict(IMPORT_QUESTIONS)
        for question in questions:
            self.assertEqual(question["DefaultValue"], "")
            self.assertEqual(question["Category"], "Parameter")
            self.assertEqual(question["ParameterKey"], "WFTextActionText")
            action = self.actions[question["ActionIndex"]]
            params = parameters(action)
            self.assertEqual(params["CustomOutputName"], expected[question["Text"]])
            self.assertEqual(params["WFTextActionText"], "")

    def test_no_placeholder_or_self_invoking_actions(self) -> None:
        identifiers = {
            action["WFWorkflowActionIdentifier"] for action in self.actions
        }
        self.assertNotIn("is.workflow.actions.rawaction", identifiers)
        self.assertNotIn("is.workflow.actions.runworkflow", identifiers)
        self.assertNotIn("is.workflow.actions.choosefrommenu", identifiers)

    def test_match_text_actions_have_explicit_inputs(self) -> None:
        matches = self.matching("is.workflow.actions.text.match")
        self.assertEqual(len(matches), 1)
        for action in matches:
            params = parameters(action)
            self.assertIn("WFInput", params)
            self.assertNotIn("text", params)
            text, references = token_string(params["WFInput"])
            self.assertEqual(params.get("CustomOutputName"), "serverMatch")
            self.assertEqual(text, "\ufffc")
            self.assertEqual(len(references), 1)
            self.assertEqual(references[0]["Type"], "ActionOutput")
            self.assertEqual(
                reference_name(params["WFInput"]),
                "normalizedServerAddress",
            )
            self.assertEqual(
                params["WFInput"]["WFSerializationType"],
                "WFTextTokenString",
            )

    def test_direct_launch_requests_a_url_without_changing_shared_input(self) -> None:
        self.assertNotIn("WFWorkflowNoInputBehavior", self.shortcut)
        prompts = self.matching("is.workflow.actions.ask")
        self.assertEqual(len(prompts), 1)
        params = parameters(prompts[0])
        self.assertEqual(params["WFInputType"], "Text")
        self.assertEqual(params["WFAskActionDefaultAnswer"], "")
        self.assertIs(params["WFAllowsMultilineText"], False)
        self.assertEqual(params["WFAskActionPrompt"], "Paste media URL")

    def test_share_sheet_accepts_app_payloads_without_notifications(self) -> None:
        self.assertIn("ActionExtension", self.shortcut["WFWorkflowTypes"])
        input_classes = set(self.shortcut["WFWorkflowInputContentItemClasses"])
        self.assertTrue({
            "WFURLContentItem", "WFStringContentItem", "WFSafariWebPageContentItem",
            "WFArticleContentItem", "WFRichTextContentItem",
            "WFGenericFileContentItem", "WFImageContentItem", "WFAVAssetContentItem",
        }.issubset(input_classes))
        self.assertEqual(self.matching("is.workflow.actions.notification"), [])
        identifiers = [action["WFWorkflowActionIdentifier"] for action in self.actions]
        self.assertEqual(identifiers.count("is.workflow.actions.detect.text"), 1)
        self.assertEqual(identifiers.count("is.workflow.actions.detect.link"), 3)

    def test_shared_url_detection_has_explicit_inputs_and_empty_result_exit(self) -> None:
        extractors = self.matching("is.workflow.actions.detect.link")
        self.assertEqual(len(extractors), 3)
        self.assertEqual(parameters(extractors[0])["WFInput"]["Value"], {
            "string": "\ufffc",
            "attachmentsByRange": {"{0, 1}": {"Type": "ExtensionInput"}},
        })
        text_action = self.matching("is.workflow.actions.detect.text")[0]
        text_params = parameters(text_action)
        self.assertEqual(text_params["WFInput"], {
            "Value": {"Type": "ExtensionInput"},
            "WFSerializationType": "WFTextTokenAttachment",
        })
        prompt = self.matching("is.workflow.actions.ask")[0]
        self.assertEqual(
            parameters(extractors[1])["WFInput"],
            action_output_text(text_params["CustomOutputName"], text_params["UUID"]),
        )
        self.assertEqual(
            parameters(extractors[2])["WFInput"],
            action_output_text(parameters(prompt)["CustomOutputName"],
                               parameters(prompt)["UUID"]),
        )
        for extractor in extractors:
            self.assertEqual(parameters(extractor)["WFInput"]["WFSerializationType"],
                             "WFTextTokenString")
        positions = [self.actions.index(action) for action in extractors]
        text_index = self.actions.index(text_action)
        prompt_index = self.actions.index(prompt)
        self.assertLess(positions[0], text_index)
        self.assertLess(text_index, positions[1])
        self.assertLess(positions[1], prompt_index)
        self.assertLess(prompt_index, positions[2])

        empty_guards = [
            index for index, action in enumerate(self.actions)
            if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.conditional"
            and parameters(action).get("WFCondition") == 101
            and any(node.get("VariableName") == "inputURLs"
                    for node in walk(parameters(action).get("WFInput", {})))
        ]
        self.assertGreaterEqual(len(empty_guards), 2)
        for start, target in zip(empty_guards[:2], (text_index, prompt_index)):
            group = parameters(self.actions[start]).get("GroupingIdentifier")
            end = next(
                index for index in range(start + 1, len(self.actions))
                if self.actions[index]["WFWorkflowActionIdentifier"]
                == "is.workflow.actions.conditional"
                and parameters(self.actions[index]).get("WFControlFlowMode") == 2
                and parameters(self.actions[index]).get("GroupingIdentifier") == group
            )
            self.assertLess(start, target)
            self.assertLess(target, end)
        first_item_index = next(
            index for index, action in enumerate(self.actions)
            if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.getitemfromlist"
        )
        preceding = self.actions[:first_item_index]
        self.assertEqual(sum(
            action["WFWorkflowActionIdentifier"] == "is.workflow.actions.text.match"
            for action in preceding
        ), 1)  # Only the public sidecar address check; no input text coercion.
        self.assertTrue(any(
            parameters(action).get("WFAlertActionTitle") == "No usable URL"
            for action in preceding
        ))
        self.assertGreaterEqual(sum(
            action["WFWorkflowActionIdentifier"] == "is.workflow.actions.exit"
            for action in preceding
        ), 2)

    def test_production_feedback_is_quiet_and_failure_alerts_are_plain(self) -> None:
        self.assertEqual(self.matching("is.workflow.actions.notification"), [])
        for action in self.matching("is.workflow.actions.alert"):
            params = parameters(action)
            self.assertNotRegex(params["WFAlertActionTitle"], r"^D\d{2}/\d{2}")
            message, references = token_string(params["WFAlertActionMessage"])
            self.assertNotRegex(message, r"^D\d{2}/\d{2}")
            self.assertEqual(references, [], "alerts must not expose upstream response data")

    def test_output_menu_contains_only_production_modes(self) -> None:
        mode_picker = next(
            parameters(action)
            for action in self.matching("is.workflow.actions.choosefromlist")
            if parameters(action).get("WFChooseFromListActionPrompt") == "Choose output"
        )
        mode_list = parameters(self.matching("is.workflow.actions.list")[0])
        self.assertEqual(
            [item["WFValue"] for item in mode_list["WFItems"]],
            ["Video", "Image", "GIF"],
        )
        self.assertEqual(reference_name(mode_picker["WFInput"]), "modeOptions")
        self.assertNotIn("debugMode", self.shortcut)
        rendered = repr(self.shortcut)
        self.assertNotIn("Debug", rendered)
        self.assertNotIn("debugMode", rendered)

    def test_http_contract_and_sensitive_header_references(self) -> None:
        requests = self.matching("is.workflow.actions.downloadurl")
        self.assertEqual([parameters(a)["WFHTTPMethod"] for a in requests], ["POST", "GET", "GET"])
        post = parameters(requests[0])
        self.assertEqual(post["WFHTTPBodyType"], "JSON")
        body = dictionary_items(post["WFJSONValues"])
        self.assertEqual(set(body), {"url", "quality", "format", "download_type", "codec"})
        self.assertEqual(token_string(body["quality"]), ("best", []))
        self.assertEqual(reference_name(body["url"]), "sourceURL")
        self.assertEqual(reference_name(body["format"]), "mediaFormat")
        self.assertEqual(reference_name(body["download_type"]), "downloadType")
        self.assertEqual(reference_name(body["codec"]), "codec")

        required = {
            "CF-Access-Client-Id": "clientID",
            "CF-Access-Client-Secret": "clientSecret",
            "X-Sidecar-Api-Key": "sidecarAPIKey",
        }
        for position, request in enumerate(requests):
            headers = dictionary_items(parameters(request)["WFHTTPHeaders"])
            for name, output in required.items():
                self.assertEqual(reference_name(headers[name]), output)
            expected_keys = set(required)
            if position == 0:
                expected_keys.add("Content-Type")
                self.assertEqual(token_string(headers["Content-Type"]), ("application/json", []))
            self.assertEqual(set(headers), expected_keys)

    def test_server_returned_paths_are_not_used_as_origins(self) -> None:
        requests = self.matching("is.workflow.actions.downloadurl")
        expected = [
            ("normalizedServerAddress",),
            ("normalizedServerAddress", "expectedPollPath"),
            ("normalizedServerAddress", "expectedFilePath"),
        ]
        self.assertEqual(len(requests), len(expected))
        for request, expected_names in zip(requests, expected):
            _, refs = token_string(parameters(request)["WFURL"])
            names = tuple(ref.get("OutputName") or ref.get("VariableName") for ref in refs)
            self.assertEqual(names, expected_names)

    def test_trailing_sidecar_slashes_are_removed_before_validation(self) -> None:
        normalizer = next(
            parameters(action)
            for action in self.matching("is.workflow.actions.text.replace")
            if parameters(action).get("CustomOutputName") == "normalizedServerAddress"
        )
        self.assertEqual(normalizer["WFReplaceTextFind"], "/+$")
        self.assertEqual(normalizer["WFReplaceTextReplace"], "")
        self.assertTrue(normalizer["WFReplaceTextRegularExpression"])
        self.assertEqual(reference_name(normalizer["WFInput"]), "serverAddress")
        self.assertEqual(
            normalizer["WFInput"]["WFSerializationType"],
            "WFTextTokenString",
        )
        matcher = next(
            parameters(action)
            for action in self.matching("is.workflow.actions.text.match")
            if parameters(action).get("CustomOutputName") == "serverMatch"
        )
        self.assertEqual(
            reference_name(matcher["WFInput"]), "normalizedServerAddress"
        )
        self.assertEqual(
            matcher["WFInput"]["WFSerializationType"],
            "WFTextTokenString",
        )

    def test_polling_and_wait_are_bounded(self) -> None:
        starts = [
            parameters(action)
            for action in self.matching("is.workflow.actions.repeat.count")
            if parameters(action).get("WFControlFlowMode") == 0
        ]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0]["WFRepeatCount"], 120)
        waits = self.matching("is.workflow.actions.delay")
        self.assertEqual(len(waits), 1)
        self.assertEqual(parameters(waits[0])["WFDelayTime"], 5)

    def test_math_actions_have_complete_native_parameters(self) -> None:
        for action in self.matching("is.workflow.actions.math"):
            params = parameters(action)
            self.assertIn("WFMathOperation", params)
            self.assertIn("WFInput", params)
            self.assertIn("WFMathOperand", params)

    def test_cleanup_covers_handled_terminal_paths(self) -> None:
        identifiers = [action["WFWorkflowActionIdentifier"] for action in self.actions]
        for index, identifier in enumerate(identifiers):
            if identifier == "is.workflow.actions.exit":
                self.assertEqual(identifiers[index - 1], "is.workflow.actions.nothing")
            if identifier in {
                "is.workflow.actions.savetocameraroll",
                "is.workflow.actions.documentpicker.save",
                "is.workflow.actions.share",
            }:
                self.assertEqual(identifiers[index + 1], "is.workflow.actions.nothing")

        picker = next(
            parameters(action)
            for action in self.matching("is.workflow.actions.choosefromlist")
            if parameters(action).get("WFChooseFromListActionPrompt") == "Keep or discard?"
        )
        destination_list = parameters(self.matching("is.workflow.actions.list")[-1])
        self.assertEqual(
            [item["WFValue"] for item in destination_list["WFItems"]],
            ["Save to Photos", "Save to Files", "Share", "Discard"],
        )
        self.assertEqual(reference_name(picker["WFInput"]), "destinationOptions")

    def test_empty_choices_and_cancelled_trim_stop_before_dependent_actions(self) -> None:
        post_index = next(
            index
            for index, action in enumerate(self.actions)
            if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.downloadurl"
            and parameters(action).get("WFHTTPMethod") == "POST"
        )
        mode_guard_start, mode_guard_end = self.guard_for_variable("modeChoice")
        self.assertLess(mode_guard_start, post_index)
        self.assertTrue(any(
            self.actions[index]["WFWorkflowActionIdentifier"] == "is.workflow.actions.exit"
            and self.actions[index - 1]["WFWorkflowActionIdentifier"] == "is.workflow.actions.nothing"
            for index in range(mode_guard_start + 1, mode_guard_end)
        ))

        trim_index = index_with_identifier(self.actions, "is.workflow.actions.trimvideo")
        trim_guard_start, trim_guard_end = self.guard_for_variable("trimmedVideo")
        self.assertLess(trim_index, trim_guard_start)
        self.assertLess(trim_guard_end, index_with_identifier(self.actions, "is.workflow.actions.makegif"))

        destination_index = self.index_with_output("destinationChoice")
        destination_guard_start, destination_guard_end = self.guard_for_variable("destinationChoice")
        first_output_index = min(
            index
            for index, action in enumerate(self.actions)
            if action["WFWorkflowActionIdentifier"] in {
                "is.workflow.actions.savetocameraroll",
                "is.workflow.actions.documentpicker.save",
                "is.workflow.actions.share",
            }
        )
        self.assertLess(destination_index, destination_guard_start)
        self.assertLess(destination_guard_end, first_output_index)

    def test_gif_creation_failure_is_fixed_stage_error_and_stops(self) -> None:
        gif_index = index_with_identifier(self.actions, "is.workflow.actions.makegif")
        guard_start, guard_end = self.guard_for_variable("gifData")
        self.assertLess(gif_index, guard_start)
        self.assertLess(guard_start, guard_end)
        guarded_actions = self.actions[guard_start + 1:guard_end]
        alert = next(
            action for action in guarded_actions
            if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.alert"
        )
        alert_params = parameters(alert)
        self.assertEqual(alert_params["WFAlertActionTitle"], "GIF creation failed")
        self.assertEqual(
            alert_params["WFAlertActionMessage"],
            "The selected video could not be converted to a GIF.",
        )
        exit_index = next(
            index for index, action in enumerate(self.actions[guard_start + 1:guard_end], guard_start + 1)
            if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.exit"
        )
        self.assertEqual(self.actions[exit_index - 1]["WFWorkflowActionIdentifier"],
                         "is.workflow.actions.nothing")

    def test_final_cleanup_and_native_media_destinations_use_expected_inputs(self) -> None:
        self.assertEqual(
            [action["WFWorkflowActionIdentifier"] for action in self.actions[-2:]],
            ["is.workflow.actions.nothing", "is.workflow.actions.exit"],
        )

        trim = self.matching("is.workflow.actions.trimvideo")[0]
        make_gif = self.matching("is.workflow.actions.makegif")[0]
        self.assertEqual(reference_name(parameters(trim)["WFInputMedia"]), "downloadedFile")
        self.assertEqual(reference_name(parameters(make_gif)["WFInput"]), "trimmedVideo")

        gif_name = next(
            parameters(action) for action in self.actions
            if parameters(action).get("CustomOutputName") == "gifName"
        )
        self.assertEqual(token_string(gif_name["WFInput"])[0], "\ufffc")
        self.assertEqual(
            [ref.get("OutputName") for ref in token_string(gif_name["WFInput"])[1]],
            ["downloadedName"],
        )
        gif_set_name = next(
            parameters(action) for action in self.matching("is.workflow.actions.setitemname")
            if reference_name(parameters(action)["WFInput"]) == "gifData"
        )
        self.assertEqual(reference_name(gif_set_name["WFName"]), "gifName")

        for identifier in (
            "is.workflow.actions.savetocameraroll",
            "is.workflow.actions.documentpicker.save",
            "is.workflow.actions.share",
        ):
            with self.subTest(identifier=identifier):
                action = self.matching(identifier)[0]
                self.assertEqual(reference_name(parameters(action)["WFInput"]), "finalFile")

    def test_download_precedes_rename_and_output(self) -> None:
        def index_with_output(name: str) -> int:
            return next(
                index
                for index, action in enumerate(self.actions)
                if parameters(action).get("CustomOutputName") == name
            )

        download_index = index_with_output("DownloadURL")
        rename_indexes = [
            index
            for index, action in enumerate(self.actions)
            if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.setitemname"
        ]
        output_indexes = [
            index
            for index, action in enumerate(self.actions)
            if action["WFWorkflowActionIdentifier"]
            in {
                "is.workflow.actions.savetocameraroll",
                "is.workflow.actions.documentpicker.save",
                "is.workflow.actions.share",
            }
        ]
        self.assertLess(download_index, min(rename_indexes))
        self.assertLess(max(rename_indexes), min(output_indexes))
        for index in output_indexes:
            self.assertEqual(reference_name(parameters(self.actions[index])["WFInput"]), "finalFile")

    def test_gif_is_trimmed_converted_and_named_gif(self) -> None:
        trim_index = index_with_identifier(self.actions, "is.workflow.actions.trimvideo")
        gif_index = index_with_identifier(self.actions, "is.workflow.actions.makegif")
        replace_index = next(
            index
            for index, action in enumerate(self.actions)
            if parameters(action).get("CustomOutputName") == "gifName"
        )
        self.assertLess(trim_index, gif_index)
        self.assertLess(gif_index, replace_index)
        replace = parameters(self.actions[replace_index])
        self.assertTrue(replace["WFReplaceTextRegularExpression"])
        self.assertEqual(replace["WFReplaceTextFind"], r"\.[^.]+$")
        self.assertEqual(replace["WFReplaceTextReplace"], ".gif")

    def test_public_artifact_contains_no_configured_values(self) -> None:
        config_names = {output for _, output in IMPORT_QUESTIONS}
        for action in self.actions:
            params = parameters(action)
            if params.get("CustomOutputName") in config_names:
                self.assertEqual(params["WFTextActionText"], "")


def index_with_identifier(actions: Iterable[dict[str, Any]], identifier: str) -> int:
    return next(
        index
        for index, action in enumerate(actions)
        if action["WFWorkflowActionIdentifier"] == identifier
    )


if __name__ == "__main__":
    unittest.main()
