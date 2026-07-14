"""
ENGONOW Smart LMS — External AI Microservices Mock Server
==========================================================
Simulates two external AI services used by the Java Spring Boot backend:
  1. /api/v1/ai/omr-scan        → Mimics OpenCV bubble-sheet extraction
  2. /api/v1/ai/speaking-analyze → Evaluates student response using Groq Whisper + Gemini 1.5 Flash

Run: uvicorn mock_ai_services:app --host 0.0.0.0 --port 8001 --reload
  or: python mock_ai_services.py
"""

import os
from dotenv import load_dotenv
load_dotenv()

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
import google.generativeai as genai


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

async def transcribe_audio_whisper(filename: str, contents: bytes, content_type: str, api_key: str) -> str:
    """
    Transcribes audio using Groq Whisper-large-v3 with verbose_json, temperature=0,
    and inserts pause markers and low confidence indicators based on timestamps and log probabilities.
    """
    logger.info("[WHISPER STT] Starting Groq Whisper transcription call for %s...", filename)
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    files = {
        "file": (filename, contents, content_type)
    }
    data = {
        "model": "whisper-large-v3",
        "response_format": "verbose_json",
        "temperature": "0.0",
        "timestamp_granularities[]": "word",
        "prompt": "Verbatim transcript. Keep every stutter, broken sentence, filler word, and grammar mistake exactly as spoken. If the speaker says 'Yesterday I go' or 'She don't like', transcribe it exactly without fixing tenses or missing plurals."
    }

    try:
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
    except Exception as e:
        logger.error("[WHISPER STT] API connection or response failure: %s", str(e))
        raise

    try:
        words = []
        raw_words = stt_json.get("words")
        segments = stt_json.get("segments", [])

        # Parse word list with fallback logprob from segments
        if segments:
            for segment in segments:
                avg_logprob = segment.get("avg_logprob")
                seg_words = segment.get("words", [])
                for sw in seg_words:
                    words.append({
                        "word": sw.get("word"),
                        "start": float(sw.get("start", 0.0)),
                        "end": float(sw.get("end", 0.0)),
                        "logprob": sw.get("logprob") if sw.get("logprob") is not None else avg_logprob
                    })

        # Fallback to flat top-level words array if segments nested words are not present
        if not words and raw_words:
            for rw in raw_words:
                words.append({
                    "word": rw.get("word"),
                    "start": float(rw.get("start", 0.0)),
                    "end": float(rw.get("end", 0.0)),
                    "logprob": rw.get("logprob")
                })

        # Aggregate transcript and inject tags
        if not words:
            text = stt_json.get("text", "")
            logger.info("[WHISPER STT] No word timestamps found. Returning raw text.")
            return text

        annotated_tokens = []
        pauses_count = 0
        low_conf_count = 0

        for i, w in enumerate(words):
            word_str = w.get("word", "").strip()
            start = w.get("start", 0.0)
            end = w.get("end", 0.0)
            logprob = w.get("logprob")

            # Check gap duration for consecutive words
            if i > 0:
                prev_end = words[i - 1].get("end", 0.0)
                gap = float(start) - float(prev_end)
                if gap > 1.5:
                    annotated_tokens.append(f"[pause: {gap:.1f}s]")
                    pauses_count += 1

            annotated_tokens.append(word_str)

            # Check pronunciation confidence logprob threshold < -0.5
            if logprob is not None:
                try:
                    if float(logprob) < -0.5:
                        annotated_tokens.append("[LOW_CONFIDENCE]")
                        low_conf_count += 1
                except (ValueError, TypeError):
                    pass

        annotated_transcript = " ".join(annotated_tokens)
        logger.info(
            "[WHISPER STT] Completed. Injected %d pause markers and %d [LOW_CONFIDENCE] tags.",
            pauses_count, low_conf_count
        )
        return annotated_transcript

    except Exception as e:
        logger.error("[WHISPER STT] Error parsing timestamps or logging metadata: %s", str(e))
        return stt_json.get("text", "")


