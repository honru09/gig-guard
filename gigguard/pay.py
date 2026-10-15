"""Pull the pay and the time out of a job post and work out the real hourly rate.

Japanese posts write money a dozen ways (5,000円 / ¥5000 / 5千円 / 1.5万円 /
文字単価1円 x 3000文字 / 時給1,200円) and time just as loosely (2時間 / 30分 /
5〜6時間). This module handles the common shapes and says "unknown" for the rest
instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Optional

from .rules import normalize

_NUM = r"([0-9]+(?:[.,][0-9]+)*)"

# Approximate fees taken from the freelancer (check your platform; they change).
PLATFORM_FEES = {
    "direct": 0.0,        # direct client, invoice yourself
    "upwork": 0.10,       # variable, roughly 0-15% per contract
    "fiverr": 0.20,
    "freelancer": 0.10,   # Freelancer.com: 10% or a minimum fixed fee
    "crowdworks": 0.20,   # small contracts
    "lancers": 0.165,
    "coconala": 0.22,
}
# Default hourly floors per currency (override with --min-hourly).
DEFAULT_FLOORS = {"JPY": 1200, "USD": 10, "CNY": 25}


def _to_float(s: str) -> float:
    s = s.replace(",", "")
    return float(s)


def _yen(num: str, unit: str | None) -> float:
    v = _to_float(num)
    if unit == "万":
        v *= 10_000
    elif unit == "千":
        v *= 1_000
    return v


@dataclass
class PayEstimate:
    total_yen: Optional[float] = None
    hourly_yen: Optional[float] = None  # stated hourly rate, if the post gives one
    hours: Optional[float] = None
    per_char_yen: Optional[float] = None
    chars: Optional[int] = None
    net_total_yen: Optional[float] = None
    effective_hourly_yen: Optional[float] = None
    fee_rate: float = 0.0
    currency: str = "JPY"
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["notes"] = list(self.notes)
        return d


_PER_CHAR = re.compile(r"文字単価\s*[:：]?\s*" + _NUM + r"\s*円")
_CHARS = re.compile(_NUM + r"\s*(万)?\s*(?:文字|字)(?!単価)")
_HOURLY = re.compile(r"(?:時給|時間単価|hourly)\s*[:：]?\s*[¥￥]?\s*" + _NUM + r"\s*(万|千)?\s*円?", re.I)
_YEN_SUFFIX = re.compile(_NUM + r"\s*(万|千)?\s*円")
_YEN_PREFIX = re.compile(r"[¥￥]\s*" + _NUM + r"\s*(万|千)?")
_REWARD_KEY = re.compile(r"(報酬|予算|お支払い|支払額|単価|固定|謝礼|budget|pay)", re.I)
_RANGE_H = re.compile(_NUM + r"\s*(?:〜|~|-|～|から)\s*" + _NUM + r"\s*時間")
_HOURS = re.compile(_NUM + r"\s*時間")
_MINUTES = re.compile(_NUM + r"\s*分(?!の)")
_TIME_KEY = re.compile(r"(作業時間|所要時間|目安|想定|工数|程度|くらい|ぐらい|ほど|かかり|見込み)")


_USD_HOURLY = re.compile(r"(?:\$|USD\s*)" + _NUM + r"\s*(?:/\s*(?:hr|hour|h)\b|per\s+hour|an\s+hour|hourly)", re.I)
_USD = re.compile(r"(?:\$|USD\s*)" + _NUM + r"(k)?|" + _NUM + r"\s*(?:USD|dollars)\b", re.I)
_CNY_HOURLY = re.compile(r"(?:时薪|每小时)\s*" + _NUM + r"\s*(?:元|块)|" + _NUM + r"\s*(?:元|块)\s*/\s*(?:小时|时)")
_CNY = re.compile(_NUM + r"\s*(万)?\s*(?:元|块|人民币|RMB)", re.I)
_EN_RANGE_H = re.compile(_NUM + r"\s*(?:-|–|to)\s*" + _NUM + r"\s*(?:hours|hrs|h)\b", re.I)
_EN_HOURS = re.compile(_NUM + r"\s*(?:hours|hrs|hour|h)\b", re.I)
_EN_MIN = re.compile(_NUM + r"\s*(?:minutes|mins|min)\b", re.I)
_ZH_RANGE_H = re.compile(_NUM + r"\s*(?:-|~|～|到|至)\s*" + _NUM + r"\s*(?:个)?小时")
_ZH_HOURS = re.compile(_NUM + r"\s*(?:个)?小时")
_ZH_MIN = re.compile(_NUM + r"\s*分钟")


def _foreign(t: str):
    """(currency, total, hourly, hours) for posts priced in USD or CNY, else None."""
    cur = None
    total = hourly = None
    m = _USD_HOURLY.search(t)
    if m:
        cur, hourly = "USD", _to_float(m.group(1))
    else:
        amounts = []
        for m in _USD.finditer(t):
            if m.group(1):
                v = _to_float(m.group(1)) * (1000 if m.group(2) else 1)
            else:
                v = _to_float(m.group(3))
            amounts.append(v)
        if amounts:
            cur, total = "USD", max(amounts)
    if cur is None:
        m = _CNY_HOURLY.search(t)
        if m:
            cur, hourly = "CNY", _to_float(m.group(1) or m.group(2))
        else:
            amounts = [
                _to_float(m.group(1)) * (10_000 if m.group(2) else 1)
                for m in _CNY.finditer(t)
                # money the worker would PAY (先交200元培训费) is not the reward
                if not re.match(r"\s*(培训费|押金|保证金|会费|入会费|激活费)", t[m.end():])
                and not re.search(r"(交|付|缴)\s*$", t[max(0, m.start() - 3):m.start()])
            ]
            if amounts:
                cur, total = "CNY", max(amounts)
    if cur is None:
        return None
    hours = None
    for rng, single, mins in ((_EN_RANGE_H, _EN_HOURS, _EN_MIN), (_ZH_RANGE_H, _ZH_HOURS, _ZH_MIN)):
        m = rng.search(t)
        if m:
            hours = (_to_float(m.group(1)) + _to_float(m.group(2))) / 2
            break
        m = single.search(t)
        if m:
            hours = _to_float(m.group(1))
            break
        m = mins.search(t)
        if m:
            hours = _to_float(m.group(1)) / 60
            break
    return cur, total, hourly, hours


def _first_reward(text: str) -> Optional[float]:
    """Prefer an amount near a reward keyword; else the largest amount in the post."""
    cands: list[tuple[int, float]] = []
    for rx in (_YEN_SUFFIX, _YEN_PREFIX):
        for m in rx.finditer(text):
            # skip amounts that are clearly per-char or hourly rates
            before = text[max(0, m.start() - 6): m.start()]
            if "文字単価" in before or "時給" in before or "時間単価" in before:
                continue
            # money the worker would PAY, or income claims ("月30万円"), is not the reward
            near = text[max(0, m.start() - 8): m.start()]
            if re.search(r"(教材費|登録料|入会金|初期費用|研修費|保証金|手数料|費用|月収?)\s*[:：]?\s*$", near):
                continue
            v = _yen(m.group(1), m.group(2))
            if v <= 0:
                continue
            ctx = text[max(0, m.start() - 20): m.start()]
            score = 1 if _REWARD_KEY.search(ctx) else 0
            cands.append((score, v))
    if not cands:
        return None
    keyed = [v for s, v in cands if s]
    return max(keyed) if keyed else max(v for _, v in cands)


def _hours(text: str) -> Optional[float]:
    m = _RANGE_H.search(text)
    if m:
        return (_to_float(m.group(1)) + _to_float(m.group(2))) / 2
    best = None
    for m in _HOURS.finditer(text):
        ctx = text[max(0, m.start() - 12): m.end() + 8]
        if "時給" in text[max(0, m.start() - 3): m.start()]:
            continue
        if _TIME_KEY.search(ctx) or best is None:
            best = _to_float(m.group(1))
            if _TIME_KEY.search(ctx):
                return best
    if best is not None:
        return best
    for m in _MINUTES.finditer(text):
        ctx = text[max(0, m.start() - 12): m.end() + 8]
        if _TIME_KEY.search(ctx):
            return _to_float(m.group(1)) / 60
    return None


def estimate(text: str, fee_rate: float = 0.20, chars_per_hour: int = 1500) -> PayEstimate:
    """Estimate total pay, hours and the effective hourly rate after platform fees.

    fee_rate: the platform's system fee taken from the worker (configurable,
    check your platform; 0.20 is a common rate for small jobs).
    chars_per_hour: writing speed used when a per-character job gives no time.
    """
    t = normalize(text)
    notes: list[str] = []
    est = PayEstimate(fee_rate=fee_rate)

    if not (_YEN_SUFFIX.search(t) or _YEN_PREFIX.search(t) or _PER_CHAR.search(t) or _HOURLY.search(t)):
        f = _foreign(t)
        if f:
            est.currency, est.total_yen, est.hourly_yen, est.hours = f
            if est.hourly_yen is not None:
                est.effective_hourly_yen = round(est.hourly_yen * (1 - fee_rate), 2)
                if est.hours:
                    est.total_yen = est.hourly_yen * est.hours
            elif est.total_yen is not None and est.hours:
                est.effective_hourly_yen = round(est.total_yen * (1 - fee_rate) / est.hours, 2)
            if est.total_yen is not None:
                est.net_total_yen = round(est.total_yen * (1 - fee_rate), 2)
            if est.hours is None:
                notes.append("hours not stated (can't compute the effective hourly rate)")
            est.notes = tuple(notes)
            return est

    pc = _PER_CHAR.search(t)
    if pc:
        est.per_char_yen = _to_float(pc.group(1))
        for m in _CHARS.finditer(t):
            if m.start() >= pc.start() and m.start() < pc.end():
                continue
            n = _to_float(m.group(1)) * (10_000 if m.group(2) else 1)
            if n >= 100:
                est.chars = int(n)
                break
        if est.chars:
            est.total_yen = est.per_char_yen * est.chars
            notes.append(f"文字単価{est.per_char_yen:g}円 × {est.chars}文字で計算")

    hm = _HOURLY.search(t)
    if hm:
        est.hourly_yen = _yen(hm.group(1), hm.group(2))

    if est.total_yen is None and est.hourly_yen is None:
        est.total_yen = _first_reward(t)

    est.hours = _hours(t)
    if est.hours is None and est.chars:
        est.hours = round(est.chars / chars_per_hour, 2)
        notes.append(f"作業時間の記載なし: 1時間{chars_per_hour}文字で推定")

    if est.hourly_yen is not None:
        est.effective_hourly_yen = round(est.hourly_yen * (1 - fee_rate))
        if est.hours:
            est.total_yen = est.hourly_yen * est.hours
    elif est.total_yen is not None and est.hours:
        est.effective_hourly_yen = round(est.total_yen * (1 - fee_rate) / est.hours)

    if est.total_yen is not None:
        est.net_total_yen = round(est.total_yen * (1 - fee_rate))
    if est.total_yen is None and est.hourly_yen is None:
        notes.append("報酬額が読み取れませんでした")
    if est.hours is None:
        notes.append("作業時間が読み取れませんでした（実質時給は計算できません）")
    est.notes = tuple(notes)
    return est
