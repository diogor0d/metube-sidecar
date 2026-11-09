# Thumbnail support upgrade review

Prepared: 2026-10-06. Status: **approved and deployed; runtime/API validation passed**.

The live API is healthy and delivered a disposable video, but its accepted download
types are video and audio. A thumbnail request fails validation with HTTP 422.
The final Shortcut's Image mode therefore requires the updated sidecar.

## Reviewed artifact

- Local image: `metube-sidecar:candidate-20261006.1`, Linux AMD64.
- Immutable image identity:
  `sha256:6e0423a98b758aade66e556e21643f23f089142d77ef98327f8bda358e85ffe7`.
- Source baseline: `d289a01d9bc77c294931804243747074200fe3fb` plus the reviewed local
  backend changes. This is an uncommitted candidate, not a remote Git release.
- Adds thumbnail jobs and image discovery, records each new job's media type,
  preserves older video/audio metadata, normalizes resolution labels, and resets
  stability observations when temporary output appears. No database migration.
- Required local checks and non-root image health/authentication/thumbnail tests
  pass. The isolated real-MeTube integration verifies synthetic video, thumbnail
  and resolution jobs before deployment approval.

## Proposed scope

The private infrastructure runbook identifies `server-2` and the existing
`metube-sidecar` service, with a shared MeTube network, read-only downloads, durable
job volume and loopback ingress. That placement is historical evidence and must
be confirmed through authorized, service-scoped inspection before changing it.

Upgrade only that sidecar to the exact reviewed image. Preserve its current mounts,
network, environment injection, loopback binding and one-worker configuration.
Keep MeTube, Cloudflare routes/policies and all unrelated services unchanged.
The sidecar will briefly restart; active polling may fail during that interval.

## Pre-change checkpoint and rollback

1. Inspect only the sidecar's service identity, architecture, image, mount modes,
   existing ingress binding and health. Abort on drift from the approved placement,
   unrelated local changes, missing capacity or an unsafe listener.
2. Record the previous immutable image and retain it. Securely back up job metadata
   and the service configuration without printing secrets. Verify restore access;
   preserve download data and the current durable volume.
3. Transfer the reviewed image archive, verify its checksum and image identity,
   and load it only after production authorization. Validate the service-specific
   Compose override without printing interpolated configuration.
4. Recreate only the sidecar. Never remove its volume or run a project-wide down.
5. Check local health, unprivileged operation, unchanged mounts/listener, Access
   denial without credentials and health with the authorized token. Confirm the
   public schema now includes thumbnail.
6. Run disposable video and JPEG thumbnail create/poll/file checks; verify actual
   media and preserved older job metadata. Then verify the final native Shortcut.

If health, access boundaries, persistence or either media path fails, restore the
previous image and service configuration, recreate only the sidecar, and recheck
health and the earlier video path. Do not delete new job records or media as part
of rollback. Existing retention remains the operator's responsibility.

Exact host paths, addresses and credentials remain in private operational context.
No SSH inspection, file transfer or production mutation has been authorized by
permission to test the existing HTTP endpoint.

## Verified result — 2026-10-06

The approved service-scoped inspection confirmed the documented placement and
non-root runtime. A private checkpoint retained the old image, service configuration
and a readable job-metadata archive. The exact image above was transferred with
SHA-256 verification and loaded, then selected through a default Compose override
that removes the old build directive and pins the immutable image identity.
Only the sidecar was recreated. Local/public health passed, the public schema
includes thumbnails, and requests without Access credentials returned HTTP 403.

Post-upgrade real video and thumbnail jobs each completed after two polls and
returned valid MP4 (1,128,375 bytes) and JPEG (8,739 bytes) respectively. All 31
earlier metadata records remained readable. Port bindings, network membership
and mount source/type/write modes matched the pre-change state exactly.
The retained checkpoint provides an image/configuration rollback; rollback was
not exercised because validation passed. Full device acceptance remains separate.
