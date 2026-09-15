#!/usr/bin/env python3
"""Reject narrowly defined personal-preparation material in tracked public files."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Rule:
    rule_id: str
    pattern: re.Pattern[str]


# Split literals keep this policy implementation from matching itself. Rules are
# intentionally phrase-based: isolated words can be valid sample-document text.
RULES = (
    Rule(
        "coaching-heading",
        re.compile(
            r"^#{1,6}\s+.*(?:inter"
            + r"view (?:discussion|preparation)|"
            + r"r[ée]sum[ée] (?:language|advice)|role-specific emphasis|career signal)",
            re.I,
        ),
    ),
    Rule(
        "rehearsed-narrative",
        re.compile(r"(?:five-minute reviewer de" + r"mo|concise project nar" + r"rative)", re.I),
    ),
    Rule(
        "role-targeting",
        re.compile(
            r"(?:tailor (?:these|your) bullets to the ro"
            + r"le|lead with .{0,80} for this ro"
            + r"le)",
            re.I,
        ),
    ),
    Rule(
        "career-roadmap",
        re.compile(
            r"(?:roadmap for stronger career sig"
            + r"nal|strongest additional career sig"
            + r"nal)",
            re.I,
        ),
    ),
)

SUSPICIOUS_NAME = re.compile(
    r"(?:^|[-_. ])(?:interview[-_. ]?(?:prep|guide)|resume[-_. ]?(?:advice|guide)|"
    r"career[-_. ]?coaching|talking[-_. ]?points)(?:[-_. ]|$)",
    re.I,
)
ALLOW_RE = re.compile(r"publication-check:\s*allow=([a-z-]+)")


def tracked_paths(root: Path) -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    ).stdout
    return [root / item.decode("utf-8") for item in output.split(b"\0") if item]


def scan_paths(paths: Iterable[Path], root: Path) -> list[tuple[str, int, str]]:
    findings: list[tuple[str, int, str]] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if SUSPICIOUS_NAME.search(relative):
            findings.append((relative, 1, "suspicious-filename"))
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            continue
        if b"\0" in content:
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            allowed = set(ALLOW_RE.findall(line))
            for rule in RULES:
                if rule.rule_id not in allowed and rule.pattern.search(line):
                    findings.append((relative, line_number, rule.rule_id))
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    root = args.root.resolve()
    findings = scan_paths(tracked_paths(root), root)
    for path, line, rule_id in findings:
        print(f"{path}:{line}: publication policy violation [{rule_id}]", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
