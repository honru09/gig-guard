"""Small, honest eval: rules alone vs rules + each Gemma model on eval/fixtures.jsonl.

    python eval/run_eval.py --models gemma3:1b gemma3:4b gemma4:e2b gemma4:e4b

20 hand-written posts (14 risky, 6 safe, several written so that the regex rules
miss them). Rules were written before this set and were NOT tuned on it.
Writes eval/results.json and eval/results.md.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gigguard.analyze import analyze  # noqa: E402
from gigguard.llm import OllamaModel  # noqa: E402
from gigguard.rules import SEVERITY_ORDER  # noqa: E402

FLAG = SEVERITY_ORDER["medium"]


def load():
    with open(ROOT / "eval" / "fixtures.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run(cases, model, label):
    rows = []
    for c in cases:
        rep = analyze(c["text"], model=model)
        rule_flag = max([SEVERITY_ORDER[h.severity] for h in rep.hits] + [0]) >= FLAG or bool(rep.below_floor)
        found = {h.rule_id for h in rep.hits} | {f["category"] for f in rep.findings}
        rows.append({
            "id": c["id"], "label": c["label"], "risk": rep.risk,
            "flagged": SEVERITY_ORDER[rep.risk] >= FLAG, "rule_flagged": rule_flag,
            "expected": c["categories"], "found": sorted(found),
            "verified": len(rep.findings), "rejected": len(rep.rejected_findings),
            "rejected_quotes": [f["quote"] for f in rep.rejected_findings],
            "json_ok": rep.model is not None, "error": rep.model_error, "seconds": rep.model_seconds,
            "summary_en": (rep.model or {}).get("summary_en"),
        })
        print(f"  {label:12} {c['id']} {rep.risk:6} {rep.model_seconds}s verified={len(rep.findings)} rejected={len(rep.rejected_findings)}", flush=True)
    return rows


def summarize(label, rows, with_model):
    risky = [r for r in rows if r["label"] == "risky"]
    safe = [r for r in rows if r["label"] == "safe"]
    exp = [(r, c) for r in risky for c in r["expected"]]
    s = {
        "config": label,
        "risky_caught": sum(r["flagged"] for r in risky), "risky_total": len(risky),
        "safe_false_flags": sum(r["flagged"] for r in safe), "safe_total": len(safe),
        "category_hits": sum(c in r["found"] for r, c in exp), "category_total": len(exp),
        "model_only_catches": sum(r["flagged"] and not r["rule_flagged"] for r in risky),
    }
    if with_model:
        ver = sum(r["verified"] for r in rows)
        rej = sum(r["rejected"] for r in rows)
        secs = [r["seconds"] for r in rows if r["seconds"] is not None]
        s.update({
            "json_ok": sum(r["json_ok"] for r in rows), "n": len(rows),
            "findings_verified": ver, "findings_rejected": rej,
            "median_seconds": round(statistics.median(secs), 1) if secs else None,
        })
    return s


def to_md(summaries):
    out = [
        "| Config | Risky posts flagged | Safe posts false-flagged | Expected categories found | Caught only thanks to Gemma | Valid JSON | Findings with quote verified / rejected | Median s/post (CPU) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries:
        out.append(
            f"| {s['config']} | {s['risky_caught']}/{s['risky_total']} | {s['safe_false_flags']}/{s['safe_total']} | "
            f"{s['category_hits']}/{s['category_total']} | {s['model_only_catches']} | "
            + (f"{s['json_ok']}/{s['n']} | {s['findings_verified']} / {s['findings_rejected']} | {s['median_seconds']} |"
               if "json_ok" in s else "– | – | – |")
        )
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=[])
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--merge", action="store_true", help="keep other configs from an earlier results.json")
    a = ap.parse_args()
    cases = load()
    results = {}
    prev = ROOT / "eval" / "results.json"
    if a.merge and prev.exists():
        results = json.loads(prev.read_text(encoding="utf-8"))["rows"]
    results["rules only"] = run(cases, None, "rules")
    for m in a.models:
        results[f"rules + {m}"] = run(cases, OllamaModel(m, a.host), m)
    order = ["rules only"] + sorted(k for k in results if k != "rules only")
    results = {k: results[k] for k in order}
    summaries = [summarize(k, v, k != "rules only") for k, v in results.items()]
    (ROOT / "eval" / "results.json").write_text(
        json.dumps({"summaries": summaries, "rows": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "eval" / "results.md").write_text(to_md(summaries), encoding="utf-8")
    print(to_md(summaries))


if __name__ == "__main__":
    main()
