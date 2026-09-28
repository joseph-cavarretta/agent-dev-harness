from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "ah-vault-find"

FILLER = " ".join(["filler"] * 50)
PAGES = {
    "wiki/repos/sketches.md": f"""# Sketches

> Probabilistic data structures in Python and C.

**Last updated:** 2026-09-01

## Bloom Filter
A bloom filter answers membership queries with false positives only. {FILLER}

## Deploying
Deployment notes for the benchmark box. {FILLER}

```python
# not a heading
```

### Rollback
Roll back by redeploying the previous tag. {FILLER}

## See Also
- [[wiki/runbooks/monitors]]
""",
    "wiki/runbooks/monitors.md": f"""# Monitors

> Dual monitor runbook.

## Overview
The second display runs over USB-C DP Alt Mode. Mentions bloom once. {FILLER}
""",
    "projects/tool/index.md": f"""# Tool

> A project that links to the sketches page.

## Links
See [[wiki/repos/sketches]] for the data structures. {FILLER}
""",
    "job-search/private.md": f"""# Private

> Personal page.

## Bloom Notes
Bloom filter interview notes. {FILLER}
""",
    "INDEX.md": "# Index\n\n- [[wiki/repos/sketches]] bloom filter\n",
}


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    for rel, text in PAGES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def _run(vault: Path, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(  # noqa: S603
        [SCRIPT, "--vault", str(vault), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) == ok, result.stderr
    return result


def _hits(vault: Path, *args: str) -> list[dict[str, str]]:
    out = _run(vault, *args, "--json").stdout
    return [json.loads(line) for line in out.splitlines()]


def test_heading_match_ranks_first(vault: Path) -> None:
    hits = _hits(vault, "bloom filter")

    assert (hits[0]["path"], hits[0]["anchor"]) == (
        "wiki/repos/sketches.md",
        "Bloom Filter",
    )


def test_stemming_matches_other_word_forms(vault: Path) -> None:
    anchors = {h["anchor"] for h in _hits(vault, "deploy")}

    assert "Deploying" in anchors


def test_falls_back_to_any_word(vault: Path) -> None:
    out = _run(vault, "bloom zebra").stdout

    assert "match any of" in out
    assert "sketches.md#Bloom Filter" in out


def test_default_scope_skips_personal_and_catalogs(vault: Path) -> None:
    paths = {h["path"] for h in _hits(vault, "bloom")}

    assert "job-search/private.md" not in paths
    assert "INDEX.md" not in paths
    assert "job-search/private.md" in {
        h["path"] for h in _hits(vault, "bloom", "--all")
    }


def test_punctuation_does_not_break_the_query(vault: Path) -> None:
    assert _hits(vault, 'DP-Alt "Mode" (USB-C)*')


def test_no_words_is_an_error(vault: Path) -> None:
    assert "no searchable words" in _run(vault, "--", "-- !!", ok=False).stderr


def test_show_returns_one_section_with_subsections(vault: Path) -> None:
    out = _run(vault, "--show", "wiki/repos/sketches#deploying").stdout

    assert out.startswith("## Deploying")
    assert "### Rollback" in out
    assert "See Also" not in out
    assert "Bloom Filter" not in out


def test_code_comments_are_not_headings(vault: Path) -> None:
    out = _run(vault, "--show", "wiki/repos/sketches").stdout

    assert "not a heading" not in out
    assert "Rollback" in out


def test_show_unknown_heading_lists_real_ones(vault: Path) -> None:
    err = _run(vault, "--show", "wiki/repos/sketches#nope", ok=False).stderr

    assert "Bloom Filter" in err


def test_related_finds_links_backlinks_and_two_hops(vault: Path) -> None:
    rels = {(r["relation"], r["path"]) for r in _hits(vault, "--related", "sketches")}

    assert ("links to", "wiki/runbooks/monitors.md") in rels
    assert ("linked from", "projects/tool/index.md") in rels
    assert not any(path == "INDEX.md" for _, path in rels)
    two_hop = {
        r["path"]
        for r in _hits(vault, "--related", "monitors")
        if r["relation"] == "2 hops"
    }
    assert two_hop == {"projects/tool/index.md"}


def test_missing_vault_is_an_error(tmp_path: Path) -> None:
    err = _run(tmp_path / "nope", "bloom", ok=False).stderr

    assert "no vault" in err
