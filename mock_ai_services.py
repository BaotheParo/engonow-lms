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
import re
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
        # SOLUTION A: FILLER BRACKETING
        filler_pattern = re.compile(r'\b(um|uh|er|ah|like|you know|i mean)\b', re.IGNORECASE)
        annotated_transcript = filler_pattern.sub(r'[FILLER: \1]', annotated_transcript)
        logger.info(
            "[WHISPER STT] Completed. Injected %d pause markers and %d [LOW_CONFIDENCE] tags.",
            pauses_count, low_conf_count
        )
        return annotated_transcript

    except Exception as e:
        logger.error("[WHISPER STT] Error parsing timestamps or logging metadata: %s", str(e))
        return stt_json.get("text", "")


async def call_gemini_with_retry(func, *args, **kwargs):
    max_retries = 3
    base_delay = 5.0
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            err_msg = str(e)
            is_rate_limit = "429" in err_msg or "ResourceExhausted" in err_msg or "quota" in err_msg.lower()
            if is_rate_limit and attempt < max_retries:
                delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                logger.warning(
                    "[GEMINI RETRY] Hit rate limit (429). Retrying attempt %d/%d in %.2fs...",
                    attempt + 1, max_retries, delay
                )
                await asyncio.sleep(delay)
            else:
                raise

