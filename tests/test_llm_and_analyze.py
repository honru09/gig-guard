import json
import unittest

from gigguard.analyze import (
    DECLINE_JA, GENERIC_CAUTION_JA, SAFE_DECLINE_JA, UNPAID_TRIAL_JA, analyze, quote_in_text,
)
from gigguard.llm import SYSTEM_PROMPT, build_user_prompt, parse_model_json


class FakeModel:
    name = "fake"

    def __init__(self, reply=None, exc=None):
        self.reply = reply
        self.exc = exc
        self.calls = []

    def chat(self, system, user):
        self.calls.append((system, user))
        if self.exc:
            raise self.exc
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply, ensure_ascii=False)


def finding(cat, sev, quote):
    return {"category": cat, "severity": sev, "quote": quote, "why_ja": "理由", "why_en": "reason"}


LINE_POST = "選考のためアンケートに回答してください。詳細はLINEで https://lin.ee/abc"
CLEAN_POST = "報酬：固定 3,000円\n作業時間の目安：2時間程度\nやり取りはすべてこちらのメッセージで行います。"
MULE_POST = "在宅で荷物の受け取りと転送をお願いします。届いた荷物を指定の住所へ送るだけで1件3,000円。"


class ParseTests(unittest.TestCase):
    def test_plain_json(self):
        d = parse_model_json(json.dumps({
            "risk": "HIGH", "summary_ja": "s", "summary_en": "e",
            "findings": [finding("off_platform_contact", "high", "LINEで")],
        }))
        self.assertEqual(d["risk"], "high")
        self.assertEqual(d["findings"][0]["quote"], "LINEで")
        self.assertEqual(d["summary_en"], "e")

    def test_fenced_and_prose(self):
        raw = 'Sure.\n```json\n{"risk":"low","summary_ja":"ok {braces} inside"}\n```'
        d = parse_model_json(raw)
        self.assertEqual(d["risk"], "low")
        self.assertEqual(d["summary_ja"], "ok {braces} inside")

    def test_garbage(self):
        self.assertIsNone(parse_model_json("no json here"))
        self.assertIsNone(parse_model_json('{"foo": 1}'))
        self.assertIsNone(parse_model_json("{broken"))

    def test_bad_fields_are_normalised(self):
        d = parse_model_json(json.dumps({
            "risk": "maybe", "summary_ja": "x",
            "findings": [
                {"category": "made_up", "severity": "extreme", "quote": "abc"},
                {"category": "unpaid_trial", "severity": "medium"},  # no quote: dropped
                "not a dict",
            ],
        }))
        self.assertIsNone(d["risk"])
        self.assertEqual(len(d["findings"]), 1)
        self.assertEqual(d["findings"][0]["category"], "other")
        self.assertEqual(d["findings"][0]["severity"], "low")

    def test_prompt_is_independent_of_rules(self):
        p = build_user_prompt(LINE_POST)
        self.assertIn("lin.ee", p)
        self.assertNotIn("ルール", p)
        self.assertIn("EXACT substring", SYSTEM_PROMPT)


class GroundingTests(unittest.TestCase):
    def test_exact_and_normalised_quotes(self):
        text = "詳細はＬＩＮＥで\nお伝えします。報酬：５，０００円"
        self.assertTrue(quote_in_text("LINEでお伝えします", text))
        self.assertTrue(quote_in_text("「報酬:5,000円」", text))
        self.assertTrue(quote_in_text("…LINEで…", text))

    def test_invented_quote_is_rejected(self):
        self.assertFalse(quote_in_text("Telegramで連絡", LINE_POST))
        self.assertFalse(quote_in_text("ア", LINE_POST))
        self.assertFalse(quote_in_text("", LINE_POST))


