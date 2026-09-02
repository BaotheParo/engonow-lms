"""
run_speaking_assessment.py
===========================
End-to-End Automated IELTS Speaking Assessment Runner for ENGONOW LMS.
Processes candidate audio files (ques1.mp3 and ques2.mp3) with:
1. Groq Whisper Cloud API (whisper-large-v3) with word-level timestamps
2. Multi-modal DSP Acoustic Diagnostics Engine (AcousticOrchestrator)
3. Production Gemini Speaking Provider (GeminiSpeakingProvider) via ProviderFactory
4. Cambridge-rounded Criteria Scoring & Pedagogical Feedback Report
"""

import asyncio
import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Ensure UTF-8 output encoding on Windows console for emojis and Vietnamese text
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

import requests
from acoustic.models import WordTimestamp
from acoustic.acoustic_orchestrator import AcousticOrchestrator
from providers.factory import get_speaking_provider


def transcribe_audio_with_groq_whisper(audio_path: Path, groq_key: str):
    """
    Transcribes audio using Groq Cloud Whisper API (whisper-large-v3)
    and extracts verbatim word timestamps and exact audio duration.
    """
    print(f"🎙️ [ASR] Transcribing {audio_path.name} via Groq Whisper API (whisper-large-v3)...")
    with open(audio_path, "rb") as f:
        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {groq_key}"},
            files={"file": (audio_path.name, f, "audio/mpeg")},
            data={
                "model": "whisper-large-v3",
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word",
            },
            timeout=45,
        )

    if resp.status_code != 200:
        raise RuntimeError(f"Groq Whisper transcription failed (HTTP {resp.status_code}): {resp.text}")

    data = resp.json()
    duration = float(data.get("duration", 0.0))
    full_text = data.get("text", "").strip()

    timestamps = []
    for w in data.get("words", []):
        cleaned_word = w.get("word", "").strip()
        if cleaned_word:
            timestamps.append(
                WordTimestamp(
                    word=cleaned_word,
                    start=round(float(w.get("start", 0.0)), 2),
                    end=round(float(w.get("end", 0.0)), 2),
                    probability=0.98,
                )
            )

    print(f"✅ [ASR] Transcription complete: {len(timestamps)} words detected (Duration: {duration:.2f}s)")
    return timestamps, full_text, duration


