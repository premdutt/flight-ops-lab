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

## After the lab
- [ ] Extract `platform_kit` into its own versioned repo (`ai-platform-kit`), installed via `pip install git+...@vX.Y.Z`
- [ ] Build `ai-agent-template` from tag `skeleton-v1`; depend on `ai-platform-kit`
- [ ] Side project: OpenAPI spec Q&A and "which API for this scenario" advisor agent