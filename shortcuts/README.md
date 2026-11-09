# MeTube Download Shortcut

Reviewable Cherri source for a native Apple Shortcut that submits video,
thumbnail, or GIF-source jobs to metube-sidecar. It is intended for Share Sheet
use and direct launch. When input has no extractable link, an explicit
URL prompt asks for the media page or link. Public source and unsigned artifacts contain no configured
hostname or credential.

The GIF mode downloads an iOS-compatible video, asks the user to trim it, and
uses the native Make GIF action. Image mode asks MeTube for its JPEG thumbnail.

Production offers only **Video**, **Image**, and **GIF**. It emits no diagnostic
notifications, debug menu choices, poll traces or stage-coded messages. Useful
plain-language errors remain. The test harness records its private receipts
without adding diagnostics to the installed product.

## Quick test on macOS

From the repository's `shortcuts` directory (or its fully synced staged copy),
run:

```bash
sh ./run-on-mac.sh
```

What it does: prompts clearly for missing Cloudflare credentials, embeds them
only in the local private artifact, removes all setup questions, signs with
Apple's CLI, and opens the signed Shortcut. The disabled sidecar API key remains
blank without another prompt.

The development script prints `MeTube runner build 2026.10.06.5` before processing.
If that line is absent, wait for the staged folder to finish syncing before
testing it.

The runner's build marker is terminal output for development, not a notification
in the production Shortcut. Build `2026.10.06.5` removes the older diagnostic
messages while retaining the same input, network and media handling.

The runner checks the credentials against the sidecar's `/healthz` endpoint
before generating or signing anything. The check sends an explicit Safari user
agent because this Cloudflare setup rejects Python's default user agent. Only
after a successful `200` response with `{"status":"ok"}` does the runner save
newly entered values in macOS Keychain. It reads them from Keychain on later
runs, so the synced Google Drive folder never receives the credentials. The
configured and signed Shortcut are generated under
`~/Library/Application Support/MeTube Sidecar` instead of the synced folder. To
remove the saved values:

```bash
sh ./run-on-mac.sh --forget-credentials
```

What it does: deletes only this Shortcut's two entries from the current Mac's Keychain; it does not delete Cloudflare service tokens.

The runner makes one authenticated `/healthz` request with curl. If troubleshooting
separately with Python's `urllib`, use an explicit Cloudflare-accepted `User-Agent`; the previous staged workflow reported rejecting the default `Python-urllib/...`
value even with valid Access credentials. That edge behavior has not been
reverified during this Mac session. A `403` from that default client therefore does not establish that
the stored credentials are invalid.

For configured copies, `prepare-private.py` validates the HTTPS origin before
signing and embeds it directly in the request-origin output action. The iPhone
does not have to re-normalize or regex-match the already validated address.

The Share Sheet declares URL, text, webpage, article, rich text, file, image,
and media support. Real app payloads still require the on-device checks. It calls **Get
URLs from Shortcut Input directly** first. If extraction is empty, it converts
the input to text and tries again, using the wiring that passed the native Mac
adapters. If neither path finds a link, an explicit Ask for Input action requests
a media URL. Successful shared links bypass that prompt. Empty or unusable
entered input shows a plain missing-URL error before any job request. No clipboard is read
automatically. Prompt display and cancellation still need device verification.

## Toolchain

- Cherri 2.3.0 at commit `d2072c62ea708e7727099fab94fa28b0bcec747b`
- Python 3.12+ and the project environment (`httpx`, `uvicorn`); plist handling
  and tests use the standard library
- Apple's `shortcuts` CLI on macOS for signing

Build the pinned Cherri executable from source rather than using an unverified
moving release:

```bash
git clone https://github.com/electrikmilk/cherri.git
git -C cherri checkout d2072c62ea708e7727099fab94fa28b0bcec747b
go build -C cherri -o cherri .
```

What it does: checks out the reviewed Cherri 2.3.0 revision and builds it locally; it requires Git and Go.

Verify the pin:

```bash
git -C cherri rev-parse HEAD
./cherri/cherri --version
```

What it does: confirms the exact source revision and compiler version before artifact generation.

