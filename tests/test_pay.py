import unittest

from gigguard.pay import estimate


class PayTests(unittest.TestCase):
    def test_fixed_reward_and_hours(self):
        e = estimate("報酬：固定 3,000円\n作業時間の目安：2時間程度", fee_rate=0.2)
        self.assertEqual(e.total_yen, 3000)
        self.assertEqual(e.hours, 2)
        self.assertEqual(e.net_total_yen, 2400)
        self.assertEqual(e.effective_hourly_yen, 1200)

    def test_man_and_yen_prefix(self):
        self.assertEqual(estimate("予算 1.5万円").total_yen, 15000)
        self.assertEqual(estimate("報酬 ¥8,000").total_yen, 8000)
        self.assertEqual(estimate("謝礼 5千円").total_yen, 5000)

    def test_fullwidth_digits(self):
        self.assertEqual(estimate("報酬　５，０００円").total_yen, 5000)

    def test_hour_range_is_averaged(self):
        self.assertEqual(estimate("報酬 10,000円、5〜6時間ほど").hours, 5.5)

    def test_minutes(self):
        e = estimate("報酬 500円 作業時間は30分程度", fee_rate=0.0)
        self.assertEqual(e.hours, 0.5)
        self.assertEqual(e.effective_hourly_yen, 1000)

    def test_per_char_job(self):
        e = estimate("文字単価1.0円、1記事3000文字程度", fee_rate=0.2, chars_per_hour=1500)
        self.assertEqual(e.per_char_yen, 1.0)
        self.assertEqual(e.chars, 3000)
        self.assertEqual(e.total_yen, 3000)
        self.assertEqual(e.hours, 2)
        self.assertEqual(e.effective_hourly_yen, 1200)

    def test_hourly_rate(self):
        e = estimate("時給1,500円、週10時間程度", fee_rate=0.2)
        self.assertEqual(e.hourly_yen, 1500)
        self.assertEqual(e.effective_hourly_yen, 1200)

    def test_fee_and_income_claims_are_not_the_reward(self):
        e = estimate("月30万円稼げる！教材費 29,800円")
        self.assertIsNone(e.total_yen)

    def test_reward_keyword_wins_over_other_amounts(self):
        e = estimate("売上100万円のお店です。報酬 2,000円")
        self.assertEqual(e.total_yen, 2000)

    def test_unknowns_are_reported(self):
        e = estimate("よろしくお願いします")
        self.assertIsNone(e.total_yen)
        self.assertIsNone(e.effective_hourly_yen)
        self.assertTrue(any("報酬額" in n for n in e.notes))


if __name__ == "__main__":
    unittest.main()
