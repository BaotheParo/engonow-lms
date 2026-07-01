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
from typing import List, Tuple
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
    criterion: str = Field(..., description="Evaluation criterion: GRAMMAR, LEXICAL, or FLUENCY")
    part: str = Field(..., description="IELTS part: PART_1, PART_2, or PART_3")
    question: str = Field(..., description="Specific question from the examiner")
    quote: str = Field(..., description="Exact quote of student spoken utterance containing error/example")
    error_type: str = Field(..., description="Categorised error type (e.g. Verb Tense, Vague Vocabulary, Unnatural Hesitation)")
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
    evidences: List[SpeakingEvidence] = Field(default=[], description="Nested evidence list supporting the lexical, grammar, and fluency bands")
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
            part="PART_1",
            question="Describe your hometown.",
            quote="Yesterday I go to the marketplace with my family",
            error_type="Verb Tense",
            correction="Yesterday I went to the marketplace with my family",
            explanation="Learner used present simple 'go' instead of past simple 'went' for a past action."
        ),
        SpeakingEvidence(
            criterion="GRAMMAR",
            part="PART_2",
            question="Describe a book you enjoyed reading.",
            quote="She don't like studying english at night",
            error_type="Subject-Verb Agreement",
            correction="She doesn't like studying English at night",
            explanation="Subject 'She' (third-person singular) requires 'doesn't' instead of 'don't'."
        )
    ]

    lexical_pool = [
        SpeakingEvidence(
            criterion="LEXICAL",
            part="PART_1",
            question="What do you do in your free time?",
            quote="I want to elevate my IELTS level because it is good",
            error_type="Vague Vocabulary",
            correction="I want to improve my IELTS score because it is crucial for my career",
            explanation="Replaced generic word 'good' with precise professional vocabulary 'crucial for my career'."
        ),
        SpeakingEvidence(
            criterion="LEXICAL",
            part="PART_2",
            question="Describe a memorable journey.",
            quote="Studying abroad gives a big chance to learn new things",
            error_type="Collocation Error",
            correction="Studying abroad offers a great opportunity to acquire new knowledge",
            explanation="Replaced generic 'gives a big chance' with formal collocation 'offers a great opportunity'."
        )
    ]

    # Syntactic Pause Mapping Mock Data
    word_timestamps = [
        {"word": "well", "start": 0.0, "end": 0.4},
        {"word": "however,", "start": 0.5, "end": 1.0},
        {"word": "I", "start": 2.7, "end": 2.9},    # Pause of 1.7s after discourse marker "however," -> ignored
        {"word": "went", "start": 3.0, "end": 3.4},
        {"word": "to", "start": 3.5, "end": 3.8},
        {"word": "the", "start": 3.9, "end": 4.1},
        {"word": "zoo", "start": 5.8, "end": 6.2},    # Pause of 1.7s after article "the" -> Unnatural hesitation! (PART_1)
        {"word": "because", "start": 6.3, "end": 6.8},
        {"word": "it", "start": 6.9, "end": 7.1},
        {"word": "is", "start": 7.2, "end": 7.4},
        {"word": "in", "start": 7.5, "end": 7.7},
        {"word": "the", "start": 7.8, "end": 8.0},
        {"word": "city", "start": 10.0, "end": 10.4}  # Pause of 2.0s after article "the" -> Unnatural hesitation! (PART_3)
    ]

    def analyze_fluency_pauses(timestamps: List[dict], initial_score: float) -> Tuple[float, List[SpeakingEvidence]]:
        penalties = 0.0
        fluency_evidences = []
        pause_count = 0
        for idx in range(1, len(timestamps)):
            prev = timestamps[idx - 1]
            curr = timestamps[idx]
            pause_duration = curr["start"] - prev["end"]
            if pause_duration > 1.5:
                word_before = prev["word"]
                word_before_clean = word_before.rstrip(".,?!").lower()
                
                # Rule 1 & 2: Natural Pause (ignored)
                if word_before.endswith((".", ",", "?")) or word_before_clean in ['well', 'so', 'however', 'therefore', 'meanwhile', 'furthermore']:
                    continue
                
                # Rule 3: Unnatural Hesitation (penalized)
                if word_before_clean in ['in', 'on', 'at', 'to', 'for', 'a', 'an', 'the', 'i', 'you', 'he', 'she', 'it']:
                    penalties += 0.5
                    quote_text = f"...{word_before} [{pause_duration:.1f}s pause] {curr['word']}..."
                    pause_count += 1
                    part_tag = "PART_1" if pause_count == 1 else "PART_3"
                    fluency_evidences.append(
                        SpeakingEvidence(
                            criterion="FLUENCY",
                            part=part_tag,
                            question="What is your favorite place in the city?",
                            quote=quote_text,
                            error_type="Unnatural Hesitation",
                            correction="Avoid pausing mid-sentence after grammatical markers.",
                            explanation=f"Student demonstrated a {pause_duration:.1f}-second breakdown."
                        )
                    )
        final_score = max(1.0, initial_score - penalties)
        final_score = round(final_score, 1)
        return final_score, fluency_evidences

    # Evaluate Fluency pauses
    raw_fluency = round(random.uniform(5.5, 9.0), 1)
    final_fluency, fluency_evidences = analyze_fluency_pauses(word_timestamps, raw_fluency)

    # Pick randomly 1 or 2 items from each pool to test validation overrides in Java backend
    selected_grammar = random.sample(grammar_pool, k=random.choice([1, 2]))
    selected_lexical = random.sample(lexical_pool, k=random.choice([1, 2]))
    evidences = selected_grammar + selected_lexical + fluency_evidences

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
        fluency_score=final_fluency,
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
