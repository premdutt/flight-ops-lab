# Flight-Ops Agent Lab

An in-progress flight-operations assistant built on Azure to explore agent workflows end to end. It answers questions from the FAA Advisory Circular text files in this repository and drafts fuel, hangar, and catering requests for review.

> Learning project, not an operational aviation system. Use synthetic inputs only: messages, preferences, and approved requests may be persisted in Cosmos DB. Verify safety-critical information against authoritative sources.

## What It Does

| Capability | Current implementation |
|---|---|
| Route messages | Router agent classifies a message as a question or service request. |
| Answer rules questions | Answer agent calls `search_docs`, which retrieves local text passages and includes source labels in the response. |
| Draft requests | Request agent produces JSON for fuel, hangar, or catering with `service`, `tail_number`, `airport`, `when`, and `details` fields. |
| Human review | CLI presents approve, edit, and reject choices. The workflow pauses for a response before its normal submission path. See the approval limitation below. |
| Remember preferences | A `remember` tool writes preferences to a Cosmos profile keyed by the supplied user ID. This is application-level scoping, not caller authentication. |
| Resume workflows | Agent Framework checkpoints are stored in Cosmos DB and can be listed and resumed. |
| Apply safety checks | Prompt Shields checks user input and retrieved passages; Azure AI Content Safety moderates generated answers. |

## Architecture

```text
User (CLI)
	|
	v
Agent Framework workflow
	|-- router --> answer agent --> search_docs --> FAA text files in data/text/
	|                                  |                 (Azure AI Search is planned)
	|                                  +--> passage screening and answer moderation
	`-- request agent --> approval response --> submit_request --> Cosmos DB
												  |
												  `--> Cosmos DB checkpoints

APIM gateway --> configured chat deployment
Azure AI Content Safety --> Prompt Shields and moderation
Cosmos DB --> checkpoints, per-ID preferences, and submitted requests
```

APIM and the model endpoint are configured outside this repository. `infra/main.bicep` deploys the lab Cosmos DB resources and Content Safety resource; it does not deploy APIM or Foundry. Tracing with Langfuse/OTel, MLflow evaluations, Azure AI Search, and Durable Functions ingestion are not implemented in this checkout.

## Progress

| Week | Topic | Repository status |
|---|---|---|
| Setup | Azure account, model endpoint, APIM | Configured through environment; platform resources are external to this repo. |
| 1 | Agent Framework agents/workflow, Cosmos checkpoints, Bicep, GitHub Actions | Present in the repository. |
| 2 | Approval flow and per-user preferences | Present; identity binding and strict decision/schema validation remain limitations. |
| 3 | Content Safety and injection evaluation | Present; see the evaluation snapshot below. |
| 4 | OTel tracing, golden-set evaluation, LLM-as-judge, MLflow | In progress/planned; no golden-set runner is present here. |
| 5 | Azure AI Search hybrid retrieval, Durable Functions ingestion | Planned. |
| 6 | LangGraph rebuild, LangSmith, open-model fallback | Planned; `langgraph_app/` is currently only a scaffold. |

## Week 3 Results

Snapshot from [`evals/results/week3.md`](evals/results/week3.md), not a current guarantee:

- Attacks blocked: **9 of 16** (input: 2, model filter: 6, document: 1, output: 0).
- Benign messages wrongly blocked: **0 of 16**.
- Requests submitted by attacks: **0**; five attacks reached the approval step and the evaluation rejected them.
- Some attacks still reached the request or answer path; reaching approval is not counted as blocked by the harness.

## Repository Layout

```text
app/              config, agents, workflow, memory, safety, storage, CLI
data/text/        extracted FAA text used by retrieval
docs/             project backlog
evals/            injection/benign cases, runner, and result snapshots
infra/            Bicep templates for Cosmos DB and Content Safety
langgraph_app/    Week 6 scaffold
scripts/          PDF extraction and smoke checks
.github/workflows/ infrastructure deployment workflow
```

PDF inputs belong in `data/pdf/`, which is git-ignored. Extract their text into `data/text/` with `scripts/pdf_to_text.py`.

## Running It

### Prerequisites

- Python 3.11 or later on Linux or macOS
- Azure CLI and an Azure identity allowed to call the configured services and access the Cosmos containers
- APIM gateway with the configured chat deployment, Azure AI Content Safety, and Cosmos DB
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
```

The first three variables and both endpoint variables are required. Deployment names default to `chat`, `judge`, and `embed`; the current workflow uses the chat deployment. `app.llm.embed` uses the embedding deployment. Azure SDK calls use Entra ID via `DefaultAzureCredential`; APIM calls use the subscription key. Keep `.env` local; it is git-ignored.

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

# Run live injection and benign-message evaluations
python -m evals.run_injections
```

The smoke scripts call live Azure services; Cosmos checks can read or write data. The injection evaluation also runs against live services, rejects any approval requests reached, and may save preferences under the `eval` user. Do not treat it as side-effect-free.

## Infrastructure Deployment

The checked-in `infra/main.bicepparam` has project-specific example values; review `suffix` and `principalIds` before deployment. `infra/main.bicep` uses the configured platform resource group and deploys Cosmos DB and Content Safety resources. An authenticated Azure CLI identity needs deployment permissions in the target groups.

```bash
az deployment group what-if --resource-group "$RG" --template-file infra/main.bicep --parameters infra/main.bicepparam
az deployment group create --resource-group "$RG" --template-file infra/main.bicep --parameters infra/main.bicepparam
```

The GitHub Actions workflow runs on pushes to `main` that change `infra/**`, or by manual dispatch. It uses OIDC rather than a client-secret credential. Client, tenant, subscription IDs, and the resource group are still read from GitHub Actions secrets. Any approval pause depends on protection rules configured on the `lab` environment in GitHub.

## Design And Limitations

- The model does not directly call `submit_request`; in the current workflow, the response handler is the submission path. However, the handler treats every action other than `reject` and `edit` as approval. Validate actions explicitly before relying on this as an approval boundary.
- Request drafts are checked for valid JSON only, not for the required fields, field types, or allowed service values.
- User profiles are keyed by a caller-supplied user ID. The CLI's `--user` option is not authenticated or bound to the Azure identity, so it must not be presented as cross-user access control.
- Retrieval is keyword-based over local text files and returns up to four matching passages; it is not semantic or hybrid search.
- Safety service failures can interrupt a run. Inputs are currently truncated for safety checks rather than rejected for exceeding the limit; blocked-event tracking uses a process-global list.
- The Week 3 evaluation is a small evolving test set, not a security certification. Attacks reached approval in the recorded run.
- Agent Framework packages are pinned in `requirements.txt`; the framework packages are pre-release.
- Planned work includes request-schema and decision validation, spotlighting untrusted passages, robust long-input handling, durable safety-event logging, per-run event state, Azure AI Search, and the Week 4-6 items above.