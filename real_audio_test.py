"""
Filename: real_audio_test.py
Description: Reads a real mp3 file, sends it to the AI Server to run
             STT (Groq Whisper) + LLM Evaluation (Gemini 1.5 Flash).
"""

import httpx
import os
import sys
import json

AI_SERVER_URL = "http://localhost:8001/api/v1/ai/speaking-analyze"
AUDIO_FILE_NAME = "tiw_mock_test_3.mp3"


def run_speaking_assessment():
    if not os.path.exists(AUDIO_FILE_NAME):
        print(f"[-] Error: File {AUDIO_FILE_NAME} not found in workspace root.")
        sys.exit(1)

    file_size_mb = os.path.getsize(AUDIO_FILE_NAME) / (1024 * 1024)
    print(f"[+] Found audio file: {AUDIO_FILE_NAME}")
    print(f"[+] File size: {file_size_mb:.2f} MB")

    # Simulate questions asked by Frontend
    questions = [
        {
            "part": "PART_1",
            "question": "Are you still friends with the people that you've known since childhood?"
        },
        {
            "part": "PART_2",
            "question": "Describe a person you know who likes to cook for other people."
        },
        {
            "part": "PART_3",
            "question": "Should children be taught cooking skills from a young age?"
        }
    ]
    
    payload_data = {
        "session_id": "101",
        "questions_metadata": json.dumps(questions)
    }

    print("[*] Reading audio file binary data...")
    with open(AUDIO_FILE_NAME, "rb") as audio_binary:
        files = {"file": (AUDIO_FILE_NAME, audio_binary, "audio/mpeg")}

        print("[*] Sending audio payload to AI Assessment Server (Port 8001)...")

        try:
            response = httpx.post(
                AI_SERVER_URL, data=payload_data, files=files, timeout=90.0
            )

            if response.status_code != 200:
                print(f"[-] API Server Error. Code: {response.status_code}")
                print(f"[-] Details: {response.text}")
                return

            result = response.json()
            print("\n" + "=" * 60)
            print("         IELTS SPEAKING AI ASSESSMENT REPORT")
            print("=" * 60)
            print(f" Session ID          : {result.get('session_id')}")
            print(f" Status              : SUCCESS")
            print("-" * 60)
            print(" CRITERION BAND SCORES (IELTS BANDS):")
            print(f"  - Pronunciation    : {result.get('pronunciation_score')}")
            print(f"  - Fluency          : {result.get('fluency_score')}")
            print(f"  - Lexical Resource : {result.get('lexical_score')}")
            print(f"  - Grammar          : {result.get('grammar_score')}")
            print("-" * 60)

            evidences = result.get("evidences", [])
            print(f" EVALUATION EVIDENCES AND ERRORS EXTRACTED ({len(evidences)}):")

            for idx, ev in enumerate(evidences, 1):
                print(f"\n  {idx}. Criterion: {ev.get('criterion')}")
                print(f"     Part: {ev.get('part')}")
                print(f"     Question: {ev.get('question')}")
                print(f"     Quote: \"{ev.get('quote')}\"")
                print(f"     Error Type: {ev.get('error_type')}")
                print(f"     Correction: {ev.get('correction')}")
                print(f"     Explanation: {ev.get('explanation')}")

            print("-" * 60)
            print(" DETECTED SELF-CORRECTIONS:")
            for sc in result.get("self_corrections", []):
                print(
                    f"  [+] Repetition/Correction: '{sc.get('original')}' -> '{sc.get('corrected')}' (marker: '{sc.get('marker')}', type: {sc.get('type')})"
                )

            print("-" * 60)
            print(" GENERAL FEEDBACK SUMMARY:")
            print(f"  {result.get('feedback_text')}")
            print("=" * 60 + "\n")

        except httpx.ConnectError:
            print("[-] Error: Cannot connect to AI Server. Please ensure mock_ai_services.py is running on port 8001.")
        except Exception as e:
            print(f"[-] Unexpected Error: {str(e)}")


if __name__ == "__main__":
    run_speaking_assessment()
