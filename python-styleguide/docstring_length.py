"""Flag docstrings that sprawl.

Nothing off the shelf does this: ruff's D rules check docstring structure, and
pylint's docstring-min-length is the inverse. Caps come from python-styleguide.md.

Usage:
    python docstring_length.py --stats PATH...   # distribution, for calibration
    python docstring_length.py PATH...           # check; exits 1 on a hard cap
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

FUNC_SOFT, FUNC_HARD = 8, 20
MOD_SOFT, MOD_HARD = 10, 25

# Loose by design. See the styleguide section on excluded paths.
LOOSE_DIRS = frozenset({"scripts", ".local"})
SKIP_DIRS = (
    frozenset(
        {
            ".venv",
            "venv",
            "node_modules",
            ".git",
            "build",
            "dist",
            "__pycache__",
            ".ruff_cache",
            ".mypy_cache",
        }
    )
    | LOOSE_DIRS
)


@dataclass(frozen=True)
class Doc:
    """One docstring found in a source file."""

    path: Path
    kind: str  # module | class | function
    name: str
    line: int
    doc_lines: int
    body_lines: int  # 0 for modules


def _docstring_node(node: ast.AST) -> ast.Expr | None:
    body = getattr(node, "body", None)
    if not body:
        return None
    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first
    return None


def walk(path: Path) -> Iterator[Doc]:
    """Yield every docstring in one file, measured in physical lines."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return
    targets: list[tuple[str, str, ast.AST]] = [("module", path.name, tree)]
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            targets.append(("function", node.name, node))
        elif isinstance(node, ast.ClassDef):
            targets.append(("class", node.name, node))
    for kind, name, node in targets:
        doc = _docstring_node(node)
        if doc is None or doc.end_lineno is None:
            continue
        end = getattr(node, "end_lineno", None)
        body_lines = 0
        if kind != "module" and end is not None:
            body_lines = max(0, end - doc.end_lineno)
        yield Doc(
            path,
            kind,
            name,
            doc.lineno,
            doc.end_lineno - doc.lineno + 1,
            body_lines,
        )


def iter_py(roots: list[str]) -> Iterator[Path]:
    """Yield .py files under each root, skipping loose and generated dirs."""
    for root in roots:
        base = Path(root)
        if base.is_file():
            # Explicit paths must honour the skip list too: callers pass file lists
            # from git, which happily includes loose directories.
            if base.suffix == ".py" and not any(p in SKIP_DIRS for p in base.parts):
                yield base
            continue
        for found in base.rglob("*.py"):
            if not any(part in SKIP_DIRS for part in found.parts):
                yield found


def _caps(doc: Doc) -> tuple[int, int]:
    if doc.kind == "module":
        return MOD_SOFT, MOD_HARD
    return FUNC_SOFT, FUNC_HARD


def _report_stats(docs: list[Doc]) -> None:
    for kind in ("module", "class", "function"):
        sizes = sorted(d.doc_lines for d in docs if d.kind == kind)
        if not sizes:
            continue
        total = len(sizes)
        marks = " ".join(
            f"p{int(q * 100)}={sizes[min(total - 1, int(total * q))]}"
            for q in (0.5, 0.75, 0.9, 0.95, 0.99)
        )
        print(f"\n{kind}: n={total} {marks} max={sizes[-1]}")
        for cap in (5, 8, 10, 15, 20, 25):
            over = sum(1 for v in sizes if v > cap)
            print(f"    > {cap:>2} lines: {over:>5} ({over * 100 // total:>3}%)")
    funcs = [d for d in docs if d.kind == "function" and d.body_lines]
    bloated = [d for d in funcs if d.doc_lines > d.body_lines]
    if funcs:
        share = len(bloated) * 100 // len(funcs)
        print(f"\nlonger than their own body: {len(bloated)} / {len(funcs)} ({share}%)")
    print("\nworst offenders:")
    for doc in sorted(docs, key=lambda d: -d.doc_lines)[:12]:
        print(
            f"  {doc.doc_lines:>4}  {doc.kind:<8} {doc.name:<34} {doc.path}:{doc.line}"
        )


def _report_violations(docs: list[Doc]) -> int:
    hard_failures = 0
    for doc in docs:
        soft, hard = _caps(doc)
        if doc.doc_lines > hard:
            print(
                f"{doc.path}:{doc.line}: DOC001 {doc.kind} docstring "
                f"{doc.doc_lines} lines > hard cap {hard} ({doc.name})"
            )
            hard_failures += 1
        elif doc.doc_lines > soft:
            print(
                f"{doc.path}:{doc.line}: DOC002 {doc.kind} docstring "
                f"{doc.doc_lines} lines > soft cap {soft} ({doc.name})"
            )
        if doc.body_lines and doc.doc_lines > doc.body_lines:
            print(
                f"{doc.path}:{doc.line}: DOC003 docstring ({doc.doc_lines} lines) "
                f"longer than its body ({doc.body_lines}) ({doc.name})"
            )
            hard_failures += 1
    return hard_failures


def main() -> int:
    """Parse arguments, then report either the distribution or the violations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--stats", action="store_true", help="print distribution only")
    args = parser.parse_args()

    docs = [d for f in iter_py(args.paths) for d in walk(f)]
    if not docs:
        print("no docstrings found")
        return 0
    if args.stats:
        _report_stats(docs)
        return 0
    return 1 if _report_violations(docs) else 0


if __name__ == "__main__":
    sys.exit(main())
