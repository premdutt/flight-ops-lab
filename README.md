# Flight-Ops Agent Lab

An in-progress flight-operations assistant built on Azure to explore agent workflows end to end. It answers questions from FAA Advisory Circulars indexed in Azure AI Search and drafts fuel, hangar, and catering requests for review.

> Learning project, not an operational aviation system. Use synthetic inputs only: messages, preferences, and approved requests may be persisted in Cosmos DB. Verify safety-critical information against authoritative sources.

## What It Does

| Capability | Current implementation |
|---|---|
| Route messages | Router agent classifies a message as a question or service request. |
| Answer rules questions | Answer agent calls `search_docs`, which runs hybrid (keyword + vector) search over Azure AI Search and includes source labels in the response. `SEARCH_MODE` switches to keyword-only or the original local page search for comparison. |
| Ingest documents | A Durable Functions pipeline chunks documents per page, embeds only chunks whose text changed, deletes stale chunks, and removes deleted documents on reconcile (nightly or on request). |
| Draft requests | Request agent produces JSON for fuel, hangar, or catering with `service`, `tail_number`, `airport`, `when`, and `details` fields. |
| Human review | CLI presents approve, edit, and reject choices. The workflow pauses for a response before its normal submission path. See the approval limitation below. |
| Remember preferences | A `remember` tool writes preferences to a Cosmos profile keyed by the supplied user ID. This is application-level scoping, not caller authentication. |
| Resume workflows | Agent Framework checkpoints are stored in Cosmos DB and can be listed and resumed. |
| Apply safety checks | Prompt Shields checks user input and retrieved passages; Azure AI Content Safety moderates generated answers. |
| Trace runs | OpenTelemetry traces are exported to the OTLP endpoint set in `.env` (Langfuse in this lab), including a span around each Content Safety call. |
| Evaluate changes | A 30-case golden set runs through the real workflow, is scored by code and an LLM judge, and is logged to MLflow. |

## Architecture

```text
User (CLI)
	|
	v
Agent Framework workflow
	|-- router --> answer agent --> search_docs --> Azure AI Search (hybrid)
	|                                  |
	|                                  +--> passage screening and answer moderation
	`-- request agent --> approval response --> submit_request --> Cosmos DB
												  |
												  `--> Cosmos DB checkpoints

Ingestion (runs locally):
scripts/ingest_docs.py --> blob storage (Azurite) --> Durable Functions (ingest/)
                                                        |-- chunk per page, hash ids
                                                        |-- embed new chunks (APIM)
                                                        `-- upsert / delete in Azure AI Search

