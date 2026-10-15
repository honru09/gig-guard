"""A one-page local web UI: paste a post, get the report. Binds to 127.0.0.1 only."""

from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .analyze import analyze
from .render import text_report

PAGE = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>gig-guard</title>
<style>
body{{font-family:system-ui,"Hiragino Sans","Noto Sans JP",sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#1f2328}}
textarea{{width:100%;height:12rem;font:inherit;padding:.6rem;box-sizing:border-box}}
button{{font:inherit;padding:.5rem 1.2rem;margin-top:.5rem;cursor:pointer}}
pre{{font-size:15px;font-family:ui-monospace,"Noto Sans Mono CJK JP",monospace;white-space:pre-wrap;background:#f6f8fa;padding:1rem;border-radius:8px;line-height:1.5}}
small{{color:#59636e}}
</style></head><body>
<h1>gig-guard</h1>
<p>Paste a job post or client message (EN / 日本語 / 中文).<br><small>すべてこのPCの中で処理されます / everything runs on this machine (Gemma via Ollama).</small></p>
<form method="post" action="/">
<textarea name="text" placeholder="例: 応募ありがとうございます。詳細はLINEでお送りします…">{text}</textarea>
<label><input type="checkbox" name="nollm" value="1" {nollm}> ルールのみ / rules only</label>
<select name="lang"><option value="all">EN + 日本語 + 中文</option><option value="both">EN + 日本語</option><option value="zh" {zh}>中文</option><option value="ja" {ja}>日本語</option><option value="en" {en}>English</option></select><br>
<button type="submit">チェック</button>
</form>
{result}
</body></html>"""


def make_handler(model_factory, fee_rate: float, min_hourly: int):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep the terminal quiet
            pass

        def do_GET(self):
            if self.path not in ("/", "/index.html"):
                return self._send(404, b"not found", "text/plain")
            page = PAGE.format(text="", nollm="", result="", ja="", en="", zh="")
            self._send(200, page.encode(), "text/html; charset=utf-8")

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 200_000:
                return self._send(413, b"too large", "text/plain")
            raw = self.rfile.read(n).decode("utf-8", "replace")
            if self.path == "/api/check":
                try:
                    data = json.loads(raw or "{}")
                except json.JSONDecodeError:
                    return self._send(400, b'{"error":"bad json"}', "application/json")
                text = str(data.get("text", ""))
                model = None if data.get("no_llm") else model_factory()
                rep = analyze(text, model=model, fee_rate=fee_rate, min_hourly_yen=min_hourly)
                body = json.dumps(rep.to_dict(), ensure_ascii=False).encode()
                return self._send(200, body, "application/json; charset=utf-8")
            form = parse_qs(raw)
            text = form.get("text", [""])[0]
            nollm = form.get("nollm", [""])[0] == "1"
            lang = form.get("lang", ["all"])[0]
            lang = lang if lang in ("ja", "en", "zh", "both", "all") else "all"
            result = ""
            if text.strip():
                rep = analyze(text, model=None if nollm else model_factory(), fee_rate=fee_rate, min_hourly_yen=min_hourly)
                result = "<pre>" + html.escape(text_report(rep, lang)) + "</pre>"
            page = PAGE.format(text=html.escape(text), nollm="checked" if nollm else "", result=result,
                               ja="selected" if lang == "ja" else "", en="selected" if lang == "en" else "", zh="selected" if lang == "zh" else "")
            self._send(200, page.encode(), "text/html; charset=utf-8")

    return Handler


def serve(port: int, model_factory, fee_rate: float, min_hourly: int) -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(model_factory, fee_rate, min_hourly))
    print(f"gig-guard: http://127.0.0.1:{port}/  (Ctrl+C で終了)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
