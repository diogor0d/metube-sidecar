# Handoff

Updated: 2026-10-06. Production API and operator confirmation: 2026-10-06.

## Objective

Make the native iOS Shortcut submit a MeTube job, poll it, retrieve the correct
media, and save the result. Automate repeatable development and Mac testing
without interfering with the user's active desktop work.

## Repository state

- Branch: `main`; HEAD: `d289a01d9bc77c294931804243747074200fe3fb`.
- The checkout was clean before this session and locally synchronized with the
  cached upstream reference. No fetch, pull, commit, push, or branch switch occurred.
- The changes described below are uncommitted. Git and the current working tree
  remain authoritative; this handoff does not imply another machine has them.
- Earlier migration notes were superseded by authorized production inspection
  and service-scoped upgrades on 2026-10-06. Images, API schema and video/JPEG
  delivery were verified; see the deployment reviews and dated history.
- The operator confirmed the Shortcut works on 2026-10-06. The confirmation did
  not identify the device, mode or destination; retain specific acceptance limits.

## Implemented locally

- Imported the staged Cherri Shortcut source and existing structural/runner tests
  into `shortcuts/`, excluding its private configuration and downloaded compiler.
- Added a reproducible Mac build script using pinned Cherri 2.3.0 source revision
  `d2072c62ea708e7727099fab94fa28b0bcec747b`. Compile with `--skip-sign`, then
  finalize before Apple signing. Do not use Cherri's `--derive-uuids` flag.
- Fixed Get URLs input serialization: its text parameter uses a text token string
  containing an `ExtensionInput` attachment without `VariableName`. Native direct
  video/image tests returned no URL with the old bare attachment and passed after
  this repair. Address transformation inputs now use text token strings too.
- Kept the private preparation scripts compatible with the system Python 3.9;
  the application and native harness use Python 3.12+.
- Updated the runner/Shortcut build marker to `2026.10.06.4`. After D00 on direct
  launch, an implicit URL no-input policy was attempted in build .3. The user
  subsequently reported D05 and no visible prompt when tapping. Build .4 removes
  reliance on that policy, preserves direct URL extraction, adds the Get Text
  conversion proven by native adapters as a fallback, then explicitly asks for a
  URL if extraction remains empty. Its version-labelled prompt, cancellation and
  real Share Sheet input still require native/device acceptance.
- Added thumbnail requests and type-aware output discovery to the sidecar. New
  metadata records the requested media type; old records retain their previous
  video/audio fallback. Submitted source URLs remain absent from metadata.
- Normalize numeric resolution labels such as `1080p` to `1080`; preserve aliases.
- Reset file stability observations when temporary output appears.
- Added `scripts/check.sh`, packaging configuration, and ignores that exclude
  private Shortcut artifacts and compiler binaries from Git and Docker context.
- Added a loopback native harness using the real sidecar with an in-process MeTube
  mock, synthetic authentication, and synthetic video/image fixtures. Test copies
  select their media type automatically and return the file instead of saving it.
- Added a bounded native runner: it requires fresh evidence, respects the shared
  Shortcuts UI lock, runs both already-imported drivers, checks hashes and request
  lifecycles, and cancels only its own CLI subprocess when a dialog stalls.
- A native preflight requires both Video/Image test and driver pairs in the
  installed list. All four signed synthetic copies were registered in a
  coordinated session. Duplicate-name imports required an explicit Replace
  confirmation; older test copies were retained with numbered names.
- Disposable native test copies return fixed failure stage/title receipts instead
  of showing blocking alerts. An optional direct CLI adapter explicitly extracts
  text from its input file before the existing URL extraction action. This
  diagnoses the workflow separately from the unverified nested driver; it does
  not prove actual Share Sheet input or destination actions.
- Added a disposable Docker integration stack using a digest-pinned official
  MeTube image and a generated HTML/media publisher. It tests the real MeTube and
  yt-dlp pipeline without real credentials, external source sites, or host ports.

## Verification and limits

- Backend regression suite: 13 tests passed.
- Shortcut structure, private runner, and harness checks: 55 tests passed on
  2026-10-06. Together with the 13 backend tests, the required check script passed
  all 68 checks. Mocked subprocess checks do not establish native execution.