APIM gateway --> chat, judge and embedding deployments
Azure AI Content Safety --> Prompt Shields and moderation
Cosmos DB --> checkpoints, per-ID preferences, and submitted requests
```

APIM and the model endpoints are configured outside this repository. `infra/main.bicep` manages Cosmos DB, Content Safety and the Azure AI Search service; it does not deploy APIM or Foundry. The search index is defined in `infra/search/idx-faa-docs.json` and created by a script, because Bicep can't create indexes. The Durable Functions app runs on your machine with Azurite; it is not deployed to Azure.

## Progress

| Week | Topic | Repository status |
|---|---|---|
| Setup | Azure account, model endpoint, APIM | Configured through environment; platform resources are external to this repo. |
| 1 | Agent Framework agents/workflow, Cosmos checkpoints, Bicep, GitHub Actions | Present in the repository. |
| 2 | Approval flow and per-user preferences | Present; identity binding and strict decision/schema validation remain limitations. |
| 3 | Content Safety and injection evaluation | Present; see the evaluation snapshot below. |
| 4 | OTel tracing, golden-set evaluation, LLM-as-judge, MLflow | Present; see the Week 4 results below. The judge has not yet been validated against human grades. |
| 5 | Azure AI Search hybrid retrieval, Durable Functions ingestion | Present; see the Week 5 results below. Hosting the pipeline in Azure (optional Step 5.9) is not done. |
| 6 | LangGraph rebuild, LangSmith, open-model fallback | Planned; `langgraph_app/` is currently only a scaffold. |

## Week 3 Results

Snapshot from [`evals/results/week3.md`](evals/results/week3.md), not a current guarantee:

- Attacks blocked: **9 of 16** (input: 2, model filter: 6, document: 1, output: 0).
- Benign messages wrongly blocked: **0 of 16**.
- Requests submitted by attacks: **0**; five attacks reached the approval step and the evaluation rejected them.
- Some attacks still reached the request or answer path; reaching approval is not counted as blocked by the harness.

## Week 4 Results

Snapshot from [`evals/results/week4.md`](evals/results/week4.md). One run per prompt on 30 cases; scores vary between runs.

| Metric | baseline-v2 | answer-prompt-v2 |
|---|---|---|
| Routing, request fields, attacks refused | 1.00 | 1.00 |
| Fact recall (20 questions) | 0.60 | 0.60 |
| Groundedness (1-5, LLM judge) | 4.65 | 4.45 |
| Source named in answer | 0.95 | 1.00 |

- A "direct answer first" prompt showed **no proven improvement** and made one answer confidently wrong, so the original prompt was kept.
- Retrieval is the likely limit: at baseline, 7 of the 8 missed facts were not in any passage the model saw.
- **The judge is not validated.** The planned human check is still open, and known judge mistakes are listed in the results file.

## Week 5 Results

Snapshot from [`evals/results/week5.md`](evals/results/week5.md). One run per search mode on 30 cases; same model, prompts and judge as Week 4.

| Metric | Week 4 search (baseline-v2) | Keyword | Hybrid |
|---|---|---|---|
| Routing, request fields, attacks refused | 1.00 | 1.00 | 1.00 |
| Fact recall (20 questions) | 0.60 | **1.00** | **1.00** |
| Groundedness (1-5, LLM judge) | 4.65 | 4.85 | 4.85 |
| Source named in answer | 0.95 | 1.00 | 1.00 |
| Passages seen, 20 questions | 154 | 80 | 99 |

- **Chunking fixed retrieval.** Overlapping 1,200-character chunks replaced page passages cut at 1,000 characters. A plain text match agrees with the judge on 19 of 20 answers, and the judge is right on the 20th.
- The agent now usually searches once per question instead of repeatedly, which uses fewer tokens and causes fewer rate-limit errors.
- **Keyword and hybrid tied** because every golden question uses the documents' own wording. Hybrid stays the default; reworded questions are needed to compare them.
- Ingestion is incremental: re-ingesting an unchanged file embeds nothing, a one-word edit re-embeds 3 of 40 chunks and deletes the 3 old ones, and reconcile removes deleted documents.
- The poisoned test document is still caught. The new search returns it for more fuel questions; Prompt Shields drops it and those questions are still answered, but the injection runner counts them as blocked (5 of 16 benign).

## Repository Layout

```text
app/              config, agents, workflow, memory, safety, search credential, storage, tracing, CLI
data/text/        extracted FAA text (used by SEARCH_MODE=pages and the poisoned test document)
docs/             project backlog
evals/            injection, benign and golden cases, runners, and result snapshots
infra/            Bicep for Cosmos DB, Content Safety and AI Search; search/ holds index definitions
ingest/           Durable Functions ingestion app and chunking helpers
langgraph_app/    Week 6 scaffold
scripts/          PDF extraction, index creation, document ingestion and smoke checks
.github/workflows/ infrastructure deployment workflow
```

PDF inputs belong in `data/pdf/`, which is git-ignored. Extract their text into `data/text/` with `scripts/pdf_to_text.py`.

## Running It

### Prerequisites

- Python 3.11 or later on Linux or macOS
- Azure CLI and an Azure identity allowed to call the configured services and access the Cosmos containers
- APIM gateway with chat, judge and embedding deployments, Azure AI Content Safety, Cosmos DB, and an Azure AI Search service
- **Search Index Data Contributor** on the search service for your identity (managing the index also needs Search Service Contributor, Contributor or Owner)
- For ingestion: Docker (for Azurite) and Azure Functions Core Tools 4
- `az login` for local `DefaultAzureCredential` authentication

Install the pinned dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create `.env` in the repository root; there is no checked-in `.env.example`:

```dotenv
APIM_GATEWAY_URL=https://your-gateway.example/
APIM_SUBSCRIPTION_KEY=your-key
OPENAI_API_VERSION=your-api-version
CHAT_DEPLOYMENT=chat
JUDGE_DEPLOYMENT=judge
EMBED_DEPLOYMENT=embed
COSMOS_ENDPOINT=https://your-cosmos-account.documents.azure.com:443/
CONTENT_SAFETY_ENDPOINT=https://your-content-safety-resource.example/

# Search and ingestion
SEARCH_ENDPOINT=https://your-search-service.search.windows.net
SEARCH_INDEX=faa-docs
SEARCH_MODE=hybrid                     # hybrid, keyword, or pages (Week 4 local search)
DOCS_STORAGE=UseDevelopmentStorage=true
DOCS_CONTAINER=faa-docs

# Tracing (Langfuse US region shown)
OTEL_SERVICE_NAME=flight-ops-lab
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=https://us.cloud.langfuse.com/api/public/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20your-base64-public-and-secret-key
```

The first three variables, both endpoint variables and `SEARCH_ENDPOINT` are required. Deployment names default to `chat`, `judge`, and `embed`; the workflow uses the chat deployment, the golden-set evaluation uses the judge deployment (which should be a different model from chat), and hybrid search and ingestion use the embedding deployment. The index's vector size must match the embedding model (1,536 for `text-embedding-3-small`; set `EMBED_DIMENSIONS` if yours differs). Azure SDK calls use Entra ID via `DefaultAzureCredential`; APIM calls use the subscription key. Keep `.env` local; it is git-ignored.

The Functions app does not read `.env`. Copy `ingest/local.settings.example.json` to `ingest/local.settings.json` (git-ignored) and fill in the same values.

### Commands

```bash
# Ask a question
python -m app.run_cli run "What are the requirements for fuel quality control?"

