# Sonarr Smart Optimizer v2.0.0

## Verified selection policy

- TorrentLeech is the primary valid candidate pool from the same Sonarr release search.
- Other indexers are used only when there is no valid TorrentLeech candidate.
- Normal 1080p optimization is storage-first: the smallest valid release wins.
- HDR, Atmos and channel count do not make a larger normal 1080p release win.
- 720p may upgrade only to 1080p.
- 720p -> 720p and 720p -> 2160p are rejected.
- 720p -> 1080p may grow by at most 40%.
- 1080p and 2160p replacements must always be strictly smaller.
- Normal downsizing is hard-capped at 40%.
- UHD candidates must be 2160p with at least HDR; DV+HDR is preferred over HDR, then Atmos, then smaller size.
- AV1 is rejected.
- Season packs and multi-episode releases are rejected for single-episode optimization.
- The episode file ID, byte size, resolution and profile are revalidated immediately before a live grab.

## Validation

The v2 policy was tested against a real Ted Lasso S04E08 replacement and a synthetic policy test suite.

Final verification:

- PASS=10
- WARN=0
- FAIL=0

The public source contains no API keys or runtime state.
