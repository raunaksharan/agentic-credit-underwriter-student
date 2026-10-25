"""Tokenisation shared by the keyword and vector retrievers."""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")

STOPWORDS = frozenset("""
a an and are as at be been by can could do does for from had has have how if in into is it
its may must not of on or shall should such than that the their them then there these this
those to under was were what when where which while who will with would you your we our
""".split())

# Abbreviations underwriters actually type. Expanding them is a deliberate, visible
# design choice: real embedding models learn these; a keyword index never will.
ABBREVIATIONS = {
    "dti": "debt to income ratio",
    "ecoa": "equal credit opportunity act",
    "cip": "customer identification program",
    "atr": "ability to repay",
    "qm": "qualified mortgage",
    "apr": "annual percentage rate",
    "kyc": "customer identification verify identity",
    "ai": "artificial intelligence complex algorithms models",
}


def _stem(tok: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if tok.endswith(suffix) and len(tok) > len(suffix) + 3:
            return tok[: -len(suffix)]
    return tok


def tokenize(text: str, expand: bool = False) -> list[str]:
    toks = _TOKEN.findall(text.lower())
    if expand:
        toks = [w for t in toks for w in (ABBREVIATIONS.get(t, t).split())]
    return [_stem(t) for t in toks if t not in STOPWORDS]
