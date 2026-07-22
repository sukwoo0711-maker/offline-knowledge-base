"""Neutral knowledge consistency checker.

This replaces the earlier hard-coded demo script. It does not know about any
specific product, dataset, database schema, game wiki, or user environment.

The tool scans configured documentation folders, extracts rule-like statements,
finds related pairs, and writes review findings. It never edits source files by
itself. Human approval should happen through a normal review or issue workflow.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_PATHS = ("docs", "skills")
DEFAULT_OUTPUT = Path("build/self_heal/findings.json")
# This is a compatibility default, not a claim that the tag is current or optimal.
# Pin an internally approved model tag for reproducible use.
DEFAULT_MODEL = os.environ.get("AUTO_GRILL_MODEL", "qwen2.5-coder:7b")
DEFAULT_MAX_FILE_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_CLAIM_CHARS = 4000
MAX_LLM_RESPONSE_BYTES = 1024 * 1024

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "chroma_db",
    "meili_data",
}

RULE_HINTS = (
    "must",
    "must not",
    "shall",
    "should",
    "required",
    "forbidden",
    "never",
    "always",
    "only",
    "필수",
    "금지",
    "해야",
    "하지 말",
    "사용 금지",
    "반드시",
)

NEGATIVE_HINTS = (
    "must not",
    "should not",
    "forbidden",
    "never",
    "do not",
    "금지",
    "하지 말",
    "사용 금지",
)

POSITIVE_HINTS = (
    "must",
    "shall",
    "required",
    "always",
    "only",
    "필수",
    "해야",
    "반드시",
)


@dataclass(frozen=True)
class Claim:
    id: str
    file: str
    line: int
    text: str
    keywords: list[str]


@dataclass
class Finding:
    severity: str
    verdict: str
    reason: str
    claim_a: Claim
    claim_b: Claim
    overlap: list[str]
    recommendation: str


def inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def iter_text_files(
    root: Path,
    include_paths: Iterable[str],
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    skipped: list[str] | None = None,
) -> Iterable[Path]:
    for rel in include_paths:
        base = (root / rel).resolve()
        if not inside(root, base):
            raise ValueError(f"Scan path escapes repository root: {rel}")
        if not base.exists():
            continue
        if base.is_file():
            if base.stat().st_size <= max_file_bytes:
                yield base
            elif skipped is not None:
                skipped.append(base.relative_to(root).as_posix())
            continue
        for path in base.rglob("*"):
            if path.is_dir():
                continue
            path = path.resolve()
            if not inside(root, path):
                raise ValueError(f"Resolved scan file escapes repository root: {path}")
            if any(part in EXCLUDED_DIRS for part in path.parts):
                continue
            if path.suffix.lower() in {".md", ".txt", ".rst"} and path.stat().st_size <= max_file_bytes:
                yield path
            elif path.suffix.lower() in {".md", ".txt", ".rst"} and skipped is not None:
                skipped.append(path.relative_to(root).as_posix())


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9가-힣_]{2,}", text.lower())
    stop = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "should",
        "must",
        "shall",
        "해야",
        "필수",
        "금지",
    }
    return sorted({token for token in tokens if token not in stop})


def looks_like_rule(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < 12:
        return False
    if any(hint in stripped.lower() for hint in RULE_HINTS):
        return True
    if re.match(r"^[-*]\s+.{12,}", stripped):
        return True
    if re.match(r"^\d+[.)]\s+.{12,}", stripped):
        return True
    return False


def extract_claims(root: Path, files: Iterable[Path]) -> list[Claim]:
    claims: list[Claim] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        in_fence = False
        for line_number, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or not looks_like_rule(line):
                continue
            clean = re.sub(r"^[-*\d.)\s]+", "", line.strip())[:DEFAULT_MAX_CLAIM_CHARS]
            rel = path.relative_to(root).as_posix()
            claim_id = f"{rel}:{line_number}"
            claims.append(
                Claim(
                    id=claim_id,
                    file=rel,
                    line=line_number,
                    text=clean,
                    keywords=tokenize(clean),
                )
            )
    return claims


def related_pairs(claims: list[Claim], min_overlap: int = 2) -> list[tuple[Claim, Claim, list[str]]]:
    pairs: list[tuple[Claim, Claim, list[str]]] = []
    for idx, left in enumerate(claims):
        left_terms = set(left.keywords)
        for right in claims[idx + 1 :]:
            if left.file == right.file:
                same_file_bonus = 1
            else:
                same_file_bonus = 0
            overlap = sorted(left_terms & set(right.keywords))
            if len(overlap) + same_file_bonus >= min_overlap:
                pairs.append((left, right, overlap))
    pairs.sort(key=lambda pair: len(pair[2]), reverse=True)
    return pairs


def polarity(text: str) -> str:
    lowered = text.lower()
    negative = any(hint in lowered for hint in NEGATIVE_HINTS)
    positive = any(hint in lowered for hint in POSITIVE_HINTS)
    if negative and not positive:
        return "negative"
    if positive and not negative:
        return "positive"
    if positive and negative:
        return "mixed"
    return "neutral"


def heuristic_judge(left: Claim, right: Claim, overlap: list[str]) -> Finding:
    left_pol = polarity(left.text)
    right_pol = polarity(right.text)
    if {left_pol, right_pol} == {"positive", "negative"} and overlap:
        return Finding(
            severity="medium",
            verdict="possible_conflict",
            reason="Related claims use opposite requirement polarity.",
            claim_a=left,
            claim_b=right,
            overlap=overlap,
            recommendation="Create an open query and ask the owner which rule has priority.",
        )
    return Finding(
        severity="low",
        verdict="needs_review",
        reason="Related claims share terminology and may duplicate or qualify each other.",
        claim_a=left,
        claim_b=right,
        overlap=overlap,
        recommendation="Review for duplication, scope, and missing condition boundaries.",
    )


def ollama_judge(left: Claim, right: Claim, overlap: list[str], model: str) -> Finding | None:
    if os.environ.get("AUTO_GRILL_USE_LLM") != "1":
        return None
    prompt = f"""You are checking internal documentation consistency.