class AnalyzeTests(unittest.TestCase):
    def test_rules_only(self):
        rep = analyze(LINE_POST)
        self.assertEqual(rep.risk, "high")
        self.assertEqual(rep.reply_ja, SAFE_DECLINE_JA)
        self.assertIsNone(rep.model)

    def test_model_cannot_downgrade_a_rule_hit(self):
        rep = analyze(LINE_POST, model=FakeModel({"risk": "low", "summary_ja": "普通の案件です", "findings": []}))
        self.assertEqual(rep.risk, "high")
        self.assertTrue(rep.model_overruled)

    def test_grounded_model_finding_escalates(self):
        m = FakeModel({"risk": "high", "findings": [finding("illegal_or_mule", "high", "荷物の受け取りと転送")]})
        rep = analyze(MULE_POST, model=m)
        self.assertEqual(analyze(MULE_POST).risk, "none")  # rules alone miss it
        self.assertEqual(rep.risk, "high")
        self.assertEqual(len(rep.model_only_findings), 1)
        self.assertEqual(rep.reply_ja, DECLINE_JA)

    def test_hallucinated_finding_cannot_escalate(self):
        m = FakeModel({"risk": "high", "findings": [finding("off_platform_contact", "high", "LINEで連絡してください")]})
        rep = analyze(CLEAN_POST, model=m)
        self.assertEqual(rep.risk, "none")
        self.assertEqual(rep.findings, [])
        self.assertEqual(len(rep.rejected_findings), 1)
        self.assertTrue(any("dropped" in n for n in rep.notes))

    def test_top_level_risk_alone_does_not_escalate(self):
        rep = analyze(CLEAN_POST, model=FakeModel({"risk": "high", "summary_ja": "怪しい", "findings": []}))
        self.assertEqual(rep.risk, "none")

    def test_medium_model_finding_gives_caution_reply(self):
        m = FakeModel({"risk": "medium", "findings": [finding("vague_scope", "medium", "やり取りはすべてこちらのメッセージ")]})
        rep = analyze(CLEAN_POST, model=m)
        self.assertEqual(rep.risk, "medium")
        self.assertEqual(rep.reply_ja, GENERIC_CAUTION_JA)

    def test_unpaid_trial_gets_template_even_if_model_accepts_it(self):
        agree = "無償でご提供させていただくという点、承知いたしました。"
        rep = analyze("トライアルは無償となります", model=FakeModel({"risk": "medium", "reply_ja": agree}))
        self.assertEqual(rep.reply_ja, UNPAID_TRIAL_JA)
        self.assertEqual(rep.reply_source, "template")

    def test_model_reply_used_when_safe(self):
        m = FakeModel({"risk": "low", "findings": [], "reply_ja": "ご連絡ありがとうございます。ぜひお願いします。"})
        rep = analyze(CLEAN_POST, model=m)
        self.assertEqual(rep.reply_source, "model")

    def test_model_reply_that_mentions_line_is_dropped(self):
        bad = "LINEのURLから友だち追加し、アンケートに回答します。ただしサイト内で進めたいです。"
        rep = analyze(CLEAN_POST, model=FakeModel({"risk": "low", "findings": [], "reply_ja": bad}))
        self.assertIsNone(rep.reply_ja)
        self.assertTrue(any("outside tool" in n for n in rep.notes))
        rep = analyze(CLEAN_POST, model=FakeModel({"risk": "low", "reply_ja": "詳細は https://x.example で"}))
        self.assertIsNone(rep.reply_ja)

    def test_model_failure_falls_back_to_rules(self):
        rep = analyze(LINE_POST, model=FakeModel(exc=TimeoutError("slow")))
        self.assertEqual(rep.risk, "high")
        self.assertIn("TimeoutError", rep.model_error)
        rep = analyze(CLEAN_POST, model=FakeModel("not json"))
        self.assertEqual(rep.model_error, "model reply was not usable JSON")

    def test_below_floor_raises_to_medium(self):
        rep = analyze("報酬 500円 作業時間は2時間程度", min_hourly_yen=1200)
        self.assertTrue(rep.below_floor)
        self.assertEqual(rep.risk, "medium")

    def test_to_dict_is_json_serialisable(self):
        m = FakeModel({"risk": "high", "findings": [finding("off_platform_contact", "high", "LINEで")]})
        d = analyze(LINE_POST, model=m).to_dict()
        json.dumps(d, ensure_ascii=False)
        self.assertEqual(d["model_only_findings"], [])
        self.assertEqual(d["verdict_en"], "Don't apply or reply")


if __name__ == "__main__":
    unittest.main()
