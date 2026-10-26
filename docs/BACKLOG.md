# Backlog

## After Week 1 is green
- [ ] Refactor reusable plumbing into `platform_kit/` (config, APIM client factory, Cosmos checkpoint storage, CLI scaffolding). Rule: `platform_kit` never imports `app`.

## After the lab
- [ ] Extract `platform_kit` into its own versioned repo (`ai-platform-kit`), installed via `pip install git+...@vX.Y.Z`
- [ ] Build `ai-agent-template` from tag `skeleton-v1`; depend on `ai-platform-kit`
- [ ] Side project: OpenAPI spec Q&A and "which API for this scenario" advisor agent