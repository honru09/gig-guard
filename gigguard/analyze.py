"""Combine the rule layer, the pay estimate and the model read into one verdict."""

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


@dataclass
class Report:
    risk: str
    verdict_ja: str
    hits: list[Hit]
    pay: PayEstimate
    below_floor: Optional[bool]
    min_hourly_yen: int
    model: Optional[dict] = None
    model_name: Optional[str] = None
    model_seconds: Optional[float] = None
    model_error: Optional[str] = None
    model_overruled: bool = False
    reply_ja: Optional[str] = None
    reply_source: str = "template"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "risk": self.risk,
            "verdict_ja": self.verdict_ja,
            "hits": [h.to_dict() for h in self.hits],
            "pay": self.pay.to_dict(),
            "below_floor": self.below_floor,
            "min_hourly_yen": self.min_hourly_yen,
            "model": self.model,
            "model_name": self.model_name,
            "model_seconds": self.model_seconds,
            "model_error": self.model_error,
            "model_overruled": self.model_overruled,
            "reply_ja": self.reply_ja,
            "reply_source": self.reply_source,
            "notes": self.notes,
        }


_REPLY_BLOCKLIST = re.compile(
    r"(https?://|lin\.ee|line\.me|t\.me/|\bLINE\b|(?<![ァ-ヶー])ライン|友だち追加|友達追加|"
    r"telegram|テレグラム|whatsapp|discord|ディスコード|chatwork|チャットワーク|"
    r"メールアドレス|電話番号|@gmail|口座番号|マイナンバー)",
    re.IGNORECASE,
)


def _reply_is_safe(reply: str) -> bool:
    """Only hand over a model-written reply that cannot move the user off-platform.

    Small models sometimes write "I'll add you on LINE, but let's talk here" in the
    same breath, so any mention of an outside tool, a URL or personal data drops
    the model reply in favour of a fixed template. Refusing politely does not need
    to name the tool.
    """
    t = normalize(reply)
    if _REPLY_BLOCKLIST.search(t):
        return False
    return not any(h.severity == "high" for h in scan(t))


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
        risk=rule_risk,
        verdict_ja="",
        hits=hits,
        pay=pay,
        below_floor=below_floor,
        min_hourly_yen=min_hourly_yen,
    )

    if model is not None:
        rep.model_name = getattr(model, "name", None)
        t0 = time.monotonic()
        try:
            raw = model.chat(llm_mod.SYSTEM_PROMPT, llm_mod.build_user_prompt(text, [h.title_ja for h in hits]))
            rep.model = llm_mod.parse_model_json(raw)
            if rep.model is None:
                rep.model_error = "model reply was not usable JSON"
        except Exception as e:  # network, timeout, model missing: the rules still stand
            rep.model_error = f"{type(e).__name__}: {e}"
        rep.model_seconds = round(time.monotonic() - t0, 1)

    risk = rule_risk
    if rep.model and rep.model.get("risk"):
        m = rep.model["risk"]
        if SEVERITY_ORDER[m] > SEVERITY_ORDER[risk]:
            risk = m  # the model may raise the alarm
        elif SEVERITY_ORDER[m] < SEVERITY_ORDER[rule_risk]:
            rep.model_overruled = True  # ...but never talk a hard rule hit down
    if below_floor and SEVERITY_ORDER[risk] < SEVERITY_ORDER["medium"]:
        risk = "medium"
        rep.notes.append(f"実質時給が下限 {min_hourly_yen}円 を下回っています")
    rep.risk = risk
    rep.verdict_ja = VERDICT_JA[risk]

    ids = {h.rule_id for h in hits}
    model_reply = (rep.model or {}).get("reply_ja")
    flagged = any(SEVERITY_ORDER[h.severity] >= SEVERITY_ORDER["medium"] for h in hits)
    # Once a rule has fired, the reply is a fixed, reviewed template. Small models
    # tend to be polite to a fault ("the unpaid trial is fine, thank you!").
    if ids & {"off_platform_contact", "personal_documents", "upfront_payment", "crypto_investment"}:
        rep.reply_ja = SAFE_DECLINE_JA
    elif "unpaid_trial" in ids:
        rep.reply_ja = UNPAID_TRIAL_JA
    elif not flagged and model_reply and _reply_is_safe(model_reply):
        rep.reply_ja, rep.reply_source = model_reply.strip(), "model"
    if model_reply and not flagged and rep.reply_source != "model":
        rep.notes.append("モデルの返信案に外部ツール名・URL等が含まれていたため、表示しませんでした")
    return rep