- Python compilation, Compose configuration, and whitespace validation passed.
- The Docker image built; an unprivileged health check and mocked thumbnail
  create/poll/file lifecycle passed inside the image.
- Real local MeTube integration passed video, JPEG thumbnail, and numeric
  resolution-label jobs, with returned bytes matching the generated fixtures.
  An initial resolution case had unknown height metadata; supplying the clip's
  actual height in the test page fixed the fixture, without changing API behavior.
- `sh scripts/integration.sh` passed all three real MeTube cases, including job
  metadata type and source-URL exclusion. Its temporary Docker resources were
  removed and cleanup was checked. This proves the local backend pipeline only.
- Apple signed the credential-free candidate. Signing proves neither execution
  nor device acceptance.
- The original configured Shortcut was privately backed up and preserved.
- The nested Text-to-Run-Shortcut driver remains unverified. A fresh Video
  driver timed out after 45 seconds with zero submit/poll/file requests. One
  editor run also stalled at Run Shortcut and was explicitly stopped. The native
  editor showed the expected target name and DriverURL input; this does not prove
  the generated workflow reference resolves at runtime. No new run should start
  until the prior run is stopped and any dialog is cleared.
- Subsequent direct CLI Video and Image adapter runs passed on 2026-10-06 after
  Get URLs was repaired to use its text-token input type. Native execution
  submitted, polled, and retrieved both outputs; the MP4 and JPEG matched the
  fixtures byte for byte. Each media type recorded one submit, two polls, and
  one file request. This proves the local native API round trip, using the real
  sidecar with mocked MeTube, but not the original Share Sheet/destination graph.
- Earlier helper permission dialogs could not be reliably controlled. Looking
  up the helper XPC as an application caused system open-document errors; do not
  repeat that path. Coordinate exclusive UI ownership with other Shortcut chats.
- Generic text-file CLI input did not exercise native URL extraction. The
  Text-to-Run-Shortcut driver is itself unverified; diagnose its native binding or
  use an explicit test-only text-input adapter before treating it as a test path.
- The harness excludes mode/destination pickers, Photos/Files/Share/Discard,
  GIF trimming/conversion, real MeTube, and actual iPhone Share Sheet behavior.
  See `shortcuts/tests/on-device.md`; none of those acceptance boxes passed here.

## Remaining acceptance and next actions

1. Endpoint credential transmission was explicitly authorized on 2026-10-06.
   Live health/schema checks passed, one disposable video job completed and
   returned valid MP4 bytes, and unauthenticated health access was denied.
   Before the upgrade, the deployed API rejected thumbnails with HTTP 422.
   The reviewed upgrade in `deployment/thumbnail-upgrade.md` is now deployed;
   live video and JPEG checks passed.
2. Coordinate exclusive Shortcuts UI use with other active chats. Direct native
   Video/Image adapters already passed; the nested driver and original address
   graph remain unverified. A bounded zero-network configuration probe timed out
   without a visible alert. Do not infer a dialog from a timeout. Organize only
   this workflow's temporary copies, preserving the original configured shortcut.
3. The final build adds explicit empty-selection/trim exits and GIF failure
   handling. Its blank signed artifact and private configured unsigned copy are
   prepared; the configured copy was signed by Apple with explicit user approval
   and is stored with its previous backup in ignored `shortcuts/private/production/`.
   Production inspection
   and the service-scoped upgrade were explicitly approved and completed. The
   exact image is deployed with rollback retained, and live MP4/JPEG checks pass.
   The exact AMD64 candidate image passed non-root health/authentication/thumbnail
   checks and all three isolated real-MeTube integration cases; cleanup passed.
4. Complete signed iPhone/iPad Share Sheet, GIF, destination, cancellation, and
   Photos acceptance before marking the goal complete.

## MeTube extractor repair verified on 2026-10-06

- A user-observed TikTok failure reached MeTube and failed during extraction;
  the deployed yt-dlp version was `2026.07.04`. This was separate from the
  Shortcut's earlier input-prompt defects.
