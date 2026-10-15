import json
import unittest

from gigguard.analyze import SAFE_DECLINE_JA, UNPAID_TRIAL_JA, analyze
from gigguard.llm import parse_model_json


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


LINE_POST = "選考のためアンケートに回答してください。詳細はLINEで https://lin.ee/abc"
CLEAN_POST = "報酬：固定 3,000円\n作業時間の目安：2時間程度\nやり取りはすべてこちらのメッセージで行います。"


class ParseTests(unittest.TestCase):
    def test_plain_json(self):
        d = parse_model_json('{"risk":"HIGH","summary_ja":"s","concerns_ja":"one","reply_ja":"r"}')
        self.assertEqual(d["risk"], "high")
        self.assertEqual(d["concerns_ja"], ["one"])

    def test_fenced_and_prose(self):
        raw = '承知しました。\n```json\n{"risk":"low","summary_ja":"ok {braces} inside"}\n```'
        d = parse_model_json(raw)
        self.assertEqual(d["risk"], "low")
        self.assertEqual(d["summary_ja"], "ok {braces} inside")

    def test_garbage(self):
        self.assertIsNone(parse_model_json("no json here"))
        self.assertIsNone(parse_model_json('{"foo": 1}'))
        self.assertIsNone(parse_model_json("{broken"))

    def test_bad_risk_value_is_dropped(self):
        d = parse_model_json('{"risk":"maybe","summary_ja":"x"}')
        self.assertIsNone(d["risk"])


class AnalyzeTests(unittest.TestCase):
    def test_rules_only(self):
        rep = analyze(LINE_POST)
        self.assertEqual(rep.risk, "high")
        self.assertEqual(rep.reply_ja, SAFE_DECLINE_JA)
        self.assertIsNone(rep.model)

    def test_model_cannot_downgrade_a_rule_hit(self):
        m = FakeModel({"risk": "low", "summary_ja": "普通の案件です"})
        rep = analyze(LINE_POST, model=m)
        self.assertEqual(rep.risk, "high")
        self.assertTrue(rep.model_overruled)
        # the rule titles are passed to the model as context
        self.assertIn("プラットフォーム外", m.calls[0][1])

    def test_model_can_raise_risk(self):
        rep = analyze(CLEAN_POST, model=FakeModel({"risk": "medium", "summary_ja": "x"}))
        self.assertEqual(rep.risk, "medium")
        self.assertFalse(rep.model_overruled)

    def test_hard_flag_always_gets_template_reply(self):
        m = FakeModel({"risk": "high", "reply_ja": "承知しました。よろしくお願いします。"})
        rep = analyze(LINE_POST, model=m)
        self.assertEqual(rep.reply_ja, SAFE_DECLINE_JA)
        self.assertEqual(rep.reply_source, "template")

    def test_model_reply_used_when_safe(self):
        m = FakeModel({"risk": "low", "reply_ja": "ご連絡ありがとうございます。ぜひお願いします。"})
        rep = analyze(CLEAN_POST, model=m)
        self.assertEqual(rep.reply_source, "model")

    def test_unpaid_trial_gets_template_even_if_model_accepts_it(self):
        # seen with gemma3:4b: it politely agreed to do the unpaid trial
        agree = "無償でご提供させていただくという点、承知いたしました。"
        rep = analyze("トライアルは無償となります", model=FakeModel({"risk": "medium", "reply_ja": agree}))
        self.assertEqual(rep.reply_ja, UNPAID_TRIAL_JA)
        self.assertEqual(rep.reply_source, "template")

    def test_model_reply_that_mentions_line_is_dropped(self):
        # seen with gemma3:4b: "I'll add you on LINE ... but let's keep it on-platform"
        bad = "LINEのURLから友だち追加し、アンケートに回答します。ただしサイト内で進めたいです。"
        rep = analyze(CLEAN_POST, model=FakeModel({"risk": "low", "reply_ja": bad}))
        self.assertIsNone(rep.reply_ja)
        self.assertTrue(any("差し替え" in n or "外部ツール" in n for n in rep.notes))
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
        rep = analyze(LINE_POST, model=FakeModel({"risk": "high", "concerns_ja": ["a"]}))
        json.dumps(rep.to_dict(), ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
