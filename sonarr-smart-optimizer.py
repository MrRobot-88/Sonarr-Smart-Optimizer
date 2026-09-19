#!/usr/bin/env python3

import os
import sys
import json
import re
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# ============================================================
# SONARR SMART OPTIMIZER
#
# Default = DRY RUN
# Live    = --live
#
# IMPORTANT:
# - This script NEVER calls Sonarr DELETE endpoints directly
# - In live mode Sonarr may replace an existing file after importing a selected release
# - NEVER touches Deluge directly
# - Sonarr performs normal Completed Download Handling/import
# - Search budgets are configurable; defaults are conservative for scheduled use
# ============================================================

# ============================================================
# QUICK SETUP
# ============================================================
# API keys are intentionally NOT stored in this source file.
# Set SONARR_KEY in your environment or use a protected wrapper/key file.
# Check the URL if Sonarr is not on the same machine, then review
# SEARCHES_PER_RUN plus NORMAL_PROFILE_ID and UHD_PROFILE_ID below.
SONARR_URL_DEFAULT = "http://127.0.0.1:8989"
SEARCHES_PER_RUN = 10

SONARR_URL = os.environ.get("SONARR_URL", SONARR_URL_DEFAULT).rstrip("/")
API_KEY = os.environ.get("SONARR_KEY", "").strip()
SEARCHES_PER_RUN = int(os.environ.get("SONARR_SEARCHES_PER_RUN", SEARCHES_PER_RUN))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.environ.get(
    "SONARR_OPTIMIZER_STATE",
    os.path.join(SCRIPT_DIR, "sonarr-smart-optimizer-state.json")
)

NORMAL_PROFILE_ID = 4
UHD_PROFILE_ID = 5

DAILY_SEARCH_BUDGET = 400
MIN_SEEDERS = 1
MIN_SAVING_PERCENT = 5.0

# Search cooldowns
COOLDOWN_RESOLUTION_UPGRADE = 30
COOLDOWN_X264 = 90
COOLDOWN_X265_LARGE = 180
COOLDOWN_X265_COMPACT = 365
COOLDOWN_4K = 180

# Don't deliberately grab the exact same release again for this long
ATTEMPT_COOLDOWN_DAYS = 365

# These are NOT hard quality limits.
# They are only used for PRIORITY.
LARGE_1080P_MIB = 1800
COMPACT_1080P_X265_MIB = 1200
LARGE_2160P_MIB = 6000

# Hard ceiling for a 1080p -> 2160p resolution upgrade.
# 8 GiB = 8192 MiB.
MAX_4K_UPGRADE_MIB = 8192

# Prevent one large series from consuming the whole daily budget.
MAX_SEARCHES_PER_SERIES_PER_RUN = 3

LIVE = "--live" in sys.argv

if not API_KEY:
    print("ERROR: Sonarr API key is not configured.")
    print()
    print("Set SONARR_KEY in your environment or protected wrapper/key file.")
    print("Then run: python3 sonarr-smart-optimizer.py")
    sys.exit(1)


# ============================================================
# BASIC HELPERS
# ============================================================

def now_ts():
    return int(time.time())


def age_days(timestamp):
    if not timestamp:
        return 999999
    return (now_ts() - int(timestamp)) / 86400.0


def mib(value):
    try:
        return float(value) / 1024 / 1024
    except Exception:
        return 0.0


def api(method, path, data=None):
    url = SONARR_URL + "/api/v3" + path

    headers = {
        "X-Api-Key": API_KEY,
        "Accept": "application/json"
    }

    body = None

    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()

            if not raw:
                return None

            return json.loads(raw.decode("utf-8"))

    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            "%s %s -> HTTP %s\n%s" %
            (method, path, e.code, detail)
        )

    except Exception as e:
        raise RuntimeError(
            "%s %s -> %s" %
            (method, path, e)
        )


def get(path):
    return api("GET", path)


def post(path, data):
    return api("POST", path, data)


# ============================================================
# STATE
# ============================================================

def blank_state():
    return {
        "version": 1,
        "episodes": {},
        "attempted_releases": {},
        "daily": {}
    }


def load_state():
    if not os.path.exists(STATE_FILE):
        return blank_state()

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)

        state.setdefault("version", 1)
        state.setdefault("episodes", {})
        state.setdefault("attempted_releases", {})
        state.setdefault("daily", {})

        return state

    except Exception as e:
        print("WARNING: Could not read state file:")
        print(" ", e)
        print("Using empty state for this run.")
        return blank_state()


