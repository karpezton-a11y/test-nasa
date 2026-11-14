"""Play the guided demos in a terminal against a running TrendTrace API.

    python scripts/run_demo.py http://127.0.0.1:8000            # all demos
    python scripts/run_demo.py http://127.0.0.1:8000 haze_rising  # one demo
    python scripts/run_demo.py http://127.0.0.1:8000 --pause 2    # slower, for screen recording

Each step prints its narration, the API call it makes and the key part of the answer
(plain-language summary, headline rows or suggestions), so the demo can be recorded or
shown live before the frontend exists.
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time

import httpx


def _wrap(text: str, indent: str = "    ") -> str:
    return textwrap.fill(text, width=100, initial_indent=indent, subsequent_indent=indent)


def _show(result: dict) -> None:
    if "plain_language" in result:
        print(_wrap(result["plain_language"]))
    if "summary" in result and "rows" in result:
        print(_wrap(result["summary"]))
        for row in result["rows"]:
            print(_wrap("- " + row["headline"], "      "))
        for c in result.get("opposite_directions", []):
            print(_wrap(f"! {c['variable']}: up in {', '.join(c['increasing_in'])}; down in {', '.join(c['decreasing_in'])}", "      "))
    if "suggestions" in result:
        for s in result["suggestions"][:4]:
            print(_wrap(f"- {s['name']} ({s['mission']}): " + " ".join(s["reasons"]), "      "))
    if "questions" in result:
        for q in result["questions"]:
            print(_wrap("? " + q["question"], "      "))


def play(base: str, only: str | None, pause: float, client: httpx.Client | None = None) -> int:
    client = client or httpx.Client(base_url=base, timeout=30)
    demos = client.get("/api/v1/demos").json()["result"]
    if only:
        demos = [d for d in demos if d["id"] == only]
        if not demos:
            print(f"No demo {only!r}", file=sys.stderr)
            return 2
    for demo in demos:
        print("=" * 100)
        print(f"{demo['title']}   [data: {demo['data']}]")
        print(_wrap("Question: " + demo["question"], ""))
        for n, step in enumerate(demo["steps"], 1):
            print(f"\n  Step {n}. {step['narration']}")
            if step["method"]:
                print(f"    -> {step['method']} {step['path']}" + (f" {json.dumps(step['body'])}" if step["body"] else ""))
                response = client.request(step["method"], step["path"], json=step["body"])
                body = response.json()
                if "error" in body:
                    print(_wrap(f"[{body['error']['code']}] {body['error']['message']}"))
                else:
                    result = body["result"]
                    if isinstance(result, dict) and "trend" in result and "plain_language" in result:
                        _show({"plain_language": result["plain_language"]})
                    elif isinstance(result, dict):
                        _show(result)
            print(_wrap("Look at: " + step["look_at"]))
            time.sleep(pause)
        print("\n" + _wrap("What to notice: " + demo["what_to_notice"], "  "))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("demo", nargs="?")
    parser.add_argument("--pause", type=float, default=0.0)
    args = parser.parse_args(argv)
    return play(args.base, args.demo, args.pause)


if __name__ == "__main__":
    sys.exit(main())
