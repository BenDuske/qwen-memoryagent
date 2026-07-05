# Aegis MemoryAgent — © 2026 Ben Duske. Licensed under the MIT License (see LICENSE).
"""Make-free, cross-platform keyless reproduce — the `make verify` equivalent.

Judges on Windows (or any box without GNU make) can run the exact same one-command
keyless check that `make verify` runs on Linux/macOS:

    python scripts/verify.py

It runs three steps, no API key required (qwen.embed/qwen.chat are monkeypatched
in the test suite, and eval.py uses deterministic keyless embeddings):

    1. install   — pip install -r requirements.txt
    2. test      — pytest -q   (107 tests)
    3. eval      — python eval.py   (salience 8/8 vs naive 0/8)

Exit code 0 only if all three pass, so it is safe to wire into CI.
Pass --skip-install if deps are already present (e.g. offline judging).
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run(label, args):
    print(f"\n=== {label}: {' '.join(args)} ===", flush=True)
    result = subprocess.run([sys.executable, *args], cwd=REPO)
    if result.returncode != 0:
        print(f"\nVERIFY FAILED at step: {label} (exit {result.returncode})")
        sys.exit(result.returncode)


def main():
    skip_install = "--skip-install" in sys.argv[1:]

    if not skip_install:
        run("install", ["-m", "pip", "install", "-r", "requirements.txt"])
    else:
        print("=== install: skipped (--skip-install) ===")

    run("test", ["-m", "pytest", "-q"])
    run("eval", ["eval.py"])

    print("\nVERIFY OK — tests green, salience budget beats naive recency. (no API key used)")


if __name__ == "__main__":
    main()
