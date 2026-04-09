from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.quality.process_round9_batch_v1 as round9


def main() -> None:
    round9.ROUND = 10
    round9.ROUND_FILES = [
        "report-15644-2836699.pdf",
        "report-15644-2847411.pdf",
        "report-15644-3618865.pdf",
        "report-15644-3931674.pdf",
        "report-15644-4254892.pdf",
        "Консультация физиотерапевта (1).pdf",
    ]
    round9.main()


if __name__ == "__main__":
    main()
