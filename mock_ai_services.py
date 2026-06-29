"""
ENGONOW Smart LMS — External AI Microservices Mock Server
==========================================================
Simulates two external AI services used by the Java Spring Boot backend:
  1. /api/v1/ai/omr-scan        → Mimics OpenCV bubble-sheet extraction
  2. /api/v1/ai/speaking-analyze → Mimics Azure Pronunciation + LLM pipeline

Run: uvicorn mock_ai_services:app --host 0.0.0.0 --port 8001 --reload
  or: python mock_ai_services.py
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, Field
from typing import List
import random
import uvicorn
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("engonow.mock")

app = FastAPI(
    title="ENGONOW External AI Mocking Services",
    description="Simulates Azure Pronunciation Assessment + OpenCV OMR microservices for integration testing.",
    version="1.0.0",
)


# ──────────────────────────────────────────────────────────────────────────────
# Response Models
# ──────────────────────────────────────────────────────────────────────────────

class OmrAnswer(BaseModel):
    question_number: int = Field(..., description="1-based question index", ge=1)
    student_answer: str = Field(..., description="Recognised bubble: A, B, C, or D")


class SpeakingEvidence(BaseModel):
    criterion: str = Field(..., description="Evaluation criterion: GRAMMAR or LEXICAL")
    quote: str = Field(..., description="Exact quote of student spoken utterance containing error/example")
    error_type: str = Field(..., description="Categorised error type (e.g. Verb Tense, Vague Vocabulary)")
    correction: str = Field(..., description="Suggested correction for the student's quote")
    explanation: str = Field(..., description="Detailed explanation of the error and correction")


class SelfCorrection(BaseModel):
    original: str = Field(..., description="The original word/phrase before self-correction")
    marker: str = Field(..., description="The marker word used (e.g. sorry, I mean, no)")
    corrected: str = Field(..., description="The corrected word/phrase")
    type: str = Field(..., description="Type of self-correction: GRAMMAR or LEXICAL")


class SpeakingAnalysisResult(BaseModel):
    session_id: str = Field(..., description="Unique speaking session identifier")
    pronunciation_score: float = Field(..., ge=1.0, le=9.0, description="IELTS Pronunciation band (1.0–9.0)")
    fluency_score: float = Field(..., ge=1.0, le=9.0, description="IELTS Fluency & Coherence band (1.0–9.0)")
    lexical_score: float = Field(..., ge=1.0, le=9.0, description="IELTS Lexical Resource band (1.0–9.0)")
    grammar_score: float = Field(..., ge=1.0, le=9.0, description="IELTS Grammatical Range & Accuracy band (1.0–9.0)")
    evidences: List[SpeakingEvidence] = Field(default=[], description="Nested evidence list supporting the lexical and grammar bands")
    self_corrections: List[SelfCorrection] = Field(default=[], description="List of self-corrections detected in student response")
    feedback_text: str = Field(..., description="AI-generated student feedback summary")


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.post(
    "/api/v1/ai/omr-scan",
    response_model=List[OmrAnswer],
    summary="OMR Bubble-Sheet Scanner",
    description=(
        "Accepts a scanned answer sheet image and an exam_id via multipart/form-data. "
        "Returns a list of {question_number, student_answer} objects simulating "
        "OpenCV bubble-detection for a 40-question exam."
    ),
)
async def mock_omr_scan(
    exam_id: int = Form(..., description="ID of the exam being scanned", ge=1),
    file: UploadFile = File(..., description="Scanned answer-sheet image (JPEG/PNG)"),
):
    if file.content_type not in ("image/jpeg", "image/png", "image/jpg", "application/octet-stream"):
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {file.content_type}. Expected image/jpeg or image/png.",
        )

    contents = await file.read()
    logger.info(
        "[OMR SERVICE] exam_id=%d | file='%s' (%d bytes) | Simulating bubble-sheet extraction...",
        exam_id, file.filename, len(contents),
    )

    # Simulate OpenCV processing delay (100–400ms)
    await asyncio.sleep(random.uniform(0.1, 0.4))

    results = [
        OmrAnswer(
            question_number=i,
            student_answer=random.choice(["A", "B", "C", "D"]),
        )
        for i in range(1, 41)
    ]

    logger.info("[OMR SERVICE] Extraction complete. Returning %d answers for exam_id=%d.", len(results), exam_id)
    return results


@app.post(
    "/api/v1/ai/speaking-analyze",
    response_model=SpeakingAnalysisResult,
    summary="Hybrid Speaking Analyzer",
    description=(
        "Accepts a session_id and audio_url via form fields. "
        "Simulates the Hybrid AI pipeline: Azure Pronunciation Assessment (80% weight) "
        "combined with LLM-based Lexical/Grammar analysis (20% weight). "
        "Returns per-criterion IELTS band scores and a feedback summary containing citable evidences."
    ),
)
async def mock_speaking_analyze(
    session_id: str = Form(..., description="Unique speaking session ID"),
    audio_url: str = Form(..., description="Cloudinary URL of the uploaded audio recording"),
):
    if not session_id.strip():
        raise HTTPException(status_code=422, detail="session_id must not be blank.")

    logger.info(
        "[SPEAKING SERVICE] session_id='%s' | audio_url='%s' | Running AI analysis pipeline...",
        session_id, audio_url,
    )

    # Simulate Azure Pronunciation Assessment + LLM latency (500ms–1500ms)
    await asyncio.sleep(random.uniform(0.5, 1.5))

    # Generate a random selection of evidences for grammar and lexical criteria
    grammar_pool = [
        SpeakingEvidence(
            criterion="GRAMMAR",
            quote="Yesterday I go to the marketplace with my family",
            error_type="Verb Tense",
            correction="Yesterday I went to the marketplace with my family",
            explanation="Learner used present simple 'go' instead of past simple 'went' for a past action."
        ),
        SpeakingEvidence(
            criterion="GRAMMAR",
            quote="She don't like studying english at night",
            error_type="Subject-Verb Agreement",
            correction="She doesn't like studying English at night",
            explanation="Subject 'She' (third-person singular) requires 'doesn't' instead of 'don't'."
        )
    ]

    lexical_pool = [
        SpeakingEvidence(
            criterion="LEXICAL",
            quote="I want to elevate my IELTS level because it is good",
            error_type="Vague Vocabulary",
            correction="I want to improve my IELTS score because it is crucial for my career",
            explanation="Replaced generic word 'good' with precise professional vocabulary 'crucial for my career'."
        ),
        SpeakingEvidence(
            criterion="LEXICAL",
            quote="Studying abroad gives a big chance to learn new things",
            error_type="Collocation Error",
            correction="Studying abroad offers a great opportunity to acquire new knowledge",
            explanation="Replaced generic 'gives a big chance' with formal collocation 'offers a great opportunity'."
        )
    ]

    # Pick randomly 1 or 2 items from each pool to test validation overrides in Java backend
    selected_grammar = random.sample(grammar_pool, k=random.choice([1, 2]))
    selected_lexical = random.sample(lexical_pool, k=random.choice([1, 2]))
    evidences = selected_grammar + selected_lexical

    # Inject static mocked self-corrections list for evaluation gatekeeper testing
    self_corrections = [
        SelfCorrection(
            original="I go",
            marker="sorry",
            corrected="I went",
            type="GRAMMAR"
        ),
        SelfCorrection(
            original="She don't",
            marker="I mean",
            corrected="She doesn't",
            type="GRAMMAR"
        )
    ]

    result = SpeakingAnalysisResult(
        session_id=session_id,
        pronunciation_score=round(random.uniform(5.0, 9.0), 1),
        fluency_score=round(random.uniform(5.0, 9.0), 1),
        lexical_score=round(random.uniform(5.0, 9.0), 1),
        grammar_score=round(random.uniform(5.0, 9.0), 1),
        evidences=evidences,
        self_corrections=self_corrections,
        feedback_text=(
            "Holistic feedback string describing overall performance. Good vocabulary range with "
            "attempts at idiomatic expression. Sentence-level stress patterns need refinement."
        ),
    )

    logger.info(
        "[SPEAKING SERVICE] Analysis complete for session_id='%s'. "
        "Pronunciation=%.1f, Fluency=%.1f, Lexical=%.1f, Grammar=%.1f | Evidences Count=%d | Self-Corrections=%d",
        session_id,
        result.pronunciation_score, result.fluency_score,
        result.lexical_score, result.grammar_score,
        len(evidences), len(self_corrections)
    )

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health", summary="Service Health Check")
def health_check():
    return {"status": "UP", "service": "ENGONOW AI Mock Services", "version": "1.0.0"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