async def evaluate_speaking_gemini(annotated_transcript: str, questions_metadata: str, api_key: str) -> dict:
    """
    Evaluates student speaking response against questions using Gemini 1.5 Flash.
    Returns a strictly structured JSON dict report according to IELTS grading criteria.
    """
    logger.info("[GEMINI EVALUATOR] Initiating Gemini evaluation call...")
    try:
        genai.configure(api_key=api_key)
        
        system_prompt = (
            "You are a Senior IELTS Speaking Examiner certified by Cambridge Assessment English. "
            "You possess forensic command of the official Cambridge Band Descriptors (Bands 1-9).\n\n"
            "CRITICAL GUARDRAIL: Do NOT penalize Pronunciation or Fluency for [LOW_CONFIDENCE] tags if they are attached to Proper Nouns, Vietnamese names (e.g., Nguyen, Ho Chi Minh), or non-English terms.\n\n"
            "══════════════════════════════════════════════════════════════════════════════\n"
            " CAMBRIDGE CALIBRATION & RANGE-OVER-ACCURACY (ANTI-COMPRESSION LAW)\n"
            "══════════════════════════════════════════════════════════════════════════════\n"
            "1. DO NOT compress scores to Band 5 or 6 out of hesitation. Use 7, 8, 9 for strong candidates, and 3, 4 for weak ones.\n"
            "2. Band 7+ candidates WILL make mistakes. Attempting complex structures (conditionals, passives) and failing slightly is Band 7 evidence. Producing only simple, error-free sentences is Band 5 evidence. RANGE OUTWEIGHS ACCURACY at high bands.\n"
            "3. Do not drop a score to 6 just because you found 1-2 errors. Rare errors + wide range = Band 8.\n\n"
            "══════════════════════════════════════════════════════════════════════════════\n"
            " THE DATA CONTRACT & INTEGER RULE (CRITICAL):\n"
            "══════════════════════════════════════════════════════════════════════════════\n"
            "The 4 criterion score fields MUST be WHOLE NUMBERS ONLY (1, 2, 3, 4, 5, 6, 7, 8, 9).\n"
            "❌ ALL DECIMALS ARE FORBIDDEN (e.g., 6.5, 7.5, 6.0, 7.0).\n"
            "If torn between bands, use the WEIGHT OF EVIDENCE to commit to ONE absolute integer."
        )

        model = genai.GenerativeModel(
            model_name="models/gemini-2.5-flash",
            generation_config={"response_mime_type": "application/json"},
            system_instruction=system_prompt
        )

        prompt = (
            f"Here are the specific questions asked by the examiner (metadata):\n{questions_metadata}\n\n"
            f"Here is the annotated transcript of the student's response:\n\"{annotated_transcript}\"\n\n"
            "══════════════════════════════════════════════════════════════════════════════\n"
            " EVALUATION PROTOCOL & QUOTE-FIRST RULE\n"
            "══════════════════════════════════════════════════════════════════════════════\n"
            "1. DIAGNOSTIC EVIDENCE: For each criterion, find diagnostic evidence. You MUST include POSITIVE STRENGTHS for high scores, not just errors.\n"
            "2. QUOTE-FIRST: The 'original_quote' field MUST be extracted exactly character-for-character from the transcript. Do not paraphrase.\n"
            "3. BIDIRECTIONAL JUSTIFICATION: In the 'overallComment', you MUST briefly justify the score by proving why it is not higher and not lower (e.g., 'Scored 7 not 8 because of X; not 6 because of Y').\n"
            "4. LATENCY OPTIMIZATION: Limit the 'evidences' array to MAXIMUM 2 items per criterion (mix strengths and weaknesses). Keep explanations brief.\n\n"
            "══════════════════════════════════════════════════════════════════════════════\n"
            " REQUIRED JSON OUTPUT SCHEMA\n"
            "══════════════════════════════════════════════════════════════════════════════\n"
            "Evaluate the response. You MUST output a JSON object matching this schema exactly:\n"
            "{\n"
            "  \"pronunciationScore\": [INSERT_INTEGER_1_TO_9_HERE],\n"
            "  \"fluencyScore\": [INSERT_INTEGER_1_TO_9_HERE],\n"
            "  \"lexicalScore\": [INSERT_INTEGER_1_TO_9_HERE],\n"
            "  \"grammarScore\": [INSERT_INTEGER_1_TO_9_HERE],\n"
            "  \"evidences\": [\n"
            "    {\n"
            "      \"criterion\": \"[CHOOSE ONE: GRAMMAR, LEXICAL, FLUENCY, PRONUNCIATION]\",\n"
            "      \"testPart\": \"[CHOOSE ONE: PART_1, PART_2, PART_3]\",\n"
            "      \"question\": \"[Question text here]\",\n"
            "      \"original_quote\": \"[Exact verbatim quote here]\",\n"
            "      \"error\": \"[Explain the mistake, OR describe the positive language strength]\",\n"
            "      \"correction\": \"[Correction, OR write 'N/A' if it is a positive strength]\",\n"
            "      \"explanation\": \"[Pedagogical reasoning]\"\n"
            "    }\n"
            "  ],\n"
            "  \"overallComment\": \"[Bidirectional Justification: Scored X not X+1 because... Not X-1 because... Summary.]\"\n"
            "}\n"
        )

        response = await model.generate_content_async(prompt)
        text_content = response.text
        
        # Parse the JSON string
        result_dict = json.loads(text_content)
        logger.info("[GEMINI EVALUATOR] Successfully generated speaking evaluation from Gemini.")
        return result_dict

    except Exception as e:
        logger.error("[GEMINI EVALUATOR] Error during Gemini generate content or JSON parsing: %s", str(e))
        # Return a safe fallback dictionary
        return {
            "pronunciationScore": 0,
            "fluencyScore": 0,
            "lexicalScore": 0,
            "grammarScore": 0,
            "evidences": [],
            "overallComment": f"Failed to perform speaking evaluation due to an error: {str(e)}"
        }


