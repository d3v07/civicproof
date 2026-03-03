# CivicProof — CLAUDE.md

## Project overview
CivicProof is a zero-customer, near-zero-cost agentic investigative control plane. It turns a vendor name, UEI, CAGE code, award ID, or tip text into an evidence-grounded, complaint-ready case pack assembled from public federal data.

**Core principle**: LLMs propose hypotheses. Facts come only from retrieved artifacts with provable provenance.

## Monorepo structure
```
/services/api       FastAPI public + internal endpoints
/services/worker    Async worker (Pub/Sub / Cloud Tasks consumer)
/services/gateway   LLM gateway: routing, caching, policy, budget
/infra              Terraform/Pulumi for GCP
/packages/common    Shared schemas, event contracts, utilities
/packages/eval      Eval harness, synthetic generators, red-team suite
/docs               SRS, ADRs, threat model, runbooks
/tests              Unit, integration, contract, e2e, red_team
.claude/agents/     Subagent definitions
.claude/commands/   Custom slash commands
.github/workflows/  CI/CD pipelines
```

## Active agents
See `.claude/agents/` directory. Use `/agents` to manage.

## Custom commands
- `/spec` — review SRS and produce delta plan
- `/arch` — architecture review, ADR proposals
- `/tests` — run full test plan, produce failure analysis
- `/release` — eval gates + release notes + deployment checklist
- `/postmortem` — generate postmortem from logs/traces

## Non-negotiable rules
1. **No secrets in code** — use .env (gitignored) and GCP Secret Manager for prod
2. **No fraud accusations** — output "risk signals" and "hypotheses" only
3. **Every claim cites a stored artifact** — Auditor blocks anything unsupported
4. **Idempotency everywhere** — all pipeline stages safe to replay
5. **Test gate before advancing** — no sprint closes without passing test suite
6. **Rate limit compliance** — SEC: 10 RPS, DOJ: 4 RPS, SAM: 4 RPS, FEC: 1000/hr
7. **Structured logs** — always include case_id, artifact_id, source, stage, policy_decision
8. **Tool permissioning** — agents cannot run destructive actions unless explicitly scoped

## Security requirements
- Prompt injection defenses on all external inputs
- PII redaction aligned with USAspending exclusion policies
- Audit trails meeting NIST SP 800-92 log management standards
- IAM least-privilege for all GCP service accounts
- No API keys or tokens committed to git ever

## Commit conventions
- Format: `<type>(<scope>): <short summary>`
- Types: feat, fix, test, docs, refactor, chore, security, infra
- No mention of AI tooling or agent names in commit messages
- All commits must pass pre-commit hooks (linting, secret scanning)

## Test requirements
Every PR must pass:
- Unit tests (parsers, normalizers, hashing, policy rules, routing)
- Contract tests (upstream connector shapes, event schemas)
- Security scan (no secrets, no prompt injection vectors)
- Coverage gate: ≥80% for core packages

## Tech stack
**Local dev**: Postgres, MinIO, OpenSearch, Redis, Kafka/queue, vLLM
**GCP prod**: Cloud Run, Cloud SQL, Cloud Storage, Memorystore, Vertex AI, Pub/Sub, Cloud Tasks
**LLM**: OpenRouter BYOK (primary, Qwen 2.5 72B + 14B) + Vertex AI Gemini (fallback)
**Pipeline**: LangGraph StateGraph, 6 nodes, conditional routing
**Frontend**: Next.js 16, React 19, Tailwind 4, Recharts, react-force-graph-2d

## Current execution phase
Read `~/.claude/projects/-Users-dev-Documents-PROJECT-LOWLEVEL-SYSTEM-DESIGN-PROJECTS-CivicProof/memory/MEMORY.md` for current phase and what's done/pending. Always check this at session start.

## Build rules (project-specific, extends global FAANG principles)
1. **Current milestone**: Get ONE vertical slice working before touching anything else
   - The slice: vendor name → Entity Resolver → Evidence Retrieval (USAspending) → Case Composer → Auditor Gate → frontend displays case pack
   - Skip Graph Builder + Anomaly Detector until the slice works
2. **Pipeline architecture**: LangGraph in `services/worker/src/graph/`. Nodes in `graph/nodes/`, legacy agents in `agents/`, connectors in `connectors/`
3. **LLM calls**: OpenRouter via `langchain_openai.ChatOpenAI` with `base_url=https://openrouter.ai/api/v1`. Config in `graph/llm.py`. Cost tracking per agent.
4. **Agent testability**: Each graph node must work with injected mocks (mock DB, mock LLM, mock HTTP). No node should require all infra running to unit test.
5. **Feature flags for optional agents**: `ENABLE_GRAPH_BUILDER`, `ENABLE_ANOMALY_DETECTOR` in config. Pipeline skips disabled nodes.
6. **No mock fallbacks in frontend**: If API is down, show error state. Never show fake data silently.