def save_state(state):
    if not LIVE:
        return

    tmp = STATE_FILE + ".tmp"

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)

    os.replace(tmp, STATE_FILE)


def today_key():
    return datetime.now().strftime("%Y-%m-%d")


def searches_used_today(state):
    return int(
        state.get("daily", {})
             .get(today_key(), {})
             .get("searches", 0)
    )


def increment_search_count(state):
    day = today_key()

    state.setdefault("daily", {})
    state["daily"].setdefault(day, {"searches": 0})

    state["daily"][day]["searches"] += 1

    # Remove ancient daily counters.
    keys = sorted(state["daily"].keys())

    if len(keys) > 60:
        for old in keys[:-60]:
            state["daily"].pop(old, None)


def mark_episode_searched(state, episode_id):
    key = str(episode_id)
    state["episodes"].setdefault(key, {})
    entry = state["episodes"][key]
    entry["last_search"] = now_ts()
    entry["search_cycles"] = min(2, int(entry.get("search_cycles", 0)) + 1)


def release_key(release):
    for field in (
        "guid",
        "downloadUrl",
        "infoUrl",
        "title"
    ):
        value = release.get(field)
        if value:
            return str(value)

    return str(release.get("title", "UNKNOWN"))


def release_recently_attempted(state, release):
    key = release_key(release)

    ts = state.get("attempted_releases", {}).get(key)

    if not ts:
        return False

    return age_days(ts) < ATTEMPT_COOLDOWN_DAYS


def mark_release_attempted(state, release):
    key = release_key(release)
    state.setdefault("attempted_releases", {})
    state["attempted_releases"][key] = now_ts()


def clean_old_attempts(state):
    cutoff = ATTEMPT_COOLDOWN_DAYS + 30

    remove = []

    for key, ts in state.get("attempted_releases", {}).items():
        if age_days(ts) > cutoff:
            remove.append(key)

    for key in remove:
        state["attempted_releases"].pop(key, None)


# ============================================================
# MEDIA PARSING
# ============================================================

def codec_from_text(text):
    """
    Detect VIDEO codec from a release title.

    Normalized values:
      x265
      x264
      av1
      vp9
      vp8
      vc1
      unknown

    MKV/MP4 are containers and intentionally do NOT determine codec.
    """
    text = text or ""

    # H.265 / HEVC
    if re.search(
        r'(?i)(?:\bx[ ._-]?265\b|\bh[ ._-]?265\b|\bhevc\b)',
        text
    ):
        return "x265"

    # H.264 / AVC
    if re.search(
        r'(?i)(?:\bx[ ._-]?264\b|\bh[ ._-]?264\b|\bavc\b)',
        text
    ):
        return "x264"

    # AV1 / AV01
    if re.search(
        r'(?i)(?:\bav[ ._-]?1\b|\bav01\b)',
        text
    ):
        return "av1"

    # VP9 / VP09
    if re.search(
        r'(?i)(?:\bvp[ ._-]?9\b|\bvp09\b)',
        text
    ):
        return "vp9"

    # VP8 / VP08
    if re.search(
        r'(?i)(?:\bvp[ ._-]?8\b|\bvp08\b)',
        text
    ):
        return "vp8"

    # VC-1 / VC1
    if re.search(
        r'(?i)\bvc[ ._-]?1\b',
        text
    ):
        return "vc1"

    return "unknown"


def audio_channels_from_text(text):
    text = (text or "").lower()

    patterns = [
        (7.1, r"\b7[\s._-]?1\b"),
        (5.1, r"\b5[\s._-]?1\b"),
        (2.1, r"\b2[\s._-]?1\b"),
        (2.0, r"\b2[\s._-]?0\b"),
        (1.0, r"\b1[\s._-]?0\b"),
    ]

    for channels, pattern in patterns:
        if re.search(pattern, text):
            return channels

    if "stereo" in text:
        return 2.0

    return None


DANGEROUS_EXTENSIONS = (
    "exe", "scr", "bat", "cmd", "msi", "com",
    "pif", "vbs", "js", "jar", "ps1"
)


