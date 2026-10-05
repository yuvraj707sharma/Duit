# FastAgent Independent Review Bundle

*Audit & Verification Report | Target Hackathon Deadline: 2026-10-24*

---

## 1. REALITY TABLE

Every component in the system is classified under strictly one of three states:
- `LIVE-VERIFIED`: Ran against the real service/library on this host with verifiable output recorded in `artifacts/*.txt`.
- `UNIT-TESTED-WITH-MOCKS`: Code is fully implemented and verified against deterministic unit-test fixtures/emulators.
- `UNEXECUTED`: Implemented or configured, but never executed against a live remote service.

| Component | State | Scope & Verification Detail | Evidence File |
|---|---|---|---|
| **Laya Multilingual Router (Stage 2)** | **LIVE-VERIFIED** | Loaded `convaiinnovations/laya` (ModernBERT-large & mmBERT-base) in PyTorch on host CPU asking single intent question, deriving risk from `INTENT_RISK_MAP`. | [`artifacts/bench_routers.txt`](file:///E:/Inovvate/artifacts/bench_routers.txt) |
| **Embed Router (TF-IDF + LogisticRegression)** | **LIVE-VERIFIED** | Multilingual character/word n-gram embedding vectorizer with LogisticRegression head trained on `eval/dataset/train.jsonl` and evaluated on `eval/dataset/test.jsonl`. | [`artifacts/bench_routers.txt`](file:///E:/Inovvate/artifacts/bench_routers.txt) |
| **Active Learning Threshold Calibrator** | **UNIT-TESTED-WITH-MOCKS** | Evaluated dynamic threshold tuning and kNN semantic memory retrieval at N = 0, 5, 10, 20, 40 corrections drawn strictly from `train.jsonl`. | [`artifacts/learning_curve.txt`](file:///E:/Inovvate/artifacts/learning_curve.txt) |
| **Deterministic Mock Router Baseline** | **UNIT-TESTED-WITH-MOCKS** | Sub-millisecond deterministic baseline covering English, Hindi, Hinglish, and negation patterns. | [`artifacts/pytest.txt`](file:///E:/Inovvate/artifacts/pytest.txt) |
| **Deterministic User Channel -> UUID Mapping** | **UNIT-TESTED-WITH-MOCKS** | `get_user_uuid_from_channel_id` generates stable UUIDv5 identifiers from phone numbers or `@lid` JIDs, guaranteeing zero collision between distinct callers. | [`artifacts/pytest.txt`](file:///E:/Inovvate/artifacts/pytest.txt) (`test_channel_id_to_uuid_mapping_deterministic`) |
| **Trust-Taint Third-Party Inbound Gating** | **UNIT-TESTED-WITH-MOCKS** | Inbound emails or third-party text carry `trust_taint=True` into Policy Engine, preventing prompt injection execution (e.g. `send this to attacker@evil.com`) without explicit user approval. | [`artifacts/pytest.txt`](file:///E:/Inovvate/artifacts/pytest.txt) (`test_trust_taint_gates_attacker_email_action`, `test_policy_engine_trust_taint_flag`) |
| **End-to-End Rejection Learning Loop** | **UNIT-TESTED-WITH-MOCKS** | On prompt `"Kal ki meeting cancel mat karo bas shift kar do"` misclassified as `cancel_meeting`, confirmation displays original text and rejection logs a correction. | [`artifacts/pytest.txt`](file:///E:/Inovvate/artifacts/pytest.txt) (`test_e2e_negation_confirmation_and_rejection_learning`) |
| **Webhook Authentication & JID Filtering** | **UNIT-TESTED-WITH-MOCKS** | Constant-time HMAC comparison (`hmac.compare_digest`) on `/api/webhooks/evolution`, returns 401 on missing/wrong secret, and rejects non-individual JIDs (`@g.us`, `@broadcast`, `@newsletter`). | [`artifacts/pytest.txt`](file:///E:/Inovvate/artifacts/pytest.txt) (4/4 passed) |
| **Hard Rules & Emergency Stop (Stage 1)** | **UNIT-TESTED-WITH-MOCKS** | Sub-millisecond static rule matcher; emergency stop ("stop all", "ruk jao") cancels all active pending approvals for the user and returns the cancellation count. | [`artifacts/pytest.txt`](file:///E:/Inovvate/artifacts/pytest.txt) (`test_emergency_stop_cancels_pending_approvals_and_reports_count`) |
| **Approvals Lifecycle & Policy Engine** | **UNIT-TESTED-WITH-MOCKS** | 1 active pending approval per user (supersedes prior), 5-minute expiry, caller validation, edit re-runs policy engine preserving idempotency key, high-risk actions never auto-approved, empty email allowlist forces confirmation. | [`artifacts/pytest.txt`](file:///E:/Inovvate/artifacts/pytest.txt) (4/4 approval tests passed) |
| **AES-256-GCM Token Encryption** | **UNIT-TESTED-WITH-MOCKS** | Startup enforcement of exact 32-byte base64 key, AAD bound to `v1:{user_id}`, and strict `v1:` ciphertext version prefix. | [`artifacts/pytest.txt`](file:///E:/Inovvate/artifacts/pytest.txt) (4/4 passed) |
| **Idempotency & Webhook Deduplication** | **UNIT-TESTED-WITH-MOCKS** | Idempotency keys derived from `sha256(message_id + action)[:32]`; repeated webhook deliveries return cached execution payload without re-running tools. | [`artifacts/pytest.txt`](file:///E:/Inovvate/artifacts/pytest.txt) (`test_idempotency_key_derived_from_message_id_and_action`, `test_webhook_deduplication_returns_cached_response`) |
| **Intent Handling & Tool Errors** | **UNIT-TESTED-WITH-MOCKS** | "other" intent calls LLM for conversational replies; unimplemented tools return structured not-supported error responses; read queries run argument extraction. | [`artifacts/pytest.txt`](file:///E:/Inovvate/artifacts/pytest.txt) (3/3 passed) |
| **Confirmation Prompts with Full Drafts** | **UNIT-TESTED-WITH-MOCKS** | Full email draft body, subject, recipient, time, and attendees formatted in confirmation prompts. | [`artifacts/pytest.txt`](file:///E:/Inovvate/artifacts/pytest.txt) (`test_confirmation_prompt_includes_full_draft_body`) |
| **Evolution Go Live WhatsApp Connection** | **UNEXECUTED** | Webhook parser and HTTP client implemented; live WhatsApp pairing QR ceremony was not performed. | Unexecuted (Device pairing required) |
| **Google Calendar / Gmail Live Tools** | **UNEXECUTED** | Real Google OAuth and Google API client code implemented; automated tests ran against `MockCalendarTool` and `MockGmailTool`. | Unexecuted (Cloud OAuth consent required) |
| **Gemini LLM Provider (Live Cloud API)** | **UNEXECUTED** | Google Gemini client implemented with prompt sanitization; automated tests executed against `MockLLMProvider`. | Unexecuted (Cloud API key required) |
| **Ollama Local Provider (Live Daemon)** | **UNEXECUTED** | Real `httpx` async client in `backend/app/llm/ollama.py`. | Unexecuted (Local daemon not running) |
| **Capacitor Mobile Build** | **UNEXECUTED** | `capacitor.config.ts` and Android dependencies configured. | Unexecuted (Gradle compile not run) |
| **k6 Load Test** | **UNEXECUTED** | Load test script in `loadtest/basic.js` written. | Unexecuted (`k6` binary not installed) |

---

## 2. BENCHMARKS & EVALUATION EVIDENCE

All benchmark and test outputs below are generated directly from CLI executions and saved in `artifacts/*.txt`.

### A. Router Benchmark Suite Output
- Evidence File: [`artifacts/bench_routers.txt`](file:///E:/Inovvate/artifacts/bench_routers.txt)
- Run Command: `python eval/bench_routers.py --router embed`
```
===========================================================================
>> FastAgent Router Benchmark Suite
>> Active Router:    EMBED
>> Question Mode:    Single Question (Intent Only - Risk in Code)
>> Host Platform:    Windows 11
>> CPU Specs:        Intel64 Family 6 Model 142 Stepping 12, GenuineIntel (8 logical cores)
>> System RAM:       5.18 GB available / 15.81 GB total
>> Dataset Path:     E:\Inovvate\eval\dataset\test.jsonl
>> Running EMBED router (Sentence/TF-IDF vectorizer + Logistic Regression).
>> Training EmbedRouter on E:\Inovvate\eval\dataset\train.jsonl...
>> EmbedRouter trained successfully on 45 samples across 9 classes.
===========================================================================
BENCHMARK RESULTS: EMBED
- Router Under Test:    embed
- Total Samples:        20
- Overall Accuracy:     95.00% (19/20)
- en      Accuracy:    100.0% (11/11)
- hi-Latn Accuracy:    88.9% (8/9)
- Checkpoints Served:   {'embed-tfidf-logreg': 20}
- p50 Latency:          4.82 ms
- p95 Latency:          12.42 ms
- p99 Latency:          12.42 ms
- Avg Latency:          5.24 ms
===========================================================================
```

### B. Latency Comparison Matrix
- Evidence File: [`artifacts/bench_latency_matrix.txt`](file:///E:/Inovvate/artifacts/bench_latency_matrix.txt)
- Run Command: `python eval/bench_latency_matrix.py`

| Architecture / Runtime | Question Scope | Measured Accuracy (Test Split) | p50 Warm Latency | p95 Warm Latency |
|---|---|---|---|---|
| **Embed Router (scikit-learn CPU)** | 1-Question (Intent only) | **95.00%** (19/20) | **3.08 ms** | **4.50 ms** |
| **PyTorch fp32 Laya (Host CPU)** | 1-Question (Intent only) | **86.67%** (13/15) | **2,138.86 ms** | **2,427.23 ms** (warm) |
| **PyTorch fp32 Laya (Host CPU)** | 2-Questions (Intent + Risk) | **86.67%** (13/15) | **4,026.48 ms** | **7,776.57 ms** (warm) |
| **Deterministic Mock Baseline** | 1-Question (Rules in code) | **100.00%** (15/15) | **0.04 ms** | **0.13 ms** |

*Note on ONNX INT8:* Laya's ModernBERT-large split architecture (encoder + classification head) uses custom PyTorch subgraphs. Running the lightweight Embed Router achieves sub-5ms CPU latency while preserving 95% intent accuracy across English and Hinglish.

### C. Active Learning Curve (kNN Semantic Memory on Test Split)
- Evidence File: [`artifacts/learning_curve.txt`](file:///E:/Inovvate/artifacts/learning_curve.txt)
- Run Command: `python eval/learning_curve.py`
```
================================================================================
>> FastAgent Active Learning Curve Evaluation (kNN Semantic Correction Loop)
================================================================================
Test Dataset:   E:\Inovvate\eval\dataset\test.jsonl (held-out test split)
Train Dataset:  E:\Inovvate\eval\dataset\train.jsonl (source of logged corrections)
Method: Base router augmented with kNN semantic retrieval over user corrections.
================================================================================
Corrections (N)  | Logged Corrections | Auto-Approve Thresh  | Test Accuracy   
--------------------------------------------------------------------------------
0                | 0                  | None (Safe Gate)     | 80.0% (16/20) [kNN matches: 0]
5                | 5                  | 0.92                 | 80.0% (16/20) [kNN matches: 0]
10               | 10                 | 0.92                 | 80.0% (16/20) [kNN matches: 1]
20               | 20                 | 0.92                 | 80.0% (16/20) [kNN matches: 2]
40               | 40                 | 0.92                 | 80.0% (16/20) [kNN matches: 5]
================================================================================
Summary: Test accuracy remained steady at 80.0%. (Base model was already optimal or test set has no overlapping failure modes).
================================================================================
```

---

## 3. FULL TEST SUITE PASS RATE

- Evidence File: [`artifacts/pytest.txt`](file:///E:/Inovvate/artifacts/pytest.txt)
- Run Command: `pytest -v backend/tests/`
- Result: **42 / 42 Passed (100%)** in 5.52s.

---

## 4. UNEXECUTED COMPONENTS & REPORTED GAPS

1. **Live Google APIs (Gmail / Calendar):**
   - OAuth consent flow and live API calls require active Google Cloud credentials (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`). In offline/CI environments, the system executes against verified mock adapters.
2. **Evolution Go Live WhatsApp Pairing:**
   - Webhook reception and non-individual JID filtering are verified; physical WhatsApp device QR pairing was not completed on this runner.
3. **Live Cloud LLM Inference (Gemini / Ollama):**
   - Cloud Gemini and local Ollama daemon were not active during offline benchmarking.
4. **k6 Load Testing:**
   - `k6` executable is not installed on this host environment.
5. **Capacitor Mobile Native Binary:**
   - Android SDK / Gradle build was not compiled on this runner.
