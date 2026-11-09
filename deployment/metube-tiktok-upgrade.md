# MeTube TikTok extractor upgrade review

Prepared, approved, deployed and verified: 2026-10-06. Status: **deployed; live
video and thumbnail delivery passed**.

The user observed a TikTok extraction error in MeTube and the Shortcut's D08
rejection alert. Authorized read-only inspection found yt-dlp `2026.07.04` in
the running MeTube service. The corresponding recent sidecar job records a
submission rejection. An earlier job remains marked downloading; the sidecar's
file-based polling does not itself establish MeTube's current queue state.

## Reviewed candidate

- Official MeTube release: `2026.09.29`, Linux AMD64.
- Pinned image:
  `ghcr.io/alexta69/metube@sha256:8f7c95941bcc560ea4ddd9ac27142698000e1abf08ac43d709828e712f71a4ea`.
- Candidate yt-dlp version: `2026.08.19`.
- Current immutable image:
  `sha256:9c23af6491bea0761400d7f80f25cfe001847c55b66d20e32ceb17f9527afd29`.
- The candidate extracted the user's failing TikTok link in an isolated local
  AMD64 container: ten formats and a thumbnail, without cookies or saved media.
  This proves extraction from the Mac's network, not from the production server.
- An isolated internal Docker stack using this candidate and the deployed
  sidecar image passed synthetic video, JPEG thumbnail and resolution jobs.
  Returned bytes matched the fixtures; source URLs were absent from sidecar
  metadata. The test containers, network and volumes were removed successfully.

The August release includes TikTok extractor and share-link fixes:
[yt-dlp release notes](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19).
Later reports show that TikTok failures can recur even with that release, so a
same-server check is required:
[upstream issue](https://github.com/yt-dlp/yt-dlp/issues/17604).

## Proposed service-only change

Inspection confirmed the existing `metube` Compose service and a single literal
image reference in its configuration. A one-line image replacement can preserve
the rest of the configuration. The internal history endpoint reported no active
or pending jobs at inspection time; recheck immediately before stopping.

1. Recheck the service identity, image, queue, storage and available capacity.
   Abort on unexpected drift or new active/pending jobs.
2. Retain the current image and privately back up the existing Compose file and
   MeTube state/history. Verify archive readability before changing the image.
   Keep actual paths, source links and configuration values private.
3. Select the exact candidate digest and validate Compose without printing its
   interpolated configuration. Recreate only `metube`; never run project-wide
   down or remove a production volume.
4. Verify runtime image/version, readiness, preserved history and unchanged
   mounts, network membership and port binding. Keep the sidecar and Cloudflare
   configuration unchanged.
5. Validate TikTok extraction on the server and a disposable video/thumbnail
   delivery through the authorized sidecar endpoint. Check retained failed-entry
   retry behavior before asking the user to run the same link again.

The user separately approved the MeTube-only upgrade after reviewing this plan.
The queue and pending list were empty immediately before the restart. The old
image was retained, configuration was copied privately, and the two-file state
archive was read back before the image reference changed. Only MeTube restarted.
Runtime inspection confirmed yt-dlp `2026.08.19`, the exact candidate image,
unchanged storage/network/port/restart/user boundaries, all 14 history entries,
and the same sidecar container identity.

Fresh jobs for the user's previously failing TikTok link were accepted through
the authorized sidecar endpoint. The video completed and returned an MP4; a
separate request using the Shortcut's JPG thumbnail payload completed and returned
a JPEG. The retained completed/failed history did not prevent a fresh submission.
Independent media probing found HEVC/AAC in the MP4 and a valid JPEG thumbnail.
Inspection of the exact deployed image confirmed the request mapping is correct:
the official `ios` preset intentionally allows both H.264 and HEVC rather than
applying the separate codec filter. A legacy-shaped diagnostic request returned
the same bytes, consistent with that preset. H.264-only output was not part of
the media-type requirement; the documentation's stricter promise was corrected.
See the pinned [format selector source](https://github.com/alexta69/metube/blob/2026.09.29/app/dl_formats.py#L99-L112).
An initial thumbnail probe incorrectly requested the video format; correcting
the test payload required no product change. A default Python client identifier
received an edge denial; an explicit validation identifier passed with the same
credentials. No edge policy was changed.

## Rollback and remaining acceptance

Retain the original image, exact Compose text and state checkpoint. If readiness,
storage boundaries or basic delivery fail, select the original image and recreate
only MeTube. Preserve new state and user files; do not blindly overwrite history
that changed after the checkpoint. Restore state only if a compatibility failure
requires it and concurrent changes have been accounted for.

Actual server TikTok extraction and fresh-job retry are verified. Final native
GIF conversion and iPhone delivery remain unverified. The iOS preset is not an
H.264-only guarantee. No additional Shortcut import is needed for this backend
image change.