def dangerous_release_title(text):
    """
    Hard-block executable/script payloads.
    MKV, MP4 and other normal media containers are unaffected.
    """
    text = text or ""

    pattern = (
        r'(?i)\.(?:'
        + '|'.join(re.escape(ext) for ext in DANGEROUS_EXTENSIONS)
        + r')(?=$|[\s._\-\[\]\(\)])'
    )

    return bool(re.search(pattern, text))


def dynamic_range_from_text(text):
    """
    Conservative release-title classification.

    Returns:
      SDR_UNKNOWN
      HDR
      DV_ONLY
      DV_HDR

    IMPORTANT:
    DV-only is never acceptable.
    Dolby Vision must explicitly also advertise HDR/HDR10/HDR10+.
    """
    text = (text or "").lower()

    has_dv = bool(
        re.search(
            r"\b(dv|dovi|dolby[\s._-]?vision)\b",
            text
        )
    )

    has_hdr = bool(
        re.search(
            r"\b(hdr10\+?|hdr|hlg)\b",
            text
        )
    )

    if has_dv and has_hdr:
        return "DV_HDR"

    if has_dv:
        return "DV_ONLY"

    if has_hdr:
        return "HDR"

    return "SDR_UNKNOWN"


def dynamic_range_allowed(existing_hdr, candidate_range):
    """
    Dynamic-range replacement policy.

    Candidate SDR_UNKNOWN means the release title does not explicitly
    advertise HDR/DV. For selection purposes it is allowed exactly like
    ordinary SDR UNLESS the existing file is positively known to be HDR.

    Rules:
      existing SDR/unknown -> SDR_UNKNOWN : ALLOW
      existing SDR/unknown -> HDR         : ALLOW
      existing SDR/unknown -> DV_HDR      : ALLOW

      existing HDR         -> SDR_UNKNOWN : BLOCK
      existing HDR         -> HDR         : ALLOW
      existing HDR         -> DV_HDR      : ALLOW

      DV_ONLY is ALWAYS blocked.
    """

    if candidate_range == "DV_ONLY":
        return False

    if existing_hdr and candidate_range == "SDR_UNKNOWN":
        return False

    return True



def hdr_from_media_info(media):
    if not media:
        return False

    pieces = []

    for key in (
        "videoDynamicRange",
        "videoDynamicRangeType",
        "videoCodec",
        "videoProfile"
    ):
        value = media.get(key)

        if value:
            pieces.append(str(value))

    text = " ".join(pieces).lower()

    return bool(
        re.search(
            r"(dolby|dovi|\bdv\b|hdr|hlg|pq)",
            text
        )
    )


def current_audio_channels(media):
    if not media:
        return None

    value = media.get("audioChannels")

    try:
        if value is not None:
            return float(value)
    except Exception:
        pass

    return None


def current_codec(file_obj):
    media = file_obj.get("mediaInfo") or {}

    codec = codec_from_text(
        " ".join([
            str(media.get("videoCodec", "")),
            str(file_obj.get("sceneName", "")),
            str(file_obj.get("relativePath", ""))
        ])
    )

    return codec


def quality_resolution(quality_obj):
    q = quality_obj or {}

    if "quality" in q:
        q = q.get("quality") or {}

    resolution = q.get("resolution")

    try:
        if resolution:
            return int(resolution)
    except Exception:
        pass

    name = str(q.get("name", ""))

    match = re.search(r"(2160|1080|720|480)", name)

    if match:
        return int(match.group(1))

    return 0


def file_resolution(file_obj):
    media = file_obj.get("mediaInfo") or {}

    width = media.get("width")
    height = media.get("height")

    try:
        height = int(height or 0)
    except Exception:
        height = 0

    if height >= 2000:
        return 2160

    if height >= 1000:
        return 1080

    if height >= 700:
        return 720

    return quality_resolution(file_obj.get("quality"))


# ============================================================
# QUEUE
# ============================================================

def active_episode_ids():
    ids = set()

    page = 1

    while True:
        path = (
            "/queue?page=%d&pageSize=100"
            "&includeUnknownSeriesItems=true"
        ) % page

        data = get(path)

        if not data:
            break

        records = data.get("records", [])

        for item in records:
            episode_id = item.get("episodeId")

            if episode_id:
                ids.add(int(episode_id))

        total = int(data.get("totalRecords", len(records)))

        if page * 100 >= total:
            break

        page += 1

    return ids