async def evaluate_gra_lr_text(annotated_transcript: str, questions_metadata: str, api_key: str) -> dict:
    """
    Evaluates student response for Grammatical Range & Accuracy (GRA) and Lexical Resource (LR) only using Gemini.
    """
    logger.info("[GEMINI EVALUATOR - TEXT TRACK] Initiating Gemini evaluation call...")
    try:
        genai.configure(api_key=api_key)
        
        system_prompt = (
            "You are a Senior IELTS Speaking Examiner certified by Cambridge Assessment English.\n"
            "YOUR STRICT SCOPE: You are evaluating GRAMMATICAL RANGE & ACCURACY (GRA) and LEXICAL RESOURCE (LR) ONLY.\n"
            "DO NOT evaluate Fluency or Pronunciation. Those are handled by a separate acoustic engine.\n\n"
            "══════════════════════════════════════════════════════════════════════════\n"
            " ASR MODALITY COMPENSATION RULES (NON-NEGOTIABLE)\n"
            "══════════════════════════════════════════════════════════════════════════\n"
            "You are reading a SPEECH-TO-TEXT (ASR) transcript. The raw ASR output lacks punctuation and acoustic prosody.\n"
            "RULE 1 — PUNCTUATION AMNESTY: The ASR engine strips commas and periods. DO NOT penalise GRA for run-on sentences. Assume correct phrasing unless structurally broken.\n"
            "RULE 2 — [FILLER: X] markers are spoken disfluencies. DO NOT penalise GRA or LR for the presence of natural fillers.\n"
            "RULE 3 — ATTEMPT OVER ACCURACY: Band 7+ candidates WILL make minor mistakes inside complex clauses. Reward RANGE and structural complexity over pure accuracy.\n\n"
            "══════════════════════════════════════════════════════════════════════════\n"
            " THE INTEGER CONTRACT (CRITICAL):\n"
            "══════════════════════════════════════════════════════════════════════════\n"
            "1. NO DECIMALS. Scores MUST be WHOLE NUMBERS (1-9).\n"
            "2. DO NOT compress scores to 5 or 6 out of hesitation. Use 7, 8, 9 confidently for strong vocabulary or complex grammar."
        )

        model = genai.GenerativeModel(
            model_name="models/gemini-3-flash-preview",
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.0
            },
            system_instruction=system_prompt
        )

        prompt = (
            f"Here are the specific questions asked by the examiner (metadata):\n{questions_metadata}\n\n"
            f"Here is the annotated transcript of the student's response:\n\"{annotated_transcript}\"\n\n"
            "══════════════════════════════════════════════════════════════════════════════\n"
            " EVALUATION PROTOCOL & QUOTE-FIRST RULE\n"
            "══════════════════════════════════════════════════════════════════════════════\n"
            "1. DIAGNOSTIC EVIDENCE: Find diagnostic evidence for Grammar and Lexical features. Include POSITIVE STRENGTHS for high scores, not just errors.\n"
            "2. QUOTE-FIRST: The 'original_quote' field MUST be extracted exactly character-for-character from the transcript.\n"
            "3. MAXIMUM EVIDENCES: Limit the 'evidences' array to MAXIMUM 3 items total to optimize latency.\n\n"
            "══════════════════════════════════════════════════════════════════════════════\n"
            " REQUIRED JSON OUTPUT SCHEMA\n"
            "══════════════════════════════════════════════════════════════════════════════\n"
            "Evaluate the response. You MUST output a JSON object matching this schema exactly:\n"
            "{\n"
            "  \"grammarScore\": [INSERT_INTEGER_1_TO_9_HERE],\n"
            "  \"lexicalScore\": [INSERT_INTEGER_1_TO_9_HERE],\n"
            "  \"evidences\": [\n"
            "    {\n"
            "      \"criterion\": \"[CHOOSE ONE: GRAMMAR, LEXICAL]\",\n"
            "      \"testPart\": \"[CHOOSE ONE: PART_1, PART_2, PART_3]\",\n"
            "      \"question\": \"[Question text here]\",\n"
            "      \"original_quote\": \"[Exact verbatim quote here]\",\n"
            "      \"error\": \"[Explain the mistake, OR describe the positive language strength]\",\n"
            "      \"correction\": \"[Correction, OR write 'N/A' if it is a positive strength]\",\n"
            "      \"explanation\": \"[Pedagogical reasoning]\"\n"
            "    }\n"
            "  ],\n"
            "  \"overallComment\": \"[Brief summary justifying the GRA and LR scores]\"\n"
            "}\n"
        )

        async def do_call():
            return await model.generate_content_async(prompt)
            
        response = await call_gemini_with_retry(do_call)
        text_content = response.text
        
        # Parse the JSON string
        try:
            result_dict = json.loads(text_content)
        except Exception as json_err:
            logger.warning("[GEMINI EVALUATOR - TEXT TRACK] Standard json.loads failed, trying regex fallback parser: %s", str(json_err))
            import re
            scores = {}
            for field in ["grammarScore", "lexicalScore"]:
                match = re.search(rf'"{field}"\s*:\s*(\d+)', text_content)
                if match:
                    scores[field] = int(match.group(1))
                else:
                    scores[field] = 0
            
            if all(scores[field] >= 1 for field in scores):
                result_dict = {
                    "grammarScore": scores["grammarScore"],
                    "lexicalScore": scores["lexicalScore"],
                    "evidences": [],
                    "overallComment": f"Partial parse successful (JSON repair). Original parsing error: {str(json_err)}"
                }
            else:
                raise json_err

        logger.info("[GEMINI EVALUATOR - TEXT TRACK] Successfully generated speaking evaluation from Gemini.")
        return result_dict

    except Exception as e:
        logger.error("[GEMINI EVALUATOR - TEXT TRACK] Error during Gemini generate content or JSON parsing: %s", str(e))
        return {
            "grammarScore": 0,
            "lexicalScore": 0,
            "evidences": [],
            "overallComment": f"Failed to perform speaking evaluation due to an error: {str(e)}"
        }


