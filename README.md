# Sonarr Smart Optimizer

> ## Smart Optimizer UI (easiest setup)
> Prefer one container with a web dashboard? Use [Smart Optimizer UI](https://github.com/MrRobot-88/Smart-Optimizer-UI). It bundles the Sonarr and Radarr optimizers and lets you configure connections from the browser.

Sonarr Smart Optimizer revisits episodes already in your Sonarr library and searches for more storage-efficient replacements while applying conservative media-safety rules before asking Sonarr to grab anything.

It is **dry-run by default**. The script never calls Sonarr DELETE endpoints and never controls your download client directly. In live mode it sends a selected release to Sonarr; Sonarr then handles downloading, import and normal file replacement.

## Current behavior

- Persistent **A-Z series queue** and persistent episode work queue/cursor.
- Newly added series are appended to the end instead of reordering existing work.
- Optimizer-only exclusions apply to an **entire series** and are checked before interactive release searches.
- Current episode files below **400 MiB** are skipped before an interactive release search.
- **TorrentLeech-first selection:** if at least one valid TorrentLeech result exists in the same Sonarr release search, only that valid TorrentLeech pool is ranked. Other indexers are fallback only when no valid TorrentLeech candidate exists.
- **Normal 1080p is storage-first:** the smallest valid 1080p release wins. HDR, Atmos and channel count do not make a larger normal 1080p release win.
- **720p upgrade rule:** an existing 720p episode may upgrade only to 1080p, never to another 720p or directly to 2160p. The 1080p replacement may grow by at most **40%**.
- Existing 1080p and 2160p replacements must be **strictly smaller** than the current file and must satisfy the configured minimum saving. Downsizing is hard-capped at **40%** even if a higher maximum is configured.
- On the UHD profile, candidates must be 2160p and advertise at least HDR. Ranking prefers **DV+HDR**, then HDR, then Atmos, then the smaller file.
- Season packs and multi-episode releases are rejected for single-episode optimization.
- AV1 candidates are rejected.
- Dolby Vision-only candidates without HDR fallback are rejected.
- Immediately before a live grab, the optimizer revalidates the current episode file ID, byte size, resolution and quality profile so a stale search result cannot replace a changed file.
- Search history, queue position and attempted releases are persisted.
- At most two optimizer search cycles per episode, with a 180-day wait before the second cycle.
- Manual UI mode can use `SMART_OPTIMIZER_TARGET_GRABS`: the requested number represents successful releases sent to Sonarr.
- `SMART_OPTIMIZER_EPISODE_ID` targets one episode directly.
- `SMART_OPTIMIZER_SERIES_ID` targets one series directly without consuming the normal persistent A-Z queue.
- `SMART_OPTIMIZER_MANUAL_TARGET=1` marks an explicit Manual Optimizer run so normal daily-search accounting is not consumed.

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
| `SONARR_MAX_SAVING_PERCENT` | `50` | Configured maximum saving; the v2 engine also applies an absolute 40% hard ceiling |
| `SMART_OPTIMIZER_CONTROL` | control JSON beside script | Optional shared runtime controls/exclusions |
| `SMART_OPTIMIZER_TARGET_GRABS` | `0` | Maximum successful grabs for targeted/manual UI runs |
| `SMART_OPTIMIZER_EPISODE_ID` | unset | Target one Sonarr episode directly |
| `SMART_OPTIMIZER_SERIES_ID` | unset | Target one Sonarr series directly |
| `SMART_OPTIMIZER_MANUAL_TARGET` | `0` | Mark an explicit Manual Optimizer run so it does not consume normal daily-search accounting |

The standalone script's base daily search budget is currently **400** searches. The shared control file can supply date-scoped temporary extra searches and override the min/max saving window.

The current script uses normal profile ID `4` and UHD profile ID `5`; verify those IDs against your own Sonarr installation before live mode.

## Resolution and ranking rules

The only allowed size-growth case is **720p → 1080p**, with a maximum increase of 40%. A 720p episode is never replaced by another 720p release and is never sent directly to 2160p.

For ordinary 1080p episodes, storage reduction is the priority: after all hard safety gates pass, the smallest valid release in the primary indexer pool wins. HDR and Atmos are allowed, but they do not outrank a smaller 1080p file.

For the UHD profile, the optimizer requires 2160p with HDR and prefers DV+HDR over plain HDR. Atmos is then a preference, followed by smaller size within the same quality tier.

Every 1080p/2160p replacement must be strictly smaller than the current file. The configured minimum saving still applies, and the optimizer will not accept more than a 40% reduction in one pass.

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