# ============================================================
# LOCAL LIBRARY CANDIDATES
# ============================================================

def priority_score(item):
    """
    Higher = search earlier.

    IMPORTANT:
    This only decides WHICH existing episodes deserve one of
    our scarce interactive searches.

    It does NOT decide which release wins after searching.
    Profile 5 can still prefer a valid <=8 GiB 2160p release.
    If no valid 2160p exists, smaller qualifying 1080p releases
    remain fully eligible.
    """

    res = item["resolution"]
    target = item["target_resolution"]
    size = item["size_mib"]
    codec = item["codec"]

    score = 0.0

    # --------------------------------------------------------
    # PROFILE 5 / 4K-PREFERRED SERIES
    # --------------------------------------------------------
    if item["profile_id"] == UHD_PROFILE_ID:

        # Missing target resolution is important, but don't give
        # every 1080p episode an identical gigantic score.
        if res < 2160:
            score += 600000

            # Lower-than-1080p files are much more urgent.
            if res < 1080:
                score += 300000

            # Larger existing files have more optimization
            # potential if no acceptable 4K release exists.
            score += min(size * 100, 300000)

            # x264 gets extra attention because x265 often gives
            # worthwhile space savings.
            if codec == "x264":
                score += 100000
            elif codec == "unknown":
                score += 50000

            # Already tiny 1080p x265 files can still eventually
            # be searched for 4K, but should not steal today's
            # scarce slots from much larger files.
            if (
                res == 1080
                and codec == "x265"
                and size <= COMPACT_1080P_X265_MIB
            ):
                score -= 150000

        else:
            # Already 2160p: only optimization potential matters.
            score += min(size * 25, 200000)

            if codec == "x264":
                score += 75000

            if size >= LARGE_2160P_MIB:
                score += 100000

        return score

    # --------------------------------------------------------
    # NORMAL 1080P PROFILE
    # --------------------------------------------------------

    # Resolution deficiency has highest priority.
    if res < target:
        score += 800000
        score += (target - res) * 500

    # x264 generally has greater compression-saving potential.
    if codec == "x264":
        score += 200000
    elif codec == "unknown":
        score += 100000

    # Large files deserve attention.
    if size >= LARGE_1080P_MIB:
        score += 200000

    score += min(size * 50, 250000)

    # Compact 1080p x265 is already in a very good state.
    if (
        res >= 1080
        and codec == "x265"
        and size <= COMPACT_1080P_X265_MIB
    ):
        score -= 200000

    return score

def collect_candidates(state, queued_ids):
    series_list = get("/series")

    candidates = []

    total_series = len(series_list)

    print("Reading local Sonarr library metadata...")
    print("Series:", total_series)
    print()

    for index, series in enumerate(series_list, 1):
        profile_id = int(series.get("qualityProfileId", 0))

        if profile_id not in (
            NORMAL_PROFILE_ID,
            UHD_PROFILE_ID
        ):
            continue

        series_id = int(series["id"])

        target = (
            2160
            if profile_id == UHD_PROFILE_ID
            else 1080
        )

        try:
            episodes = get(
                "/episode?seriesId=%d" % series_id
            )

            files = get(
                "/episodefile?seriesId=%d" % series_id
            )

        except Exception as e:
            print(
                "WARNING: Could not inspect series:",
                series.get("title"),
                e
            )
            continue

        files_by_id = {
            int(f["id"]): f
            for f in files
            if f.get("id")
        }

        for ep in episodes:
            episode_id = int(ep.get("id", 0))

            if not episode_id:
                continue

            # Optimize existing files regardless of Sonarr
            # monitored/unmonitored status.
            if not ep.get("hasFile", False):
                continue

            # NEVER search while replacement/download exists.
            if episode_id in queued_ids:
                continue

            file_id = ep.get("episodeFileId")

            if not file_id:
                continue

            file_obj = files_by_id.get(int(file_id))

            if not file_obj:
                continue

            resolution = file_resolution(file_obj)

            if not resolution:
                continue

            size_mib = mib(file_obj.get("size", 0))
            codec = current_codec(file_obj)
            media = file_obj.get("mediaInfo") or {}

            item = {
                "series_id": series_id,
                "series_title": series.get("title", ""),
                "episode_id": episode_id,
                "season": int(ep.get("seasonNumber", 0)),
                "episode": int(ep.get("episodeNumber", 0)),
                "episode_title": ep.get("title", ""),
                "profile_id": profile_id,
                "target_resolution": target,
                "file": file_obj,
                "resolution": resolution,
                "size_mib": size_mib,
                "codec": codec,
                "audio_channels": current_audio_channels(media),
                "hdr": hdr_from_media_info(media),
            }

            # Optimizer search-cycle policy:
            #   cycle 0: eligible now
            #   cycle 1: wait at least 180 days
            #   cycle 2: permanently excluded from this optimizer.
            #
            # Old last_search entries without search_cycles do NOT
            # count toward the new two-cycle system.
            episode_state = state.get(
                "episodes", {}
            ).get(str(episode_id), {})

            cycles = int(episode_state.get("search_cycles", 0))
            last_search = episode_state.get("last_search")

            if cycles >= 2:
                continue

            if cycles == 1 and last_search and age_days(last_search) < 180:
                continue

            item["cooldown_days"] = 180
            item["priority"] = priority_score(item)

            candidates.append(item)

    candidates.sort(
        key=lambda x: (
            x["priority"],
            x["size_mib"]
        ),
        reverse=True
    )

    return candidates


