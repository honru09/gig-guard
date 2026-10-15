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
    advice_en: str = ""


@dataclass
class Hit:
    rule_id: str
    severity: str
    title_ja: str
    title_en: str
    advice_ja: str
    evidence: list[str] = field(default_factory=list)
    advice_en: str = ""

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "title_ja": self.title_ja,
            "title_en": self.title_en,
            "advice_ja": self.advice_ja,
            "advice_en": self.advice_en,
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
            '(whatsapp|telegram|signal|wechat|skype|google\\s*chat|hangouts)\\b',
            '(contact|message|text|reach|add)\\s+me\\s+(on|via|at)\\s+(whatsapp|telegram|signal|wechat|skype|discord|gmail|email|my\\s+(email|number|phone))',
            '(outside|off)\\s+(of\\s+)?(upwork|fiverr|freelancer|the\\s+platform|the\\s+site|this\\s+site)',
            '(avoid|skip|save\\s+on)\\s+(the\\s+)?(platform|upwork|fiverr|service)\\s+fees?',
            '(加|添加|联系)\\s*(我的?)?\\s*(微信|威信|vx|VX|QQ|电报|飞机|whatsapp)',
            '(微信|vx|QQ|电报)\\s*(号|ID|联系|沟通|详聊|私聊)',
            '(平台外|站外|私下)\\s*(联系|交易|沟通)',
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
            '(pay|purchase|buy)\\s+(for\\s+)?(the\\s+|a\\s+)?(training|starter\\s+kit|software\\s+license|equipment|onboarding)',
            '(refundable\\s+)?(deposit|activation\\s+fee|membership\\s+fee)',
            '(押金|保证金|培训费|会费|入会费|激活费|先交|先付)',
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
            '(free|unpaid)\\s+(sample|test\\s+task|trial\\s+task|test\\s+project)',
            '(test|trial|sample)\\s+(task|work|project)?\\s*(will\\s+)?(not\\s+be\\s+paid|is\\s+not\\s+paid|without\\s+pay)',
            '(免费|无偿|不付费|没有报酬)\\s*(的)?\\s*(试稿|试译|测试|试用|样稿)',
            '(试稿|试译|测试|样稿)\\s*(是|为)?\\s*(免费|无偿|不付费|没有报酬)',
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
            '\\b(ssn|social\\s+security\\s+number)\\b',
            '(send|share|upload)\\s+(me\\s+)?(a\\s+)?(photo|copy|scan)\\s+of\\s+your\\s+(id|passport|driver)',
            '(身份证|银行卡号|银行卡密码|护照)\\s*(照片|号码|复印件|发给|提供)?',
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
            '(earn|make)\\s+\\$?[0-9,]+\\s*(\\+\\s*)?(per|a|/)\\s*(day|week)\\s+(from\\s+home|easily|with\\s+no\\s+experience)',
            'no\\s+experience\\s+(needed|required).{0,30}\\$[0-9,]{3,}',
            '(日赚|日入|月入)\\s*[0-9]+',
            '(轻松|躺着)\\s*(赚|月入|日入)',
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
            '(刷单|虚拟币|数字货币|USDT|炒币)',
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
            '(禁止|不得|不能|不允许)\\s*(使用)?\\s*(AI|人工智能|ChatGPT)',
            '(AI|人工智能)\\s*(生成|写作)?\\s*(的)?\\s*(内容)?\\s*(禁止|不可|不接受)',
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
            '(urgent|asap|immediately).{0,20}(reply|respond|confirm|send)',
            '(reply|respond|confirm)\\s+(asap|immediately|urgently|right\\s+away)',
            '(今天之内|马上|立即)\\s*(回复|联系|添加|确认)',
        ),
    ),
)


_ADVICE_EN = {'off_platform_contact': "Upwork, Fiverr, CrowdWorks and most platforms forbid moving contact or payment off-platform. Reply inside the site and don't open the link.", 'upfront_payment': "A job you have to pay for is almost always a scam or an info-product sale. Don't pay.", 'unpaid_trial': 'Unpaid tests are a classic way to get real work for free. Ask for a small paid test contract.', 'personal_documents': "Don't send ID, bank details or My Number before a contract. The platform handles payment.", 'too_good_to_be_true': "'Anyone can earn ¥300k a month on a phone' is stock side-hustle-scam wording.", 'crypto_investment': 'Possibly an investment pitch or self-affiliate scheme dressed up as a job.', 'ai_banned': 'AI tools are explicitly banned. If you planned to use AI, skip this one.', 'rushed_pressure': "'Reply ASAP / today only' pressure takes away your time to think. Check the terms calmly."}
RULES = tuple(
    Rule(r.id, r.severity, r.title_ja, r.title_en, r.advice_ja, r.patterns, _ADVICE_EN.get(r.id, ""))
    for r in RULES
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
                Hit(rule.id, rule.severity, rule.title_ja, rule.title_en, rule.advice_ja, evidence, rule.advice_en)
            )
    return hits


def max_severity(levels) -> str:
    best = "none"
    for lv in levels:
        if SEVERITY_ORDER.get(lv, 0) > SEVERITY_ORDER[best]:
            best = lv
    return best