WSL can build and run Cherri while the repository remains on Windows. Final
signing still requires macOS.

## Public build

Run from this directory:

```bash
cherri main.cherri --skip-sign
python3 finalize.py "MeTube Download_unsigned.shortcut"
python3 -m unittest discover -s tests -v
```

What it does: compiles without any signing fallback, repairs and deterministically rewrites the unsigned plist, and runs structural regression tests.

Do not omit `--skip-sign`. Cherri otherwise supports non-Apple signing
fallbacks, which this project deliberately does not use. Do not modify the
artifact after signing because any plist change invalidates Apple's signature.

`finalize.py` is intentionally in-place. Repeating compilation and finalization
from the same source produces the same finalized bytes. The generated
`*_unsigned.shortcut` and signed `.shortcut` files are Git-ignored.

## Local native test harness

The harness prepares test-only Video and Image Shortcuts from the finalized
unsigned artifact and runs the actual sidecar app against a mocked MeTube
transport. It binds only to `127.0.0.1`, requires the synthetic fixture files
`fixture.mp4` and `fixture.jpg` in the work directory, and writes request counts
to `report.json`. It does not contact a real MeTube server or the internet.

From the repository root, prepare the four unsigned artifacts and start the
mock service in separate Terminal windows:

```bash
.venv/bin/python shortcuts/native_test.py prepare --work-dir /tmp/metube-shortcut-test --port 18765
.venv/bin/python shortcuts/native_test.py serve --work-dir /tmp/metube-shortcut-test --port 18765
```

What it does: writes unsigned Video and Image test Shortcuts, matching URL
driver Shortcuts, and a synthetic URL input file, then serves the actual
sidecar API on loopback. Preparation copies bundled synthetic `fixture.mp4`
and `fixture.jpg` files into the work directory, preserving existing fixtures.
The server uses fixed
synthetic authentication values embedded in the test variants and rejects
requests without them. Do not substitute production or private credentials.

On macOS, sign and import the unsigned test and driver artifacts with Apple's
Shortcuts CLI. Run **MeTube Local Driver Video** and **MeTube Local Driver
Image** to supply URL text to the corresponding test Shortcut; running a test
Shortcut with a generic `.txt` or `.webloc` file does not make its contents a
Share Sheet URL. The driver calls the test Shortcut with a native Text action.
The driver path is currently unverified: a native run stalled at Run Shortcut
before sending a request. Test artifacts now return fixed stage/title receipts
on failure instead of displaying blocking alerts; the public Shortcut retains
its user-facing alerts. The explicit URL prompt is also replaced by a fixed
failure receipt and stop in headless copies, so missing input cannot open a
textbox or silently produce a successful test.
Inspect `/tmp/metube-shortcut-test/report.json` after requests and stop the
server with Ctrl-C when finished.

After importing both test Shortcuts and their matching drivers, run in another
terminal while the loopback server is active:

```bash
.venv/bin/python shortcuts/native_test.py run --work-dir /tmp/metube-shortcut-test --port 18765
```

What it does: acquires the shared Shortcuts UI lock, checks that both test/driver
pairs have registered in `shortcuts list`, checks that the loopback
server has no previous job requests, runs both native drivers, then checks returned file hashes against
the actual server fixtures and requires submit/poll/file requests for both media
types. macOS may require manual permission approvals. A failed check exits with
status 1. Each driver has a 45-second deadline; a timeout cancels only its CLI
process and stops before starting another driver. The script never clicks a
dialog, imports a Shortcut, or changes desktop focus. A stalled dialog may still
need manual cancellation. It refuses to run while another chat owns the shared
UI lock, and preserves previous output files instead of overwriting them.
An import dialog disappearing does not establish registration: wait for both
pairs to appear in the installed list before running this command. Missing
registration stops the test before network requests or driver execution.
Use a fresh work directory and server for each acceptance run so stale outputs and
request counts cannot be mistaken for evidence from a new run. The verifier
checks saved evidence; it cannot establish how that evidence was produced.
The runner records its invocation result in `native-run.json`. To check existing
files without launching anything, use `native_test.py verify --work-dir` with the
same directory.

