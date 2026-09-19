# Sonarr Smart Optimizer

A small Python tool that searches your **existing Sonarr library** for smaller replacement releases while applying safety checks before it asks Sonarr to grab anything.

It is **dry-run by default**. It does not delete media files, call Sonarr DELETE endpoints, or control your download client directly. In live mode, the script sends the selected release to Sonarr and lets Sonarr handle its normal download/import/replacement workflow.

## What it protects

- Avoids resolution downgrades.
- Requires a minimum size saving before replacing a same-resolution file.
- Protects HDR/Dolby Vision rules used by the optimizer.
- Protects audio channel count and Atmos where detected.
- Rejects releases with no known seeders.
- Blocks suspicious executable/script filenames in release titles.
- Rechecks the Sonarr queue immediately before a live grab.
- Remembers search attempts in a local state file.
- Runs at most two optimizer search cycles per episode, with a 180-day wait before the second cycle.

## Requirements

- Sonarr v4 with its API reachable from the machine running the script.
- Python 3.8+.
- Your Sonarr API key.
- Indexers/download clients already configured normally in Sonarr/Prowlarr.

No third-party Python packages are required.

## Quick start

Download `sonarr-smart-optimizer.py`, then set your API key:

```sh
export SONARR_KEY='YOUR_API_KEY'
python3 sonarr-smart-optimizer.py
```

The command above is a **dry run**. Read the results first.

When you are satisfied with the choices it makes:

```sh
python3 sonarr-smart-optimizer.py --live
```

Live mode can start downloads through Sonarr, so use dry-run first.

## Configuration

Environment variables keep secrets and machine-specific settings out of the script:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SONARR_URL` | `http://127.0.0.1:8989` | Sonarr URL |
| `SONARR_KEY` | none | Sonarr API key (required) |
| `SONARR_OPTIMIZER_STATE` | state JSON beside the script | State-file location |
| `SONARR_DAILY_SEARCH_BUDGET` | `400` | Maximum optimizer searches per live day |
| `SONARR_MIN_SEEDERS` | `1` | Minimum known seeders |
| `SONARR_MIN_SAVING_PERCENT` | `5` | Minimum same-resolution saving |
| `SONARR_NORMAL_PROFILE_ID` | `4` | Normal/1080p profile ID used by this version |
| `SONARR_UHD_PROFILE_ID` | `5` | UHD/2160p profile ID used by this version |

**Check the two profile IDs before live mode.** Sonarr installations do not necessarily use the same IDs.

## Scheduling

After testing manually, schedule the same command with cron, Synology Task Scheduler, or another scheduler. Keep the API key in an environment variable or a protected wrapper/key file rather than putting it in this repository.

The script has its own daily search budget, so running it several times per day does not mean it will exceed that configured daily maximum.

### Synology DSM Task Scheduler example

On Synology DSM, open **Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script**.

Use a user that can run Python and access the optimizer folder. Under **Schedule**, choose how often you want it to run. A practical example is every 3 hours.

Under **Task Settings → User-defined script**, use a protected wrapper script rather than putting the API key directly in Task Scheduler. Example wrapper:

```sh
#!/bin/sh
export SONARR_KEY="$(cat /path/to/.sonarr-smart-optimizer-key)"
exec python3 /path/to/sonarr-smart-optimizer.py --live
```

Protect the key and wrapper:

```sh
chmod 600 /path/to/.sonarr-smart-optimizer-key
chmod 700 /path/to/run-sonarr-smart-optimizer.sh
```

Then make the DSM task run:

```sh
/path/to/run-sonarr-smart-optimizer.sh
```

Run the optimizer manually in **dry-run mode first**. Only add `--live` to the scheduled wrapper after you have checked its proposed replacements.

## State file

The optimizer creates `sonarr-smart-optimizer-state.json` beside the script by default. It tracks optimizer search cycles, daily search counts, and recently attempted releases. Do not commit this file.

Existing old state entries without `search_cycles` do not automatically count as one of the new two-cycle searches.

## Important

This project was built for cautious library optimization, but release metadata is not perfect. Test with dry-run on your own library before enabling `--live`.

Looking for movies instead? See **Radarr Smart Optimizer**: https://github.com/MrRobot-88/Radarr-Smart-Optimizer
