"""Build dist/LatexEditor/LatexEditor.exe with PyInstaller and self-test it.

One-folder build (starts faster than one-file): the web UI and vendored
libraries are bundled as data. MiKTeX is not bundled; the app uses the
installed one. After building, the .exe is launched with --self-test and must
report that the UI, Monaco, PDF.js and LuaLaTeX are all available.

Usage:  .venv\\Scripts\\python scripts/build_exe.py [--skip-test]
"""

import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
NAME = "LatexEditor"

sys.path.insert(0, str(ROOT / "scripts"))
import make_icon  # noqa: E402


def build():
    if not (ROOT / "web" / "vendor" / "VERSIONS.json").exists():
        sys.exit("web/vendor is missing: run scripts/fetch_vendor.py first")
    icon = BUILD / "icon.ico"
    make_icon.write_ico(icon)

    import PyInstaller.__main__

    PyInstaller.__main__.run([
        str(ROOT / "latexeditor.py"),
        "--name", NAME,
        "--windowed",
        "--noconfirm",
        "--clean",
        "--icon", str(icon),
        "--add-data", f"{ROOT / 'web'};web",
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "pyinstaller"),
        "--specpath", str(BUILD),
        # dev-only files are not needed in the app
        "--exclude-module", "pytest",
    ])
    return DIST / NAME / f"{NAME}.exe"


SAMPLE = "\\documentclass{article}\n\\begin{document}\nHello from the packaged app: àèéíòóú.\n\\end{document}\n"


def self_test(exe: Path) -> bool:
    """Run the built .exe: UI loads, imports + compiles a sample, serves the PDF, spell-checks."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "self-test.json"
        sample = Path(tmp) / "selftest-paper.zip"
        with zipfile.ZipFile(sample, "w") as zf:
            zf.writestr("main.tex", SAMPLE)
        subprocess.run([str(exe), "--self-test", str(out), "--self-test-zip", str(sample)], timeout=300)
        if not out.exists():
            print("Self-test: no report written")
            return False
        report = json.loads(out.read_text(encoding="utf-8"))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report.get("ok", False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-test", action="store_true")
    args = parser.parse_args()
    exe = build()
    size = sum(f.stat().st_size for f in exe.parent.rglob("*") if f.is_file())
    print(f"\nBuilt {exe.relative_to(ROOT)} ({size / 1024**2:.0f} MB folder)")
    if not args.skip_test:
        ok = self_test(exe)
        print("Self-test:", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
