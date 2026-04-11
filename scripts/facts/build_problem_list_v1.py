from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(".").resolve()
SRC_ROOT = PROJECT_ROOT / "apps/cli/src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sympsense.problem_list import build_problem_list


def main() -> None:
    report = build_problem_list(project_root=PROJECT_ROOT, write_report=True)
    print(json.dumps({"ok": True, "version": report.get("version"), "summary": report.get("summary")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
