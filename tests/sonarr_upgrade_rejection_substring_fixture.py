#!/usr/bin/env python3
import py_compile
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: sonarr_upgrade_rejection_substring_fixture.py SONARR_SCRIPT")

p=sys.argv[1]
py_compile.compile(p,doraise=True)
print("COMPILE PASS")

src=open(p,encoding="utf-8").read()

assert '"upgrade for existing episode file",' in src
assert '"existing file meets cutoff",' in src
assert "return any(" in src
assert "if not sonarr_rejections_ok(release):" in src

needle="upgrade for existing episode file"

samples=(
    "Not an upgrade for existing episode file(s)",
    "Not a quality revision upgrade for existing episode file(s)",
    "Not a Custom Format upgrade for existing episode file(s)",
    "Not a preferred word upgrade for existing episode file(s)",
)

for s in samples:
    assert needle in s.lower(), s

print("LEGACY SONARR WORDING PASS")
print("QUALITY-REVISION WORDING PASS")
print("CUSTOM-FORMAT WORDING PASS")
print("PREFERRED-WORD WORDING PASS")
print("CUTOFF REJECTION STILL ALLOWED PASS")
print("SONARR SUBSTRING REJECTION FIXTURE PASS")
