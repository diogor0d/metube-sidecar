# MeTube Shortcut testing guidelines

Updated: 2026-10-06 (`Europe/Lisbon`). Derived from the October 2026 MeTube and
Media Manager work. Observations describe tested versions, not Apple guarantees.
Media Manager maintains the broader reusable guide; this is its MeTube-specific
application.

## Identify the failing layer

| Check | Establishes | Does not establish |
| --- | --- | --- |
| Source/plist validation | References, inputs and guards | Apple runtime behavior |
| Mocked upstream | Sidecar and simulated API behavior | Real MeTube compatibility |
| Exact-image integration | Real upstream schema and synthetic processing | Production source-site access |
| Authorized live API | Authentication, processing and media | Native input or destinations |
| Native adapter | The graph exercised by the adapter | Replaced pickers, Share Sheet or iPhone |
| Operator run | What the operator explicitly observed | Unnamed modes/devices/destinations |

Input extraction failures and upstream job rejection are different problems.
Correlate requests, job state and private upstream failure categories before
editing the Shortcut. No visible alert does not prove no dialog; timeout does
not prove a hidden dialog either.

## Build and identify the artifact

Compile pinned source, finalize references, validate, then sign. Signing/import
are not execution tests. Names and IDs alone do not identify an installed build;
imports create numbered copies and change IDs. Attribute a run using the
artifact checksum and import receipt. The production URL prompt is intentionally
just `Paste media URL`, with no build label.

A file link may reveal Finder rather than import. Opening the artifact and
completing Add/Replace are separate steps. Avoid new imports for backend failures.

## Native input and terminal behavior

Test direct input, text-conversion fallback and explicit prompt separately. Bare
attachments and text-token inputs are not interchangeable. CLI files, nested
Run Shortcut drivers and direct adapters have different input semantics.
No-input metadata failed to show the expected prompt in the observed test;
verify actual prompting and cancellation rather than assuming metadata proves it.

Harnesses must fail on missing input instead of inserting a successful default.
Keep production runs quiet: no progress notifications, debug choices, stage
codes or build labels in user-facing prompts. Reserve diagnostic receipts for
test harnesses and keep failure alerts plain and useful. Revalidate the final
graph after adding/removing test diagnostics. Coordinate one native owner
across chats, bound runners and cancel only owned processes. Stop after a stall
before another run; never open helper XPC bundles as applications.

## Production and media verification

Identify exact runtime images, schema and extractor version. Validate synthetic
fixtures and the failing source before an authorized service-only deployment.
Local extraction does not prove the server's network works; retry through that
server. Fresh sidecar jobs avoid UI Retry's old folder association. Active
duplicate submissions remain a separate known risk.

Inspect bytes and codecs, not just MIME/extension/size. MeTube's iOS preset allows
H.264 or HEVC even with `codec=h264`; MP4 MIME is not an H.264 guarantee. Image
means JPEG thumbnail, not a whole carousel. GIF trimming/animation and actual
save destinations need native evidence.

## Security, progress and cleanup

- Keep blank masters separate from private configured copies. Never sync
  credentials, raw responses or user media into shared testing packages.
- Scope authenticated tests to the approved origin and reject redirects.
  Signing configured artifacts with Apple is a separate credential destination.
- Retain rollback configuration/image/state before production changes. Archive
  readability and a temporary restore are narrower than production restoration.
- Production is quiet. If the operator later requests progress feedback, use
  validated stage changes, keep polling unblocked and never fabricate
  percentage/ETA from poll counts, elapsed time or temporary file size.
- Keep only the production copies once testing ends. Create only a few temporary
  copies, then delete run-created tests/probes and verified superseded copies;
  retain sources, fixtures and private backups for reproducibility and recovery.
  Preserve ambiguous copies while their role is uncertain, then resolve those
  duplicates before release. Coordinate ownership across chats.
- Cleanup is complete only after a fresh global library check confirms test and
  superseded copies are absent and protected production copies remain. Record
  archived, removed and still-installed separately. Archiving does not satisfy
  cleanup or hide a Shortcut from All Shortcuts. Check native folder assignment
  with a fresh folder query. Supported GUI operations are acceptable. A
  successful delete command is insufficient; verify the resulting library
  state. Do not edit the private library database.
- The observed single-object and folder-content deletion calls did not remove
  entries from the global library; folder deletion changed membership only.
  Later inventory showed 24 obsolete candidates absent, but the actor and
  deletion method are unknown. See [cleanup evidence](testing-cleanup.md).

Evidence: [2026-10-06 history](../docs/history/2026-10-06-shortcut-production-validation.md).
