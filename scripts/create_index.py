"""Create or update a search index from a JSON file in Azure's own index format.

Run:  python -m scripts.create_index infra/search/idx-faa-docs.json
      python -m scripts.create_index infra/search/idx-faa-docs.json --recreate   # deletes all documents

The file is the same JSON the REST API takes and the portal shows under "Edit JSON".
Settings: SEARCH_ENDPOINT, EMBED_DIMENSIONS (default 1536, text-embedding-3-small).
"""
import argparse, json, sys
from pathlib import Path
import httpx
from azure.identity import DefaultAzureCredential
from app.config import env

API_VERSION = "2024-07-01"
SCOPE = "https://search.azure.com/.default"
# Field names the ingestion pipeline and search_docs depend on
REQUIRED = {"id", "doc_id", "source", "chunk", "chunk_vector"}


def load(path: Path) -> dict:
    """Read the index definition; without a "name", idx-<name>.json gives <name>."""
    index = json.loads(path.read_text(encoding="utf-8"))
    index.setdefault("name", path.stem.removeprefix("idx-"))
    return index


def check(index: dict) -> list[str]:
    """Problems that would only show up later, during ingestion or search."""
    fields = {f["name"]: f for f in index.get("fields", [])}
    problems = [f"missing field: {n}" for n in sorted(REQUIRED - fields.keys())]
    keys = [n for n, f in fields.items() if f.get("key")]
    if keys != ["id"]:
        problems.append(f"the key must be 'id' only, found {keys}")
    vector = fields.get("chunk_vector", {})
    want = int(env("EMBED_DIMENSIONS", "1536"))
    if vector and vector.get("dimensions") != want:
        problems.append(f"chunk_vector has {vector.get('dimensions')} dimensions, "
                        f"the embedding model gives {want} (EMBED_DIMENSIONS)")
    return problems


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("file", type=Path, help="index definition, e.g. infra/search/idx-faa-docs.json")
    p.add_argument("--recreate", action="store_true",
                   help="delete and create the index (needed for changes such as vector size)")
    a = p.parse_args()

    index = load(a.file)
    name = index["name"]
    if problems := check(index):
        sys.exit("Index definition not valid:\n  " + "\n  ".join(problems))

    token = DefaultAzureCredential().get_token(SCOPE).token
    base = env("SEARCH_ENDPOINT").rstrip("/")
    url = f"{base}/indexes('{name}')?api-version={API_VERSION}"
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=30, headers=headers) as http:
        if a.recreate:
            answer = input(f"This deletes index '{name}' and all its documents. "
                           f"Type the index name to continue: ")
            if answer.strip() != name:
                sys.exit("Cancelled.")
            r = http.delete(url)
            if r.status_code not in (204, 404):
                sys.exit(f"Delete failed ({r.status_code}): {r.text}")
            print(f"Deleted {name}" if r.status_code == 204 else f"{name} did not exist")

        r = http.put(url, json=index, headers={"Prefer": "return=representation"})
        if r.status_code >= 400:
            hint = ("\nSome changes can't be applied to an existing index; "
                    "use --recreate (this deletes its documents).") if r.status_code == 400 else ""
            sys.exit(f"Create/update failed ({r.status_code}): {r.text}{hint}")

    created = r.json()
    print(f"Index {'created' if r.status_code == 201 else 'updated'}: {created['name']}")
    for f in created["fields"]:
        extra = f"  dimensions={f['dimensions']}" if f.get("dimensions") else ""
        print(f"  {f['name']:<13} {f['type']}{extra}")


if __name__ == "__main__":
    main()
