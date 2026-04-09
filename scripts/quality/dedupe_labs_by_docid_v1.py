from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


LABS_DIR = Path("data/canonical/labs")
ARCHIVE_DIR = LABS_DIR / "_orphaned_dedupe_2026-04-09"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    grouped: dict[str, list[Path]] = {}
    for p in sorted(LABS_DIR.glob("*.json")):
        try:
            j = load_json(p)
        except Exception:
            continue
        doc_id = str(j.get("doc_id") or "").strip()
        if not doc_id:
            continue
        grouped.setdefault(doc_id, []).append(p)

    moved: list[dict[str, str]] = []
    for doc_id, files in grouped.items():
        if len(files) <= 1:
            continue
        preferred_name = f"lab_full_doc_{doc_id.replace('doc_', '')}.json"
        preferred = next((p for p in files if p.name == preferred_name), files[0])
        for p in files:
            if p == preferred:
                continue
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            dst = ARCHIVE_DIR / p.name
            shutil.move(str(p), str(dst))
            moved.append(
                {
                    "doc_id": doc_id,
                    "kept": str(preferred).replace("\\", "/"),
                    "moved": str(dst).replace("\\", "/"),
                }
            )

    print(json.dumps({"deduped_docs": len({x["doc_id"] for x in moved}), "moved_files": len(moved), "moves": moved}, ensure_ascii=False))


if __name__ == "__main__":
    main()
