"""Tiny Ollama client (stdlib only) and the prompt for the nuanced read.

The model is asked for strict JSON. Small local models sometimes wrap JSON in
prose or code fences, so parse_model_json() digs the first object out and
validates every field; anything unusable becomes None and the rule layer stands
on its own.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Optional, Protocol

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("GIGGUARD_MODEL", "gemma3:4b")

SYSTEM_PROMPT = """あなたは日本のクラウドソーシング（クラウドワークス、ランサーズ、ココナラ等）で働くフリーランスの相談役です。
受け取った案件文・クライアントのメッセージを読み、応募者の立場で分析してください。

必ず次のJSONだけを返してください（説明文やコードブロックは不要）:
{
  "risk": "low" | "medium" | "high",
  "summary_ja": "案件の中身を1〜2文で",
  "concerns_ja": ["気になる点", ...],
  "questions_ja": ["応募前にクライアントに確認すべき質問", ...],
  "reply_ja": "サイト内メッセージでそのまま送れる丁寧な返信文"
}

判断のルール:
- LINE・Telegram・メール等、サイト外での連絡に誘導するのは規約違反で、詐欺の典型です（risk は high）。
- 応募者にお金を払わせる、身分証や口座を早く求める、投資や仮想通貨の話は high。
- 無報酬のテストは medium 以上。
- 返信文はサイト内でのやり取りを前提にし、外部リンクを開かない・個人情報を送らない内容にしてください。
- 返信文には LINE などの外部ツール名、URL、連絡先を書かないでください。
- 怪しい場合の返信は、角が立たない形で「サイト内でのやり取り」「有償テスト」等を提案してください。
"""

_RISKS = ("low", "medium", "high")


class ChatModel(Protocol):
    name: str

    def chat(self, system: str, user: str) -> str: ...


class OllamaModel:
    def __init__(self, model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST, timeout: float = 180.0):
        self.name = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def chat(self, system: str, user: str) -> str:
        body = json.dumps(
            {
                "model": self.name,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.2},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode()
        req = urllib.request.Request(
            self.host + "/api/chat", data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.load(resp)
        return data.get("message", {}).get("content", "")

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


def _str_list(v) -> list[str]:
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    return [s.strip() for s in v if isinstance(s, str) and s.strip()][:6]


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
        "summary_ja": data.get("summary_ja") if isinstance(data.get("summary_ja"), str) else None,
        "concerns_ja": _str_list(data.get("concerns_ja")),
        "questions_ja": _str_list(data.get("questions_ja")),
        "reply_ja": data.get("reply_ja") if isinstance(data.get("reply_ja"), str) else None,
    }
    if not any([out["risk"], out["summary_ja"], out["concerns_ja"], out["reply_ja"]]):
        return None
    return out


def build_user_prompt(text: str, rule_titles: list[str]) -> str:
    hint = ""
    if rule_titles:
        hint = "\n\n（参考: ルールチェックで検出済みの項目: " + "、".join(rule_titles) + "）"
    return "次の案件文・メッセージを分析してください。\n\n---\n" + text.strip() + "\n---" + hint
