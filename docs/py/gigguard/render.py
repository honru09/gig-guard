"""Plain-text report (English, Japanese, Chinese, or several at once)."""

from __future__ import annotations

from .analyze import Report
from .rules import RULE_ZH

ICON = {"high": "🔴", "medium": "🟡", "low": "🟢", "none": "🟢"}
CAT = {
    "en": {
        "off_platform_contact": "off-platform contact", "upfront_payment": "pay-to-work", "unpaid_trial": "unpaid test",
        "personal_documents": "ID / bank request", "too_good_to_be_true": "too good to be true", "crypto_investment": "investment / crypto",
        "ai_banned": "AI banned", "rushed_pressure": "pressure", "illegal_or_mule": "illegal / mule",
        "vague_scope": "vague scope", "low_pay": "low pay", "other": "other",
    },
    "ja": {
        "off_platform_contact": "外部連絡への誘導", "upfront_payment": "先払いの要求", "unpaid_trial": "無償テスト",
        "personal_documents": "個人情報の要求", "too_good_to_be_true": "楽すぎる高収入", "crypto_investment": "投資・仮想通貨",
        "ai_banned": "AI禁止", "rushed_pressure": "急かし", "illegal_or_mule": "違法・名義貸しの疑い",
        "vague_scope": "作業内容が曖昧", "low_pay": "低すぎる報酬", "other": "その他",
    },
    "zh": {
        "off_platform_contact": "引到平台外", "upfront_payment": "先付钱", "unpaid_trial": "无偿测试",
        "personal_documents": "索要证件信息", "too_good_to_be_true": "高收入诱饵", "crypto_investment": "投资 / 虚拟币",
        "ai_banned": "禁止 AI", "rushed_pressure": "催促", "illegal_or_mule": "违法 / 代收转运",
        "vague_scope": "工作内容模糊", "low_pay": "报酬过低", "other": "其他",
    },
}
VERDICT_ZH = {"high": "建议不要接单或回复", "medium": "先确认条件", "low": "没大问题（核对条件即可）", "none": "没大问题（核对条件即可）"}
T = {
    "en": {"rules": "Rule hits", "pay": "Pay", "rate": "stated rate", "total": "pay", "after": "after {fee} fee",
           "hours": "hours", "eff": "effective hourly", "floor": "floor", "below": "below your floor",
           "gemma": "on this machine", "only": "Gemma only", "dropped": "dropped, quote not in post",
           "ask": "Ask the client:", "overruled": "Gemma said risk={r}; the rule hit wins",
           "reply": "Reply to send on-platform", "tpl": "template", "nomodel": "model unavailable ({e}); rules and pay math only"},
    "ja": {"rules": "ルールで検出", "pay": "お金と時間", "rate": "提示時給", "total": "報酬", "after": "手数料{fee}引き後",
           "hours": "作業時間", "eff": "実質時給", "floor": "下限", "below": "下限割れ",
           "gemma": "ローカル実行", "only": "Gemma のみ検出", "dropped": "引用が本文にないため破棄",
           "ask": "確認したいこと:", "overruled": "Gemma の判定は risk={r}。ルール検出を優先",
           "reply": "サイト内で送る返信案", "tpl": "定型文", "nomodel": "モデル利用不可（{e}）。ルール判定のみ"},
    "zh": {"rules": "规则检出", "pay": "报酬与时间", "rate": "标明时薪", "total": "报酬", "after": "扣除{fee}手续费后",
           "hours": "工时", "eff": "实际时薪", "floor": "底线", "below": "低于底线",
           "gemma": "本机运行", "only": "仅 Gemma 发现", "dropped": "已丢弃：引用不在原文中",
           "ask": "建议向客户确认：", "overruled": "Gemma 判断 risk={r}，以规则检出为准",
           "reply": "建议在平台内回复", "tpl": "模板", "nomodel": "模型不可用（{e}），仅规则与报酬计算"},
}
NOTE = {  # pay-estimate notes, by prefix of the stored text
    "報酬額が読み取れ": {"en": "couldn't read the pay", "ja": "報酬額が読み取れませんでした", "zh": "没读出报酬金额"},
    "作業時間が読み取れ": {"en": "hours not stated (can't compute the effective hourly rate)",
                     "ja": "作業時間が読み取れませんでした（実質時給は計算できません）", "zh": "没写工时（无法计算实际时薪）"},
    "hours not stated": {"en": "hours not stated (can't compute the effective hourly rate)",
                         "ja": "作業時間が読み取れませんでした（実質時給は計算できません）", "zh": "没写工时（无法计算实际时薪）"},
}


