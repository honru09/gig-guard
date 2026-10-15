"""English / Chinese posts and platform-agnostic pay math."""

import unittest
from pathlib import Path

from gigguard.analyze import TEMPLATES, analyze, detect_lang
from gigguard.pay import DEFAULT_FLOORS, PLATFORM_FEES, estimate
from gigguard.rules import scan

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def ids(text):
    return {h.rule_id for h in scan(text)}


def sample(name):
    return (SAMPLES / name).read_text(encoding="utf-8")


class EnglishAndChineseRules(unittest.TestCase):
    def test_upwork_whatsapp_scam(self):
        found = ids(sample("07_upwork_whatsapp.txt"))
        self.assertIn("off_platform_contact", found)
        self.assertIn("rushed_pressure", found)

    def test_avoid_fees_is_off_platform(self):
        self.assertIn("off_platform_contact", ids("Let's continue outside Upwork to avoid the fees"))

    def test_free_sample(self):
        self.assertIn("unpaid_trial", ids(sample("08_fiverr_free_sample.txt")))

    def test_chinese_wechat_and_fee(self):
        found = ids(sample("09_zh_wechat.txt"))
        self.assertTrue({"off_platform_contact", "upfront_payment", "too_good_to_be_true"} <= found)

    def test_normal_upwork_job_is_clean(self):
        self.assertEqual(scan(sample("10_upwork_normal.txt")), [])

    def test_more_patterns(self):
        self.assertIn("personal_documents", ids("Please send me a photo of your passport"))
        self.assertIn("personal_documents", ids("We need your SSN for onboarding"))
        self.assertIn("ai_banned", ids("本项目禁止使用AI"))
        self.assertIn("unpaid_trial", ids("试稿是免费的"))


class PayAnyCurrency(unittest.TestCase):
    def test_usd_fixed_with_range(self):
        e = estimate("Fixed price $200, estimated 4-6 hours", fee_rate=PLATFORM_FEES["upwork"])
        self.assertEqual((e.currency, e.total_yen, e.hours), ("USD", 200, 5))
        self.assertAlmostEqual(e.effective_hourly_yen, 36.0)

    def test_usd_hourly(self):
        e = estimate("$15/hr, 10 hours per week", fee_rate=0.2)
        self.assertEqual(e.hourly_yen, 15)
        self.assertEqual(e.effective_hourly_yen, 12)

    def test_usd_k(self):
        self.assertEqual(estimate("Budget: $1.5k").total_yen, 1500)

    def test_cny(self):
        e = estimate("报酬500元，大概2小时", fee_rate=0)
        self.assertEqual((e.currency, e.effective_hourly_yen), ("CNY", 250))

    def test_cny_fee_is_not_the_reward(self):
        self.assertIsNone(estimate("入职需要先交200元培训费").total_yen)

    def test_presets_are_sane(self):
        self.assertEqual(PLATFORM_FEES["direct"], 0.0)
        self.assertTrue(all(0 <= v < 0.5 for v in PLATFORM_FEES.values()))
        self.assertEqual(set(DEFAULT_FLOORS), {"JPY", "USD", "CNY"})

    def test_floor_follows_currency(self):
        rep = analyze("Fixed price $20 for about 5 hours of work")
        self.assertEqual(rep.min_hourly_yen, DEFAULT_FLOORS["USD"])
        self.assertTrue(rep.below_floor)
        self.assertEqual(rep.risk, "medium")


class ReportLanguage(unittest.TestCase):
    def test_single_language_reports(self):
        from gigguard.render import text_report
        rep = analyze(sample("09_zh_wechat.txt"))
        zh = text_report(rep, "zh")
        self.assertIn("规则检出", zh)
        self.assertIn("把沟通引到平台外", zh)
        self.assertNotIn("Rule hits", zh)
        self.assertNotIn("ルール", zh)
        en = text_report(rep, "en")
        self.assertIn("Rule hits", en)
        self.assertNotIn("規約", en)
        ja = text_report(analyze(sample("01_line_redirect.txt")), "ja")
        self.assertIn("ルールで検出", ja)
        self.assertNotIn("Upwork", ja)


class Replies(unittest.TestCase):
    def test_lang_detection(self):
        self.assertEqual(detect_lang("詳細はLINEで"), "ja")
        self.assertEqual(detect_lang("加我微信详聊"), "zh")
        self.assertEqual(detect_lang("contact me on WhatsApp"), "en")

    def test_reply_matches_post_language(self):
        # "buy the equipment" (the fake-check scam) means there is nothing to negotiate
        self.assertEqual(analyze(sample("07_upwork_whatsapp.txt")).reply_ja, TEMPLATES["en"]["decline"])
        self.assertEqual(analyze("Please message me on Telegram").reply_ja, TEMPLATES["en"]["safe_decline"])
        self.assertEqual(analyze(sample("09_zh_wechat.txt")).reply_ja, TEMPLATES["zh"]["decline"])
        self.assertEqual(analyze(sample("08_fiverr_free_sample.txt")).reply_ja, TEMPLATES["en"]["unpaid_trial"])


if __name__ == "__main__":
    unittest.main()
