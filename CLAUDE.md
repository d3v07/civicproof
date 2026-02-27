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
**LLM**: Vertex AI Gemini (primary, GCP credits) + OpenRouter BYOK (fallback)
