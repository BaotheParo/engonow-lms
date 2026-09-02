import asyncio
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

from acoustic.models import WordTimestamp
from acoustic.acoustic_orchestrator import AcousticOrchestrator
from providers.config import ProviderConfig

def get_audio_info(file_path: Path): 
    """Read the audio file and extract the actual length using wave/soundfile/pydub.""" 
    data = file_path.read_bytes() 

    # Predict temporal duration if metadata decoding library is not available 
    duration = 15.0 
    try: 
        import soundfile as sf 
        import io 
        info = sf.info(io.BytesIO(data)) 
        duration = float(info.duration) 
    except Exception: 
        # Fallback calculated according to PCM size if it is a wav or estimate file 
        duration = max(5.0, len(data) / (16000 * 2)) 

    return data, duration

def generate_timestamps_from_audio(file_path: Path, fallback_text: str): 
    """ 
    Use Groq Whisper Cloud API (whisper-large-v3) or local Faster-Whisper to extract
    word timestamps, falling back to calibrated alignment if offline.
    """ 
    # 1. Try Groq Cloud Whisper API (Ultra fast, exact word timestamps)
    groq_key = os.getenv("GROQ_API_KEY") or os.getenv("WHISPER_API_KEY")
    if groq_key and groq_key.startswith("gsk_"):
        try:
            import requests
            print(f"🎙️ Transcribing {file_path.name} via Groq Whisper API (whisper-large-v3)...")
            with open(file_path, "rb") as f:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    files={"file": (file_path.name, f, "audio/mpeg")},
                    data={
                        "model": "whisper-large-v3",
                        "response_format": "verbose_json",
                        "timestamp_granularities[]": "word",
                    },
                    timeout=30,
                )
            if resp.status_code == 200:
                data = resp.json()
                timestamps = []
                transcript_words = []
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
                        transcript_words.append(cleaned_word)
                full_text = data.get("text", "").strip() or " ".join(transcript_words)
                print(f"✅ Groq Whisper transcription complete ({len(timestamps)} words detected)")
                return timestamps, full_text
            else:
                print(f"⚠️ Groq API responded with HTTP {resp.status_code}: {resp.text[:150]}")
        except Exception as e:
            print(f"⚠️ Groq Whisper transcription failed: {e}")

    # 2. Try local Faster-Whisper
    try: 
        from faster_whisper import WhisperModel 
        print(f"🎙️ Running Faster-Whisper to detect transcript for {file_path.name}...") 
        model = WhisperModel("base", device="cpu", compute_type="int8") 
        segments, _ = model.transcribe( 
            str(file_path), 
            word_timestamps=True, 
            initial_prompt="Umm, this is, uh, a verbatim transcript that includes all filler words like um, uh, and like." 
        ) 
        timestamps = [] 
        transcript_words = [] 
        for segment in segments: 
            for w in segment.words: 
                cleaned_word = w.word.strip() 
                if cleaned_word: 
                    timestamps.append(WordTimestamp( 
                        word=cleaned_word, 
                        start=round(w.start, 2), 
                        end=round(w.end, 2), 
                        probability=round(w.probability, 2) 
                    )) 
                    transcript_words.append(cleaned_word) 
        return timestamps, " ".join(transcript_words) 
    except Exception as e: 
        print(f"⚠️ Faster-Whisper not active ({e}), using calibrated word timestamp alignment...") 
        words = fallback_text.split() 
        timestamps = [] 
        cur_t = 0.5 
        for w in words: 
            timestamps.append(WordTimestamp( 
                word=w, 
                start=round(cur_t, 2), 
                end=round(cur_t + 0.35, 2), 
                probability=0.95 
            )) 
            cur_t += 0.45 
        return timestamps, fallback_text

