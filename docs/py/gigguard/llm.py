"""Ollama client (stdlib only), the Gemma prompt, and strict parsing of its JSON.

Gemma is asked for structured findings, each tied to an exact quote from the
post. parse_model_json() only validates *shape*; analyze.ground_findings() then
checks every quote against the post and throws away the ones that are not there.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Optional, Protocol

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("GIGGUARD_MODEL", "gemma4:e4b")

CATEGORIES = (
    "off_platform_contact",
    "upfront_payment",
    "unpaid_trial",
    "personal_documents",
    "too_good_to_be_true",
    "crypto_investment",
    "ai_banned",
    "rushed_pressure",
    "illegal_or_mule",
    "vague_scope",
    "low_pay",
    "other",
)
_RISKS = ("low", "medium", "high")

SYSTEM_PROMPT = """You are a careful advisor for freelancers. You read job posts and client messages from any
platform (Upwork, Fiverr, Freelancer.com, CrowdWorks, Lancers, Coconala) or from direct DMs and e-mail.
The text may be in English, Japanese or Chinese. Read it from the worker's side and return ONLY this JSON:

{
  "risk": "low" | "medium" | "high",
  "job_type_en": "a few words, e.g. 'store list research'",
  "summary_en": "1-2 sentences in English",
  "summary_ja": "1-2 sentences in natural Japanese",
  "summary_zh": "1-2 sentences in Simplified Chinese",
  "findings": [
    {
      "category": one of %s,
      "severity": "low" | "medium" | "high",
      "quote": "an EXACT substring copied from the post, 4-40 characters",
      "why_en": "short reason in English",
      "why_ja": "short reason in Japanese",
      "why_zh": "short reason in Simplified Chinese"
    }
  ],
  "questions": ["polite questions to ask the client before accepting, in the post's language"],
  "reply": "a polite reply the worker can send inside the platform, in the post's language"
}

Rules:
- Every finding MUST quote the post exactly. If you cannot quote it, do not report it.
- Moving contact or payment off the platform (WhatsApp, Telegram, WeChat, LINE, Instagram DM, personal
  e-mail, "to avoid the fees") breaks platform terms and is the usual first step of a scam: high.
- The worker paying anything (deposit, training, starter kit), early ID / bank / SSN requests,
  investment or crypto: high.
- Forwarding parcels, cashing checks, lending or opening accounts, buying/selling accounts, fake reviews,
  receiving and re-sending money: illegal_or_mule, high.
- Unpaid tests or free samples: medium. Pay far below a fair rate: low_pay, medium.
- Normal jobs are normal. A video call for a briefing, words like "online" or "guidelines", or a job
  ABOUT a messaging app are not red flags. If nothing is wrong, return an empty findings list and risk "low".
- "reply" must not mention any outside tool, URL, phone number or e-mail address.
""" % (", ".join(f'"{c}"' for c in CATEGORIES))


class ChatModel(Protocol):
    name: str

    def chat(self, system: str, user: str) -> str: ...


class OllamaModel:
    def __init__(self, model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST, timeout: float = 300.0, retries: int = 2):
        self.name = model
        self.retries = retries
        self.host = host.rstrip("/")
        self.timeout = timeout

    def chat(self, system: str, user: str) -> str:
        body = json.dumps(
            {
                "model": self.name,
                "stream": False,
                "format": "json",
                "think": False,
                "options": {"temperature": 0.1, "num_ctx": 4096},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode()
        req = urllib.request.Request(
            self.host + "/api/chat", data=body, headers={"Content-Type": "application/json"}
        )
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.load(resp)
                return data.get("message", {}).get("content", "")
            except urllib.error.HTTPError as e:
                # Ollama answers 500 while it is still swapping a model into memory
                if e.code < 500 or attempt == self.retries:
                    raise
                last = e
                time.sleep(2 * (attempt + 1))
        raise last  # pragma: no cover

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(self.host + "/api/tags", timeout=3) as resp:
                tags = json.load(resp)
        except (urllib.error.URLError, OSError, ValueError):
            return False
        names = {m.get("name") for m in tags.get("models", [])}
        return self.name in names or f"{self.name}:latest" in names


def _first_json_object(text: str) -> Optional[str]:
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start: i + 1]
        start = text.find("{", start + 1)
    return None


def _s(v) -> Optional[str]:
    return v.strip() if isinstance(v, str) and v.strip() else None


def _str_list(v) -> list[str]:
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    return [s.strip() for s in v if isinstance(s, str) and s.strip()][:6]


def _findings(v) -> list[dict]:
    out = []
    if not isinstance(v, list):
        return out
    for f in v[:12]:
        if not isinstance(f, dict):
            continue
        quote = _s(f.get("quote"))
        if not quote:
            continue
        cat = str(f.get("category", "other")).strip()
        sev = str(f.get("severity", "")).strip().lower()
        out.append(
            {
                "category": cat if cat in CATEGORIES else "other",
                "severity": sev if sev in _RISKS else "low",
                "quote": quote,
                "why_ja": _s(f.get("why_ja")),
                "why_en": _s(f.get("why_en")),
                "why_zh": _s(f.get("why_zh")),
            }
        )
    return out


def parse_model_json(raw: str) -> Optional[dict]:
    """Return a cleaned dict, or None if the reply holds nothing usable."""
    blob = _first_json_object(raw or "")
    if blob is None:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    risk = str(data.get("risk", "")).strip().lower()
    out = {
        "risk": risk if risk in _RISKS else None,
        "job_type_en": _s(data.get("job_type_en")),
        "summary_ja": _s(data.get("summary_ja")),
        "summary_en": _s(data.get("summary_en")),
        "summary_zh": _s(data.get("summary_zh")),
        "findings": _findings(data.get("findings")),
        "questions_ja": _str_list(data.get("questions") or data.get("questions_ja")),
        "reply_ja": _s(data.get("reply") or data.get("reply_ja")),
    }
    if not any([out["risk"], out["summary_ja"], out["summary_en"], out["findings"], out["reply_ja"]]):
        return None
    return out


def build_user_prompt(text: str) -> str:
    # Rule hits are deliberately NOT passed in: the model reads the post cold, so
    # what it finds is an independent second opinion (and evals measure it fairly).
    return "Job post / client message:\n<<<\n" + text.strip() + "\n>>>"
