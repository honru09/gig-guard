import io
import json
import threading
import unittest
import urllib.request
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path

from gigguard.__main__ import main
from gigguard.web import make_handler

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(list(args))
        return code, buf.getvalue()

    def test_text_report(self):
        code, out = self.run_cli("--no-llm", "check", str(SAMPLES / "01_line_redirect.txt"))
        self.assertEqual(code, 0)
        self.assertIn("HIGH", out)
        self.assertIn("lin.ee", out)

    def test_json_report(self):
        code, out = self.run_cli("--no-llm", "check", "--json", str(SAMPLES / "05_writing.txt"))
        d = json.loads(out)
        self.assertEqual(d["pay"]["chars"], 3000)
        self.assertEqual(d["risk"], "none")

    def test_all_samples_run(self):
        for f in sorted(SAMPLES.glob("*.txt")):
            code, out = self.run_cli("--no-llm", "check", str(f))
            self.assertEqual(code, 0, f)
            self.assertTrue(out.strip(), f)


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(lambda: None, 0.2, 1200))
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def url(self, p):
        return f"http://127.0.0.1:{self.port}{p}"

    def test_index(self):
        with urllib.request.urlopen(self.url("/")) as r:
            self.assertIn("gig-guard", r.read().decode())

    def test_api(self):
        body = json.dumps({"text": "LINEで連絡ください", "no_llm": True}).encode()
        req = urllib.request.Request(self.url("/api/check"), data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            d = json.loads(r.read())
        self.assertEqual(d["risk"], "high")

    def test_form_escapes_input(self):
        data = "text=%3Cscript%3Ealert(1)%3C%2Fscript%3E&nollm=1".encode()
        with urllib.request.urlopen(urllib.request.Request(self.url("/"), data=data)) as r:
            html = r.read().decode()
        self.assertNotIn("<script>alert(1)", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