async def evaluate_speaking_sample(audio_path: Path, question_title: str, fallback_transcript: str): 
    if not audio_path.exists(): 
        print(f"❌ Error: File {audio_path.name} not found in project directory!") 
        return 

    print("\n" + "=" * 70) 
    print(f"🎯 UNDER REVIEW: {question_title} ({audio_path.name})") 
    print("=" * 70) 

    # 1. Read audio and create timestamps 
    audio_bytes, duration = get_audio_info(audio_path) 
    timestamps, final_transcript = generate_timestamps_from_audio(audio_path, fallback_transcript) 

    # 2. In-depth acoustic analysis using AcousticOrchestrator 
    orchestrator = AcousticOrchestrator() 
    print("🔍 Analyzing acoustic indices (Fluency, GOP Phonetics, Stress, Intonation)...") 

    acoustic_result = orchestrator.process_speaking_audio( 
        audio_data=audio_bytes, 
        sample_rate=16000, 
        word_timestamps=timestamps, 
        total_duration=duration 
    ) 

    print("\n📊 1. MEASUREMENT RESULTS ACOUSTIC METRICS & FLUENCY:")
    print(f" - Total duration            : {acoustic_result.total_duration_seconds:.2f} seconds")
    print(f" - Speaking Rate             : {acoustic_result.speaking_rate_wpm:.1f} WPM")
    print(f" - Articulation Rate         : {acoustic_result.articulation_rate_wpm:.1f} WPM")
    print(f" - Phonation Ratio           : {acoustic_result.phonation_ratio * 100:.1f}%")
    print(f" - Long pauses (>0.75s)      : {acoustic_result.pause_analysis.get('silent_cognitive_pause_count', 0)}")
    print(f" - Filler words detected     : {acoustic_result.pause_analysis.get('filled_pause_count', 0)}")
    print(f" - Word stress accuracy      : {acoustic_result.word_stress_analysis.stress_accuracy_ratio * 100:.1f}%")
    print(f" - Pitch/Intonation pattern  : {acoustic_result.intonation_analysis.dominant_contour_pattern} (Monotone: {acoustic_result.intonation_analysis.monotone_flag})")
    print(f" - Phoneme errors detected   : {len(acoustic_result.phoneme_errors)}")
    for err in acoustic_result.phoneme_errors[:5]:
        print(f"    * Word '{err.word_context}': Mispronounced phoneme /{err.expected_phoneme_ipa}/ -> /{err.produced_phoneme_ipa}/ (Type: {err.error_type})")

    # 3. Scoring via AI Examiner
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        from providers.gemini_writing_provider import GeminiWritingProvider 
        provider = GeminiWritingProvider(ProviderConfig(api_key=api_key, model_name="gemini-2.5-flash")) 

        prompt_content = f""" 
IELTS Speaking Evaluation Request: 
Question: {question_title} 
Candidate Transcript: {final_transcript} 

Acoustic Diagnostics: 
- Speaking Rate: {acoustic_result.speaking_rate_wpm} WPM 
- Articulation Rate: {acoustic_result.articulation_rate_wpm} WPM 
- Silent Cognitive Pauses (>0.75s): {acoustic_result.pause_analysis.get('silent_cognitive_pause_count', 0)} 
- Filled Pauses / Fillers: {acoustic_result.pause_analysis.get('filled_pause_count', 0)} 
- Stress Accuracy: {acoustic_result.word_stress_analysis.stress_accuracy_ratio * 100:.1f}% 
- Intonation: {acoustic_result.intonation_analysis.dominant_contour_pattern} 
""" 

        print("\n🧠 Compiling scores of 4 Speaking criteria via Gemini Examiner...") 
        eval_result = await provider.evaluate( 
            prompt=prompt_content, 
            essay=final_transcript, 
            task_type="TASK2" 
        ) 

        print("\n" + "-" * 70) 
        print("🏆 IELTS SPEAKING SUMMARY SCORE SHEET:") 
        print(f"🎯 OVERALL BAND SCORE: {eval_result.overall_band}") 
        print(f"🔹 Fluency & Coherence (FC) : {eval_result.coherence_cohesion_score}") 
        print(f"🔹 Lexical Resource (LR)     : {eval_result.lexical_resource_score}") 
        print(f"🔹 Grammatical Range (GRA)   : {eval_result.grammatical_range_score}") 
        print(f"🔹 Pronunciation (PR)        : {eval_result.task_achievement_score}") 
        print("-" * 70)

async def main(): 
    # Question 1: Part 1 
    await evaluate_speaking_sample( 
        audio_path=Path("ques1.mp3"), 
        question_title="Part 1: What is your favorite time of day?", 
        fallback_transcript="Well, to be honest, my favorite time of the day is early morning because it is peaceful and I can focus on my study." 
    ) 

    # Question 2: Part 2 
    await evaluate_speaking_sample( 
        audio_path=Path("ques2.mp3"), 
        question_title="Part 2: Describe a beautiful place you have visited (Where, When, What you did, Why beautiful)", 
        fallback_transcript="I would like to talk about Da Lat, a beautiful mountainous city in Vietnam that I visited last summer with my family..." 
    )

if __name__ == "__main__": 
    asyncio.run(main())
