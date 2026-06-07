#!/usr/bin/env python3
"""Repository-level SchoolFit Skill release checks.

This script intentionally lives outside the published skill directory so the
ClawHub runtime package stays read-only and does not include local file
inspection commands.
"""

from __future__ import annotations

import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "schoolfit-hk"
SCRIPT = SKILL_DIR / "scripts" / "schoolfit_api.py"
PUBLIC_DOCS = [
    SKILL_DIR / "SKILL.md",
    SKILL_DIR / "AUDIT.md",
    ROOT / "README.md",
    ROOT / "MARKETPLACE.md",
]


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    checks: list[tuple[str, bool]] = []
    for path in [*PUBLIC_DOCS, SCRIPT, SKILL_DIR / ".clawhubignore"]:
        checks.append((f"exists:{path.relative_to(ROOT)}", path.exists()))

    skill = read(SKILL_DIR / "SKILL.md")
    script = read(SCRIPT)
    public_text = "\n".join(read(path) for path in PUBLIC_DOCS if path.exists())

    version_match = re.search(r'^version:\s*([0-9]+\.[0-9]+\.[0-9]+)$', skill, re.MULTILINE)
    version = version_match.group(1) if version_match else ""
    checks.append(("version_current", bool(version) and f'SKILL_VERSION = "{version}"' in script))
    checks.append(("clawhub_slug_current", "clawhub:schoolfit-hk" not in public_text and "clawhub.ai/djanngau/schoolfit-hk" not in public_text))
    checks.append(("brand_current", "SchoolFit HK Skill" not in public_text and "Schoolfit Hk" not in public_text))
    checks.append(("no_legacy_install_path", "sh skill/bin/install.sh" not in public_text and "node skill/bin/schoolfit-skill.mjs" not in public_text))
    checks.append(("runtime_no_env_reads", "os.environ" not in script and "getenv" not in script))
    checks.append(("runtime_no_local_doc_reads", "with open" not in script and "README.md" not in script and "MARKETPLACE.md" not in script))
    checks.append(("no_packaged_maintenance_commands", "self-check" not in skill and "marketplace-demo" not in script))
    checks.append(("query_disclosure_present", "Query disclosure" in skill and "https://schoolfit.hk/api/..." in skill))

    ok = all(passed for _, passed in checks)
    for name, passed in checks:
        print(f"{'OK' if passed else 'FAIL'} {name}")
    print(f"version={version or 'unknown'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
