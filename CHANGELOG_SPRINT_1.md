# Sprint 1 Changelog — IELTS AI Writing Subsystem

**Sprint Timeline:** Sprint 1  
**Target Milestone:** Production-Ready Asynchronous AI Essay Assessment Engine  
**Status:** COMPLETE & FROZEN (100% Tests Passing)

---

## 🚀 Summary of Deliverables

Sprint 1 successfully delivered the end-to-end architecture, database schema, AI evaluation engine, Spring Boot service layer, and OpenAPI 3.1 contracts for the automated IELTS Writing evaluation pipeline of the ENGONOW Smart LMS.

---

## 📦 Key Deliverables by Architectural Layer

### 1. Database & Persistence Layer (Flyway V3)
* **Hybrid Relational + JSONB Schema**:
  * `writing_submissions`: Tracks student essay text, prompt question, word count, task type, optimistic lock version, and evaluation status (`PENDING`, `PROCESSING`, `SCORED`, `FAILED`).
  * `writing_results`: Stores structured numeric band scores (`DECIMAL(2,1)` precision) and raw JSON feedback payload (`feedback_detail`).
  * `outbox_events`: Implements the Transactional Outbox Pattern to decouple HTTP request ingestion from AI queue dispatching.
* **Dialect Portability**: Hardened JPA annotations (`@UuidGenerator`, `@JdbcTypeCode(SqlTypes.JSON)`) to guarantee compatibility across MySQL 8.x and PostgreSQL 15+.

### 2. Psychometric & Scoring Precision (`CambridgeRoundingUtil`)
* Implemented the official Cambridge IELTS half-band rounding algorithm:
  $$\text{Mean Fraction} \in [0.0, 0.25) \implies 0.0$$
  $$\text{Mean Fraction} \in [0.25, 0.75) \implies 0.5$$
  $$\text{Mean Fraction} \in [0.75, 1.0) \implies 1.0 \text{ (next whole band)}$$
* Validated with **33 comprehensive unit tests** covering standard distributions, boundary values, and all 0.25-step rounding permutations.

### 3. AI Worker Pipeline (Gemini 2.5 Flash & Prompt Decoupling)
* **Prompt Decoupling**: Externalized system and user prompts into `providers/prompts/writing_system.txt` and `writing_user.txt`, dynamically referenced via environment variables for zero-downtime prompt engineering.
* **Injection-Proof Substitution**: Replaced dangerous `str.format()` with deterministic `.replace()` parameter substitution, eliminating brace-injection crashes on student essays.
* **Non-Blocking File I/O & Thread-Safe Caching**: Utilized `asyncio.to_thread` with thread locks to eliminate event-loop blocking during prompt hot-reloading.
* **Resiliency & Metrics**: Integrated `backoff` with exponential backoff and full jitter across transient Google GenAI exceptions (`ResourceExhausted`, `DeadlineExceeded`, `InternalServerError`), instrumented with Prometheus telemetry.

### 4. Cross-Language Enum & Type Parity (Python ↔ Java)
* Synchronized Pydantic v2 schemas and Java Jackson records 1:1:
  * `TaskType`: `ACADEMIC_TASK1`, `GENERAL_TASK1`, `TASK2`, `FULL_TEST`
  * `CorrectionErrorType`: `GRAMMAR`, `VOCABULARY`, `SPELLING`, `PUNCTUATION`, `COHESION`, `TASK_RELEVANCE`
  * `ErrorSeverity`: `MINOR`, `MAJOR`, `CRITICAL`
  * `WritingCriterion`: `TASK_ACHIEVEMENT`, `TASK_RESPONSE`, `COHERENCE_COHESION`, `LEXICAL_RESOURCE`, `GRAMMATICAL_RANGE_ACCURACY`
* Added pre-validation normalizers in Python to seamlessly map legacy short-codes (e.g. `TR` $\to$ `TASK_RESPONSE`, `SVA` $\to$ `GRAMMAR`).

### 5. Java Spring Boot Service & REST API Layer
* **`WritingSubmissionService` & `WritingSubmissionServiceImpl`**:
  * Transactional outbox serialization occurs *prior* to database insertion with fail-fast validation.
  * Atomic invalidation and version management for previous evaluation results.
* **`WritingSubmissionController`**:
  * `POST /api/v1/writing/submissions/submit` $\implies$ Returns `202 Accepted` with `WritingSubmissionResponseDTO`.
  * `GET /api/v1/writing/submissions/{submissionId}` $\implies$ Returns `200 OK` with `WritingResultResponseDTO` (or `422 Unprocessable Entity` while evaluating).
* **`WritingWebhookController`**:
  * `POST /api/v1/writing/webhook/result` $\implies$ Protected by `@Idempotent` Redis distributed lock (`webhook:writing:{submissionId}`, 24h TTL).
* **`GlobalExceptionHandler`**:
  * Mapped `ConcurrencyFailureException` and `ObjectOptimisticLockingFailureException` to `HTTP 409 Conflict`.

### 6. Documentation & Contract Freeze
* **OpenAPI 3.1.0 Specification**: [`docs/api/openapi-spec-v1.0.yaml`](file:///d:/Project%20CV/engonow-lms/docs/api/openapi-spec-v1.0.yaml)
* **Frontend & Developer Integration Guide**: [`docs/WRITING_SUBSYSTEM_INTEGRATION_GUIDE.md`](file:///d:/Project%20CV/engonow-lms/docs/WRITING_SUBSYSTEM_INTEGRATION_GUIDE.md)

---

## 🧪 Validation & Test Coverage Summary

| Test Suite | Scope | Total Tests | Status |
| :--- | :--- | :---: | :---: |
| **CambridgeRoundingUtilTest** | Cambridge Half-Band Rounding Math | 33 | **PASSED** |
| **WritingSubmissionServiceTest** | Submission lifecycle, outbox events, invalidation | 6 | **PASSED** |
| **WritingSubmissionControllerTest** | REST endpoints (`POST /submit`, `GET /{id}`) | 2 | **PASSED** |
| **WritingWebhookControllerTest** | Webhook callback ingestion & Redis idempotency | 1 | **PASSED** |
| **WritingWebhookConcurrencyIntegrationTest** | Parallel webhook bursts & optimistic locking | 2 | **PASSED** |
| **Full Spring Boot Backend Suite** | All application modules | 65 | **PASSED (BUILD SUCCESS)** |
| **Python Gemini Writing Provider** | Gemini 2.5 Flash provider, validation, backoff | 11 | **PASSED** |
| **Python Prompt Loader Concurrency** | Thread-safe prompt caching & hot-reloading | 2 | **PASSED** |