# ============================================================
# RELEASE EVALUATION
# ============================================================

def rejection_allowed(rejection):
    """
    We ONLY ignore Sonarr's cutoff rejection because the
    optimizer intentionally evaluates replacements beyond
    Sonarr's normal cutoff.

    Every other Sonarr rejection remains respected.
    """

    reason = ""

    if isinstance(rejection, dict):
        reason = str(
            rejection.get("reason")
            or rejection.get("message")
            or ""
        )
    else:
        reason = str(rejection)

    reason = reason.lower()

    return "existing file meets cutoff" in reason


def sonarr_rejections_ok(release):
    rejected = release.get("rejections") or []

    for rejection in rejected:
        if not rejection_allowed(rejection):
            return False

    return True


def candidate_resolution(release):
    return quality_resolution(release.get("quality"))


def evaluate_release(item, release, state):
    title = str(release.get("title", ""))

    # HARD SAFETY BLOCK:
    # Never grab executable/script payloads.
    if dangerous_release_title(title):
        return None

    if not sonarr_rejections_ok(release):
        return None

    if release_recently_attempted(state, release):
        return None

    # Require positive seeder evidence before grabbing.
    # Unknown, missing, invalid or zero seeders are rejected.
    seeders = release.get("seeders")

    try:
        seeders = int(seeders)
    except (TypeError, ValueError):
        return None

    if seeders < MIN_SEEDERS:
        return None

    new_res = candidate_resolution(release)

    if not new_res:
        return None

    old_res = item["resolution"]
    target = item["target_resolution"]

    # NEVER exceed profile target.
    if new_res > target:
        return None

    # NEVER resolution downgrade.
    if new_res < old_res:
        return None

    new_size = mib(release.get("size", 0))

    if new_size <= 0:
        return None

    codec = codec_from_text(title)
    candidate_audio = audio_channels_from_text(title)

    dynamic_range = dynamic_range_from_text(title)
    candidate_hdr = dynamic_range in ("HDR", "DV_HDR")

    # HARD RULE:
    # Dolby Vision without an explicit HDR fallback is rejected.
    if not dynamic_range_allowed(item["hdr"], dynamic_range):
        return None

    # --------------------------------------------------------
    # HIGHER RESOLUTION
    # --------------------------------------------------------

    if new_res > old_res:

        # 1080p -> 2160p is allowed only up to 8 GiB/episode.
        if (
            old_res <= 1080
            and new_res == 2160
            and new_size > MAX_4K_UPGRADE_MIB
        ):
            return None

        # Protect known audio even when gaining resolution.
        old_audio = item["audio_channels"]

        if old_audio is not None:
            if candidate_audio is None:
                return None

            if candidate_audio < old_audio:
                return None

        # Existing HDR must not become SDR/unknown merely
        # because the candidate has higher resolution.
        

        return {
            "release": release,
            "resolution": new_res,
            "size_mib": new_size,
            "codec": codec,
            "audio": candidate_audio,
            "hdr": candidate_hdr,
            "dynamic_range": dynamic_range,
            "saving_percent": None,
            "reason": "resolution upgrade"
        }

    # --------------------------------------------------------
    # SAME RESOLUTION
    # --------------------------------------------------------

    old_size = item["size_mib"]

    if old_size <= 0:
        return None

    saving = (
        (old_size - new_size)
        / old_size
        * 100.0
    )

    # Must actually save meaningful space.
    if saving < MIN_SAVING_PERCENT:
        return None

    # Audio protection.
    #
    # If current file has known channel count, candidate must
    # ALSO tell us its channel count and it cannot be lower.
    old_audio = item["audio_channels"]

    if old_audio is not None:
        if candidate_audio is None:
            return None

        if candidate_audio < old_audio:
            return None

    # HDR/DV protection at BOTH 1080p and 2160p.
    #
    # Existing HDR/DV -> SDR/unknown = NEVER for space saving.
    #
    # Existing SDR -> HDR/DV is allowed.
    

    return {
        "release": release,
        "resolution": new_res,
        "size_mib": new_size,
        "codec": codec,
        "audio": candidate_audio,
        "hdr": candidate_hdr,
        "dynamic_range": dynamic_range,
        "saving_percent": saving,
        "reason": "smaller same-resolution file"
    }