- The separately authorized MeTube-only upgrade selected official release
  `2026.09.29` with yt-dlp `2026.08.19`. The exact AMD64 image passed local
  extraction and all three isolated integration cases before deployment.
- The original image, Compose configuration and two-file state/history archive
  were retained privately. Archive contents were read back before changing the
  service. The idle queue, all 14 history entries and original storage/network/
  port/restart/user boundaries were verified; the sidecar was not recreated.
- Fresh production jobs for the previously failing user link completed and
  returned valid MP4 video and JPEG thumbnail responses. Failed history does not
  itself require deletion or a UI retry; submit a fresh sidecar job.
- Independent media probing found HEVC/AAC in that MP4. Exact-image source
  inspection confirmed the request mapping is correct and MeTube's `ios` preset
  intentionally accepts both H.264 and HEVC. A legacy request returned the same
  bytes. Corrected the overly strict H.264-only documentation; no code fix or
  subsequent sidecar mutation was needed.
- See `deployment/metube-tiktok-upgrade.md` for the pinned image and rollback.
  Final native GIF, destinations and iPhone acceptance remain pending. This
  backend repair does not require another Shortcut import.
- The user asked about progress feedback. Existing status supports coarse stage
  notifications without API changes; percentage/ETA require measured MeTube
  progress integration. Avoid a notification per poll or fabricated percentages.
  No Shortcut graph change was made for this request yet.

## Constraints

- Keep this public handoff free of real endpoints, credential identifiers,
  private paths, production data, and raw operational evidence.
- Keep the downloads mount read-only, container port internal, path containment
  checks intact, and Uvicorn at one worker.
- MeTube may accept a duplicate queued URL without creating the second job's
  requested folder. Concurrent duplicate submission remains an existing limitation.
- Saving or discarding in the Shortcut does not delete server output. Retention
  remains the operator's responsibility.
- Preserve unrelated user changes. Reconcile this checkout and any staged copy
  before editing; never assume uncommitted changes transferred between machines.

## Durable records and cleanup on 2026-10-06

- Full record: `docs/history/2026-10-06-shortcut-production-validation.md`.
- Lessons: `shortcuts/testing-guidelines.md`; Media Manager owns its broader guide.
- Installed test-copy cleanup: `shortcuts/testing-cleanup.md`. A later fresh global
  inventory confirms all 24 obsolete candidates are absent, with exactly one
  MeTube production copy and both Media Manager products retained. Earlier native
  scripting deletion only removed folder membership; it did not delete workflows.
  Preserve source fixtures, private originals and deployment rollback checkpoints.

## Quiet production update on 2026-10-06

- At the operator's request, build `2026.10.06.5` removes all diagnostic
  notifications, Debug choices, stage codes and the build-labelled URL prompt.
  Normal Video/Image/GIF and destination choices, plain errors, validation,
  authenticated API calls and local GIF conversion remain. No backend mutation.
- The required check script passed 68 tests, compilation, Compose validation
  and whitespace checks. Both blank and private configured copies were signed;
  configured Apple signing follows the operator's explicit prior approval.
- Media Manager owns supported native GUI replacement for both projects.
  Replace the existing product instead of adding another numbered copy.
  Installation verification is separate from the artifact audit.

- Supported Add/Replace installed the quiet MeTube product; its editor has the
  plain URL prompt and exactly Video/Image/GIF choices. Replacement also retained
  three superseded originals across the projects with numbered suffixes. Media
  Manager batches their deletion after the native tool's required fresh
  action-time confirmation. Do not equate the earlier 24-copy cleanup checkpoint
  with absence of these subsequently created replacement originals.

## Final duplicate cleanup, 2026-10-06

The operator confirmed deletion of superseded installed copies. Media Manager
used supported native Delete for only MeTube Download Configured 2, Compress
Media 2 and Convert Media 2. Two independent fresh global checks verified all
three old identifiers absent, all three quiet products retained, exactly one
entry per workflow and 44 library entries total. Supported UI agreed. No new
test copies or media runs were created. The earlier pending deletion checkpoint
is resolved. Future replacement/testing cleanup must finish with global absence
verification, not archive assignment or a successful command return value.
