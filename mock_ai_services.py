"""
ENGONOW Smart LMS — External AI Microservices Mock Server
==========================================================
Simulates two external AI services used by the Java Spring Boot backend:
  1. /api/v1/ai/omr-scan        → Mimics OpenCV bubble-sheet extraction
  2. /api/v1/ai/speaking-analyze → Evaluates student response using Groq Whisper + Gemini 1.5 Flash

Run: uvicorn mock_ai_services:app --host 0.0.0.0 --port 8001 --reload
  or: python mock_ai_services.py
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import random
import uvicorn
import asyncio
import logging
import httpx
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("engonow.mock")

app = FastAPI(
    title="ENGONOW External AI Services",
    description="Azure Pronunciation Assessment (Groq Whisper + Gemini) + OpenCV OMR microservices.",
    version="2.0.0",
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────────────────
# Response Models
# ──────────────────────────────────────────────────────────────────────────────

class OmrAnswer(BaseModel):
    question_number: int = Field(..., description="1-based question index", ge=1)
    student_answer: str = Field(..., description="Recognised bubble: A, B, C, or D")


class SpeakingEvidence(BaseModel):
    criterion: str = Field(..., description="Evaluation criterion: GRAMMAR, LEXICAL, FLUENCY, or PRONUNCIATION")
    part: str = Field(..., description="IELTS part: PART_1, PART_2, or PART_3")
    question: str = Field(..., description="Specific question from the examiner")
    quote: str = Field(..., description="Exact quote of student spoken utterance containing error/example")
    error_type: str = Field(..., description="Categorised error type")
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
    evidences: List[SpeakingEvidence] = Field(default=[], description="Nested evidence list supporting scores")
    self_corrections: List[SelfCorrection] = Field(default=[], description="List of self-corrections detected")
    feedback_text: str = Field(..., description="AI-generated student feedback summary")


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.post(
    "/api/v1/ai/omr-scan",
    response_model=List[OmrAnswer],
    summary="OMR Bubble-Sheet Scanner",
    description="Scans OpenCV bubble-sheet extraction.",
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
    summary="AI IELTS Speaking Analyzer (Groq Whisper + Gemini 1.5 Flash)",
    description=(
        "Transcribes the student response audio using Groq Whisper, calculates hesitation pauses, "
        "and evaluates grammar, lexical resource, and fluency against the specific questions using Gemini 1.5 Flash."
    ),
)
async def mock_speaking_analyze(
    file: UploadFile = File(..., description="The audio containing ONLY the student's answers"),
    questions_metadata: str = Form(..., description="JSON string array of the exact questions asked by the Frontend"),
    session_id: str = Form("mock-session-123", description="Unique speaking session ID")
):
    if not questions_metadata.strip():
        raise HTTPException(status_code=422, detail="questions_metadata must not be blank.")

    try:
        metadata_list = json.loads(questions_metadata)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON format in questions_metadata: {str(e)}")

    GROQ_API_KEY = "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"
    GEMINI_API_KEY = "AQ.Ab8RN6IgM2qCjp5qTChQ6LPme0NaOAUGXY6Iwq6x_-vXB9WMxQ"

    contents = await file.read()
    logger.info(
        f"[SPEAKING SERVICE] Analyzing student audio for session_id='{session_id}' | "
        f"file='{file.filename}' ({len(contents)} bytes) | metadata length={len(metadata_list)}"
    )

    try:
        # ─── PHASE 1: STT (Groq Whisper-large-v3) ───
        logger.info("[SPEAKING SERVICE] Initializing Groq Whisper transcription call...")
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}"
        }
        files = {
            "file": (file.filename, contents, file.content_type or "audio/mpeg")
        }
        data = {
            "model": "whisper-large-v3",
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word"
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            stt_response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data
            )

        if stt_response.status_code != 200:
            raise Exception(f"Groq API error: {stt_response.status_code} - {stt_response.text}")

        stt_json = stt_response.json()

        # Parse word timestamps
        words = []
        raw_words = stt_json.get("words")
        if raw_words:
            for w in raw_words:
                words.append({
                    "word": w.get("word"),
                    "start": w.get("start"),
                    "end": w.get("end")
                })

        # Calculate hesitation pauses
        annotated_transcript = ""
        if words:
            annotated_transcript = words[0]["word"]
            for i in range(1, len(words)):
                prev_end = words[i - 1]["end"]
                curr_start = words[i]["start"]
                pause_duration = curr_start - prev_end
                if pause_duration > 1.5:
                    annotated_transcript += f" [{round(pause_duration, 1)}s pause]"
                annotated_transcript += " " + words[i]["word"]
        else:
            annotated_transcript = stt_json.get("text", "")

        logger.info(f"[SPEAKING SERVICE] Transcript generated: {annotated_transcript[:200]}...")

        # ─── PHASE 2: LLM Evaluation (Gemini 2.5 Flash) ───
        logger.info("[SPEAKING SERVICE] Initializing Gemini 2.5 Flash evaluation call...")
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

        system_instruction = (
            "You are an IELTS Examiner. The student was asked the following specific questions:\n"
            f"{json.dumps(metadata_list, indent=2)}\n\n"
            f"Here is their complete transcribed response with recorded pauses:\n"
            f"\"{annotated_transcript}\"\n\n"
            "Evaluate grammar, lexical, and fluency errors based on these exact questions. "
            "You must respond with a single, valid JSON object matching the SpeakingAnalysisResult Pydantic schema exactly. "
            "Ensure the JSON matches this structure exactly:\n"
            "{\n"
            "  \"pronunciation_score\": float (1.0 to 9.0),\n"
            "  \"fluency_score\": float (1.0 to 9.0),\n"
            "  \"lexical_score\": float (1.0 to 9.0),\n"
            "  \"grammar_score\": float (1.0 to 9.0),\n"
            "  \"evidences\": [\n"
            "    {\n"
            "      \"criterion\": \"GRAMMAR\" | \"LEXICAL\" | \"FLUENCY\" | \"PRONUNCIATION\",\n"
            "      \"part\": \"PART_1\" | \"PART_2\" | \"PART_3\",\n"
            "      \"question\": \"exact question from metadata\",\n"
            "      \"quote\": \"exact quote from transcript\",\n"
            "      \"error_type\": \"category of error\",\n"
            "      \"correction\": \"suggested correction\",\n"
            "      \"explanation\": \"pedagogical explanation\"\n"
            "    }\n"
            "  ],\n"
            "  \"self_corrections\": [\n"
            "    {\n"
            "      \"original\": \"original incorrect/repeated text\",\n"
            "      \"marker\": \"marker word used (like sorry, I mean, no, etc.)\",\n"
            "      \"corrected\": \"corrected text\",\n"
            "      \"type\": \"GRAMMAR\" | \"LEXICAL\"\n"
            "    }\n"
            "  ],\n"
            "  \"feedback_text\": \"summary of feedback\"\n"
            "}\n"
            "Note: Return raw JSON only, do not wrap in markdown block wrappers."
        )

        gemini_payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": system_instruction
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            gemini_response = await client.post(
                gemini_url,
                headers={"Content-Type": "application/json"},
                json=gemini_payload
            )

        if gemini_response.status_code != 200:
            raise Exception(f"Gemini API error: {gemini_response.status_code} - {gemini_response.text}")

        gemini_json = gemini_response.json()

        candidates = gemini_json.get("candidates", [])
        if not candidates:
            raise Exception("No candidates returned from Gemini.")

        text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if text_content.strip().startswith("```"):
            text_content = text_content.strip().split("```")[1]
            if text_content.startswith("json"):
                text_content = text_content[4:]

        evaluation_result = json.loads(text_content)

        result = SpeakingAnalysisResult(
            session_id=session_id,
            pronunciation_score=round(float(evaluation_result.get("pronunciation_score", 7.0)), 1),
            fluency_score=round(float(evaluation_result.get("fluency_score", 7.0)), 1),
            lexical_score=round(float(evaluation_result.get("lexical_score", 7.0)), 1),
            grammar_score=round(float(evaluation_result.get("grammar_score", 7.0)), 1),
            evidences=[
                SpeakingEvidence(
                    criterion=e.get("criterion", "GRAMMAR"),
                    part=e.get("part", "PART_1"),
                    question=e.get("question", ""),
                    quote=e.get("quote", ""),
                    error_type=e.get("error_type", ""),
                    correction=e.get("correction", ""),
                    explanation=e.get("explanation", "")
                )
                for e in evaluation_result.get("evidences", [])
            ],
            self_corrections=[
                SelfCorrection(
                    original=sc.get("original", ""),
                    marker=sc.get("marker", ""),
                    corrected=sc.get("corrected", ""),
                    type=sc.get("type", "GRAMMAR")
                )
                for sc in evaluation_result.get("self_corrections", [])
            ],
            feedback_text=evaluation_result.get("feedback_text", "")
        )

        logger.info(f"[SPEAKING SERVICE] Evaluation generated successfully for session_id='{session_id}'")
        return result

    except Exception as e:
        logger.error(f"[SPEAKING SERVICE] API call failure: {str(e)}. Using fallback mock analyzer...")

        # ─── FALLBACK CODE (Offline & Key protection) ───
        q1 = "Describe a person you know who likes to cook for other people."
        q2 = "Should children be taught cooking skills from a young age?"
        if len(metadata_list) > 0:
            q1 = metadata_list[0].get("question", q1)
        if len(metadata_list) > 1:
            q2 = metadata_list[1].get("question", q2)

        evidences = [
            SpeakingEvidence(
                criterion="FLUENCY",
                part="PART_2",
                question=q1,
                quote="...she is really enjoy baking she she She doesn't take any class...",
                error_type="Unnatural Hesitation",
                correction="...she really enjoys baking. She doesn't take any classes...",
                explanation="The student repeats 'she she She' during Part 2 when transitioning, resulting in an unnatural hesitation."
            ),
            SpeakingEvidence(
                criterion="FLUENCY",
                part="PART_3",
                question=q2,
                quote="...Because sometimes... [2.1s pause] they could first start with some recipe...",
                error_type="Natural Cognitive Pause",
                correction="...Because sometimes, they could start with a base recipe...",
                explanation="A pause of 2.1s is recorded after 'sometimes' in Part 3. This is classified as a natural cognitive pause."
            )
        ]

        self_corrections = [
            SelfCorrection(
                original="she",
                marker="repetition and shift",
                corrected="She doesn't",
                type="GRAMMAR"
            )
        ]

        return SpeakingAnalysisResult(
            session_id=session_id,
            pronunciation_score=7.8,
            fluency_score=6.5,
            lexical_score=7.0,
            grammar_score=7.5,
            evidences=evidences,
            self_corrections=self_corrections,
            feedback_text="Fallback analysis: The student shows strong grammatical range but has some natural hesitation."
        )


# ──────────────────────────────────────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health", summary="Service Health Check")
def health_check():
    return {"status": "UP", "service": "ENGONOW AI Services", "version": "2.0.0"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
