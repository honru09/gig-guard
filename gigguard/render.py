"""Plain-text report for the terminal (Japanese, English, or both)."""

from __future__ import annotations

from .analyze import Report

ICON = {"high": "🔴", "medium": "🟡", "low": "🟢", "none": "🟢"}
CAT_JA = {
    "off_platform_contact": "外部連絡への誘導", "upfront_payment": "先払いの要求", "unpaid_trial": "無償テスト",
    "personal_documents": "個人情報の要求", "too_good_to_be_true": "楽すぎる高収入", "crypto_investment": "投資・仮想通貨",
    "ai_banned": "AI禁止", "rushed_pressure": "急かし", "illegal_or_mule": "違法・名義貸しの疑い",
    "vague_scope": "作業内容が曖昧", "low_pay": "低すぎる報酬", "other": "その他",
}


def _yen(v) -> str:
    return "?" if v is None else f"{v:,.0f}円"


def text_report(rep: Report, lang: str = "both") -> str:
    ja = lang in ("ja", "both")
    en = lang in ("en", "both")
    label = "OK" if rep.risk == "none" else rep.risk.upper()
    head = f"{ICON[rep.risk]} {label}  "
    head += " / ".join(x for x in ((rep.verdict_ja if ja else ""), (rep.verdict_en if en else "")) if x)
    out = [head, ""]
    if rep.hits:
        out.append("■ ルールで検出 / Rule hits")
        for h in rep.hits:
            title = " / ".join(x for x in ((h.title_ja if ja else ""), (h.title_en if en else "")) if x)
            out.append(f"  [{h.severity}] {title}")
            for ev in h.evidence:
                out.append(f"      「{ev}」")
            if ja:
                out.append(f"      → {h.advice_ja}")
            if en and h.advice_en:
                out.append(f"      → {h.advice_en}")
        out.append("")
    p = rep.pay
    out.append("■ お金と時間 / Pay")
    if p.hourly_yen is not None:
        out.append(f"  提示時給: {_yen(p.hourly_yen)}")
    out.append(f"  報酬: {_yen(p.total_yen)}（手数料{p.fee_rate:.0%}引き後 {_yen(p.net_total_yen)}）")
    out.append(f"  作業時間: {'?' if p.hours is None else f'{p.hours:g}時間'}")
    if p.effective_hourly_yen is not None:
        flag = "  ⚠ 下限割れ / below your floor" if rep.below_floor else ""
        out.append(f"  実質時給 / effective hourly: {_yen(p.effective_hourly_yen)}（下限 {rep.min_hourly_yen:,}円）{flag}")
    for n in p.notes:
        out.append(f"  ・{n}")
    out.append("")
    if rep.model:
        m = rep.model
        out.append(f"■ Gemma ({rep.model_name}, {rep.model_seconds}s, ローカル実行 / on this machine)")
        if ja and m.get("summary_ja"):
            out.append(f"  {m['summary_ja']}")
        if en and m.get("summary_en"):
            out.append(f"  {m['summary_en']}")
        rule_ids = {h.rule_id for h in rep.hits}
        for f in rep.findings:
            tag = "" if f["category"] in rule_ids else "  ★ Gemma only"
            out.append(f"  ✓ [{f['severity']}] {CAT_JA.get(f['category'], f['category'])} 「{f['quote']}」{tag}")
            if ja and f.get("why_ja"):
                out.append(f"      {f['why_ja']}")
            if en and f.get("why_en"):
                out.append(f"      {f['why_en']}")
        for f in rep.rejected_findings:
            out.append(f"  ✗ 引用が本文にないため破棄 / quote not in post: 「{f['quote']}」")
        if ja and m.get("questions_ja"):
            out.append("  確認したいこと:")
            for q in m["questions_ja"]:
                out.append(f"   - {q}")
        if rep.model_overruled:
            out.append(f"  ※ Gemma said risk={m.get('risk')}; the rule hit wins / ルール検出を優先")
        out.append("")
    elif rep.model_error:
        out.append(f"■ モデル: 利用できませんでした（{rep.model_error}）。ルール判定のみです。")
        out.append("")
    if rep.reply_ja:
        src = "Gemma" if rep.reply_source == "model" else "定型文 / template"
        out.append(f"■ サイト内で送る返信案 / reply to send on-platform（{src}）")
        out.append("  " + rep.reply_ja.replace("\n", "\n  "))
        out.append("")
    for n in rep.notes:
        out.append(f"※ {n}")
    return "\n".join(out).rstrip() + "\n"
