import unittest
from pathlib import Path

from gigguard.rules import max_severity, normalize, scan

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def ids(text):
    return {h.rule_id for h in scan(text)}


class RuleTests(unittest.TestCase):
    def test_line_short_link(self):
        self.assertIn("off_platform_contact", ids("詳細はこちら https://lin.ee/AbCd"))

    def test_line_word_and_fullwidth(self):
        self.assertIn("off_platform_contact", ids("ＬＩＮＥで友だち追加してください"))
        self.assertIn("off_platform_contact", ids("ラインで連絡ください"))

    def test_online_is_not_line(self):
        # "オンライン" contains ライン; it must not read as LINE
        self.assertNotIn("off_platform_contact", ids("オンラインで15分ほど説明会を行います"))
        self.assertNotIn("off_platform_contact", ids("ガイドラインに沿って作業してください"))

    def test_telegram_and_email(self):
        self.assertIn("off_platform_contact", ids("続きは t.me/xxxx でお願いします"))
        self.assertIn("off_platform_contact", ids("Gmailで連絡します"))

    def test_upfront_fee(self):
        self.assertIn("upfront_payment", ids("教材費 29,800円をお支払いください"))
        self.assertIn("upfront_payment", ids("Please pay a small fee to start"))

    def test_unpaid_trial_both_orders(self):
        self.assertIn("unpaid_trial", ids("無償のテストをお願いします"))
        self.assertIn("unpaid_trial", ids("トライアルは無償となります"))
        self.assertIn("unpaid_trial", ids("テストにつきましては報酬は発生しません"))
        self.assertNotIn("unpaid_trial", ids("テスト記事は1本1,000円でお支払いします"))

    def test_personal_documents(self):
        self.assertIn("personal_documents", ids("運転免許証の写真を送付してください"))
        self.assertIn("personal_documents", ids("マイナンバーを教えてください"))

    def test_ai_ban(self):
        self.assertIn("ai_banned", ids("AIツールの使用は禁止です"))
        self.assertIn("ai_banned", ids("生成AIの利用は一切NG"))
        self.assertIn("ai_banned", ids("No AI please"))
        self.assertNotIn("ai_banned", ids("AIの活用を歓迎します"))

    def test_too_good(self):
        self.assertIn("too_good_to_be_true", ids("スマホ1台で月30万円以上稼げる"))

    def test_crypto(self):
        self.assertIn("crypto_investment", ids("仮想通貨の自動売買ツール"))

    def test_evidence_is_capped_and_quoted(self):
        hits = scan("LINEで LINEに LINEを LINEから")
        h = [x for x in hits if x.rule_id == "off_platform_contact"][0]
        self.assertLessEqual(len(h.evidence), 2)
        self.assertTrue(all("LINE" in e for e in h.evidence))

    def test_clean_post_has_no_hits(self):
        text = (SAMPLES / "03_store_research.txt").read_text(encoding="utf-8")
        self.assertEqual(scan(text), [])

    def test_max_severity(self):
        self.assertEqual(max_severity([]), "none")
        self.assertEqual(max_severity(["low", "high", "medium"]), "high")

    def test_normalize(self):
        self.assertEqual(normalize("ＡＢＣ１２３"), "ABC123")


if __name__ == "__main__":
    unittest.main()