def _note(n: str, ls) -> str:
    for k, v in NOTE.items():
        if n.startswith(k):
            return " / ".join(v[l] for l in ls)
    return n


LANGS = {"en": ["en"], "ja": ["ja"], "zh": ["zh"], "both": ["en", "ja"], "all": ["en", "ja", "zh"]}

_CUR = {"JPY": ("¥", 0), "USD": ("$", 2), "CNY": ("¥", 2)}


def _money(v, cur) -> str:
    sym, dp = _CUR.get(cur, ("", 2))
    if v is None:
        return "?"
    return f"{sym}{v:,.{dp}f}" + (" CNY" if cur == "CNY" else "")


def text_report(rep: Report, lang: str = "all") -> str:
    """lang: en, ja, zh, both (= en + ja), all (= en + ja + zh)."""
    ls = LANGS.get(lang, LANGS["all"])

    def t(key, **kw):
        return " / ".join(T[l][key].format(**kw) for l in ls)

    def verdict():
        v = {"en": rep.verdict_en, "ja": rep.verdict_ja, "zh": VERDICT_ZH[rep.risk]}
        return " / ".join(v[l] for l in ls)

    cur = rep.pay.currency
    label = "OK" if rep.risk == "none" else rep.risk.upper()
    out = [f"{ICON[rep.risk]} {label}  {verdict()}", ""]
    if rep.hits:
        out.append(f"■ {t('rules')}")
        for h in rep.hits:
            titles = {"en": h.title_en, "ja": h.title_ja, "zh": RULE_ZH.get(h.rule_id, (h.title_en, ""))[0]}
            advice = {"en": h.advice_en, "ja": h.advice_ja, "zh": RULE_ZH.get(h.rule_id, ("", h.advice_en))[1]}
            out.append(f"  [{h.severity}] " + " / ".join(titles[l] for l in ls))
            for ev in h.evidence:
                out.append(f"      「{ev}」")
            for l in ls:
                if advice[l]:
                    out.append(f"      → {advice[l]}")
        out.append("")
    p = rep.pay
    out.append(f"■ {t('pay')}")
    if p.hourly_yen is not None:
        out.append(f"  {t('rate')}: {_money(p.hourly_yen, cur)}")
    out.append(f"  {t('total')}: {_money(p.total_yen, cur)}  ({t('after', fee=f'{p.fee_rate:.1%}')}: {_money(p.net_total_yen, cur)})")
    out.append(f"  {t('hours')}: {'?' if p.hours is None else f'{p.hours:g}'}")
    if p.effective_hourly_yen is not None:
        flag = f"  ⚠ {t('below')}" if rep.below_floor else ""
        out.append(f"  {t('eff')}: {_money(p.effective_hourly_yen, cur)}  ({t('floor')} {_money(rep.min_hourly_yen, cur)}){flag}")
    for n in p.notes:
        out.append(f"  ・{_note(n, ls)}")
    out.append("")
    if rep.model:
        m = rep.model
        out.append(f"■ Gemma ({rep.model_name}, {rep.model_seconds}s, {t('gemma')})")
        for l in ls:
            if m.get(f"summary_{l}"):
                out.append(f"  {m[f'summary_{l}']}")
        rule_ids = {h.rule_id for h in rep.hits}
        for f in rep.findings:
            tag = "" if f["category"] in rule_ids else f"  ★ {t('only')}"
            cat = " / ".join(CAT[l].get(f["category"], f["category"]) for l in ls)
            out.append(f"  ✓ [{f['severity']}] {cat} 「{f['quote']}」{tag}")
            for l in ls:
                if f.get(f"why_{l}"):
                    out.append(f"      {f[f'why_{l}']}")
        for f in rep.rejected_findings:
            out.append(f"  ✗ {t('dropped')}: 「{f['quote']}」")
        if m.get("questions_ja"):
            out.append(f"  {t('ask')}")
            for q in m["questions_ja"]:
                out.append(f"   - {q}")
        if rep.model_overruled:
            out.append(f"  ※ {t('overruled', r=m.get('risk'))}")
        out.append("")
    elif rep.model_error:
        out.append(f"■ {t('nomodel', e=rep.model_error)}")
        out.append("")
    if rep.reply_ja:
        src = "Gemma" if rep.reply_source == "model" else t("tpl")
        out.append(f"■ {t('reply')} ({src})")
        out.append("  " + rep.reply_ja.replace("\n", "\n  "))
        out.append("")
    for n in rep.notes:
        out.append(f"※ {n}")
    return "\n".join(out).rstrip() + "\n"