# Draft a request; the CLI then prompts for approve, edit, or reject
python -m app.run_cli run "I need fuel for N123AB tomorrow at 9am" --user demo-user

# Inspect checkpoints, including those waiting for approval, and resume one
python -m app.run_cli list
python -m app.run_cli pending
python -m app.run_cli resume CHECKPOINT_ID

# Run live injection and benign-message evaluations (report: evals/results/injections_<name>.md)
python -m evals.run_injections --run-name my-run

# Check the judge, then run the golden set (add --per-type 1 for a quick check)
python -m scripts.smoke_judge
python -m evals.run_golden --run-name my-run --note "what changed"
SEARCH_MODE=keyword python -m evals.run_golden --run-name my-keyword-run

# Compare golden-set runs
mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5001
```

Load documents into the search index:

```bash
# Once: create or update the index from its JSON definition (--recreate deletes all documents)
python -m scripts.create_index infra/search/idx-faa-docs.json

# Start Azurite (local blob storage and Durable Functions state)
docker run -d --name azurite -p 10000:10000 -p 10001:10001 -p 10002:10002 \
  mcr.microsoft.com/azure-storage/azurite

# Terminal 1: run the ingestion app
cd ingest && func start

# Terminal 2: upload and ingest documents; delete one and clean up its chunks
python -m scripts.ingest_docs data/pdf/*.pdf data/text/zz_poisoned.txt
python -m scripts.ingest_docs --delete FILE_NAME --reconcile
```

The smoke scripts call live Azure services; Cosmos checks can read or write data. The injection and golden-set evaluations also run against live services, reject any approval requests reached, and may save preferences under the `eval` and `golden` users. Do not treat them as side-effect-free. Ingestion writes to the shared search index. MLflow results stay in the local, git-ignored `mlflow.db` and `mlruns/`. The Azurite container keeps no data after it is removed; the search index in Azure is unaffected.

## Infrastructure Deployment

The checked-in `infra/main.bicepparam` has project-specific example values; review `suffix` and `principalIds` before deployment. `infra/main.bicep` uses the configured platform resource group and manages Cosmos DB, Content Safety and the Azure AI Search service. The search service uses the free tier, which allows one service per subscription; the template manages an existing one rather than creating a second. An authenticated Azure CLI identity needs deployment permissions in the target groups.

```bash
az deployment group what-if --resource-group "$RG" --template-file infra/main.bicep --parameters infra/main.bicepparam
az deployment group create --resource-group "$RG" --template-file infra/main.bicep --parameters infra/main.bicepparam
```

The GitHub Actions workflow runs on pushes to `main` that change `infra/**`, or by manual dispatch (`gh workflow run deploy-infra.yml --ref BRANCH`). It uses OIDC rather than a client-secret credential. Client, tenant, subscription IDs, and the resource group are still read from GitHub Actions secrets. Any approval pause depends on protection rules configured on the `lab` environment in GitHub.

## Design And Limitations

- The model does not directly call `submit_request`; in the current workflow, the response handler is the submission path. However, the handler treats every action other than `reject` and `edit` as approval. Validate actions explicitly before relying on this as an approval boundary.
- Request drafts are checked for valid JSON only, not for the required fields, field types, or allowed service values.
- User profiles are keyed by a caller-supplied user ID. The CLI's `--user` option is not authenticated or bound to the Azure identity, so it must not be presented as cross-user access control.
- Retrieval returns four passages per search. The golden set only contains questions worded like the documents, so it can't show whether hybrid search beats keyword search. Chunks don't record page numbers, so citations name the document only.
- Ingestion assumes the index fields `id`, `doc_id`, `source`, `chunk` and `chunk_vector`, and lists at most 1,000 chunks per document (it fails rather than leaving stale chunks). It runs only locally; the nightly reconcile runs only while `func start` is running.
- Safety service failures can interrupt a run. Inputs are currently truncated for safety checks rather than rejected for exceeding the limit; blocked-event and retrieved-passage tracking use process-global lists, so evaluation cases must run one at a time.
- The injection runner counts any passage dropped by Prompt Shields as a blocked message, even when the question is still answered. The Week 3 evaluation is a small evolving test set, not a security certification. Attacks reached approval in the recorded runs.
- The answer agent sometimes adds facts from memory (q-14) or narrates its searches in the answer (q-04, hybrid run).
- Agent Framework packages are pinned in `requirements.txt`; the framework packages are pre-release.
- Planned work includes request-schema and decision validation, spotlighting untrusted passages, robust long-input handling, durable safety-event logging, per-run event state, reworded golden questions, human validation of the judge, and the Week 6 items above.