def choose_best(item, releases, state):
    valid = []

    for release in releases:
        result = evaluate_release(
            item,
            release,
            state
        )

        if result:
            valid.append(result)

    if not valid:
        return None

    old_res = item["resolution"]

    higher = [
        x for x in valid
        if x["resolution"] > old_res
    ]

    if higher:
        # Higher resolution wins.
        #
        # Within that resolution:
        # x265 preferred, then smaller file.
        higher.sort(
            key=lambda x: (
                x["resolution"],
                1 if x["codec"] == "x265" else 0,
                -x["size_mib"]
            ),
            reverse=True
        )

        return higher[0]

    # Same resolution:
    #
    # Smaller file is the main purpose.
    # x265 breaks close/equal choices rather than allowing a
    # larger x265 to beat a smaller x264.
    valid.sort(
        key=lambda x: (
            x["size_mib"],
            0 if x["codec"] == "x265" else 1
        )
    )

    return valid[0]


# ============================================================
# OUTPUT
# ============================================================

def describe_item(number, item):
    audio = (
        "%.1f" % item["audio_channels"]
        if item["audio_channels"] is not None
        else "unknown"
    )

    print(
        "%2d. %s S%02dE%02d"
        % (
            number,
            item["series_title"],
            item["season"],
            item["episode"]
        )
    )

    print(
        "    Current: %dp | %s | %.0f MiB | %sch | HDR=%s"
        % (
            item["resolution"],
            item["codec"],
            item["size_mib"],
            audio,
            item["hdr"]
        )
    )

    print(
        "    Target: %dp | priority %.0f | cooldown %d days"
        % (
            item["target_resolution"],
            item["priority"],
            item["cooldown_days"]
        )
    )


def describe_choice(choice):
    release = choice["release"]

    audio = (
        "%.1f" % choice["audio"]
        if choice["audio"] is not None
        else "unknown"
    )

    print("    FOUND:", release.get("title", ""))

    print(
        "    New: %dp | %s | %.0f MiB | %sch | HDR=%s"
        % (
            choice["resolution"],
            choice["codec"],
            choice["size_mib"],
            audio,
            choice["hdr"]
        )
    )

    if choice["saving_percent"] is not None:
        print(
            "    Saving: %.1f%%"
            % choice["saving_percent"]
        )

    print(
        "    Indexer:",
        release.get("indexer", "unknown")
    )

    print(
        "    Seeders:",
        release.get("seeders", "unknown")
    )


# ============================================================
# MAIN
# ============================================================

