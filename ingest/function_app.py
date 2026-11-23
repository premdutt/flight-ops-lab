"""Durable ingestion: load documents into Azure AI Search, embed only changed chunks, delete stale ones.

Starters   : HTTP /api/ingest?name=<blob>, HTTP /api/reconcile, nightly timer
Orchestrators decide what to do (no I/O: they are replayed). Activities do all the I/O.
Settings come from local.settings.json locally, or app settings in Azure.
"""
import io
import os
from pathlib import Path

import azure.durable_functions as df
import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI
from pypdf import PdfReader

from chunking import chunk_id, chunk_text, doc_id_for

BATCH = int(os.environ.get("EMBED_BATCH", "16"))             # chunks per embedding call
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "150"))
MAX_IDS = 1000                                               # chunks per document we can list

# A failed embedding call (e.g. 429) is retried by Durable Functions: 3 more tries, 20s apart
EMBED_RETRY = df.RetryOptions(first_retry_interval_in_milliseconds=20_000, max_number_of_attempts=4)

app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)


def search_client() -> SearchClient:
    return SearchClient(os.environ["SEARCH_ENDPOINT"], os.environ["SEARCH_INDEX"],
                        DefaultAzureCredential())


def container():
    svc = BlobServiceClient.from_connection_string(os.environ["DOCS_STORAGE"])
    return svc.get_container_client(os.environ["DOCS_CONTAINER"])


def embedder() -> AzureOpenAI:
    return AzureOpenAI(azure_endpoint=os.environ["APIM_GATEWAY_URL"],
                       api_key=os.environ["APIM_SUBSCRIPTION_KEY"],
                       api_version=os.environ["OPENAI_API_VERSION"])


# ---------- starters ----------

@app.route(route="ingest", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_ingest(req: func.HttpRequest, client) -> func.HttpResponse:
    name = req.params.get("name")
    if not name:
        return func.HttpResponse("Pass the blob name: /api/ingest?name=<file>", status_code=400)
    instance_id = await client.start_new("ingest", client_input={"name": name})
    return client.create_check_status_response(req, instance_id)


@app.route(route="reconcile", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_reconcile(req: func.HttpRequest, client) -> func.HttpResponse:
    instance_id = await client.start_new("reconcile")
    return client.create_check_status_response(req, instance_id)


@app.timer_trigger(schedule="0 0 3 * * *", arg_name="timer")    # nightly at 03:00 UTC
@app.durable_client_input(client_name="client")
async def nightly_reconcile(timer: func.TimerRequest, client) -> None:
    await client.start_new("reconcile")


# ---------- orchestrators (deterministic: no I/O, clocks or random values) ----------

@app.orchestration_trigger(context_name="context")
def ingest(context: df.DurableOrchestrationContext):
    name = context.get_input()["name"]
    doc = yield context.call_activity("extract_chunks", name)
    existing = set((yield context.call_activity("existing_ids", doc["doc_id"])))

    new = [c for c in doc["chunks"] if c["id"] not in existing]
    batches = [new[i:i + BATCH] for i in range(0, len(new), BATCH)]
    yield context.task_all([                                  # fan out, then wait for all
        context.call_activity_with_retry(
            "embed_and_upsert", EMBED_RETRY,
            {"doc_id": doc["doc_id"], "source": doc["source"], "batch": b})
        for b in batches])

    stale = sorted(existing - {c["id"] for c in doc["chunks"]})
    if stale:
        yield context.call_activity("delete_chunks", stale)
    return {"doc": name, "pages": doc["pages"], "chunks": len(doc["chunks"]),
            "embedded": len(new), "unchanged": len(doc["chunks"]) - len(new), "deleted": len(stale)}


@app.orchestration_trigger(context_name="context")
def reconcile(context: df.DurableOrchestrationContext):
    in_index = set((yield context.call_activity("indexed_doc_ids", None)))
    in_storage = set((yield context.call_activity("stored_doc_ids", None)))
    removed = sorted(in_index - in_storage)
    for doc_id in removed:
        ids = yield context.call_activity("existing_ids", doc_id)
        if ids:
            yield context.call_activity("delete_chunks", ids)
    return {"removed_docs": len(removed)}


# ---------- activities (all I/O lives here) ----------

def read_pages(name: str, data: bytes) -> list[str]:
    """PDFs page by page; text files by blank-line-separated block."""
    if name.lower().endswith(".pdf"):
        return [p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages]
    return data.decode("utf-8", errors="ignore").split("\n\n")


@app.activity_trigger(input_name="name")
def extract_chunks(name: str) -> dict:
    data = container().get_blob_client(name).download_blob().readall()
    pages = read_pages(name, data)
    doc_id = doc_id_for(name)
    seen, chunks = set(), []
    for page in pages:              # chunk each page on its own: an edit only shifts chunks on its page
        for c in chunk_text(page, CHUNK_SIZE, CHUNK_OVERLAP):
            cid = chunk_id(doc_id, c)
            if cid not in seen:     # identical text twice in a document is stored once
                seen.add(cid)
                chunks.append({"id": cid, "chunk": c})
    # source = file name without extension, e.g. AC_103-6, so citations match the golden set
    return {"doc_id": doc_id, "source": Path(name).stem, "pages": len(pages), "chunks": chunks}


@app.activity_trigger(input_name="docId")
def existing_ids(docId: str) -> list:
    results = search_client().search(search_text="*", filter=f"doc_id eq '{docId}'",
                                     select=["id"], top=MAX_IDS)
    ids = [r["id"] for r in results]
    if len(ids) >= MAX_IDS:         # a silent cut-off would leave stale chunks behind
        raise RuntimeError(f"{docId} has {MAX_IDS}+ chunks; page through results before ingesting it")
    return ids


@app.activity_trigger(input_name="payload")
def embed_and_upsert(payload: dict) -> int:
    batch = payload["batch"]
    vectors = embedder().embeddings.create(model=os.environ["EMBED_DEPLOYMENT"],
                                           input=[c["chunk"] for c in batch]).data
    docs = [{"id": c["id"], "doc_id": payload["doc_id"], "source": payload["source"],
             "chunk": c["chunk"], "chunk_vector": v.embedding} for c, v in zip(batch, vectors)]
    results = search_client().merge_or_upload_documents(documents=docs)
    failed = [r.key for r in results if not r.succeeded]
    if failed:
        raise RuntimeError(f"Search rejected {len(failed)} chunks, e.g. {failed[:3]}")
    return len(docs)


@app.activity_trigger(input_name="ids")
def delete_chunks(ids: list) -> int:
    search_client().delete_documents(documents=[{"id": i} for i in ids])
    return len(ids)


@app.activity_trigger(input_name="unused")
def indexed_doc_ids(unused) -> list:
    results = search_client().search(search_text="*", facets=["doc_id,count:1000"], top=0)
    return [f["value"] for f in (results.get_facets() or {}).get("doc_id", [])]


@app.activity_trigger(input_name="unused")
def stored_doc_ids(unused) -> list:
    return [doc_id_for(b.name) for b in container().list_blobs()]
