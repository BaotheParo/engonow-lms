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


class SpeakingAnalysisResult(BaseModel):
    session_id: str = Field(..., description="Unique speaking session identifier")
    pronunciation_score: float = Field(..., ge=1.0, le=9.0, description="IELTS Pronunciation band (1.0–9.0)")
    fluency_score: float = Field(..., ge=1.0, le=9.0, description="IELTS Fluency & Coherence band (1.0–9.0)")
    lexical_score: float = Field(..., ge=1.0, le=9.0, description="IELTS Lexical Resource band (1.0–9.0)")
    grammar_score: float = Field(..., ge=1.0, le=9.0, description="IELTS Grammatical Range & Accuracy band (1.0–9.0)")
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
        "Returns per-criterion IELTS band scores and a feedback summary."
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

    result = SpeakingAnalysisResult(
        session_id=session_id,
        pronunciation_score=round(random.uniform(5.0, 9.0), 1),
        fluency_score=round(random.uniform(5.0, 9.0), 1),
        lexical_score=round(random.uniform(5.0, 9.0), 1),
        grammar_score=round(random.uniform(5.0, 9.0), 1),
        feedback_text=(
            "Good vocabulary range with attempts at idiomatic expression. "
            "Watch out for final consonant deletion in words like 'past' and 'test'. "
            "Sentence-level stress patterns need refinement for improved intelligibility. "
            "Consider expanding use of cohesive devices to improve discourse coherence."
        ),
    )

    logger.info(
        "[SPEAKING SERVICE] Analysis complete for session_id='%s'. "
        "Pronunciation=%.1f, Fluency=%.1f, Lexical=%.1f, Grammar=%.1f",
        session_id,
        result.pronunciation_score, result.fluency_score,
        result.lexical_score, result.grammar_score,
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
