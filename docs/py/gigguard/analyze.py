"""Combine the rule layer, the pay estimate and Gemma's grounded findings.

Safety contract:
- Rule hits are facts in the text. The model can never lower them.
- The model can raise the risk only through a finding whose quote really
  appears in the post. Unverifiable findings are dropped and counted.
- Once anything at medium+ fires, the reply is a fixed, reviewed template.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

from . import llm as llm_mod
from .pay import PayEstimate, estimate
from .rules import Hit, SEVERITY_ORDER, max_severity, normalize, scan

VERDICT_JA = {
    "high": "応募・返信は見送り推奨",
    "medium": "条件を確認してから",
    "low": "大きな問題なし（条件だけ確認）",
    "none": "大きな問題なし（条件だけ確認）",
}
VERDICT_EN = {
    "high": "Don't apply or reply",
    "medium": "Check the terms first",
    "low": "Looks fine (just check the terms)",
    "none": "Looks fine (just check the terms)",
}

SAFE_DECLINE_JA = (
    "ご連絡ありがとうございます。恐れ入りますが、規約に沿ってやり取りはすべて"
    "こちらのメッセージ機能で進めさせていただけますでしょうか。"
    "案件の詳細や条件もこちらでご共有いただけましたら、検討のうえお返事いたします。"
)
UNPAID_TRIAL_JA = (
    "ご連絡ありがとうございます。テストの件、承知いたしました。"
    "大変恐縮ですが、本番と同等の作業量となる場合は、少額でも有償のテスト契約として"
    "お願いできますでしょうか。ご検討いただけますと幸いです。"
)
GENERIC_CAUTION_JA = (
    "ご連絡ありがとうございます。お引き受けする前に、作業内容・報酬・お支払い方法について、"
    "こちらのメッセージ機能で詳しく確認させていただけますでしょうか。よろしくお願いいたします。"
)

_HARD_CATEGORIES = {"off_platform_contact", "personal_documents", "upfront_payment", "crypto_investment", "illegal_or_mule"}
_STRIP = re.compile(r"[\s「」『』\"'“”‘’…・。、,.!！?？()（）\[\]【】]")


def _squash(s: str) -> str:
    return _STRIP.sub("", normalize(s)).lower()


def quote_in_text(quote: str, text: str) -> bool:
    """True if the quote really appears in the text.

    Comparison ignores whitespace, brackets and punctuation and applies NFKC, so
    full-width/half-width and line breaks don't matter. A trailing or leading
    "..." in the quote is allowed. Anything shorter than 2 characters is rejected:
    a one-character quote proves nothing.
    """
    q = _squash(quote)
    if len(q) < 2:
        return False
    return q in _squash(text)


@dataclass
class Report:
    risk: str
    verdict_ja: str
    verdict_en: str
    hits: list[Hit]
    pay: PayEstimate
    below_floor: Optional[bool]
    min_hourly_yen: int
    model: Optional[dict] = None
    model_name: Optional[str] = None
    model_seconds: Optional[float] = None
    model_error: Optional[str] = None
    model_overruled: bool = False
    findings: list[dict] = field(default_factory=list)  # verified model findings
    rejected_findings: list[dict] = field(default_factory=list)  # quotes not in the post
    reply_ja: Optional[str] = None
    reply_source: str = "template"
    notes: list[str] = field(default_factory=list)

    @property
    def model_only_findings(self) -> list[dict]:
        rule_ids = {h.rule_id for h in self.hits}
        return [f for f in self.findings if f["category"] not in rule_ids]

    def to_dict(self) -> dict:
        return {
            "risk": self.risk,
            "verdict_ja": self.verdict_ja,
            "verdict_en": self.verdict_en,
            "hits": [h.to_dict() for h in self.hits],
            "pay": self.pay.to_dict(),
            "below_floor": self.below_floor,
            "min_hourly_yen": self.min_hourly_yen,
            "model": self.model,
            "model_name": self.model_name,
            "model_seconds": self.model_seconds,
            "model_error": self.model_error,
            "model_overruled": self.model_overruled,
            "findings": self.findings,
            "model_only_findings": self.model_only_findings,
            "rejected_findings": self.rejected_findings,
            "reply_ja": self.reply_ja,
            "reply_source": self.reply_source,
            "notes": self.notes,
        }


_REPLY_BLOCKLIST = re.compile(
    r"(https?://|lin\.ee|line\.me|t\.me/|\bLINE\b|(?<![ァ-ヶー])ライン|友だち追加|友達追加|"
    r"telegram|テレグラム|whatsapp|discord|ディスコード|chatwork|チャットワーク|instagram|インスタ|"
    r"メールアドレス|電話番号|@gmail|口座番号|マイナンバー)",
    re.IGNORECASE,
)


def _reply_is_safe(reply: str) -> bool:
    """Only hand over a model-written reply that cannot move the user off-platform."""
    t = normalize(reply)
    if _REPLY_BLOCKLIST.search(t):
        return False
    return not any(h.severity == "high" for h in scan(t))


def ground_findings(text: str, findings: list[dict]) -> tuple[list[dict], list[dict]]:
    verified, rejected = [], []
    for f in findings:
        (verified if quote_in_text(f["quote"], text) else rejected).append(f)
    return verified, rejected


def analyze(
    text: str,
    model: Optional[llm_mod.ChatModel] = None,
    fee_rate: float = 0.20,
    min_hourly_yen: int = 1200,
) -> Report:
    hits = scan(text)
    pay = estimate(text, fee_rate=fee_rate)
    rule_risk = max_severity(h.severity for h in hits)

    below_floor = None
    if pay.effective_hourly_yen is not None:
        below_floor = pay.effective_hourly_yen < min_hourly_yen

    rep = Report(
        risk=rule_risk, verdict_ja="", verdict_en="", hits=hits, pay=pay,
        below_floor=below_floor, min_hourly_yen=min_hourly_yen,
    )

    if model is not None:
        rep.model_name = getattr(model, "name", None)
        t0 = time.monotonic()
        try:
            raw = model.chat(llm_mod.SYSTEM_PROMPT, llm_mod.build_user_prompt(text))
            rep.model = llm_mod.parse_model_json(raw)
            if rep.model is None:
                rep.model_error = "model reply was not usable JSON"
        except Exception as e:  # network, timeout, model missing: the rules still stand
            rep.model_error = f"{type(e).__name__}: {e}"
        rep.model_seconds = round(time.monotonic() - t0, 1)

    risk = rule_risk
    if rep.model:
        rep.findings, rep.rejected_findings = ground_findings(text, rep.model.get("findings", []))
        if rep.rejected_findings:
            rep.notes.append(
                f"Gemma の指摘のうち {len(rep.rejected_findings)} 件は本文に引用が見つからないため破棄しました"
            )
        grounded = max_severity(f["severity"] for f in rep.findings)
        if SEVERITY_ORDER[grounded] > SEVERITY_ORDER[risk]:
            risk = grounded  # the model may raise the alarm, with evidence
        m = rep.model.get("risk")
        if m and SEVERITY_ORDER[m] < SEVERITY_ORDER[rule_risk]:
            rep.model_overruled = True  # ...but never talk a rule hit down
    if below_floor and SEVERITY_ORDER[risk] < SEVERITY_ORDER["medium"]:
        risk = "medium"
        rep.notes.append(f"実質時給が下限 {min_hourly_yen}円 を下回っています")
    rep.risk = risk
    rep.verdict_ja = VERDICT_JA[risk]
    rep.verdict_en = VERDICT_EN[risk]

    ids = {h.rule_id for h in hits}
    cats = {f["category"] for f in rep.findings if SEVERITY_ORDER[f["severity"]] >= SEVERITY_ORDER["medium"]}
    flagged = SEVERITY_ORDER[risk] >= SEVERITY_ORDER["medium"]
    model_reply = (rep.model or {}).get("reply_ja")
    # Once anything fires, the reply is a fixed, reviewed template. Small models
    # tend to be polite to a fault ("the unpaid trial is fine, thank you!").
    if (ids | cats) & _HARD_CATEGORIES:
        rep.reply_ja = SAFE_DECLINE_JA
    elif "unpaid_trial" in ids | cats:
        rep.reply_ja = UNPAID_TRIAL_JA
    elif flagged:
        rep.reply_ja = GENERIC_CAUTION_JA
    elif model_reply and _reply_is_safe(model_reply):
        rep.reply_ja, rep.reply_source = model_reply, "model"
    elif model_reply:
        rep.notes.append("モデルの返信案に外部ツール名・URL等が含まれていたため、表示しませんでした")
    return rep