async def evaluate_pr_fc_audio(audio_contents: bytes, audio_content_type: str, api_key: str) -> dict:
    """
    Evaluates Pronunciation (PR) and Fluency & Coherence (FC) directly from the raw audio file.
    """
    logger.info("[GEMINI EVALUATOR - AUDIO TRACK] Initiating Gemini evaluation call...")
    try:
        genai.configure(api_key=api_key)
        
        system_prompt = (
            "You are a Senior IELTS Speaking Examiner certified by Cambridge Assessment English.\n"
            "YOUR STRICT SCOPE: You are evaluating PRONUNCIATION (PR) and FLUENCY & COHERENCE (FC) ONLY by actively listening to the provided audio.\n"
            "DO NOT evaluate Grammar or Lexical Resource. Those are handled by a separate text engine.\n\n"
            "══════════════════════════════════════════════════════════════════════════\n"
            " ACOUSTIC EVALUATION RULES (NON-NEGOTIABLE)\n"
            "══════════════════════════════════════════════════════════════════════════\n"
            "RULE 1 — PRONUNCIATION: Listen for phoneme clarity, word stress, sentence stress, and intonation. Accent is fine as long as it does not impede intelligibility.\n"
            "RULE 2 — FLUENCY: Listen for speech rate, natural rhythm, and hesitations. Natural cognitive pauses are acceptable. Only penalize long, disruptive, language-related pauses.\n"
            "RULE 3 — NO TRANSCRIPT NEEDED: Base your judgment entirely on the acoustic qualities of the voice.\n\n"
            "══════════════════════════════════════════════════════════════════════════\n"
            " THE INTEGER CONTRACT (CRITICAL):\n"
            "══════════════════════════════════════════════════════════════════════════\n"
            "1. NO DECIMALS. Scores MUST be WHOLE NUMBERS (1-9).\n"
            "2. DO NOT compress scores to 5 or 6 out of hesitation. Use 7, 8, 9 confidently for smooth, intelligible speech."
        )

        model = genai.GenerativeModel(
            model_name="models/gemini-3-flash-preview",
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.0
            },
            system_instruction=system_prompt
        )

        prompt_text = (
            "Listen to the attached audio file of the student's IELTS Speaking response.\n\n"
            "══════════════════════════════════════════════════════════════════════════════\n"
            " REQUIRED JSON OUTPUT SCHEMA\n"
            "══════════════════════════════════════════════════════════════════════════════\n"
            "Evaluate the acoustic response. You MUST output a JSON object matching this schema exactly:\n"
            "{\n"
            "  \"pronunciationScore\": [INSERT_INTEGER_1_TO_9_HERE],\n"
            "  \"fluencyScore\": [INSERT_INTEGER_1_TO_9_HERE],\n"
            "  \"evidences\": [\n"
            "    {\n"
            "      \"criterion\": \"[CHOOSE ONE: PRONUNCIATION, FLUENCY]\",\n"
            "      \"testPart\": \"[CHOOSE ONE: PART_1, PART_2, PART_3]\",\n"
            "      \"question\": \"General Audio Assessment\",\n"
            "      \"original_quote\": \"[Describe the approximate timestamp or the spoken phrase where the issue/strength occurred]\",\n"
            "      \"error\": \"[Explain the acoustic mistake, OR describe the positive acoustic strength]\",\n"
            "      \"correction\": \"[Correction, OR write 'N/A']\",\n"
            "      \"explanation\": \"[Acoustic/Phonetic reasoning]\"\n"
            "    }\n"
            "  ],\n"
            "  \"overallComment\": \"[Brief summary justifying the PR and FC scores based on rhythm, stress, and clarity]\"\n"
            "}\n"
        )

        # Format the audio for Gemini multimodal input
        audio_part = {
            "mime_type": audio_content_type if audio_content_type else "audio/mpeg",
            "data": audio_contents
        }

        # Pass BOTH the audio blob and the text prompt in a list
        async def do_call():
            return await model.generate_content_async([audio_part, prompt_text])
            
        response = await call_gemini_with_retry(do_call)
        text_content = response.text
        
        # Parse the JSON string
        try:
            result_dict = json.loads(text_content)
        except Exception as json_err:
            logger.warning("[GEMINI EVALUATOR - AUDIO TRACK] Standard json.loads failed, trying regex fallback parser: %s", str(json_err))
            import re
            scores = {}
            for field in ["pronunciationScore", "fluencyScore"]:
                match = re.search(rf'"{field}"\s*:\s*(\d+)', text_content)
                if match:
                    scores[field] = int(match.group(1))
                else:
                    scores[field] = 0
            
            if all(scores[field] >= 1 for field in scores):
                result_dict = {
                    "pronunciationScore": scores["pronunciationScore"],
                    "fluencyScore": scores["fluencyScore"],
                    "evidences": [],
                    "overallComment": f"Partial parse successful (JSON repair). Original parsing error: {str(json_err)}"
                }
            else:
                raise json_err

        logger.info("[GEMINI EVALUATOR - AUDIO TRACK] Successfully generated speaking evaluation from Gemini.")
        return result_dict

    except Exception as e:
        logger.error("[GEMINI EVALUATOR - AUDIO TRACK] Error during Gemini generate content or JSON parsing: %s", str(e))
        return {
            "pronunciationScore": 0,
            "fluencyScore": 0,
            "evidences": [],
            "overallComment": f"Failed to perform speaking evaluation due to an error: {str(e)}"
        }