Return JSON only with keys severity, verdict, reason, recommendation.
verdict must be one of: conflict, possible_conflict, duplicate, consistent, needs_review.

Claim A ({left.id}): {left.text}
Claim B ({right.id}): {right.text}
Shared terms: {", ".join(overlap)}
"""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0, "num_predict": 256},
    }
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read(MAX_LLM_RESPONSE_BYTES + 1)
            if len(body) > MAX_LLM_RESPONSE_BYTES:
                return None
            raw = json.loads(body.decode("utf-8")).get("response", "")
    except Exception:
        return None
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return Finding(
        severity=str(data.get("severity", "low")),
        verdict=str(data.get("verdict", "needs_review")),
        reason=str(data.get("reason", "LLM review returned no reason.")),
        claim_a=left,
        claim_b=right,
        overlap=overlap,
        recommendation=str(data.get("recommendation", "Review manually.")),
    )


def scan(
    root: Path,
    paths: Iterable[str],
    output: Path,
    max_pairs: int,
    model: str,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict:
    root = root.resolve()
    if max_pairs < 0 or max_file_bytes < 1:
        raise ValueError("max_pairs must be non-negative and max_file_bytes must be positive")
    skipped_files: list[str] = []
    files = sorted(set(iter_text_files(root, paths, max_file_bytes, skipped_files)))
    claims = extract_claims(root, files)
    pairs = related_pairs(claims)[:max_pairs]

    findings: list[Finding] = []
    for left, right, overlap in pairs:
        judged = ollama_judge(left, right, overlap, model)
        findings.append(judged or heuristic_judge(left, right, overlap))

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": root.name,  # repo dir name only; avoid leaking absolute local paths
        "paths": list(paths),
        "file_count": len(files),
        "max_file_bytes": max_file_bytes,
        "skipped_oversize_files": sorted(set(skipped_files)),
        "claim_count": len(claims),
        "pair_count": len(pairs),
        "llm_enabled": os.environ.get("AUTO_GRILL_USE_LLM") == "1",
        "findings": [asdict(item) for item in findings],
    }
    output_path = ((root / output) if not output.is_absolute() else output).resolve()
    if not inside(root, output_path):
        raise ValueError(f"Output must stay inside repo: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan internal docs for knowledge consistency findings.")
    parser.add_argument("command", choices=["scan"], help="Command to run.")
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--paths", nargs="*", default=list(DEFAULT_PATHS), help="Relative files or folders to scan.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Relative JSON report path.")
    parser.add_argument("--max-pairs", type=int, default=50, help="Maximum related pairs to review.")
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES,
                        help="Skip larger text files before reading them.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Local Ollama model when AUTO_GRILL_USE_LLM=1.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scan":
        report = scan(
            root=Path(args.root),
            paths=args.paths,
            output=Path(args.output),
            max_pairs=args.max_pairs,
            model=args.model,
            max_file_bytes=args.max_file_bytes,
        )
        print(
            "scan complete: "
            f"files={report['file_count']} claims={report['claim_count']} "
            f"pairs={report['pair_count']} output={args.output}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