async def process_speaking_evaluation_task(
    session_id: str,
    filename: str,
    contents: bytes,
    content_type: str,
    questions_metadata: str,
    groq_api_key: str,
    gemini_api_key: str,
    webhook_url: str
):
    logger.info("[ORCHESTRATOR] Starting speaking evaluation task for session_id=%s, file=%s", session_id, filename)
    
    annotated_transcript = ""
    gemini_result_dict = {}
    status_flag = "SUCCESS"
    overall_comment = ""
    
    # Step 1: Whisper STT Transcription
    try:
        annotated_transcript = await transcribe_audio_whisper(
            filename=filename,
            contents=contents,
            content_type=content_type,
            api_key=groq_api_key
        )
    except Exception as e:
        logger.error("[ORCHESTRATOR] Whisper transcription failed: %s", str(e))
        status_flag = "SYSTEM_ERROR"
        annotated_transcript = ""
        
    # Step 2: Gemini LLM Evaluation (Only if Whisper succeeded)
    if status_flag == "SUCCESS":
        try:
            gemini_result_dict = await evaluate_speaking_gemini(
                annotated_transcript=annotated_transcript,
                questions_metadata=questions_metadata,
                api_key=gemini_api_key
            )
            # If the call returned the fallback dict representing an error, update status_flag
            if gemini_result_dict.get("pronunciationScore") == 0 and "Failed" in gemini_result_dict.get("overallComment", ""):
                status_flag = "LLM_ERROR"
                overall_comment = gemini_result_dict.get("overallComment", "")
            else:
                overall_comment = gemini_result_dict.get("overallComment", "")
        except Exception as e:
            logger.error("[ORCHESTRATOR] Gemini evaluation failed: %s", str(e))
            status_flag = "LLM_ERROR"
            overall_comment = f"Speaking evaluation failed due to LLM error: {str(e)}"
            
    # Step 3: DTO Mapping & Status Handling
    mapped_evidences = []
    if status_flag == "SUCCESS":
        for ev in gemini_result_dict.get("evidences", []):
            mapped_ev = {
                "criterion": ev.get("criterion", "GRAMMAR"),
                "testPart": ev.get("testPart") or ev.get("part", "PART_1"),
                "part": ev.get("testPart") or ev.get("part", "PART_1"),
                "question": ev.get("question", ""),
                "original_quote": ev.get("original_quote") or ev.get("quote", ""),
                "quote": ev.get("original_quote") or ev.get("quote", ""),
                "error": ev.get("error") or ev.get("error_type", ""),
                "error_type": ev.get("error") or ev.get("error_type", ""),
                "correction": ev.get("correction", ""),
                "explanation": ev.get("explanation", "")
            }
            mapped_evidences.append(mapped_ev)
            
        def safe_int(val, default=0):
            try:
                return int(float(val)) if val is not None else default
            except (ValueError, TypeError):
                return default

        pron_score = safe_int(gemini_result_dict.get("pronunciationScore"))
        flu_score = safe_int(gemini_result_dict.get("fluencyScore"))
        lex_score = safe_int(gemini_result_dict.get("lexicalScore"))
        gra_score = safe_int(gemini_result_dict.get("grammarScore"))
    else:
        pron_score = 0
        flu_score = 0
        lex_score = 0
        gra_score = 0
        overall_comment = f"[CRITICAL SYSTEM ERROR] Groq/Gemini connectivity failed. Please re-queue this session. (Status: {status_flag})"

    payload = {
        # User requested fields
        "sessionId": session_id,
        "pronunciationScore": pron_score,
        "fluencyScore": flu_score,
        "lexicalScore": lex_score,
        "grammarScore": gra_score,
        "evidences": mapped_evidences,
        "transcribedText": annotated_transcript,
        "overallComment": overall_comment,
        "status": status_flag,

        # Snake_case and Spring Boot record mappings compatibility
        "session_id": session_id,
        "pronunciation_score": pron_score,
        "fluency_score": flu_score,
        "lexical_score": lex_score,
        "grammar_score": gra_score,
        "feedback_text": overall_comment,
        "feedbackText": overall_comment,
        "self_corrections": [],
        "selfCorrections": []
    }

    # Step 4: Fire Webhook Callback
    logger.info("[ORCHESTRATOR] Sending webhook callback to %s with status=%s...", webhook_url, status_flag)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                json=payload,
                timeout=10.0
            )
        
        if response.status_code >= 200 and response.status_code < 300:
            logger.info("[ORCHESTRATOR] Webhook successfully delivered to Java server. Status code: %d", response.status_code)
        else:
            logger.error("[ORCHESTRATOR] Webhook rejected by Java server. Status code: %d, Response: %s", response.status_code, response.text)
            
    except Exception as e:
        logger.error("[ORCHESTRATOR] Webhook request delivery failed: %s", str(e))


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

    groq_key = os.getenv("WHISPER_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if not groq_key or not gemini_key:
        raise HTTPException(status_code=500, detail="Missing API keys in .env")

    contents = await file.read()
    logger.info(
        f"[SPEAKING SERVICE] Analyzing student audio for session_id='{session_id}' | "
        f"file='{file.filename}' ({len(contents)} bytes) | metadata length={len(metadata_list)}"
    )

    try:
        # ─── PHASE 1: STT (Groq Whisper-large-v3) ───
        annotated_transcript = await transcribe_audio_whisper(
            filename=file.filename,
            contents=contents,
            content_type=file.content_type or "audio/mpeg",
            api_key=groq_key
        )

        logger.info(f"[SPEAKING SERVICE] Transcript generated: {annotated_transcript[:200]}...")

        # ─── PHASE 2: LLM Evaluation (Gemini 1.5 Flash) ───
        logger.info("[SPEAKING SERVICE] Initializing Gemini 1.5 Flash evaluation call...")
        gemini_result_dict = await evaluate_speaking_gemini(
            annotated_transcript=annotated_transcript,
            questions_metadata=questions_metadata,
            api_key=gemini_key
        )

        evidences = [
            SpeakingEvidence(
                criterion=e.get("criterion", "GRAMMAR"),
                part=e.get("testPart") or e.get("part", "PART_1"),
                question=e.get("question", ""),
                quote=e.get("original_quote") or e.get("quote", ""),
                error_type=e.get("error") or e.get("error_type", ""),
                correction=e.get("correction", ""),
                explanation=e.get("explanation", "")
            )
            for e in gemini_result_dict.get("evidences", [])
        ]

        result = SpeakingAnalysisResult(
            session_id=session_id,
            pronunciation_score=float(gemini_result_dict.get("pronunciationScore", 0.0)),
            fluency_score=float(gemini_result_dict.get("fluencyScore", 0.0)),
            lexical_score=float(gemini_result_dict.get("lexicalScore", 0.0)),
            grammar_score=float(gemini_result_dict.get("grammarScore", 0.0)),
            evidences=evidences,
            self_corrections=[],
            feedback_text=gemini_result_dict.get("overallComment", "")
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
