from __future__ import annotations

import argparse
import json
import sys

from ashare_worker.report import generate_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an A-share stock research report as JSON.")
    parser.add_argument("--code", required=True, help="6 digit A-share stock code")
    args = parser.parse_args()

    try:
        report = generate_report(args.code)
    except Exception as exc:  # noqa: BLE001 - CLI should return a clean error envelope.
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
