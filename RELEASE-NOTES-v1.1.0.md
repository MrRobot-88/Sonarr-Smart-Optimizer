# Sonarr Smart Optimizer v1.1.0

## Highlights

- Added targeted episode execution with `SMART_OPTIMIZER_EPISODE_ID`.
- Added targeted series execution with `SMART_OPTIMIZER_SERIES_ID`.
- Added explicit `SMART_OPTIMIZER_MANUAL_TARGET` mode for UI-triggered targeted runs.
- Targeted Manual Optimizer runs do not consume the normal persistent A-Z queue or daily-search counter.
- Current episode files below **400 MiB** are skipped before interactive searching.
- Low-resolution upgrades may grow by at most **40%** while moving toward the series profile target.
- Existing 1080p and 2160p same-resolution replacements remain storage reductions only.
- 1080p → 2160p does not receive the low-resolution +40% growth exception.
- Preserved HDR/DV, AV1, audio/channel and Atmos-aware ranking protections.
