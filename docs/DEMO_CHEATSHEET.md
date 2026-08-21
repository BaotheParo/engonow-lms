# ENGONOW AI Writing Subsystem — 5-Minute Technical Demo Cheatsheet

---

## 🎯 Demo Overview
This cheat sheet guides you step-by-step through a **5-minute live technical demonstration** of the ENGONOW AI Writing Subsystem, illustrating the asynchronous submission flow, Outbox Event generation, Redis-guarded idempotent webhook ingestion, and Cambridge IELTS score calculation.

---

## 🚀 Pre-Demo Checklist (30 Seconds Before Demo)
1. **Ensure Postman is open** with `ENGONOW Writing Subsystem Demo` collection and `ENGONOW Local Environment` selected.
2. **Ensure Backend is running**: Spring Boot active at `http://localhost:8080`.
3. **Reset Environment**: Verify `currentSubmissionId` is empty in Postman Environment variables.

---

## 🕹️ Live 4-Step Click & Presentation Sequence

### Step 1: Submit Essay (`POST /api/v1/writing/submissions/submit`)
* **Action**: Click **Send** on Request `01. Submit Essay (Student Submission)`.
* **Expected Response**: `HTTP 202 Accepted` returning `{ "id": "...", "status": "PENDING", ... }`.
* **Screen Highlights**:
  - Show the `HTTP 202 Accepted` status code (asynchronous decoupling design).
  - Point out that word count (`168` words) is automatically computed server-side.
  - Show the Postman Console / Environment tab showing `currentSubmissionId` dynamically populated by the test script without manual copy-pasting.
* **Talking Point**: *"We accept student submissions asynchronously, returning a 202 immediately to maintain high throughput. Under the hood, an Outbox Event is atomically saved alongside the submission in the same database transaction."*

---

### Step 2: Explain Asynchronous Architecture (No Click Required)
* **Screen Highlights**: Open the Architecture / System Diagram slide or code snippet of `WritingSubmissionServiceImpl`.
* **Talking Point**: *"The Spring Boot backend emits a Kafka event via the Transactional Outbox Pattern. A Python worker running Google Gemini 2.5 Flash processes the essay in a background event loop, enforcing JSON schema outputs with Pydantic v2."*

---

### Step 3: Trigger AI Webhook Ingestion (`POST /api/v1/writing/webhook/result`)
* **Action**: Click **Send** on Request `02. Simulate AI Webhook Callback (Auto-Grading Callback)`.
* **Expected Response**: `HTTP 200 OK` with `{ "status": "ACK" }`.
* **Screen Highlights**:
  - Point out `submissionId`: `"{{currentSubmissionId}}"` in the request body, seamlessly resolving the saved ID.
  - Highlight the 4 raw sub-scores: `taskAchievementScore: 6.0`, `coherenceCohesionScore: 5.0`, `lexicalResourceScore: 6.0`, `grammaticalRangeScore: 5.0`.
  - Highlight the rich structured JSON `feedbackDetail` containing `examinerSummary`, character-offset `corrections` (`startIndex`/`endIndex`), and `band7Option`/`band8Option` upgrades.
  - Note the `@Idempotent` annotation protecting this endpoint with Redis distributed locks to handle network retries safely.
* **Talking Point**: *"The Python worker sends back granular IELTS criterion scores and character-anchored corrections. Notice how our Distributed Idempotency Lock in Redis prevents duplicate scoring even if the webhook retries."*

---

### Step 4: Query Final Graded Result (`GET /api/v1/writing/submissions/{{currentSubmissionId}}`)
* **Action**: Click **Send** on Request `03. Get Final Graded Result (Client Poll)`.
* **Expected Response**: `HTTP 200 OK` with `overallBand: 5.5` and Postman assertions passing (`2/2 PASS`).
* **Screen Highlights**:
  - Highlight the `overallBand: 5.5` field in the response.
  - Point to the passing Postman test script asserting `overallBand === 5.5`.
  - Explain the official Cambridge IELTS rounding logic: `(6.0 + 5.0 + 6.0 + 5.0) / 4 = 5.5` (Exact half-band rounding).
* **Talking Point**: *"The backend applies the official Cambridge IELTS rounding algorithm. The student receives their overall band score of 5.5 along with detailed pedagogical advice."*

---

## ⚡ Secret Weapons (30-Second Technical Differentiators)

### Secret Weapon 1: Live Idempotency Lock Proof (Trigger Request 02 a Second Time)
* **Action**: Right after Request 02 returns `200 OK`, click **Send** again immediately in front of the mentor/examiner.
* **Result**: Postman returns `HTTP 409 Conflict` (or blocked by Redis Lock).
* **Talking Point**: *"As you can see, if the AI Worker experiences network instability and retries sending a duplicate result, my Redis Idempotency Lock immediately blocks it with HTTP 409, ensuring that duplicate results never enter the database."*

### Secret Weapon 2: PostgreSQL JSONB GIN Index & Partial Unique Index
* **Action**: When opening DBeaver or pgAdmin in Step 4—in addition to showing `SELECT * FROM writing_results`—expand the Indexes tab for the `writing_results` table.
* **Screen Highlights**:
  - `idx_writing_results_feedback_detail_gin`: GIN Index on JSONB `feedback_detail`.
  - `ux_writing_results_current_per_submission`: Partial Unique Index (`WHERE is_current = true`).
* **Talking Point**: *"The entire detailed feedback structure is compressed within the JSONB column, but I have created a GIN Index so that if the center later wants to run system-wide queries to gather statistics on grammar errors across millions of submissions, the query performance remains $O(1)$ fast. Furthermore, the partial unique index guarantees at database level that only one result per submission can be active (`is_current = true`)."*

---

## ❓ Frequently Asked Examiner Questions & Rapid Answers

| Question | Rapid Technical Answer |
| :--- | :--- |
| **Q1: How do you prevent double-grading if the Python worker retries the webhook callback?** | *"We use an `@Idempotent` AOP annotation backed by Redis distributed locks on key `'webhook:writing:' + submissionId` with a 24-hour TTL. Duplicate callbacks are rejected immediately with HTTP 409."* |
| **Q2: What happens if the student's essay contains curly braces `{}` or injection strings?** | *"On the Python worker side, our custom `_secure_format_prompt` engine uses explicit substring replacement rather than Python's `.format()`, preventing `KeyError` crashes and template injection."* |
| **Q3: How is Cambridge IELTS rounding implemented?** | *"According to the IELTS Cambridge standard, if the average of the 4 criteria has a fractional part of .25 (or .125), it is rounded UP to .50 (e.g. $6.125 \implies 6.25 \implies 6.5$); if the fractional part is .75 (or .625), it is rounded UP to the next whole band (e.g. $6.625 \implies 6.75 \implies 7.0$). The system uses BigDecimal with RoundingMode.HALF_UP and custom Cambridge rounding logic to ensure absolute precision."* |
| **Q4: How do you guarantee database consistency when queuing submissions?** | *"We use the Transactional Outbox Pattern. Saving the `WritingSubmission` and the `OutboxEvent` happens in a single `@Transactional` method, eliminating dual-write race conditions."* |
| **Q5: How do frontend clients highlight sentence-level errors?** | *"The AI response provides exact `startIndex` and `endIndex` character offsets relative to the original submission, allowing the UI to render highlights without fuzzy text matching."* |
