"""Copy the gigguard package into docs/py/ for the GitHub Pages demo (Pyodide).

The browser demo runs the exact same Python code as the CLI. tests/test_web_demo.py
fails if the copies drift, so run this after changing gigguard/.
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ["__init__.py", "rules.py", "pay.py", "llm.py", "analyze.py", "render.py"]


def main():
    dst = ROOT / "docs" / "py" / "gigguard"
    dst.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        shutil.copyfile(ROOT / "gigguard" / f, dst / f)
    print("synced", len(FILES), "files to", dst.relative_to(ROOT))


if __name__ == "__main__":
    main()