async def evaluate_speaking_gemini(annotated_transcript: str, questions_metadata: str, api_key: str) -> dict:
    """
    Wrapper for backward compatibility. Calls evaluate_gra_lr_text and injects default
    scores for pronunciation and fluency to maintain legacy contract.
    """
    logger.info("[GEMINI EVALUATOR] Calling evaluate_gra_lr_text via compatibility wrapper...")
    result_dict = await evaluate_gra_lr_text(annotated_transcript, questions_metadata, api_key)
    
    # Inject default values for pronunciation and fluency if not present (or if 0 due to error)
    if "pronunciationScore" not in result_dict:
        result_dict["pronunciationScore"] = 5 if result_dict.get("grammarScore", 0) > 0 else 0
    if "fluencyScore" not in result_dict:
        result_dict["fluencyScore"] = 5 if result_dict.get("grammarScore", 0) > 0 else 0
        
    return result_dict


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
    status_flag = "SUCCESS"
    
    # Track 1 text execution helper
    async def run_text_track():
        try:
            transcript = await transcribe_audio_whisper(filename, contents, content_type, groq_api_key)
            if not transcript or "failed" in transcript.lower():
                return {"grammarScore": 0, "lexicalScore": 0, "evidences": [], "overallComment": "STT failed."}, ""
            eval_res = await evaluate_gra_lr_text(transcript, questions_metadata, gemini_api_key)
            return eval_res, transcript
        except Exception as e:
            logger.error(f"[TRACK 1] Error during text processing: {e}")
            return {"grammarScore": 0, "lexicalScore": 0, "evidences": [], "overallComment": f"Track 1 failed: {str(e)}"}, ""

    logger.info("[ORCHESTRATOR] Launching Track 1 (Text) and Track 2 (Audio) concurrently...")
    
    try:
        (text_result, annotated_transcript), audio_result = await asyncio.gather(
            run_text_track(),
            evaluate_pr_fc_audio(contents, content_type, gemini_api_key)
        )
    except Exception as gather_err:
        logger.error("[ORCHESTRATOR] Concurrent execution failed: %s", str(gather_err))
        status_flag = "SYSTEM_ERROR"
        text_result = {"grammarScore": 0, "lexicalScore": 0, "evidences": [], "overallComment": f"Gather failed: {str(gather_err)}"}
        audio_result = {"pronunciationScore": 0, "fluencyScore": 0, "evidences": [], "overallComment": f"Gather failed: {str(gather_err)}"}
        annotated_transcript = ""

    # Merge evidences from both tracks
    raw_evidences = []
    if isinstance(text_result, dict) and "evidences" in text_result:
        raw_evidences.extend(text_result.get("evidences", []))
    if isinstance(audio_result, dict) and "evidences" in audio_result:
        raw_evidences.extend(audio_result.get("evidences", []))
        
    mapped_evidences = []
    for ev in raw_evidences:
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

    # Extract criteria scores
    gra_score = safe_int(text_result.get("grammarScore"))
    lex_score = safe_int(text_result.get("lexicalScore"))
    pron_score = safe_int(audio_result.get("pronunciationScore"))
    flu_score = safe_int(audio_result.get("fluencyScore"))
    
    # Update status flag based on grading integrity
    if status_flag == "SUCCESS":
        if gra_score == 0 or lex_score == 0 or pron_score == 0 or flu_score == 0:
            status_flag = "LLM_ERROR"

    # Consolidate overall comment feedback
    text_comment = text_result.get("overallComment", "") if isinstance(text_result, dict) else ""
    audio_comment = audio_result.get("overallComment", "") if isinstance(audio_result, dict) else ""
    
    if status_flag == "SUCCESS":
        overall_comment = (
            f"Grammar & Lexical Feedback: {text_comment}\n\n"
            f"Pronunciation & Fluency Feedback: {audio_comment}"
        )
    else:
        overall_comment = (
            f"[CRITICAL SYSTEM ERROR] Groq/Gemini evaluation incomplete. (Status: {status_flag})\n"
            f"Text Track Comment: {text_comment}\n"
            f"Audio Track Comment: {audio_comment}"
        )

    payload = {
        "sessionId": session_id,
        "pronunciationScore": pron_score,
        "fluencyScore": flu_score,
        "lexicalScore": lex_score,
        "grammarScore": gra_score,
        "evidences": mapped_evidences,
        "transcribedText": annotated_transcript,
        "overallComment": overall_comment,
        "status": status_flag,

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
        # Helper task for text evaluation
        async def run_text_track():
            transcript = await transcribe_audio_whisper(
                filename=file.filename,
                contents=contents,
                content_type=file.content_type or "audio/mpeg",
                api_key=groq_key
            )
            eval_res = await evaluate_gra_lr_text(
                annotated_transcript=transcript,
                questions_metadata=questions_metadata,
                api_key=gemini_key
            )
            return eval_res, transcript

        logger.info("[SPEAKING SERVICE] Launching Track 1 (Text) and Track 2 (Audio) concurrently...")
        (text_result, annotated_transcript), audio_result = await asyncio.gather(
            run_text_track(),
            evaluate_pr_fc_audio(
                audio_contents=contents,
                audio_content_type=file.content_type or "audio/mpeg",
                api_key=gemini_key
            )
        )

        # Merge evidences
        raw_evidences = []
        if isinstance(text_result, dict) and "evidences" in text_result:
            raw_evidences.extend(text_result.get("evidences", []))
        if isinstance(audio_result, dict) and "evidences" in audio_result:
            raw_evidences.extend(audio_result.get("evidences", []))

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
            for e in raw_evidences
        ]

        def safe_int(val, default=0):
            try:
                return int(float(val)) if val is not None else default
            except (ValueError, TypeError):
                return default

        pron_score = safe_int(audio_result.get("pronunciationScore"))
        flu_score = safe_int(audio_result.get("fluencyScore"))
        lex_score = safe_int(text_result.get("lexicalScore"))
        gra_score = safe_int(text_result.get("grammarScore"))

        if pron_score == 0 or flu_score == 0 or lex_score == 0 or gra_score == 0:
            raise Exception(
                f"Evaluation scores incomplete (PR={pron_score}, FC={flu_score}, LR={lex_score}, GRA={gra_score})."
            )

        text_comment = text_result.get("overallComment", "")
        audio_comment = audio_result.get("overallComment", "")
        combined_comment = (
            f"Grammar & Lexical Feedback: {text_comment}\n\n"
            f"Pronunciation & Fluency Feedback: {audio_comment}"
        )

        result = SpeakingAnalysisResult(
            session_id=session_id,
            pronunciation_score=float(pron_score),
            fluency_score=float(flu_score),
            lexical_score=float(lex_score),
            grammar_score=float(gra_score),
            evidences=evidences,
            self_corrections=[],
            feedback_text=combined_comment
        )

        logger.info(f"[SPEAKING SERVICE] Evaluation generated successfully for session_id='{session_id}'")
        return result

    except Exception as e:
        logger.error(f"[SPEAKING SERVICE] API call failure: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI Pipeline Failed: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health", summary="Service Health Check")
def health_check():
    return {"status": "UP", "service": "ENGONOW AI Services", "version": "2.0.0"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
