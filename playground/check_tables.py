"""
Did the markdown table serialiser help, and did it split any table away from its header?
Compares the chunks against a saved copy of the previous run.

    uv run --project backend python playground/check_tables.py <before-dir>
"""

import json
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO_ROOT = Path(__file__).resolve().parents[1]

NEEDLE = "quasi-trailer"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def table_rows(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.count("|") >= 2)


def orphaned(text: str) -> bool:
    """Table rows with no header separator above them — a split that lost its columns."""
    return table_rows(text) > 2 and "|--" not in text.replace(" ", "")


def describe(name: str, rows: list[dict]) -> None:
    sizes = sorted(len(r["text"]) for r in rows)
    tabular = [r for r in rows if table_rows(r["text"]) > 2]
    lost = [r for r in rows if orphaned(r["text"])]
    print(
        f"  {name:9} {len(rows):4} chunks  median {sizes[len(sizes) // 2]:5} ch  "
        f"max {sizes[-1]:6} ch  mean {int(statistics.mean(sizes)):5}  "
        f"{len(tabular):3} tabular  {len(lost):2} header-less"
    )
    for row in lost[:3]:
        print(f"      header-less: p{row['pages_pdf'][:2]} {row['heading_path'][:50]}")


def main() -> None:
    before_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    after_dir = REPO_ROOT / "data" / "chunks"

    for path in sorted(after_dir.glob("*.jsonl")):
        print(f"\n{path.stem}")
        if before_dir and (old := before_dir / path.name).exists():
            describe("before", load(old))
        describe("after", load(path))

    for path in sorted(after_dir.glob("*.jsonl")):
        for row in load(path):
            if NEEDLE in row["text"]:
                index = row["text"].find(NEEDLE)
                print(f"\n{NEEDLE} in {path.stem}, chunk {len(row['text'])} ch:")
                print("  " + row["text"][max(0, index - 260) : index + 120].replace("\n", "\n  "))
                return


if __name__ == "__main__":
    main()
