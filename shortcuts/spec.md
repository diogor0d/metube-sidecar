# MeTube Download Shortcut specification

## Contract

The Shortcut receives URL, text, webpage, article, rich-text, file, image,
and media Share Sheet items. It passes `Shortcut Input` directly to the native
Get URLs action using a `WFTextTokenString` containing the native
`ExtensionInput` token without `VariableName`.
A macOS probe confirmed that adding that named-variable field loses the URL.
The corrected full workflow still requires native and iOS acceptance. If no URL is
found, it converts Shortcut Input to text through Get Text and retries Get URLs
using that action's output. If this also yields no link, an explicit Ask for Input
action requests a URL. This runs within the graph rather than relying on an
implicit no-input policy. Valid shared links bypass the prompt; unusable entered
input shows a plain missing-URL error before networking. No clipboard is read
automatically.
The selected URL is sent to the sidecar, which validates that it is an absolute
HTTP(S) URL before submitting it to MeTube.
Each invocation uses one output picker with Video, Image and GIF. The production
graph contains no notification actions, Debug choices or stage-coded diagnostic
messages. URL entry, output/destination choices and useful plain-language failure
alerts remain. Developer diagnostics belong in private testing receipts.
Its four distributable configuration actions are blank import questions:

| Output name | Setup question | Required |
|---|---|---|
| `serverAddress` | HTTPS sidecar address | yes |
| `clientID` | Cloudflare Access client ID | yes |
| `clientSecret` | Cloudflare Access client secret | yes |
| `sidecarAPIKey` | Optional sidecar API key | no |

The sidecar address must be an HTTPS origin. Paths, query strings, fragments,
and userinfo are rejected before any network action. Trailing slashes are
removed before validation and URL construction.
Configured artifacts embed the origin validated by `prepare-private.py` directly
in the request-origin output and replace the redundant runtime match with a
nonempty validated marker. The public unsigned artifact retains runtime address
normalization and validation for interactive imports.

## Media modes

| Choice | Sidecar request | Local processing |
|---|---|---|
| Video | `download_type=video`, `format=ios`, `codec=h264`, `quality=best` | none |
| Image | `download_type=thumbnail`, `format=jpg`, `codec=auto`, `quality=best` | none |
| GIF | same request as Video | Trim Video, Make GIF, replace extension with `.gif` |

All modes offer Save to Photos, Save to Files, Share, and Discard. The file is
downloaded and renamed before any destination action. Empty media/destination
selections and empty trim results stop before dependent operations; empty GIF
output raises a plain GIF creation error and stops. The workflow ends with an explicit stop.

## HTTP graph

1. `POST {serverAddress}/jobs` with a JSON body and Cloudflare, optional sidecar,
   and content-type headers.
2. Require `id` and require `poll_url` to equal `/jobs/{id}`.
3. Poll `{serverAddress}/jobs/{id}` at most 120 times, waiting five seconds first.
4. On `complete`, require `file_url` to equal `/jobs/{id}/file`.
5. Download only `{serverAddress}/jobs/{id}/file`, using the same authentication headers.
6. On `failed`, rejection, unsafe response, or timeout, alert, clean up, and stop.

Server-provided strings never supply an origin. This prevents credentials from
being forwarded to an attacker-selected host.

## Structural invariants

- Every `ActionOutput` UUID resolves to an earlier action.
- Direct Get URLs and fallback Get Text use native `ExtensionInput` attachments
  without `VariableName`. Fallback and entered-URL extractors use explicit
  ActionOutput text tokens for their respective producers.
- Import questions target the four named Text actions and have blank defaults.
- Match Text uses explicit `WFInput`; no raw placeholder or Run Shortcut remains.
- There are exactly three HTTP actions with methods `POST`, `GET`, `GET`.
- Sensitive headers are ActionOutput references, never literals.
- The only repeat is 120 iterations and the only wait is five seconds.
- Native Math actions, if introduced, must contain operation and both operands.
- Explicit terminal exits and all keep/discard branches contain cleanup.
- Download precedes rename; rename precedes Save or Share.

`finalize.py` repairs known Cherri 2.3.0 serialization defects, derives stable
UUIDs from graph positions, enforces these invariants, and rewrites the unsigned
plist deterministically before signing.
