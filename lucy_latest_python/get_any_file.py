"""Fuzzy file lookup helper.

Usage:
    python get_any_file.py "rough file name"
    python get_any_file.py "invoice" --root "C:\\Users\\ragha\\Documents"
    python get_any_file.py "report" --max-results 5

The main entry point is `get_any_file()`, which returns the best matching
files for a rough name using filename similarity, substring checks, and a
light weight token overlap score.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class FileMatch:
    path: Path
    score: float


def _normalize(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


def _tokenize(text: str) -> list[str]:
    cleaned = []
    current = []
    for ch in text.lower():
        if ch.isalnum():
            current.append(ch)
        else:
            if current:
                cleaned.append("".join(current))
                current = []
    if current:
        cleaned.append("".join(current))
    return cleaned


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _score_match(query: str, path: Path) -> float:
    query_norm = _normalize(query)
    if not query_norm:
        return 0.0

    name = path.name
    stem = path.stem
    full_path = str(path)

    name_norm = _normalize(name)
    stem_norm = _normalize(stem)
    path_norm = _normalize(full_path)

    exact_bonus = 0.0
    if query_norm == name_norm or query_norm == stem_norm:
        exact_bonus = 1.0
    elif query_norm in name_norm or query_norm in stem_norm:
        exact_bonus = 0.92
    elif query_norm in path_norm:
        exact_bonus = 0.75

    ratios = [
        _similarity(query_norm, name_norm),
        _similarity(query_norm, stem_norm),
        _similarity(query_norm, path_norm),
    ]

    query_tokens = _tokenize(query)
    name_tokens = _tokenize(name)
    stem_tokens = _tokenize(stem)

    token_hits = 0
    if query_tokens:
        searchable_tokens = set(name_tokens) | set(stem_tokens)
        token_hits = sum(1 for token in query_tokens if token in searchable_tokens)

    token_score = (token_hits / len(query_tokens)) if query_tokens else 0.0
    best_ratio = max(ratios)

    score = max(best_ratio, exact_bonus)
    score = max(score, 0.15 * token_score + 0.85 * best_ratio)

    # Prefer file names over long path-only matches.
    path_depth_penalty = min(max(len(path.parts) - 1, 0) * 0.01, 0.12)
    score = max(0.0, score - path_depth_penalty)

    return round(score, 6)


def _iter_files(root: Path, include_hidden: bool = False) -> Iterable[Path]:
    for current_root, dirnames, filenames in os.walk(root):
        current_path = Path(current_root)

        if not include_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            filenames = [f for f in filenames if not f.startswith(".")]

        for filename in filenames:
            yield current_path / filename


def get_any_file(
    rough_name: str,
    root: str | Path = ".",
    *,
    max_results: int = 10,
    include_hidden: bool = False,
    min_score: float = 0.15,
) -> list[FileMatch]:
    """Return the best fuzzy matches for `rough_name` under `root`."""

    root_path = Path(root).expanduser().resolve()
    matches: list[FileMatch] = []

    for path in _iter_files(root_path, include_hidden=include_hidden):
        score = _score_match(rough_name, path)
        if score >= min_score:
            matches.append(FileMatch(path=path, score=score))

    matches.sort(key=lambda item: (-item.score, len(item.path.parts), item.path.name.lower()))
    return matches[:max_results]


def _format_matches(matches: list[FileMatch], as_json: bool) -> str:
    if as_json:
        return json.dumps(
            [
                {"path": str(match.path), "score": match.score}
                for match in matches
            ],
            indent=2,
        )

    if not matches:
        return "No files matched."

    lines = []
    for index, match in enumerate(matches, start=1):
        lines.append(f"{index}. {match.path}  (score: {match.score:.3f})")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find files by rough name using fuzzy matching."
    )
    parser.add_argument("query", help="A rough file name to search for.")
    parser.add_argument(
        "--root",
        default=".",
        help="Directory to search from. Defaults to the current directory.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Maximum number of matches to show.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.15,
        help="Minimum match score to include a file.",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden files and folders.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print results as JSON.",
    )

    args = parser.parse_args()
    matches = get_any_file(
        args.query,
        root=args.root,
        max_results=args.max_results,
        include_hidden=args.include_hidden,
        min_score=args.min_score,
    )
    print(_format_matches(matches, args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
