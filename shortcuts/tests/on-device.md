# On-device acceptance gate

The Shortcut is not complete until a finalized artifact is signed with Apple's
macOS `shortcuts` CLI and every applicable check below passes on a supported
iPhone or iPad. Record device/OS, sidecar revision, signed artifact checksum,
test URL class, observed filename, extension, media type, and byte count.

Current status: **PENDING**. The Mac GUI control connection is unavailable;
there are no pending dialogs or active test runners reported. The local native harness provides a narrower check of the actual
sidecar API and the Shortcut's submit/poll/path-check/download/rename graph;
it does not pass this device acceptance gate.

On 2026-10-06 the operator confirmed a successful working Shortcut run after the
MeTube repair. Device, mode and destination were not specified, so no individual
checkbox below is marked from that generic confirmation. Production API video
and JPEG checks passed independently; native GIF and destination checks are
separate. See the dated development history for the evidence boundaries.

## Local loopback harness scope

Preparation copies bundled synthetic `fixture.mp4` and `fixture.jpg` files into
its work directory without overwriting existing fixtures. Prepare and serve it
from the repository root:

```bash
.venv/bin/python shortcuts/native_test.py prepare --work-dir /tmp/metube-shortcut-test --port 18765
.venv/bin/python shortcuts/native_test.py serve --work-dir /tmp/metube-shortcut-test --port 18765
```

What it does: creates unsigned Video and Image test Shortcuts plus native URL
driver Shortcuts, then binds the actual sidecar app to `127.0.0.1` with a
mocked in-process MeTube transport. Run the matching **MeTube Local Driver
Video** or **MeTube Local Driver Image** Shortcut on the Mac to pass the URL
through a native Text action. Generic `.txt` and `.webloc` file inputs do not
exercise Shortcut URL extraction. The server writes request counts to
`report.json`; stop it with Ctrl-C.

Save the two native driver outputs as `video-result.mp4` and `image-result.jpg`
in that work directory, then run `native_test.py verify --work-dir` with the same
directory. It requires matching fixture hashes and a complete request lifecycle
for each media type. Use a fresh work directory and record the native invocation;
the verifier checks artifacts and counts, not their origin.

The `native_test.py run --work-dir ... --port ...` command automates both CLI
invocations and verification after import. It requires a fresh server and output
directory, respects the shared Shortcuts UI lock, and cancels only its own CLI
process after a 45-second timeout. macOS permissions remain manual; no dialog
automation is performed. This runner's subprocess tests do not prove a real
native run.

The harness uses only synthetic authentication and fixture data. It does not
contact real MeTube or the internet. It removes notifications, chooses one
media type in advance, reduces the poll delay to one second, and returns after
file rename. The native picker, destination selection, Save to Photos, Save to
Files, Share, Discard, GIF processing, real MeTube, and actual iPhone/iPad
behavior remain untested by this harness. Do not mark the device checks below
complete based on a harness run.

## Installation and configuration

- [ ] Fresh import from `MeTube Download.shortcut` asks all four setup questions.
- [ ] Fresh import from the intended distribution mechanism behaves identically.
- [ ] Blank, malformed, HTTP and path-bearing sidecar addresses are rejected; trailing origin slashes are normalized.
- [ ] Missing or rejected Cloudflare credentials produce a clear terminal failure.
- [ ] A wrong optional sidecar API key produces a clear terminal failure.
- [ ] No credential or configured hostname appears in the public artifact or test record.

## Invocation and media

- [ ] Direct invocation without shared input shows the media URL prompt and reaches the output picker.
- [ ] Cancelling the explicit URL prompt ends without creating a job.
- [ ] Share Sheet invocation accepts a URL from Safari and another application.
- [ ] TikTok Share Sheet reaches the output picker without a URL prompt when its native input contains a usable URL.
- [ ] Video produces a playable iOS-compatible file.
- [ ] Image produces a viewable JPEG thumbnail.
- [ ] GIF allows trimming and produces an animated `.gif`.
- [ ] A successful result reports the expected filename, extension, media type, and byte count.

## Terminal behavior

- [ ] A server-rejected job ends with a useful error.
- [ ] A job that enters `failed` shows a useful plain-language error without echoing upstream response text and ends.
- [ ] Production runs emit no diagnostic notifications, Debug menu choices, build labels or stage codes.
- [ ] A job still incomplete after 120 five-second polls times out and ends.
- [ ] Save to Photos preserves the selected media and ends.
- [ ] Save to Files preserves the selected filename and bytes and ends.
- [ ] Share succeeds with at least one non-Files destination and ends.
- [ ] Discard leaves no saved media and ends.
- [ ] Cancelling each menu, GIF trimming, Share, and Save to Files exits cleanly.
- [ ] Backgrounding and returning during polling does not duplicate requests or output.

## Security observation

- [ ] Every sidecar request carries both Cloudflare service-token headers.
- [ ] `X-Sidecar-Api-Key` is sent only as the configured value (blank is acceptable when disabled).
- [ ] A response containing an absolute or mismatched `poll_url` or `file_url` is rejected and never requested.

Do not use production credentials for this gate. Apple receives any private
configured artifact submitted to its signing service.
