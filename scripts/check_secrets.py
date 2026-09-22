"""Fail CI when tracked source files contain high-confidence secret formats."""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import argparse
import math
import os
from collections import Counter

PATTERNS = {
    "GitLab personal access token": re.compile(r"glpat-[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "Slack token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "AWS access key": re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "Stripe live key": re.compile(r"(?:sk|rk)_live_[A-Za-z0-9]{20,}"),
    "Generic private key PEM": re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
}

SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".pyc", ".pdf"}
ALLOWED_ENV_FILES = {".env.local.example", ".env.test.example"}
ASSIGNED_SECRET = re.compile(
    r"(?im)^\s*[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PRIVATE_KEY|API_KEY)[A-Z0-9_]*\s*[:=]\s*['\"]?([A-Za-z0-9_+/=.-]{32,})['\"]?\s*(?:#.*)?$"
)


def tracked_files() -> list[pathlib.Path]:
    try:
        output = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard"], text=True)
        return [pathlib.Path(line) for line in output.splitlines() if line]
    except FileNotFoundError:
        excluded = {".git", ".runtime", ".venv", "venv", "node_modules", "__pycache__", "build", "staticfiles"}
        files = []
        for root, directories, names in os.walk(pathlib.Path.cwd()):
            directories[:] = [name for name in directories if name not in excluded]
            for name in names:
                if name.startswith(".env") and name not in ALLOWED_ENV_FILES:
                    continue
                files.append(pathlib.Path(root) / name)
        return files


def _entropy(value: str) -> float:
    counts = Counter(value)
    return -sum((count / len(value)) * math.log2(count / len(value)) for count in counts.values())


def _scan_text(*, label: str, text: str, include_entropy: bool) -> list[str]:
    findings = []
    for name, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(f"{label}:{line}: {name}")
    if include_entropy:
        for match in ASSIGNED_SECRET.finditer(text):
            candidate = match.group(1)
            if _entropy(candidate) >= 4.3 and not any(marker in candidate.lower() for marker in ("example", "placeholder", "changeme")):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{label}:{line}: high-entropy assigned secret")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", action="store_true", help="Scan removed lines across reachable Git history.")
    args = parser.parse_args()
    findings = []
    for path in tracked_files():
        normalized = path.as_posix()
        if path.name.startswith(".env") and path.name not in ALLOWED_ENV_FILES:
            findings.append(f"{normalized}:1: tracked environment file")
            continue
        if path.suffix.lower() in SKIP_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(_scan_text(label=normalized, text=text, include_entropy=True))
    if args.history:
        try:
            history = subprocess.run(
                ["git", "log", "--all", "-p", "--no-ext-diff", "--pretty=format:commit:%H"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
            ).stdout
        except FileNotFoundError:
            print("Git is required for --history.", file=sys.stderr)
            return 2
        removed_lines = "\n".join(line[1:] for line in history.splitlines() if line.startswith("-") and not line.startswith("---"))
        findings.extend(_scan_text(label="git-history", text=removed_lines, include_entropy=False))
    if findings:
        print("Potential secrets detected:", file=sys.stderr)
        print("\n".join(findings), file=sys.stderr)
        return 1
    print("No secrets detected in tracked/pending sources" + (" or reachable history." if args.history else "."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