async def assess_speaking_file(
    audio_path: Path,
    exam_part: str,
    question_title: str,
    orchestrator: AcousticOrchestrator,
    provider: Any,
    groq_key: str,
):
    if not audio_path.exists():
        print(f"❌ Error: File {audio_path} not found!")
        return

    print("\n" + "=" * 80)
    print(f"🎯 PROCESSING IELTS SPEAKING: {exam_part.upper()} ({audio_path.name})")
    print(f"📌 PROMPT / QUESTION: {question_title}")
    print("=" * 80)

    # Step 1: Read Audio Bytes & Transcribe via Groq Whisper
    audio_bytes = audio_path.read_bytes()
    timestamps, transcript, audio_duration = transcribe_audio_with_groq_whisper(audio_path, groq_key)

    # Step 2: Multi-modal Acoustic DSP Feature Extraction
    print(f"\n🔬 [DSP] Computing acoustic diagnostics via AcousticOrchestrator...")
    acoustic_result = orchestrator.process_speaking_audio(
        audio_data=audio_bytes,
        sample_rate=16000,
        word_timestamps=timestamps,
        total_duration=audio_duration,
    )

    # Step 3: Production LLM Evaluation via GeminiSpeakingProvider
    print(f"🧠 [EVALUATOR] Running production GeminiSpeakingProvider assessment...")
    eval_result = await provider.evaluate_speaking(
        question=question_title,
        transcript=transcript,
        acoustic_result=acoustic_result,
        exam_part=exam_part,
    )

    # Step 4: Structured Console Reporting
    print("\n" + "─" * 80)
    print(f"📝 1. CANDIDATE VERBATIM TRANSCRIPT:")
    print(f"\"{transcript}\"")

    print("\n" + "─" * 80)
    print("📊 2. OBJECTIVE ACOUSTIC DSP MEASUREMENTS TABLE:")
    print(f"  ┌──────────────────────────────┬──────────────────────────────────────────┐")
    print(f"  │ Metric                       │ Measured Value                           │")
    print(f"  ├──────────────────────────────┼──────────────────────────────────────────┤")
    print(f"  │ Measured Total Duration      │ {acoustic_result.total_duration_seconds:6.2f} seconds                    │")
    print(f"  │ Speaking Rate (Overall)      │ {acoustic_result.speaking_rate_wpm:6.1f} WPM                            │")
    print(f"  │ Articulation Rate (Active)   │ {acoustic_result.articulation_rate_wpm:6.1f} WPM                            │")
    print(f"  │ Phonation Ratio              │ {acoustic_result.phonation_ratio * 100:6.1f} %                              │")
    print(f"  │ Long Cognitive Pauses (>0.75s)│ {acoustic_result.pause_analysis.get('silent_cognitive_pause_count', 0):6d} occurrences                    │")
    print(f"  │ Total Silent Pause Time      │ {acoustic_result.pause_analysis.get('total_silent_pause_duration_seconds', 0.0):6.2f} seconds                    │")
    print(f"  │ Filler Words Detected        │ {acoustic_result.pause_analysis.get('filled_pause_count', 0):6d} occurrences                    │")
    print(f"  │ Word Stress Accuracy Ratio   │ {acoustic_result.word_stress_analysis.stress_accuracy_ratio * 100:6.1f} %                              │")
    print(f"  │ Dominant Pitch Contour       │ {acoustic_result.intonation_analysis.dominant_contour_pattern:12s} (Monotone: {str(acoustic_result.intonation_analysis.monotone_flag):5s})  │")
    print(f"  │ Phoneme GOP Errors Detected  │ {len(acoustic_result.phoneme_errors):6d} errors                         │")
    print(f"  └──────────────────────────────┴──────────────────────────────────────────┘")

    print("\n" + "─" * 80)
    print("🏆 3. OFFICIAL IELTS SPEAKING 4-CRITERIA SCORE SHEET:")
    print(f"  ┌────────────────────────────────────────────────────────┬────────┐")
    print(f"  │ Official IELTS Speaking Assessment Criterion           │ Score  │")
    print(f"  ├────────────────────────────────────────────────────────┼────────┤")
    print(f"  │ 🔹 Fluency and Coherence (FC)                           │  {eval_result.fluency_coherence_score or 0.0:3.1f}   │")
    print(f"  │ 🔹 Lexical Resource (LR)                               │  {eval_result.lexical_resource_score or 0.0:3.1f}   │")
    print(f"  │ 🔹 Grammatical Range and Accuracy (GRA)                │  {eval_result.grammatical_range_score or 0.0:3.1f}   │")
    print(f"  │ 🔹 Pronunciation (PR)                                  │  {eval_result.pronunciation_score or 0.0:3.1f}   │")
    print(f"  ├────────────────────────────────────────────────────────┼────────┤")
    print(f"  │ 🎯 OVERALL BAND SCORE (Cambridge Rounded)              │  {eval_result.overall_band or 0.0:3.1f}   │")
    print(f"  └────────────────────────────────────────────────────────┴────────┘")

    # Step 5: Pedagogical Narrative & Detected Corrections
    feedback = eval_result.feedback_detail
    print("\n" + "─" * 80)
    print("📋 4. EXAMINER DIAGNOSTIC SUMMARY & CRITERIA FEEDBACK:")
    summary = getattr(feedback, "examiner_summary", getattr(feedback, "examinerSummary", ""))
    print(f"Examiner Summary:\n  {summary}")

    print("\nCriteria Justifications:")
    criteria_list = getattr(feedback, "criteria", [])
    for crit in criteria_list:
        crit_name = getattr(crit, "criterion", "")
        if hasattr(crit_name, "value"):
            crit_name = crit_name.value
        crit_score = getattr(crit, "score", 0.0) or 0.0
        crit_sum = getattr(crit, "summary", "")
        print(f"  • [{crit_name}] Band {crit_score:.1f}: {crit_sum}")
        ac_note = getattr(crit, "acoustic_grounding_note", getattr(crit, "acousticGroundingNote", None))
        if ac_note:
            print(f"    (Acoustic Grounding: {ac_note})")

    # Spoken Grammar Corrections
    grammar_corrections = getattr(feedback, "grammar_corrections", getattr(feedback, "grammarCorrections", []))
    if grammar_corrections:
        print("\n" + "─" * 80)
        print("🛠️ 5. DETECTED SPOKEN ERRORS & BAND 7/8 UPGRADES:")
        for idx, err in enumerate(grammar_corrections, 1):
            err_type = getattr(err, "error_type", getattr(err, "errorType", ""))
            err_sev = getattr(err, "severity", "")
            orig_utt = getattr(err, "original_utterance", getattr(err, "originalUtterance", ""))
            corr_utt = getattr(err, "corrected_utterance", getattr(err, "correctedUtterance", ""))
            expl = getattr(err, "explanation", "")
            better_alt = getattr(err, "better_alternative", getattr(err, "betterAlternative", None))
            print(f"\n  Correction #{idx} [{err_type} - {err_sev}]:")
            print(f"   - Original Spoken : \"{orig_utt}\"")
            print(f"   - Corrected Speech: \"{corr_utt}\"")
            print(f"   - Explanation     : {expl}")
            if better_alt:
                print(f"   - Band 7/8 Upgrade: \"{better_alt}\"")

    # Vocabulary Upgrades
    vocabulary_upgrades = getattr(feedback, "vocabulary_upgrades", getattr(feedback, "vocabularyUpgrades", []))
    if vocabulary_upgrades:
        print("\n" + "─" * 80)
        print("💡 6. RECOMMENDED VOCABULARY UPGRADES:")
        for idx, voc in enumerate(vocabulary_upgrades[:4], 1):
            orig_word = getattr(voc, "original_word_or_phrase", getattr(voc, "originalWordOrPhrase", ""))
            upgrades = getattr(voc, "upgraded_alternatives", getattr(voc, "upgradedAlternatives", []))
            alts = ", ".join(upgrades)
            print(f"  {idx}. Original: '{orig_word}' -> Upgrades: [{alts}]")
            colloc = getattr(voc, "collocation_notes", getattr(voc, "collocationNotes", None))
            if colloc:
                print(f"     Note: {colloc}")

    # Improvement Tips
    improvement_tips = getattr(feedback, "improvement_tips", getattr(feedback, "improvementTips", []))
    if improvement_tips:
        print("\n" + "─" * 80)
        print("🚀 7. ACTIONABLE TARGET BAND TIPS:")
        for tip in improvement_tips:
            target_b = getattr(tip, "target_band", getattr(tip, "targetBand", 6.0)) or 6.0
            cat = getattr(tip, "category", getattr(tip, "criterion", "Overall"))
            if hasattr(cat, "value"):
                cat = cat.value
            text = getattr(tip, "tip_text", getattr(tip, "tipText", ""))
            print(f"  • [Target Band {target_b:.1f} - {cat}]: {text}")

    print("\n" + "=" * 80)


