"""Download the public regulatory corpus listed in data/corpus/manifest.json.

Standard library only. Records each file's sha256 and size in the manifest, so
a later run can detect when a source has changed (a lesson 2 discussion point).

    python scripts/fetch_corpus.py            # fetch anything missing
    python scripts/fetch_corpus.py --refresh  # re-download everything
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
MANIFEST = DATA / "corpus" / "manifest.json"
USER_AGENT = "Mozilla/5.0 (FDE Academy course corpus; educational use)"


def fetch(url: str, attempts: int = 4) -> bytes:
    for i in range(attempts):
        req = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return body
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or i == attempts - 1:
                raise
        except urllib.error.URLError:
            if i == attempts - 1:
                raise
        time.sleep(2 ** (i + 1))  # backoff; the retry lesson (L8) does this properly
    raise RuntimeError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text())
    for doc in manifest["documents"]:
        dest = DATA / doc["path"]
        if "url" not in doc:  # internal documents live in the repo already
            body = dest.read_bytes()
        elif dest.exists() and not args.refresh:
            body = dest.read_bytes()
        else:
            print(f"fetching {doc['doc_id']} ...", flush=True)
            body = fetch(doc["url"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            time.sleep(2)  # be polite to public servers
        digest = hashlib.sha256(body).hexdigest()
        if doc.get("sha256") and doc["sha256"] != digest:
            print(f"  ! {doc['doc_id']} changed since the manifest was recorded")
        doc["sha256"], doc["bytes"] = digest, len(body)
        print(f"  {doc['doc_id']:<28} {len(body):>9,} bytes  {doc['status']}")

    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
