# Installed test Shortcut cleanup

Pre-update cleanup checkpoint: 2026-10-06 (`Europe/Lisbon`). Fresh global library
inventory contained 44 name/identifier pairs. All 24 obsolete test/probe
candidate identifiers from the preceding inventory were absent. The configured
MeTube Shortcut and the working Convert Media and Compress Media Shortcuts
remained present. The library has changed since the earlier inventory, so that
archived inventory is historical and does not describe the final state.

This records observed absence, not who deleted the entries or how. The earlier
single-object and folder-content deletion calls returned without globally
removing their targets; folder deletion changed folder membership only. Do not
attribute the final removals to those calls or claim a particular deletion
method.

No private identifiers, inventory paths or raw library data are included here.
The private before/after evidence remains local. The broader operating rules are
in [testing guidelines](testing-guidelines.md).

## Quiet production replacement checkpoint

Later on 2026-10-06, supported native Add/Replace installed quiet production
replacements but retained the three originals with a `2` suffix. After the
operator's fresh direct confirmation, supported native Delete removed only
MeTube Download Configured 2, Compress Media 2 and Convert Media 2.

Two independent fresh global CLI checks verified all three superseded
identifiers absent, all three quiet production identifiers retained, and 44
library entries in total. Supported native UI also showed 44 entries and no
numbered product duplicates. Exactly one entry remains for each product:
MeTube Download Configured, Compress Media and Convert Media. No unrelated
shortcuts, server files or production services were changed.

Keep the library clean after every replacement: remove verified superseded
installed copies, delete temporary test copies after testing, then verify the
entire library. Retain private source/artifact rollback separately from installed
shortcuts. Cleanup is complete for the observed library on 2026-10-06.
