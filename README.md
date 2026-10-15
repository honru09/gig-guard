# gig-guard

**Check a Japanese freelance job post before you reply to it. Runs entirely on your own machine.**

クラウドワークス・ランサーズ・ココナラの案件文やクライアントからのメッセージを貼り付けると、
詐欺っぽいサイン・無償テスト・実質時給をチェックして、サイト内でそのまま送れる返信案を出します。
処理はすべてローカル（Gemma 3 / Ollama）。クライアントとのやり取りを外部のAPIに送りません。

![demo](docs/demo.gif)

## What it does

1. **Rule layer (no model needed).** Deterministic red flags in Japanese and English, with the exact
   quoted evidence:
   off-platform contact (LINE / `lin.ee` / Telegram / email …), the worker paying first (教材費, 登録料),
   unpaid trials (無償テスト), early ID / bank requests (免許証, マイナンバー), investment / crypto pitches,
   too-good-to-be-true pay, rush pressure, and "AI禁止" clauses.
2. **Pay math.** Reads 3,000円 / ¥8,000 / 1.5万円 / 文字単価1円 × 3000文字 / 時給1,500円 and
   "5〜6時間" / "30分程度", subtracts the platform fee, and gives the **effective hourly rate**
   against your own floor.
3. **Gemma read.** A local `gemma3:4b` summarises the job, lists concerns, and suggests questions to
   ask the client. It can *raise* the risk level, never lower a rule hit.
4. **Reply draft.** For clean posts, Gemma's reply draft (screened so it never mentions an outside
   tool, a URL or personal data). Once a rule fires, a fixed, reviewed template instead.

## Quick start

```bash
# 1. Ollama + Gemma (any Gemma 3 build works; 4B runs on a laptop CPU in ~20 s per post)
ollama pull gemma3:4b

# 2. gig-guard (Python 3.10+, no dependencies)
git clone https://github.com/honru09/gig-guard && cd gig-guard
python -m gigguard check samples/01_line_redirect.txt
python -m gigguard serve            # http://127.0.0.1:8765
```

Options: `--no-llm` (rules + pay math only, instant), `--model gemma3:12b`, `--fee 0.165`,
`--min-hourly 1500`, `check --json` for scripting.

## Why rules *and* a model

On the first test, `gemma3:4b` rated a "please add us on LINE to answer the screening survey" message
as **low risk**, and later drafted a reply that politely agreed to an unpaid trial. Small local models
are good at reading the job and asking useful questions; they are not reliable judges of a scam. So
hard facts in the text (a `lin.ee` link is a `lin.ee` link) come from rules, and the model is only
allowed to make things stricter. See `tests/test_llm_and_analyze.py` for those cases pinned as tests.

## Tests

```bash
python -m unittest discover -s tests -v   # 44 tests, no model or network needed
```

## Limits

- Japanese job-post phrasing varies a lot; the rules catch common patterns, not everything.
- The fee rate defaults to 20%; check your platform's current fee and pass `--fee`.
- This is a second opinion, not legal advice. When in doubt, ask the platform's support.

## License

MIT
