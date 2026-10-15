"""Plain-text report for the terminal."""

from __future__ import annotations

from .analyze import Report

ICON = {"high": "🔴", "medium": "🟡", "low": "🟢", "none": "🟢"}


def _yen(v) -> str:
    return "?" if v is None else f"{v:,.0f}円"


def text_report(rep: Report) -> str:
    label = "OK" if rep.risk == "none" else rep.risk.upper()
    out = [f"{ICON[rep.risk]} {label}  {rep.verdict_ja}", ""]
    if rep.hits:
        out.append("■ ルールで検出した項目")
        for h in rep.hits:
            out.append(f"  [{h.severity}] {h.title_ja}")
            for ev in h.evidence:
                out.append(f"      「{ev}」")
            out.append(f"      → {h.advice_ja}")
        out.append("")
    p = rep.pay
    out.append("■ お金と時間")
    if p.hourly_yen is not None:
        out.append(f"  提示時給: {_yen(p.hourly_yen)}")
    out.append(f"  報酬: {_yen(p.total_yen)}（手数料{p.fee_rate:.0%}引き後 {_yen(p.net_total_yen)}）")
    out.append(f"  作業時間: {'?' if p.hours is None else f'{p.hours:g}時間'}")
    if p.effective_hourly_yen is not None:
        flag = "  ⚠ 下限割れ" if rep.below_floor else ""
        out.append(f"  実質時給: {_yen(p.effective_hourly_yen)}（下限 {rep.min_hourly_yen:,}円）{flag}")
    for n in p.notes:
        out.append(f"  ・{n}")
    out.append("")
    if rep.model:
        m = rep.model
        out.append(f"■ {rep.model_name} の読み（{rep.model_seconds}s, ローカル実行）")
        if m.get("summary_ja"):
            out.append(f"  {m['summary_ja']}")
        for c in m.get("concerns_ja", []):
            out.append(f"  ・{c}")
        if m.get("questions_ja"):
            out.append("  確認したいこと:")
            for q in m["questions_ja"]:
                out.append(f"   - {q}")
        if rep.model_overruled:
            out.append(f"  ※ モデルは risk={m.get('risk')} と判断しましたが、ルール検出を優先しました")
        out.append("")
    elif rep.model_error:
        out.append(f"■ モデル: 利用できませんでした（{rep.model_error}）。ルール判定のみです。")
        out.append("")
    if rep.reply_ja:
        src = "モデル作成" if rep.reply_source == "model" else "定型文"
        out.append(f"■ サイト内で送る返信案（{src}）")
        out.append("  " + rep.reply_ja.replace("\n", "\n  "))
        out.append("")
    for n in rep.notes:
        out.append(f"※ {n}")
    return "\n".join(out).rstrip() + "\n"
