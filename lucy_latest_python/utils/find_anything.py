"""
lucy_shallow_multi_search.py - Multi-directory shallow search module for Lucy.
Searches specified target directories in fixed order without inspecting subfolders.
"""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import List, Optional, Set, Tuple


@dataclass
class SearchResult:
    score: int
    type: str
    name: str
    path: str
    search_root: str
    root_rank: int


def normalize_lucy_name(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def get_lucy_collapsed_name(text: str) -> str:
    return re.sub(r"\s+", "", normalize_lucy_name(text))


def get_lucy_tokens(text: str) -> List[str]:
    normalized = normalize_lucy_name(text)
    return [token for token in normalized.split() if token]


def get_lucy_token_variants(token: str) -> Set[str]:
    variants: Set[str] = set()
    if not token:
        return variants

    variants.add(token)

    if token.endswith("ies") and len(token) > 4:
        variants.add(token[:-3] + "y")
    elif token.endswith("y") and len(token) > 3:
        variants.add(token[:-1] + "ies")

    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        variants.add(token[:-1])
    elif len(token) > 2:
        variants.add(token + "s")

    return variants


def get_lucy_edit_distance(left: str, right: str, limit: int = 8) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    if abs(len(left) - len(right)) > limit:
        return limit + 1

    previous = list(range(len(right) + 1))
    current = [0] * (len(right) + 1)

    for i in range(1, len(left) + 1):
        current[0] = i
        row_min = current[0]

        for j in range(1, len(right) + 1):
            cost = 0 if left[i - 1] == right[j - 1] else 1
            current[j] = min(
                current[j - 1] + 1,
                previous[j] + 1,
                previous[j - 1] + cost,
            )
            row_min = min(row_min, current[j])

        if row_min > limit:
            return limit + 1

        previous, current = current, previous

    return previous[len(right)]


def test_lucy_token_match(candidate_token: str, search_token: str) -> bool:
    if len(candidate_token) < 3 and len(search_token) > 2:
        return False

    candidate_variants = get_lucy_token_variants(candidate_token)
    search_variants = get_lucy_token_variants(search_token)

    for c_var in candidate_variants:
        for s_var in search_variants:
            if (
                c_var == s_var
                or (len(s_var) >= 3 and s_var in c_var)
                or (len(c_var) >= 3 and s_var in c_var)
            ):
                return True

            longer = max(len(c_var), len(s_var))
            shorter = min(len(c_var), len(s_var))
            if longer > 0 and (shorter / longer) < 0.78:
                continue

            limit = 1 if longer <= 5 else 2
            if get_lucy_edit_distance(c_var, s_var, limit) <= limit:
                return True

    return False


def get_lucy_match_score(candidate: str, search_name: str) -> Optional[int]:
    if not candidate or not search_name:
        return None

    if candidate.lower() == search_name.lower():
        return 100

    candidate_collapsed = get_lucy_collapsed_name(candidate)
    search_collapsed = get_lucy_collapsed_name(search_name)
    candidate_tokens = get_lucy_tokens(candidate)
    search_tokens = get_lucy_tokens(search_name)

    if not search_collapsed:
        return None

    if candidate_collapsed == search_collapsed:
        return 100

    if search_collapsed in candidate_collapsed:
        return 92

    if search_tokens:
        matched_tokens = 0
        for s_token in search_tokens:
            for c_token in candidate_tokens:
                if test_lucy_token_match(c_token, s_token):
                    matched_tokens += 1
                    break

        if matched_tokens == len(search_tokens):
            return 86

        if matched_tokens > 0 and len(search_tokens) > 1:
            return int(38 + (24 * matched_tokens / len(search_tokens)))

    length = max(len(candidate_collapsed), len(search_collapsed))
    limit = max(1, min(8, int((length * 0.28) + 0.5)))
    distance = get_lucy_edit_distance(
        candidate_collapsed, search_collapsed, limit
    )
    if distance <= limit:
        return max(55, int(88 - (38 * distance / length)))

    return None


def get_default_search_roots() -> List[Tuple[str, Path]]:
    """Returns the ordered default profile directories matching the PS1 target scope."""
    home = Path.home()
    roots = [
        ("Downloads", home / "Downloads"),
        ("Desktop", home / "Desktop"),
        ("Documents", home / "Documents"),
        ("Pictures", home / "Pictures"),
        ("Music", home / "Music"),
        ("Videos", home / "Videos"),
    ]
    return [(label, path) for label, path in roots if path.exists()]


def search_lucy_directories(
    search_name: str,
    roots: Optional[List[Tuple[str, Path]]] = None,
    min_score: int = 55,
    limit: int = 100,
) -> List[SearchResult]:
    """
    Performs a shallow search across multiple ordered directories.
    Only inspects direct contents of each directory (no subfolder recursion).
    """
    if roots is None:
        roots = get_default_search_roots()

    results: List[SearchResult] = []
    query = search_name.strip()

    if not query:
        return results

    for root_rank, (label, root_path) in enumerate(roots):
        root = Path(root_path).resolve()
        if not root.exists() or not root.is_dir():
            continue

        try:
            # Iterates ONLY immediate items in the folder (shallow search)
            for item in root.iterdir():
                if "bin" in item.parts or "obj" in item.parts:
                    continue

                score = get_lucy_match_score(item.name, query)
                if score is None or score < min_score:
                    continue

                results.append(
                    SearchResult(
                        score=score,
                        type="Folder" if item.is_dir() else "File",
                        name=item.name,
                        path=str(item),
                        search_root=label,
                        root_rank=root_rank,
                    )
                )
        except PermissionError:
            continue

    # Order by highest score first, then root directory precedence (root_rank), then type and name
    results.sort(key=lambda x: (-x.score, x.root_rank, x.type, x.name))
    return results[:limit]


def process_multi_search(
    input_text: str,
    roots: Optional[List[Tuple[str, Path]]] = None,
    min_score: int = 55,
    limit: int = 50,
) -> List[SearchResult]:
    """Helper runner function to format and print search results to stdout."""
    query = input_text.strip()

    if not query:
        print("\n[Clearing Results] Input empty.")
        return []

    print(f"\n{'=' * 70}")
    print(f" Query: '{query}'")
    print(f"{'=' * 70}")

    results = search_lucy_directories(
        query, roots=roots, min_score=min_score, limit=limit
    )

    if not results:
        print(" No matches found.")
    else:
        for res in results:
            print(
                f"[{res.search_root:<9}] {res.type:<6}  [{res.score:>3}]  {res.name} -> ({res.path})"
            )
        print(f"\nTotal Matches: {len(results)}")

    return results


if __name__ == "__main__":
    # Test run across standard user profile directories
    process_multi_search("Refesume")