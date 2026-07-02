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

    logger.info(f"[SPEAKING SERVICE] Analyzing real audio binary mapping for session_id='{session_id}'")
    await asyncio.sleep(1.0)  # Giả lập độ trễ xử lý tín hiệu âm thanh

    # ─── BỘ BẰNG CHỨNG THỰC TẾ TRÍCH XUẤT TỪ TIW_MOCK_TEST.MP3 ───
    evidences = [
        # 1. TIÊU CHÍ: FLUENCY (Part 2 - Lỗi lặp từ gây mất trôi chảy tự nhiên)
        SpeakingEvidence(
            criterion="FLUENCY",
            part="PART_2",
            question="Describe a person you know who likes to cook for other people.",
            quote="...she is really enjoy baking she she She doesn't take any class...",
            error_type="Unnatural Hesitation",
            correction="...she really enjoys baking. She doesn't take any classes...",
            explanation=(
                "Thí sinh bị lặp từ (she she She) trong 1.8 giây tại Part 2 "
                "khi đang cố gắng tìm cấu trúc câu phủ định tiếp theo. Đây là lỗi "
                "Unnatural Hesitation làm giảm độ mượt mà của chuỗi nói dài."
            )
        ),

        # 2. TIÊU CHÍ: FLUENCY (Part 3 - Ngắt nghỉ tư duy hợp lệ -> Java Gatekeeper sẽ cứu điểm)
        SpeakingEvidence(
            criterion="FLUENCY",
            part="PART_3",
            question="Should children be taught cooking skills from a young age?",
            quote="...Because sometimes... [2.1s pause] they could first start with some recipe...",
            error_type="Natural Cognitive Pause",
            correction="...Because sometimes, they could start with a base recipe...",
            explanation=(
                "Khoảng lặng dài 2.1 giây xuất hiện ở Part 3 sau trạng từ 'sometimes'. "
                "Đây là khoảng lặng tư duy hợp lệ (Cognitive Pause) để thí sinh "
                "sắp xếp lập luận trừu tượng, không bị tính là lỗi sụp đổ ngôn ngữ."
            )
        ),

        # 3. TIÊU CHÍ: GRAMMAR (Part 1 - Lỗi dùng sai giới từ ngữ cảnh)
        SpeakingEvidence(
            criterion="GRAMMAR",
            part="PART_1",
            question="Are you still friends with the people that you've known since childhood?",
            quote="...I moved to the central of Vietnam. So we have been separated apart...",
            error_type="Preposition Usage",
            correction="...I moved to central Vietnam. So we have been separated for a long time...",
            explanation=(
                "Thí sinh sử dụng cụm từ 'to the central of Vietnam'. "
                "Cấu trúc chính xác phải là 'to central Vietnam' hoặc 'to the central region of Vietnam'."
            )
        ),

        # 4. TIÊU CHÍ: GRAMMAR (Part 2 - Lỗi chia động từ và danh từ đếm được)
        SpeakingEvidence(
            criterion="GRAMMAR",
            part="PART_2",
            question="Describe a person you know who likes to cook for other people.",
            quote="...she is really enjoy baking... give the cakes as a gift for other people, include me...",
            error_type="Verb Form & Participle",
            correction="...she really enjoys baking... giving the cakes as gifts to other people, including me...",
            explanation=(
                "Dính lỗi cấu trúc 'she is really enjoy' (thừa động từ to be) "
                "và dùng sai phân từ 'include me' thay vì 'including me'."
            )
        ),

        # 5. TIÊU CHÍ: LEXICAL RESOURCE (Part 3 - Lỗi dùng sai quán ngữ/Collocation tự nhiên)
        SpeakingEvidence(
            criterion="LEXICAL",
            part="PART_3",
            question="In your opinion, how important is it to learn how to cook?",
            quote="...when we live in another country and the food does not suit to our taste...",
            error_type="Collocation Error",
            correction="...and the food does not suit our taste / is not to our taste...",
            explanation=(
                "Ngoại động từ 'suit' tác động trực tiếp lên tân ngữ, "
                "việc chèn giới từ 'to' tạo thành cụm 'suit to our taste' là sai collocation chuẩn."
            )
        ),

        # 6. TIÊU CHÍ: PRONUNCIATION (Part 2 - Lỗi nuốt âm đuôi s/es ở danh từ)
        SpeakingEvidence(
            criterion="PRONUNCIATION",
            part="PART_2",
            question="Describe a person you know who likes to cook for other people.",
            quote="...she enjoys looking for some recipes on the internet...",
            error_type="Final Consonant Deletion",
            correction="...she enjoys looking for some /ˈresəpiz/ on the internet...",
            explanation=(
                "Thí sinh phát âm từ 'recipes' bị nuốt mất âm đuôi /z/ "
                "của dạng số nhiều, chuyển thành danh từ số ít, làm giảm độ chính xác ngữ âm."
            )
        )
    ]

    # ─── BỘ CÁC PHA TỰ SỬA LỖI (SELF-CORRECTION) GHI NHẬN THẬT TỪ FILE ───
    self_corrections = [
        SelfCorrection(
            original="she",
            marker="repetition and shift",
            corrected="She doesn't",
            type="GRAMMAR"
        ),
        SelfCorrection(
            original="recipe",
            marker="discourse restructuring",
            corrected="the base recipe",
            type="LEXICAL"
        )
    ]

    # Đồng bộ dữ liệu tính toán và đóng gói Response DTO
    initial_fluency = 6.5 # AI chấm thô dải thấp do bắt lỗi ngập ngừng câu hỏi Part 2
    
    result = SpeakingAnalysisResult(
        session_id=session_id,
        pronunciation_score=7.8, # Giữ nguyên phản xạ âm chuẩn Studio rất tốt của file gốc
        fluency_score=round(initial_fluency, 1),
        lexical_score=7.0,
        grammar_score=7.5,
        evidences=evidences,
        self_corrections=self_corrections,
        feedback_text=(
            "The candidate demonstrates a strong operational command of English with "
            "noticeable academic phrasing ('pivotal skills', 'fully develop'). Part 2 showed "
            "minor vocabulary and grammatical constraints, which were swiftly self-corrected. "
            "Part 3 displayed natural cognitive pausing for logical coherence."
        )
    )

    logger.info(f"[SPEAKING SERVICE] Generation completed for session_id='{session_id}'")
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/health", summary="Service Health Check")
def health_check():
    return {"status": "UP", "service": "ENGONOW AI Mock Services", "version": "1.0.0"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
