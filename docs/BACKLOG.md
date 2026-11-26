# Backlog

## Before production

### Product and operational scope
- [ ] Define the supported operational use cases, authoritative source corpus and update process, human escalation path, and named operational owner. Keep the assistant advisory until explicitly approved for any real-world action.
- [ ] Define launch acceptance criteria with aviation subject-matter experts, including answer accuracy, citation correctness, request handling, and safe refusal behavior.

### Identity, authorization, and approvals
- [ ] Authenticate end users and derive the user ID from a trusted identity; remove caller-controlled `--user` as an authorization boundary and test cross-user access denial.
- [ ] Add explicit authorization for approvers and bind each approval/rejection to the authenticated approver, request, and displayed draft; persist an auditable decision record.
- [ ] Make approval fail closed: accept only `approve`, `edit`, or `reject`; require explicit `approve` to submit; validate edited and generated drafts against a strict schema and domain rules before submission.
- [ ] Test retries, checkpoint replay, duplicate approval, edited drafts, malformed decisions, and submission failures to prove requests cannot be submitted without one valid approval and are submitted at most once.

### Safety and model behavior
- [ ] Fail closed when Prompt Shields or output moderation times out, returns an HTTP error, or returns an invalid response; add bounded retry and timeout behavior with a clear user-safe error.
- [ ] Reject over-limit input and output instead of silently truncating safety-check content; test limits and malformed service responses.
- [ ] Add defenses and tests for untrusted retrieved passages, prompt injection, unsupported claims, citation/source mismatch, and unsafe or invalid request fields.
- [ ] Establish a reviewed golden and adversarial evaluation set, measurable launch thresholds, regression checks in CI, and documented human review of evaluation failures.

### Data protection and security
- [ ] Document data classification, purpose, retention, deletion, and access for prompts, preferences, requests, and workflow checkpoints; remove or expire data when its retention period ends.
- [ ] Minimize sensitive data in prompts and logs; redact identifiers and content from diagnostics, and verify that logs and traces do not expose secrets or user data.
- [ ] Review Entra ID/RBAC assignments for least privilege; separate development, staging, and production resources and identities; rotate APIM credentials and store them in an approved secret manager.
- [ ] Review network exposure and encryption for Cosmos DB, Content Safety, APIM, and model endpoints; restrict public access or use private connectivity where required by the deployment threat model.

### Reliability and operations
- [ ] Add structured per-run safety and workflow telemetry, correlation IDs, actionable alerts, and dashboards without using process-global event state or logging sensitive payloads.
- [ ] Define and test rate limits, concurrency limits, retries, backoff, dependency outage behavior, and capacity/throughput limits for model, safety, and Cosmos services.
- [ ] Configure and test backup/restore and disaster recovery for request and checkpoint data; document recovery objectives and operational runbooks for stuck approvals and failed submissions.
- [ ] Add health checks, service-level objectives, incident response ownership, deployment rollback procedures, and a production support plan.

### Release and supply chain
- [ ] Add automated unit, integration, security, and configuration tests to CI; include Bicep validation/what-if and require review before production deployment.
- [ ] Review pinned dependencies for vulnerabilities and licensing; replace or explicitly accept pre-release Agent Framework dependencies before production, and establish an update process.
- [ ] Perform a production threat model and security/privacy review, then obtain explicit sign-off from application, platform, security, and aviation operations owners.

## After Week 1 is green
- [ ] Refactor reusable plumbing into `platform_kit/` (config, APIM client factory, Cosmos checkpoint storage, CLI scaffolding). Rule: `platform_kit` never imports `app`.

## After Week 4
- [ ] Make the judge reusable (by Step 6.4): load the judge prompt, deployment, score schema and thresholds from a versioned config; load cases and facts from JSONL; pass answers and passages in at runtime (never from config). Validate judge output against the schema, log the config version to MLflow, and re-check agreement with human grades (at least 8 of 10) whenever the prompt or model changes. Done when Agent Framework and LangGraph use it unchanged.

## After Week 5
- [ ] Make the chunk-store field names configurable. Index definitions are already JSON files (`infra/search/idx-<index>.json`), but ingestion, `search_docs` and `scripts/create_index.py` assume `id`, `doc_id`, `source`, `chunk`, `chunk_vector`. Add a field mapping only when a second project needs different names.
- [ ] Add 5-10 golden questions worded differently from the documents (e.g. "How long do we keep driver training paperwork?" for q-05), then rerun `SEARCH_MODE=keyword` vs `hybrid`. Week 5 runs tied at facts_recall 1.00 because every question uses the documents' own wording (`evals/results/week5.md`).
- [ ] Stop the answer agent narrating its searches in the answer (q-04 hybrid: "I found it. Let me get the exact quote.") and adding facts from memory (q-14 expands VR/IR). Change the prompt in its own experiment, not together with a search change.

## Week 6: channels and runners
Channels (`channels/`) call only `start` / `resume` / `status` on a `WorkflowRunner` (`workflows/runner_base.py`) and get an `Outcome` back; `workflows/factory.py` picks the framework.
- [x] Add `AgentFrameworkRunner` (`workflows/agent_framework/runner.py`). Each thread has its own workflow name `flightops-<thread>` (the Cosmos partition key); its latest checkpoint gives the status, and the pending `request_id` comes from that checkpoint, so no separate mapping is needed. `pending` has the same shape as LangGraph. Works with `channels/cli.py --framework agent_framework`; the golden runner is next.
- [ ] Record the time per case in `evals/run_golden.py` (workflow only, without the judge), so both frameworks have latency numbers. Week 6 has LangGraph latency from LangSmith only; Agent Framework's model calls aren't visible there (`evals/results/week6.md`).
- [ ] Add `--framework` to `evals/run_injections.py` (still drives Agent Framework directly) and run the injection set on LangGraph.
- [ ] Separate design from framework: try one search + passages in the prompt in Agent Framework (or the tool-calling agent in LangGraph). Week 6's groundedness gap (q-14) comes from the answer design.
- [ ] Keep the final result of finished Agent Framework threads. Checkpoints don't store outputs, so `status()` of a finished thread has `result=None` (LangGraph keeps it in the state).
- [ ] Make safety events per request before any channel serves more than one call at a time (web API, chat bot). `app/safety.EVENTS` is a module-level list cleared at the start of each call, so concurrent requests would mix their events. Use a `contextvars.ContextVar` or return events from the safety functions.
- [ ] Add a list of waiting approvals for web and chat channels ("show me everything waiting for approval"). Keep it in the runner (thread id, user, draft id, created time), filled on `waiting` and cleared on `done`, rather than scanning checkpoints.
- [ ] Delete `app/run_cli.py` (the Week 2 Agent Framework terminal runner) once `python -m channels.cli --framework agent_framework` works.

## After the lab
- [ ] Extract `platform_kit` into its own versioned repo (`ai-platform-kit`), installed via `pip install git+...@vX.Y.Z`
- [ ] Build `ai-agent-template` from tag `skeleton-v1`; depend on `ai-platform-kit`
- [ ] Side project: OpenAPI spec Q&A and "which API for this scenario" advisor agent