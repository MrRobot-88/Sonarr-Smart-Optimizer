#!/usr/bin/env python3
import hashlib
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("usage: sonarr_upgrade_rejection_substring_patch.py SONARR_SCRIPT")

p = Path(sys.argv[1])
src = p.read_text(encoding="utf-8")

EXPECTED = "490ba5af4f46bfa713cf627908e6c9f376b2a50121c16a0a8ee67034487e607f"
actual = hashlib.sha256(src.encode("utf-8")).hexdigest()
if actual != EXPECTED:
    raise SystemExit("STOP: Sonarr optimizer hash mismatch: " + actual)

old = '''    return "existing file meets cutoff" in reason
'''

new = '''    allowed_rejection_substrings = (
        "existing file meets cutoff",
        "upgrade for existing episode file",
    )

    return any(
        token in reason
        for token in allowed_rejection_substrings
    )
'''

if src.count(old) != 1:
    raise SystemExit(
        "STOP: rejection_allowed anchor count=%d"
        % src.count(old)
    )

src = src.replace(old, new, 1)
p.write_text(src, encoding="utf-8")

print("SONARR UPGRADE-REJECTION SUBSTRING PATCH COMPLETE")
print("SHA256", hashlib.sha256(src.encode("utf-8")).hexdigest())
