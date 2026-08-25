from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", ".cursor"}
SKIP_SUFFIXES = {".joblib", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".html",
    ".json",
    ".ipynb",
    ".yml",
    ".yaml",
    ".txt",
    ".csv",
    ".toml",
    ".ini",
    ".parquet",
}

# Negative assertions in tests may name a carrier in order to forbid it.
ALLOWED_LINE = re.compile(
    r"""assert\s+["'].*(etihad|auh|aed|emirates|qatar|doha|dxb)""",
    re.I,
)

PATTERNS = (
    ("Etihad", re.compile(r"Etihad", re.I)),
    ("AUH hub", re.compile(r"AUH[-–]|AUH →|FIX-AUH|AUHBOM")),
    ("AED", re.compile(r"\bAED\b")),
    ("DXB", re.compile(r"\bDXB\b")),
    ("DOH", re.compile(r"\bDOH\b")),
    ("Qatar", re.compile(r"\bQatar\b")),
    ("Emirates", re.compile(r"\bEmirates\b")),
    ("Doha", re.compile(r"\bDoha\b")),
)


def test_repo_has_no_named_carrier_branding():
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name == "test_no_carrier_branding.py":
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.name not in {".gitignore", ".gitattributes", ".nojekyll"} and path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.suffix.lower() == ".parquet":
            import pandas as pd

            frame = pd.read_parquet(path)
            text = frame.to_csv(index=False)
        else:
            text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(ROOT).as_posix()
        for i, line in enumerate(text.splitlines(), 1):
            if ALLOWED_LINE.search(line):
                continue
            for name, pat in PATTERNS:
                if pat.search(line):
                    hits.append(f"{rel}:{i}: {name}: {line.strip()[:140]}")
    assert hits == []
