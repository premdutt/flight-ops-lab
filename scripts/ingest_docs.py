"""Upload documents to blob storage and run the ingestion pipeline on them.

Needs the Functions app running (cd ingest && func start).
Run:  python -m scripts.ingest_docs data/pdf/*.pdf data/text/zz_poisoned.txt
      python -m scripts.ingest_docs --delete zz_poisoned.txt --reconcile
Settings: DOCS_STORAGE, DOCS_CONTAINER (default faa-docs), FUNCTIONS_URL (default local).
"""
import argparse
import sys
import time
from pathlib import Path

import httpx
from azure.storage.blob import BlobServiceClient
from app.config import env

BASE = env("FUNCTIONS_URL", "http://localhost:7071/api")
TIMEOUT = 600                       # seconds to wait for one pipeline run


def run(route: str, params: dict | None = None) -> dict:
    """Start an orchestration and poll its status URL until it finishes."""
    r = httpx.post(f"{BASE}/{route}", params=params, timeout=30)
    r.raise_for_status()
    status_url = r.json()["statusQueryGetUri"]
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        s = httpx.get(status_url, timeout=30).json()
        if s["runtimeStatus"] in ("Completed", "Failed", "Terminated"):
            if s["runtimeStatus"] != "Completed":
                sys.exit(f"{route} {params or ''} {s['runtimeStatus']}: {s.get('output')}")
            return s["output"]
        time.sleep(2)
    sys.exit(f"{route} {params or ''} still running after {TIMEOUT}s; check the func terminal")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="*", help="files to upload and ingest")
    p.add_argument("--delete", help="blob name to delete")
    p.add_argument("--reconcile", action="store_true", help="remove chunks of deleted documents")
    a = p.parse_args()

    container = BlobServiceClient.from_connection_string(env("DOCS_STORAGE")) \
        .get_container_client(env("DOCS_CONTAINER", "faa-docs"))
    if not container.exists():
        container.create_container()

    for f in a.files:
        path = Path(f)
        container.upload_blob(path.name, path.read_bytes(), overwrite=True)
        print(path.name, run("ingest", {"name": path.name}))
    if a.delete:
        container.delete_blob(a.delete)
        print("deleted blob", a.delete)
    if a.reconcile:
        print("reconcile", run("reconcile"))


if __name__ == "__main__":
    main()