For diagnosis of the nested driver separately from the workflow, prepare with
`--direct-cli`. This also writes `MeTube Local Direct Video` and
`MeTube Local Direct Image`. These copies now use the production URL path,
including its text-conversion fallback, and can be invoked directly with
`shortcuts run ... --input-path .../url-input.txt --output-path ...` after signing
and importing. This adapter does not prove Share Sheet input behavior. Its
returned file must still match the fixture and the request counts must show
submit, poll, and file delivery. A returned stage/title receipt is a failed test.
The bounded runner accepts `run --direct-cli` for these two copies. It checks
their registration and requires `url-input.txt`, then applies the same fresh
server, lock, timeout, file hash, and request lifecycle checks.
Earlier direct native Video and Image adapter runs passed on 2026-10-06: each submitted,
polled, and downloaded its fixture, with exact byte matches. The Get URLs input
requires `WFTextTokenString`; the earlier bare attachment returned no URLs.
Build .4 reuses that tested text-to-URL wiring as a fallback; the new three-stage
input graph and explicit prompt have not yet been run natively. The address
replacement and match text inputs now use this serialization too.
Their original native configuration graph remains unverified: a bounded
configuration-only probe timed out without a visible alert. Private preparation
continues to validate the origin locally and embed the validated literal values.

These test variants intentionally remove notifications, select Video or Image
without a picker, reduce the polling delay to one second, and stop after the
renamed file is returned. They do not exercise mode selection, destination
selection, Save to Photos, Save to Files, Share, Discard, GIF processing, real
MeTube, or production network access. The separate on-device acceptance gate
below remains required.

## Private test copy

Run `prepare-private.py` once to create an ignored blank template at
`private/config.json`, then fill it with disposable test configuration:

```json
{
  "cf_access_client_id": "synthetic-test-id.access",
  "cf_access_client_secret": "synthetic-disposable-secret",
  "server_url": "https://download-api.example.com",
  "sidecar_api_key": ""
}
```

Create the private copy only after finalizing and testing the public artifact:

```bash
python3 prepare-private.py
```

What it does: validates the HTTPS origin, embeds each non-blank ignored test value, retains setup questions for blank values, and creates an ignored unsigned artifact plus private signing script.

To avoid Apple's setup textboxes, prompt for credentials locally instead:

```bash
python3 prepare-private.py --prompt-credentials
```

What it does: clearly prompts for the Cloudflare client ID, hides secret input,
embeds all answers only in the ignored private artifact, and removes every
Shortcut import question. It does not write the entered credentials back to
`config.json`.

If the shell already contains the credentials as `CF_ID` and `CF_SECRET`, use
the non-interactive form instead. `SIDECAR_API_KEY` is optional and should be
unset or empty when the sidecar has no secondary API key configured:

```bash
python3 prepare-private.py --from-env
```

What it does: reads those environment variables without echoing them, embeds
them only in the ignored private artifact, and removes all setup questions.

Never use long-lived or production credentials in a configured artifact. Apple
receives the complete private artifact when it is submitted for signing.

## Apple signing

Transfer the repository or unsigned artifact to macOS and run from this
directory:

```bash
./sign-on-mac.sh
```

What it does: invokes Apple's `shortcuts sign --mode anyone` service and creates `MeTube Download.shortcut`; it requires macOS, iCloud availability, and the Apple Shortcuts CLI.

For an ignored configured test copy, run `private/sign-private.sh` from the
`private` directory instead.

## Acceptance status

Compilation and structural tests are necessary but not sufficient. Native
acceptance is **PENDING**: the Mac GUI control connection is unavailable, and
the local native harness does not cover the picker, destination actions, Photos,
or real MeTube. Complete `tests/on-device.md` against the signed artifact.
Until that gate passes, the Shortcut is not claimed complete or
production-ready.

The Shortcut clears its implicit action output and stops on handled terminal paths. It does
not delete the server-side MeTube output: the sidecar's `/downloads` mount is
read-only, so retention remains an operator responsibility.

See `spec.md` for the exact graph and security invariants.

See `RELEASE.md` for the final candidate, verified scope and required backend upgrade.
