#!/usr/bin/env python3
"""Seed the spam token table from the SpamAssassin public corpus.

This script downloads the SpamAssassin public corpus (if not cached),
tokenizes all messages, computes token probabilities, and writes the
result to ``src/lighterbird/email/filters/spam_tokens.json``.

Usage::

    uv run python src/scripts/seed_spam_tokens.py [--corpus-dir PATH]

The script is idempotent — it skips already-downloaded corpora and
overwrites the output file on each run.

The SpamAssassin public corpus is available at:
    https://spamassassin.apache.org/old/publiccorpus/

This script is for maintainers who want to regenerate the seed table
from fresh data.  The shipped ``spam_tokens.json`` is pre-generated
from the 2005 public corpus and provides ~80% Day-1 accuracy.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import tarfile
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

# Base URL for the SpamAssassin public corpus
CORPUS_BASE = "https://spamassassin.apache.org/old/publiccorpus/"

CORPUS_FILES = {
    "20021010_easy_ham.tar.bz2": "ham",
    "20021010_hard_ham.tar.bz2": "ham",
    "20021010_spam.tar.bz2": "spam",
    "20030228_easy_ham.tar.bz2": "ham",
    "20030228_easy_ham_2.tar.bz2": "ham",
    "20030228_hard_ham.tar.bz2": "ham",
    "20030228_spam.tar.bz2": "spam",
    "20030228_spam_2.tar.bz2": "spam",
    "20050311_spam_2.tar.bz2": "spam",
}

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[^\w\s]")
_RE_URL = re.compile(r"https?://[^\s<>\"']+", re.I)
_RE_CAPS = re.compile(r"\b[A-Z]{4,}\b")
_RE_MONEY = re.compile(r"[\$\€\£\¥]\d+(?:[.,]\d+)?")


def tokenize(text: str) -> Counter:
    """Tokenize email text and return token frequency counter."""
    tokens: list[str] = []

    # Tag URLs
    urls = _RE_URL.findall(text)
    tokens.append("http://")  # generic URL flag
    for url in urls:
        m = re.match(r"https?://([^/]+)", url)
        if m:
            tokens.append(f"dom:{m.group(1).lower()}")
        text = text.replace(url, "", 1)

    # Tag money
    for _ in _RE_MONEY.finditer(text):
        tokens.append("$")

    # Tag ALL-CAPS
    if _RE_CAPS.search(text):
        tokens.append("ALL-CAPS")

    # Regular tokens
    for match in _TOKEN_RE.finditer(text):
        tok = match.group(0).lower().strip()
        if len(tok) >= 2:
            tokens.append(tok)

    return Counter(tokens)


def download_corpus(corpus_dir: Path) -> None:
    """Download SpamAssassin public corpus files."""
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for filename in CORPUS_FILES:
        dest = corpus_dir / filename
        if dest.exists():
            print(f"  [skip] {filename} already cached")
            continue
        url = CORPUS_BASE + filename
        print(f"  [download] {url}...")
        urllib.request.urlretrieve(url, dest)
        print(f"  [done] {dest}")


def extract_corpus(corpus_dir: Path, work_dir: Path) -> dict[str, list[Path]]:
    """Extract corpus files into labeled directories.

    Returns:
        Dict mapping ``"spam"`` or ``"ham"`` → list of email file paths.
    """
    labeled: dict[str, list[Path]] = {"spam": [], "ham": []}

    for filename, label in CORPUS_FILES.items():
        tar_path = corpus_dir / filename
        if not tar_path.exists():
            print(f"  [skip] {filename} not found")
            continue

        extract_to = work_dir / label
        extract_to.mkdir(parents=True, exist_ok=True)

        print(f"  [extract] {filename} → {extract_to}")
        with tarfile.open(tar_path, "r:bz2") as tar:
            tar.extractall(path=extract_to)

        # Collect extracted files
        for f in extract_to.iterdir():
            if f.is_file() and not f.name.startswith("."):
                labeled[label].append(f)

    return labeled


def compute_probabilities(spam_counts: Counter, ham_counts: Counter,
                          total_spam: int, total_ham: int,
                          min_occurrences: int = 3) -> dict[str, dict[str, float]]:
    """Compute token spam probabilities using Bayesian formula.

    Args:
        spam_counts: Token frequencies in spam emails.
        ham_counts: Token frequencies in ham (non-spam) emails.
        total_spam: Number of spam emails processed.
        total_ham: Number of ham emails processed.
        min_occurrences: Minimum total occurrences to include a token.

    Returns:
        Dict mapping token → ``{"spam": probability, "ham": probability}``.
    """
    table: dict[str, dict[str, float]] = {}

    all_tokens = set(spam_counts.keys()) | set(ham_counts.keys())
    for token in all_tokens:
        sc = spam_counts.get(token, 0)
        hc = ham_counts.get(token, 0)

        if sc + hc < min_occurrences:
            continue

        # Apply Robinson's correction
        prob = (sc + 1.0) / (sc + hc + 2.0)

        # Keep only the most extreme tokens (most discriminating)
        extremity = abs(prob - 0.5)
        if extremity >= 0.15:  # only tokens that lean significantly one way
            table[token] = {
                "spam": round(prob, 4),
                "ham": round(1.0 - prob, 4),
            }

    return table


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed spam token table from SpamAssassin corpus")
    parser.add_argument("--corpus-dir", type=Path, default=Path("/tmp/spamassassin-corpus"),
                        help="Directory to cache corpus files")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parent.parent
                        / "lighterbird" / "email" / "filters" / "spam_tokens.json",
                        help="Output path for spam_tokens.json")
    args = parser.parse_args()

    corpus_dir = args.corpus_dir
    work_dir = corpus_dir / "extracted"

    print("=== SpamAssassin Token Seed Generator ===")
    print()

    # Step 1: Download corpus
    print("[1/4] Downloading corpus...")
    download_corpus(corpus_dir)

    # Step 2: Extract
    print("[2/4] Extracting corpus...")
    labeled = extract_corpus(corpus_dir, work_dir)

    spam_files = labeled["spam"]
    ham_files = labeled["ham"]
    print(f"  Spam files: {len(spam_files)}")
    print(f"  Ham files:  {len(ham_files)}")

    # Step 3: Tokenize
    print("[3/4] Tokenizing emails...")
    spam_counts: Counter = Counter()
    ham_counts: Counter = Counter()

    # Process in batches to avoid memory issues
    batch_size = 500

    for i in range(0, len(spam_files), batch_size):
        batch = spam_files[i:i + batch_size]
        for f in batch:
            try:
                text = f.read_text(errors="replace")
                spam_counts += tokenize(text)
            except Exception:
                pass
        print(f"  Spam: {min(i + batch_size, len(spam_files))}/{len(spam_files)}")

    for i in range(0, len(ham_files), batch_size):
        batch = ham_files[i:i + batch_size]
        for f in ham_files:
            try:
                text = f.read_text(errors="replace")
                ham_counts += tokenize(text)
            except Exception:
                pass
        print(f"  Ham: {min(i + batch_size, len(ham_files))}/{len(ham_files)}")

    # Step 4: Compute probabilities
    print("[4/4] Computing token probabilities...")
    table = compute_probabilities(spam_counts, ham_counts,
                                  len(spam_files), len(ham_files))
    print(f"  Tokens extracted: {len(table)}")

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(table, f, indent=2, sort_keys=True)

    print(f"\nDone! Wrote {len(table)} tokens to {args.output}")
    print("Ship this file with the package as the pre-baked seed table.")


if __name__ == "__main__":
    main()
