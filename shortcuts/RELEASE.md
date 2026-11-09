# MeTube Download — final candidate

Build: `2026.10.06.5`. Prepared and checked: 2026-10-06.

This production update removes diagnostic notifications, Debug choices, stage
codes and the build-labelled URL prompt. Helpful plain-language errors and
the input/media/save workflow remain. Replace the existing production copy;
do not import another numbered test copy. Backend configuration is unchanged.

Operator confirmation on 2026-10-06: the Shortcut works after the backend repair.
That report preceded this quiet update and did not name its mode, device or destination; specific acceptance
gates below remain separate from that successful run.

Install only `MeTube Download.shortcut`; the Local, Driver, Probe and Test copies
are development tools. The signed distributable has four blank setup questions.
Enter the existing HTTPS sidecar origin, Access client ID and secret, and optional
sidecar API key locally in Shortcuts. Preserve the older configured copy until
the replacement passes a real Share Sheet test.

Share a supported media page or link, or launch directly and paste its URL into
the URL prompt. Select an output, then choose Save to Photos,
Save to Files, Share or Discard. When a shared item has no usable URL, the prompt asks for its page or
link. Local media files are not uploaded or converted by this downloader.

| Output | Behavior |
| --- | --- |
| Video | Download video using MeTube's iOS preset, which permits H.264 or HEVC |
| Image | Retrieve the page's JPEG thumbnail, not an entire photo carousel |
| GIF | Download video, let the user trim it, then create and name an animated GIF |

Empty output/destination selections and empty trim results stop before the next
operation. Empty GIF output produces a fixed error and stops. Terminal branches
clear the implicit action output and stop; they do not delete downloaded server files.

## Verified and remaining

- Required local checks: 68 passed (13 backend and 55 Shortcut/runner/harness).
- Native Mac direct adapters retrieved exact synthetic MP4/JPEG bytes. Those runs
  used the real sidecar with mocked MeTube and excluded pickers and destinations.
- The authorized live API accepted, completed and delivered a valid MP4; requests
  without Access credentials were denied. This was an API check, not a run of the
  final installed Shortcut.
- The older deployed API rejected thumbnails with HTTP 422. The approved
  service-only upgrade has now completed; the live API accepts thumbnails and
  delivered an 8,739-byte JPEG. Existing mounts, ports and network are unchanged;
  31 earlier job records remained readable and a rollback checkpoint was retained.
- A separately approved MeTube extractor upgrade to release `2026.09.29`
  (yt-dlp `2026.08.19`) resolved a user-reported TikTok submission rejection.
  Fresh live jobs for that source returned MP4 video and a JPEG thumbnail.
  MeTube's history and service boundaries were preserved, and the sidecar was
  not restarted. This backend change requires no additional Shortcut import.
  Independent probing found HEVC/AAC in the returned MP4; the exact MeTube image's
  iOS selector intentionally allows both HEVC and H.264. The request mapping is
  correct, and the preset does not guarantee H.264-only output.
- Direct-launch explicit URL prompting, native GIF conversion, real iPhone Share Sheet input, Photos/Files/Share delivery and cancellation
  remain acceptance gates in `tests/on-device.md`. Supported native GUI updates
  are coordinated with Media Manager; signed artifacts alone do not prove installation.

The production backend is verified for video and JPEG thumbnail delivery. The
quiet configured Shortcut was imported through supported Add/Replace. Its
editor has the plain URL prompt and only Video/Image/GIF choices. Native GIF/device
acceptance remains unverified. Do not distribute an artifact containing real
credentials. Apple
receives artifacts submitted to its signing service; the public signed file
contains blank credential fields. The user explicitly approved signing the
configured copy with Apple. The final
configured signed/unsigned artifacts and older backup are retained under ignored
`private/production/` with restrictive permissions; none is in the shared package.

## Installed replacement checkpoint

The supported native editor verified the quiet input prompt and three media
choices on 2026-10-06. The signed artifact has zero notification actions.
Add/Replace retained the superseded original with a numbered suffix. Following
the operator's fresh confirmation, supported native Delete removed all three
superseded products across the projects. Independent global checks confirmed
exactly one quiet production entry per workflow. This editor/import check does
not substitute for device acceptance.
