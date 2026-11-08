"""One-off probe: fetch a few queries once and save the raw answers.

Purpose: see the real field names of a query.

    python probe.py            # only checks credits (free)
    python probe.py --run      # runs the queries below (1 credit each)

Raw answers go to samples/. They contain your game data but NOT your API key.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from rgtool.api import QUERIES, APIError, ResourcesAPI

# Queries the monitor will need: warehouse, mine summary, market, missions, player
PROBE = [2, 51, 1006, 10, 7]
LOG_QUERIES = {6, 9, 11}  # logs: fetch the max 30 days


def describe(data, indent=0, max_items=3) -> list[str]:
    """Short structural description of a JSON value (keys + example values)."""
    pad = "  " * indent
    out = []
    if isinstance(data, dict):
        for k, v in list(data.items())[:40]:
            if isinstance(v, (dict, list)):
                out.append(f"{pad}{k}: {type(v).__name__}")
                out += describe(v, indent + 1, max_items)
            else:
                out.append(f"{pad}{k}: {v!r}")
    elif isinstance(data, list):
        out.append(f"{pad}[{len(data)} items]")
        for item in data[:max_items]:
            out += describe(item, indent + 1, max_items)
    else:
        out.append(f"{pad}{data!r}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help=f"run {len(PROBE)} paid queries")
    ap.add_argument("--q", type=int, nargs="+", help="run only these query IDs, e.g. --q 1")
    ap.add_argument("--all", action="store_true", help="run every query once (22 credits)")
    args = ap.parse_args()
    probe = args.q or PROBE
    if args.all:
        probe = [q for q in QUERIES if q != 0]
    if args.q or args.all:
        args.run = True

    load_dotenv()
    try:
        api = ResourcesAPI(os.getenv("RG_API_KEY", ""), lang=os.getenv("RG_LANG", "en"))
        print("Credits:", api.credits())
    except APIError as e:
        sys.exit(f"Error: {e}")

    if not args.run:
        print(f"\nAdd --run to fetch {PROBE} (costs {len(PROBE)} credits), or --q 1 for one query.")
        return

    samples = Path("samples")
    samples.mkdir(exist_ok=True)
    report = []
    for q in probe:
        name = QUERIES[q]
        try:
            data = api.query(q, days=30 if q in LOG_QUERIES else None)
        except APIError as e:
            report.append(f"\n=== q={q} {name}: ERROR {e}")
            continue
        (samples / f"{q}_{name}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        report.append(f"\n=== q={q} {name} ===")
        report += describe(data)

    text = "\n".join(report)
    if args.all:
        name = "structure_all.txt"
    elif args.q:
        name = f"structure_{'_'.join(map(str, probe))}.txt"
    else:
        name = "structure.txt"
    (samples / name).write_text(text, encoding="utf-8")
    print(text)
    print("\nCredits left:", api.credits())
    print(f"Saved to samples/{name} (samples/ is git-ignored: it contains your game data).")


if __name__ == "__main__":
    main()
