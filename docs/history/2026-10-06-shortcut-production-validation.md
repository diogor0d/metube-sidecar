# MeTube Shortcut development and production repair

Occurred and verified: 2026-10-05 through 2026-10-06.
Documented: 2026-10-06 (`Europe/Lisbon`). Recall period: October 2026.

## Outcome

The operator confirmed on 2026-10-06 that the Shortcut is working after the
MeTube extractor repair. This is a successful operator-reported run; the message
did not identify its device, output mode or save destination. It does not fill
every GIF, iPhone, cancellation or destination acceptance checkbox.

Automated production API checks independently verified video and JPEG thumbnail
delivery, including the previously failing TikTok source. The prepared working
artifact was build `2026.10.06.4`; the later quiet update is build `.5`. Installed
names and identifiers changed during imports; use verified replacement receipts
rather than infer which version the user ran from its name.

## Development and native testing

- Reconciled the Mac checkout and cross-machine staging. Public sources,
  fixtures and blank signed artifacts can transfer through the testing folder;
  configured artifacts and credentials remain private.
- Pinned Cherri compilation and finalized generated plists before Apple signing.
  Repaired text-token inputs and references used by native URL extraction.
- Direct launch initially stopped at D00; a later no-input metadata policy
  still failed to show the prompt. Build `.4` uses direct URL extraction, a
  text-conversion fallback, then an explicit version-labelled URL prompt.
- Added Video, Image and GIF choices. Image retrieves a JPEG page thumbnail,
  not a whole photo carousel. GIF uses downloaded video and native trimming/
  conversion. Local media upload is outside this downloader.
- Added empty-selection, trim and terminal exits. Kept polling bounded and
  validated relative job/file paths before authenticated requests.
- Required local checks passed 68 tests: 13 backend and 55 Shortcut/runner/
  harness checks. Python compilation, Compose and whitespace validation passed.
  These checks do not establish native execution or iPhone behavior.
- Direct Mac Video/Image adapters completed submit, poll and file delivery
  against the real sidecar with mocked MeTube; fixture hashes matched. Nested
  Run Shortcut drivers stalled and did not prove the original graph.
- Exact-image Docker integration passed synthetic video, JPEG and resolution
  cases using real MeTube. Temporary resources were removed and cleanup checked.

## Authorized production changes and evidence

The thumbnail and extractor upgrades had separate explicit authorization.
Credentials were authorized only for the designated downloader API; signing the
private configured artifact with Apple had separate approval. No Cloudflare
policy or unrelated service was changed.

1. The older sidecar rejected thumbnails with HTTP 422. The reviewed upgrade
   added type-aware discovery and persistent metadata while retaining legacy
   records, path containment and the read-only download mount. All 31 earlier
   records remained readable. A restore into a temporary directory checked
   those records without overwriting production state.
2. Live API checks returned valid MP4 and JPEG bytes. Missing Access credentials
   were denied. The exact deployed sidecar image passed local health,
   authentication, thumbnail and real-MeTube integration checks.
3. A subsequent D08 rejection correlated with a real TikTok extractor failure
   in MeTube running yt-dlp `2026.07.04`. Official AMD64 MeTube `2026.09.29`
   (yt-dlp `2026.08.19`) extracted that source locally and passed integration
   before the separately approved service-only upgrade.
4. MeTube's queue was idle. The old image and configuration were retained;
   the two-file state/history archive was read back before recreation. All 14
   history entries and storage/network/port/restart/user boundaries were
   preserved. The sidecar container did not change during this upgrade.
5. Fresh jobs for the failed source completed and delivered video and JPEG.
   Failed history required neither deletion nor UI retry. Independent probing
   found HEVC/AAC video and a JPEG image. Exact-image source inspection confirmed
   the iOS selector permits H.264 or HEVC; corrected an overly strict H.264-only
   description rather than changing the correct request mapping.

