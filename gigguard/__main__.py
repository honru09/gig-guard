"""CLI: gig-guard check [FILE|-] / gig-guard serve"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .analyze import analyze
from .llm import DEFAULT_HOST, DEFAULT_MODEL, OllamaModel
from .render import text_report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="gig-guard", description="Check a freelance job post before you reply. Runs locally.")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default {DEFAULT_MODEL})")
    ap.add_argument("--host", default=DEFAULT_HOST, help="Ollama host")
    ap.add_argument("--no-llm", action="store_true", help="rules + pay math only")
    ap.add_argument("--fee", type=float, default=0.20, help="platform fee taken from you (default 0.20)")
    ap.add_argument("--min-hourly", type=int, default=1200, help="your hourly floor in yen (default 1200)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check a post from a file or stdin")
    c.add_argument("file", nargs="?", default="-")
    c.add_argument("--json", action="store_true", help="machine-readable output")
    s = sub.add_parser("serve", help="local web UI on 127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)

    def factory():
        if a.no_llm:
            return None
        return OllamaModel(a.model, a.host)

    if a.cmd == "serve":
        from .web import serve
        serve(a.port, factory, a.fee, a.min_hourly)
        return 0

    text = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8").read()
    if not text.strip():
        print("empty input", file=sys.stderr)
        return 2
    model = factory()
    if model is not None and not model.available():
        print(f"(Ollama に {a.model} が見つからないため、ルール判定のみで続行します)", file=sys.stderr)
        model = None
    rep = analyze(text, model=model, fee_rate=a.fee, min_hourly_yen=a.min_hourly)
    if a.json:
        print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(text_report(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
