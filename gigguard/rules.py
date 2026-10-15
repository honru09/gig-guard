"""Deterministic red-flag rules (Japanese + English).

These run without any model. A rule hit can never be downgraded by the LLM:
if a client asks you to move to LINE, that is a fact in the text, not an opinion.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str
    title_ja: str
    title_en: str
    advice_ja: str
    patterns: tuple[str, ...]


@dataclass
class Hit:
    rule_id: str
    severity: str
    title_ja: str
    title_en: str
    advice_ja: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "title_ja": self.title_ja,
            "title_en": self.title_en,
            "advice_ja": self.advice_ja,
            "evidence": self.evidence,
        }


RULES: tuple[Rule, ...] = (
    Rule(
        "off_platform_contact",
        "high",
        "プラットフォーム外での連絡に誘導",
        "Moves the conversation off the platform",
        "クラウドワークス・ランサーズ等は規約で外部連絡を禁止しています。返信は必ず"
        "サイト内メッセージで行い、リンクは開かないでください。",
        (
            r"lin\.ee/",
            r"line\.me/",
            r"LINE\s*(ID|で|に|を|から|追加|登録|友だち|友達|公式)",
            r"(?<![ァ-ヶー])ライン\s*(で|に|を|追加|登録|ID)",
            r"t\.me/",
            r"(telegram|テレグラム|whatsapp|signal|カカオ|kakao)",
            r"(discord|ディスコード)\s*(で|に|へ|サーバー|server)",
            r"(chatwork|チャットワーク)\s*(で|に|へ|を)",
            r"(gmail|メール|e-?mail)\s*(アドレス)?\s*(で|に|へ)\s*(連絡|送|返信|やり取り)",
            r"(外部|別の?)\s*(ツール|アプリ|サイト)\s*(で|に|へ)",
        ),
    ),
    Rule(
        "upfront_payment",
        "high",
        "応募者側に支払いを要求",
        "Asks the worker to pay first",
        "仕事を受けるためにお金を払う案件は、ほぼ詐欺か情報商材です。支払わないでください。",
        (
            r"(登録料|入会金|初期費用|教材費|研修費|保証金|手数料)\s*(が|は|を|として)?\s*[0-9０-９,，]+",
            r"(登録料|入会金|初期費用|教材費|研修費|保証金)",
            r"(マニュアル|教材|ツール)\s*(を|の)?\s*(購入|ご購入|買って)",
            r"(registration|starter|training)\s+fee",
            r"pay\s+(a|the)?\s*(small\s+)?(fee|deposit)",
        ),
    ),
    Rule(
        "unpaid_trial",
        "medium",
        "無報酬のテスト・試作",
        "Unpaid test work",
        "無償テストは本番作業を只でやらされる典型パターンです。報酬付きテスト"
        "（テスト契約）にできないか確認しましょう。",
        (
            r"(無償|無料|報酬なし|報酬は発生しません|謝礼なし|ノーギャラ)\s*(の|で|にて)?\s*(テスト|試作|トライアル|課題|サンプル|試験|トライ)",
            r"(テスト|トライアル|試作|課題)\s*(は|につきましては)?\s*(無償|無料|報酬なし|報酬は発生しません|報酬対象外)",
            r"unpaid\s+(test|trial|sample)",
            r"(test|trial)\s+(task\s+)?(is\s+)?unpaid",
        ),
    ),
    Rule(
        "personal_documents",
        "high",
        "早い段階で個人情報・書類を要求",
        "Asks for ID / bank details early",
        "契約前に身分証・口座・マイナンバーを求めるのは危険です。報酬はプラットフォーム経由で受け取れます。",
        (
            r"(マイナンバー|個人番号)",
            r"(身分証|運転免許証|免許証|保険証|パスポート|在留カード)\s*(の)?\s*(写真|画像|コピー|提出|送付|アップ)",
            r"(銀行|口座)\s*(番号|情報)?\s*(を|の)?\s*(教え|送|記入|入力|提出)",
            r"(暗証番号|キャッシュカード)",
            r"(passport|driver'?s\s+licen[cs]e|bank\s+account)\s+(photo|copy|number|details)",
        ),
    ),
    Rule(
        "too_good_to_be_true",
        "medium",
        "楽すぎる高収入アピール",
        "Too-good-to-be-true pay",
        "「誰でも簡単」「スマホだけで月◯万」は情報商材や副業詐欺の決まり文句です。",
        (
            r"(誰でも|だれでも|初心者でも)\s*(簡単|かんたん|カンタン|すぐ)",
            r"(スマホ|スマートフォン)\s*(1台|一台|だけ)\s*(で)?",
            r"(1日|一日)\s*[0-9０-９]+\s*分\s*(で|だけ)",
            r"(月|月収)\s*[0-9０-９]+\s*万\s*(円)?\s*(以上|保証|確実|稼げ)",
            r"(即日|すぐに)\s*(高収入|稼げ)",
            r"(guaranteed|easy)\s+(income|money)",
        ),
    ),
    Rule(
        "crypto_investment",
        "high",
        "投資・仮想通貨・アフィリエイト系",
        "Investment / crypto / self-affiliate scheme",
        "業務委託に見せかけた投資勧誘・自己アフィリエイトの可能性があります。",
        (
            r"(仮想通貨|暗号資産|FX|バイナリー|NFT|ウォレット)",
            r"(自己アフィリ|セルフバック|口座開設).{0,10}(報酬|案件)",
            r"(crypto|wallet\s+address|usdt|binance)",
        ),
    ),
    Rule(
        "ai_banned",
        "low",
        "AIツールの使用を禁止",
        "Bans AI tools",
        "AI禁止と明記されています。AIで作業する予定なら、この案件は見送るのが誠実です。",
        (
            r"(AI|ＡＩ|生成AI|ChatGPT|チャットGPT)\s*(ツール)?\s*(の)?\s*(使用|利用|活用)?\s*(は)?\s*(一切)?\s*(禁止|不可|NG|ご遠慮|お断り|厳禁)",
            r"(AI|ＡＩ)\s*(を)?\s*(使った|使用した|利用した)\s*(作業|納品|文章|原稿)\s*(は)?\s*(禁止|不可|NG|お断り)",
            r"no\s+(ai|chatgpt)",
            r"(ai|chatgpt)[- ]generated\s+(content|work|text)\s+(is\s+)?(not\s+allowed|prohibited|banned)",
        ),
    ),
    Rule(
        "rushed_pressure",
        "low",
        "急かし・即決の要求",
        "Pressure to decide fast",
        "「本日中」「先着」で急かすのは考える時間を奪う手口のことがあります。条件を落ち着いて確認しましょう。",
        (
            r"(本日中|今日中|至急|先着\s*[0-9０-９]*\s*名|今すぐ)\s*(に)?\s*(ご連絡|返信|登録|追加|決め|お願い|限定)",
            r"(reply|respond|decide)\s+(within|in)\s+[0-9]+\s+(minutes|hours)",
        ),
    ),
)


def normalize(text: str) -> str:
    """NFKC-normalize so full-width ＬＩＮＥ / ０-９ match the same rules."""
    return unicodedata.normalize("NFKC", text)


def _snippet(text: str, start: int, end: int, pad: int = 14) -> str:
    s = max(0, start - pad)
    e = min(len(text), end + pad)
    out = text[s:e].replace("\n", " ").strip()
    return ("…" if s > 0 else "") + out + ("…" if e < len(text) else "")


def scan(text: str, rules: tuple[Rule, ...] = RULES) -> list[Hit]:
    """Return one Hit per rule that matched, with up to 2 evidence snippets."""
    norm = normalize(text)
    hits: list[Hit] = []
    for rule in rules:
        evidence: list[str] = []
        spans: list[tuple[int, int]] = []
        for pat in rule.patterns:
            for m in re.finditer(pat, norm, flags=re.IGNORECASE):
                if any(m.start() < e and s < m.end() for s, e in spans):
                    continue
                spans.append((m.start(), m.end()))
                evidence.append(_snippet(norm, m.start(), m.end()))
                if len(evidence) >= 2:
                    break
            if len(evidence) >= 2:
                break
        if evidence:
            hits.append(
                Hit(rule.id, rule.severity, rule.title_ja, rule.title_en, rule.advice_ja, evidence)
            )
    return hits


def max_severity(levels) -> str:
    best = "none"
    for lv in levels:
        if SEVERITY_ORDER.get(lv, 0) > SEVERITY_ORDER[best]:
            best = lv
    return best