See [sidecar upgrade](../../deployment/thumbnail-upgrade.md) and
[MeTube upgrade](../../deployment/metube-tiktok-upgrade.md) for image pins and
rollback. Archive readback proves readability, not a full production restore;
MeTube image rollback was retained but not exercised.

## Coordination, cleanup and remaining limits

[Testing guidelines](../../shortcuts/testing-guidelines.md) capture the lessons.
The Media Manager chat owns its broader reusable guide and corresponding records.
Installed test/probe cleanup is tracked in
[the cleanup record](../../shortcuts/testing-cleanup.md). Test source and synthetic
fixtures, private configured backups, rollback and unrelated entries are retained.

Progress feedback was assessed but not implemented: stages need no API change,
while percentage/ETA require measured backend progress. Native GIF, iPhone Share
Sheet, save destinations, cancellation and backgrounding still need corresponding
observations; see [on-device checks](../../shortcuts/tests/on-device.md).

Concurrent duplicate source submissions remain a known limitation: MeTube may
accept a duplicate without creating the second sidecar directory. Saving or
discarding does not remove server files; retention is separate. All repository
changes remain uncommitted. This documentation/cleanup request changes no backend.

## Quiet production and final cleanup, 2026-10-06

The operator requested production shortcuts without debug messages. Build
`2026.10.06.5` removes every notification action, Debug menu choice, D-stage label
and build-labelled URL prompt. The public and privately configured graphs each
contain 213 actions. Normal menus, short actionable errors, authentication,
response-path guards, polling, local GIF conversion and save destinations remain.
Both artifacts were signed; the configured submission to Apple was explicitly
approved earlier. The required check script passed 13 backend and 55 Shortcut,
runner and harness tests, compilation, Compose validation and whitespace checks.
The first standalone backend test invocation lacked temporary state directories;
rerunning the repository check script with isolated state passed.

A fresh global library inventory now shows all 24 obsolete candidates absent,
exactly one MeTube production entry and the Convert Media and Compress Media
products retained. The removal actor is not established. Earlier native delete
commands returned success without global deletion, and folder-content deletion
only cleared membership. The latest absence check, rather than that command
return value, establishes cleanup. Sources, fixtures and private rollback copies
are retained; they are not extra installed shortcuts.

Media Manager coordinates the supported native GUI replacements for both projects
under one owner. Its quiet production changes remove schema reports, request
counts and internal state from error messages while retaining user choices and
validation. This update makes no production service or API changes.

Supported native Add/Replace subsequently installed the quiet MeTube production
copy. Its editor contains the plain URL prompt and exactly Video/Image/GIF
choices. The interface kept the three prior production copies with numbered
suffixes. Their exact superseded identities are recorded privately, and Media
Manager coordinates a single deletion batch after the native tool's mandatory
fresh action-time confirmation. The 24-copy cleanup inventory above predates
these replacements. No new test workflows were imported.

The quiet Convert Media and Compress Media replacements contain 282 and 243
actions according to native metadata. Their existing configuration was reused
locally without exposing values or signing configured Media Manager artifacts.
MeTube's published action-count metadata reports zero despite its supported
editor displaying the new graph, plain prompt and three normal choices. Treat
that metadata as unreliable for this imported entry; the 213-action claim is
verified for the source artifacts, not a native export. No final media run was
added for this text-only update. Native activity paused when concurrent user
interaction was observed. The batched deletion confirmation is pending in the
Media Manager chat.

## Final duplicate cleanup, 2026-10-06

The operator confirmed deletion of superseded installed copies. Media Manager
used supported native Delete for only MeTube Download Configured 2, Compress
Media 2 and Convert Media 2. Two independent fresh global checks verified all
three old identifiers absent, all three quiet products retained, exactly one
entry per workflow and 44 library entries total. Supported UI agreed. No new
test copies or media runs were created. The earlier pending deletion checkpoint
is resolved. Future replacement/testing cleanup must finish with global absence
verification, not archive assignment or a successful command return value.
