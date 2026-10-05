# AGENTS.md
Project: FastAgent. Hackathon deadline: 2026-10-24. Team of 3.
## Rules for AI assistants
- Read contracts/ before changing any API or schema. Contracts are the source of truth; change them first, then code.
- Never add a dependency or swap a stack component without asking.
- Never invent third-party APIs. Read the library docs or source.
- Policy, permissions, and confirmation rules belong in code (backend/app/policy), never only in prompts.
- Every side-effecting tool call needs an idempotency key and an audit log entry.
- Never log tokens, secrets, or message bodies. Use synthetic data for any cloud LLM.
- Keep changes small and in your module. Do not edit another module without noting it in the PR.
## Modules and owners
- cascade, policy, learning: <owner 1>
- web, Capacitor app: <owner 2>
- tools (Google adapters), eval, loadtest: <owner 3>
## Commands
- docker compose up; pytest; python eval/bench_routers.py; k6 run loadtest/basic.js
## Definition of done
Tests pass, latency timings present, audit log written, contracts updated.
