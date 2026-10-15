# gig-guard

**Paste a Japanese freelance job post. Gemma tells you if it's a scam, quotes the exact line that gives it away, and works out what the job really pays. Everything runs on your own machine.**

クラウドワークス・ランサーズ・ココナラの案件文やクライアントのメッセージを貼り付けると、
詐欺のサイン・無償テスト・実質時給をチェックし、根拠になる一文を本文から引用して示します。
処理はすべてローカル（Gemma 4 / Ollama）。クライアントとのやり取りを外部のAPIに送りません。

**▶ Try it in your browser:** https://honru09.github.io/gig-guard/ (rules + pay math run in the tab; connect your local Gemma for the full check)

![demo](docs/demo.gif)

## One command

```bash
ollama pull gemma4:e4b
git clone https://github.com/honru09/gig-guard && cd gig-guard
python -m gigguard serve      # http://127.0.0.1:8765   (or: python -m gigguard check post.txt)
```

Python 3.10+, no dependencies. `--no-llm` gives the rule and pay checks instantly without a model.
Other flags: `--model gemma4:e2b`, `--lang ja|en|both`, `--fee 0.165`, `--min-hourly 1500`, `check --json`.

## How it works

```
 post ──► rule layer (regex, JP+EN) ─────────────┐
   │                                             ├─► verdict: rules can only be escalated
   ├──► pay math (円/万円/文字単価/時給, fees) ───┤
   │                                             │
   └──► Gemma (local, JSON mode) ──► findings ──► quote check ──┘
                                     each with an exact quote,
                                     JP + EN reasons
```

1. **Rules** catch the textbook red flags with zero latency: off-platform contact (LINE / `lin.ee` / Telegram …),
   paying to get work (教材費, 登録料), unpaid trials, early ID / bank / マイナンバー requests, crypto pitches,
   "月30万円" bait, rush pressure, and "AI禁止" clauses.
2. **Gemma reads the post cold** (it is not shown the rule hits) and returns structured findings:
   category, severity, an **exact quote from the post**, and a reason in Japanese and English, plus a
   bilingual summary and questions to ask the client. This is where the scams that don't use the textbook
   words get caught: parcel forwarding (荷物の受け取りと転送), buying bank or SNS accounts, paid fake reviews,
   "let's deal directly to skip the fee", "free test article".
3. **Quote grounding.** Every quote is checked against the post (NFKC, ignoring whitespace and punctuation).
   A finding whose quote is not in the post is thrown away and shown as rejected. Only grounded findings
   can raise the risk; Gemma's overall "risk" field on its own changes nothing.
4. **One-way safety.** Rules are facts in the text; the model can never lower a rule hit. Once anything at
   medium or above fires, the suggested reply is a fixed, reviewed template, because small models tend to be
   polite to a fault (one draft cheerfully agreed to do an unpaid trial). Gemma's reply draft is only used
   for clean posts, and only if it names no outside tool, URL or personal data.

## Which Gemma? A small, honest eval

`eval/fixtures.jsonl`: 20 hand-written posts in Japanese (14 risky, 6 normal). Six of the risky ones avoid
the words the rules look for. The rules were written before this set and were not tuned on it.
8-core CPU, no GPU, Q4_K_M quantisation, `python eval/run_eval.py --models …`.

TABLE

- "Caught only thanks to Gemma" = risky posts the rules alone did not flag.
- Quotes rejected = findings Gemma attributed to text that is not in the post (all from Gemma 3 1B,
  e.g. 「投資はしません。」 on a transcription job). The quote check stopped every one of them.
- The one false flag in every config is the rules' fault: "LINE公式アカウントの運用代行" (a normal job running
  a restaurant's LINE account) trips the LINE rule, and by design the model can't clear a rule hit.
- 20 posts is small. Treat this as a sanity check, not a benchmark. Full per-post output is in
  `eval/results.json`.

## Privacy

Client messages contain names, shop details and sometimes things nobody should have sent. gig-guard never
sends them anywhere: the CLI and local web UI talk only to Ollama on `127.0.0.1`, and the browser demo runs
the same Python code in the tab (Pyodide) and calls your local Ollama directly.

## Tests

```bash
python -m unittest discover -s tests -v   # no model or network needed
```

Covers the rules (including "オンライン" / "ガイドライン" not being read as LINE), pay parsing, JSON
parsing of messy model output, quote grounding, the escalation-only contract, reply safety, the CLI, the
local web UI, and that the browser copy of the code is in sync (`python tools/sync_web.py`).

## Limits

- Japanese job-post phrasing varies a lot; neither the rules nor a 4B model catch everything.
- The fee rate defaults to 20%; check your platform's current fee and pass `--fee`.
- A second opinion, not legal advice. When in doubt, ask the platform's support.

## License

MIT