def main():
    state = load_state()

    if LIVE:
        clean_old_attempts(state)

    print()
    print("=" * 68)
    print("SONARR SMART OPTIMIZER")
    print("=" * 68)

    if LIVE:
        print("MODE: LIVE")
    else:
        print("MODE: DRY RUN -- NO RELEASES WILL BE GRABBED")

    print("Daily interactive-search budget:", DAILY_SEARCH_BUDGET)
    print("Minimum same-resolution saving: %.1f%%" % MIN_SAVING_PERCENT)
    print()

    used = searches_used_today(state)

    # Maximum interactive searches in one execution.
    PER_RUN_SEARCH_BUDGET = max(1, SEARCHES_PER_RUN)

    if LIVE:
        remaining = min(
            PER_RUN_SEARCH_BUDGET,
            max(0, DAILY_SEARCH_BUDGET - used)
        )
    else:
        # Dry run does NOT consume persistent budget.
        remaining = min(
            PER_RUN_SEARCH_BUDGET,
            DAILY_SEARCH_BUDGET
        )

    print(
        "Persistent searches already used today:",
        used
    )

    print(
        "Searches available this run:",
        remaining
    )

    if remaining <= 0:
        print()
        print("Daily search budget exhausted.")
        print("Nothing to do.")
        return

    print()
    print("Reading Sonarr queue...")

    queued_ids = active_episode_ids()

    print(
        "Episodes currently represented in queue:",
        len(queued_ids)
    )

    print()

    candidates = collect_candidates(
        state,
        queued_ids
    )

    print()
    print(
        "Eligible local optimization candidates:",
        len(candidates)
    )

    if not candidates:
        print("Nothing currently needs an optimizer search.")
        return

    # Only high-priority candidates get an indexer search,
    # but one large series must not consume the whole budget.
    selected = []
    per_series = {}

    for item in candidates:
        series_id = item["series_id"]

        used_for_series = per_series.get(series_id, 0)

        if used_for_series >= MAX_SEARCHES_PER_SERIES_PER_RUN:
            continue

        selected.append(item)
        per_series[series_id] = used_for_series + 1

        if len(selected) >= remaining:
            break

    print()
    print(
        "Highest-priority episodes selected for this run:",
        len(selected)
    )

    print(
        "Maximum searches from one series this run:",
        MAX_SEARCHES_PER_SERIES_PER_RUN
    )
    print()

    searches = 0
    grabs = 0
    no_match = 0
    errors = 0

    for number, item in enumerate(selected, 1):
        print("-" * 68)

        describe_item(number, item)

        episode_id = item["episode_id"]

        try:
            # THIS is the expensive interactive indexer search.
            releases = get(
                "/release?episodeId=%d"
                % episode_id
            )

            searches += 1

            if LIVE:
                increment_search_count(state)
                mark_episode_searched(
                    state,
                    episode_id
                )

                # Save immediately so a crash/restart does not
                # accidentally reset our search budget.
                save_state(state)

        except Exception as e:
            errors += 1
            print("    SEARCH ERROR:", e)
            print()
            continue

        choice = choose_best(
            item,
            releases,
            state
        )

        if not choice:
            no_match += 1
            print("    KEEP CURRENT: no qualifying replacement.")
            print()
            continue

        describe_choice(choice)

        if not LIVE:
            print("    DRY RUN: WOULD GRAB")
            print()
            continue

        # ----------------------------------------------------
        # SAFETY CHECK AGAIN immediately before grabbing.
        # ----------------------------------------------------

        try:
            fresh_queue = active_episode_ids()

            if episode_id in fresh_queue:
                print(
                    "    SKIP: episode entered Sonarr queue "
                    "while we were evaluating it."
                )
                print()
                continue

        except Exception as e:
            print(
                "    SKIP: could not perform final queue safety check:",
                e
            )
            print()
            continue

        try:
            # The ONLY Sonarr write operation used to initiate
            # replacement.
            #
            # NO DELETE.
            # NO filesystem manipulation.
            # NO direct Deluge manipulation.
            post(
                "/release",
                choice["release"]
            )

            grabs += 1

            mark_release_attempted(
                state,
                choice["release"]
            )

            save_state(state)

            print("    LIVE: RELEASE SENT TO SONARR")
            print(
                "    Existing episode remains until Sonarr "
                "successfully downloads and imports replacement."
            )


        except Exception as e:
            errors += 1
            print("    GRAB ERROR:", e)

        print()

    print("=" * 68)
    print("SUMMARY")
    print("=" * 68)

    print("Interactive searches this run:", searches)

    if LIVE:
        print("Releases sent to Sonarr:", grabs)
        print(
            "Persistent searches used today:",
            searches_used_today(state)
        )
    else:
        print("Downloads started: 0")
        print("State changes: 0")

    print("No qualifying replacement:", no_match)
    print("Errors:", errors)

    if not LIVE:
        print()
        print(
            "DRY RUN COMPLETE -- no releases were grabbed and "
            "no persistent cooldown changes were made."
        )


if __name__ == "__main__":
    main()