async def main():
    print("================================================================================")
    print("🚀 ENGONOW SMART LMS - AUTOMATED IELTS SPEAKING QA SUBSYSTEM VERIFICATION")
    print("================================================================================")

    # 1. Environment & API Key Verification
    groq_key = os.getenv("GROQ_API_KEY") or os.getenv("WHISPER_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if not groq_key:
        print("❌ Error: GROQ_API_KEY or WHISPER_API_KEY not found in .env!")
        return
    if not gemini_key:
        print("❌ Error: GEMINI_API_KEY not found in .env!")
        return

    print("🔑 API Credentials loaded successfully:")
    print(f" - Groq Whisper Key : {groq_key[:8]}...{groq_key[-4:]} (Active)")
    print(f" - Gemini LLM Key   : {gemini_key[:8]}...{gemini_key[-4:]} (Active)")

    # 2. Instantiate Orchestrator and Speaking Provider
    orchestrator = AcousticOrchestrator()
    provider = get_speaking_provider("GEMINI_2_5_FLASH_SPEAKING")
    print(f"🏗️ Speaking Provider: {type(provider).__name__} (ID: {provider.provider_id})")

    # 3. Assess Question 1 (Part 1)
    await assess_speaking_file(
        audio_path=Path("ques1.mp3"),
        exam_part="PART1",
        question_title="Part 1: What is your favorite time of day?",
        orchestrator=orchestrator,
        provider=provider,
        groq_key=groq_key,
    )

    # 4. Assess Question 2 (Part 2)
    await assess_speaking_file(
        audio_path=Path("ques2.mp3"),
        exam_part="PART2",
        question_title="Part 2: Describe a beautiful place you have visited (Where, When, What you did, Why beautiful)",
        orchestrator=orchestrator,
        provider=provider,
        groq_key=groq_key,
    )

    print("\n🎉 ALL SPEAKING ASSESSMENTS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
