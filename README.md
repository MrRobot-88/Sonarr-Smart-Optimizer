# Sonarr Smart Optimizer

> ## Smart Optimizer UI (easiest setup)
> Prefer one container with a web dashboard? Use [Smart Optimizer UI](https://github.com/MrRobot-88/Smart-Optimizer-UI). It bundles the Sonarr and Radarr optimizers and lets you configure connections from the browser.

Sonarr Smart Optimizer revisits episodes already in your Sonarr library and searches for more storage-efficient replacements while applying conservative media-safety rules before asking Sonarr to grab anything.

It is **dry-run by default**. The script never calls Sonarr DELETE endpoints and never controls your download client directly. In live mode it sends a selected release to Sonarr; Sonarr then handles downloading, import and normal file replacement.

## Current behavior

- Persistent **A-Z series queue** and persistent episode work queue/cursor.
- Newly added series are appended to the end instead of reordering existing work.
- Optimizer-only exclusions apply to an **entire series** and are checked before interactive release searches.
- No resolution downgrade.
- Same-resolution replacements use the configured minimum/maximum saving window.
- **Low-resolution upgrade rule (Sonarr only):** when the current episode is below 1080p, a higher-resolution candidate up to the profile target may be smaller, equal-sized or at most **50% larger** than the current episode.
- That +50% exception does **not** apply to 1080p → 2160p.
- AV1 candidates are rejected.
- Dolby Vision-only candidates without HDR fallback are rejected.
- Existing HDR/Dolby Vision state is protected by the dynamic-range rules.
- Multichannel → stereo is rejected; multichannel-to-multichannel changes such as 7.1 → 5.1 are allowed.
- Atmos is a preference rather than a hard preservation requirement.
- Candidate ranking prefers dynamic range, Atmos, channel count, smaller size and then x265 among candidates that already passed hard safety gates.
- Search history, queue position and attempted releases are persisted.
- At most two optimizer search cycles per episode, with a 180-day wait before the second cycle.
- Manual UI mode can use `SMART_OPTIMIZER_TARGET_GRABS`: the requested number represents successful releases sent to Sonarr, while the normal search budget remains the ceiling.

## Requirements

- Sonarr v4 with its API reachable from the machine running the script
- Python 3.8+
- Sonarr API key
- A working indexer setup in Sonarr
- A download client already configured in Sonarr

No third-party Python packages are required.

Prowlarr works well for managing indexers, but the optimizer does **not** call the Prowlarr API and does not require a Prowlarr API key.

## Quick start

1. Download `sonarr-smart-optimizer.py`.
2. Supply the API key through `SONARR_KEY` or a protected wrapper/key file. Do not put the key in the Python source.
3. Review the normal/UHD profile IDs used by the script.
4. Run a dry run:

```sh
export SONARR_KEY="$(cat /path/to/.sonarr-smart-optimizer-key)"
python3 sonarr-smart-optimizer.py
```

When the proposed replacements look correct:

```sh
python3 sonarr-smart-optimizer.py --live
```

In Sonarr, the API key is under **Settings → General → Security → API Key**.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `SONARR_URL` | `http://127.0.0.1:8989` | Sonarr URL |
| `SONARR_KEY` | none | Sonarr API key; required |
| `SONARR_SEARCHES_PER_RUN` | `10` | Maximum interactive searches per normal execution |
| `SONARR_OPTIMIZER_STATE` | state JSON beside script | Persistent optimizer state |
| `SONARR_MIN_SAVING_PERCENT` | `5` | Minimum same-resolution saving |
| `SONARR_MAX_SAVING_PERCENT` | `50` | Maximum same-resolution saving / quality-risk guardrail |
| `SMART_OPTIMIZER_CONTROL` | control JSON beside script | Optional shared runtime controls/exclusions |
| `SMART_OPTIMIZER_TARGET_GRABS` | `0` | Manual/UI target; 0 keeps normal search-count behavior |

The standalone script's base daily search budget is currently **400** searches. The shared control file can supply date-scoped temporary extra searches and override the min/max saving window.

The current script uses normal profile ID `4` and UHD profile ID `5`; verify those IDs against your own Sonarr installation before live mode.

## Sonarr-only low-resolution upgrade rule

For an existing episode below 1080p, Sonarr Smart Optimizer can move upward toward the resolution requested by the profile even when the replacement is not smaller.

Examples for a 720p episode currently using 1.2 GiB:

- 1080p at 700 MiB: allowed by the size rule
- 1080p at 1.2 GiB: allowed by the size rule
- 1080p at 1.8 GiB: allowed at the exact +50% ceiling
- 1080p above 1.8 GiB: rejected by the low-resolution size rule

All other hard safety checks still apply. This exception is deliberately **not shared with Radarr**.

## Dynamic range and audio

The dynamic-range policy permits SDR/unknown → HDR or DV+HDR upgrades, prevents HDR → SDR/unknown, and requires DV+HDR when the existing file is already DV+HDR. DV-only candidates without HDR fallback are rejected.

For audio, 5.1/7.1 → stereo is blocked. Changes between multichannel layouts are allowed, and Atmos is used as a ranking preference rather than a mandatory preservation rule.

Release-title/metadata detection can be incomplete, so **dry-run against your own library/indexers before enabling live mode**.

## State and exclusions

By default the state file is `sonarr-smart-optimizer-state.json` beside the script. It tracks the persistent series/episode queues, cursors, search cycles, daily counters and attempted releases. Do not commit it.

When `SMART_OPTIMIZER_CONTROL` points at a control JSON used by Smart Optimizer UI, the Sonarr section can also provide downsize controls, temporary daily allowance and whole-series optimizer exclusions. Excluding a series only tells the optimizer not to search/replace its episodes; it does **not** delete the series, episodes or files.

## Scheduling

After validating dry-run output, schedule the live command with cron, Synology Task Scheduler or another scheduler. Keep the API key in a protected environment/wrapper rather than in the task text or repository.

Example wrapper:

```sh
#!/bin/sh
export SONARR_KEY="$(cat /path/to/.sonarr-smart-optimizer-key)"
exec python3 /path/to/sonarr-smart-optimizer.py --live
```

Protect the files:

```sh
chmod 600 /path/to/.sonarr-smart-optimizer-key
chmod 700 /path/to/run-sonarr-smart-optimizer.sh
```

## Related projects

- [Smart Optimizer UI](https://github.com/MrRobot-88/Smart-Optimizer-UI)
- [Radarr Smart Optimizer](https://github.com/MrRobot-88/Radarr-Smart-Optimizer)
- [Deluge Smart Cleanup](https://github.com/MrRobot-88/Deluge-Smart-Cleanup)
