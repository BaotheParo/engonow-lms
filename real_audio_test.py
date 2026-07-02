"""
Filename: real_audio_test.py
Description: Đọc file mp3 thực tế, gửi qua Mock AI Server để chạy luồng 
             Syntactic Pause Mapping và hiển thị kết quả chấm điểm ra Console.
"""

import httpx
import os
import sys

# Cấu hình cổng kết nối đến Mock AI Server của bạn
AI_SERVER_URL = "http://localhost:8001/api/v1/ai/speaking-analyze"
AUDIO_FILE_NAME = "tiw_mock_test.mp3"


def run_speaking_assessment():
    # 1. Kiểm tra sự tồn tại của file mp3 mục tiêu
    if not os.path.exists(AUDIO_FILE_NAME):
        print(
            f"[-] Lỗi: Không tìm thấy file {AUDIO_FILE_NAME} trong thư mục gốc."
        )
        print("[*] Hãy copy file mp3 từ YouTube vào thư mục này để tiếp tục.")
        sys.exit(1)

    file_size_mb = os.path.getsize(AUDIO_FILE_NAME) / (1024 * 1024)
    print(f"[+] Tìm thấy file âm thanh: {AUDIO_FILE_NAME}")
    print(f"[+] Dung lượng file: {file_size_mb:.2f} MB")
    print("[*] Đang đọc file và đóng gói payload giả lập...")

    # 2. Chuẩn bị dữ liệu Form-Data để gửi sang AI Server
    # session_id đóng vai trò đại diện cho booking ID phía Java
    payload_data = {
        "session_id": "101",
        "audio_url": f"https://res.cloudinary.com/engonow/video/upload/{AUDIO_FILE_NAME}",
    }

    # Đọc file dưới dạng binary để chuẩn bị stream qua HTTP
    with open(AUDIO_FILE_NAME, "rb") as audio_binary:
        files = {"file": (AUDIO_FILE_NAME, audio_binary, "audio/mpeg")}

        print("[*] Gửi file âm thanh đến máy chủ AI (Port 8001)...")

        try:
            # Gọi API chấm điểm Speaking nâng cao
            response = httpx.post(
                AI_SERVER_URL, data=payload_data, timeout=30.0
            )

            if response.status_code != 200:
                print(
                    f"[-] Lỗi kết nối AI Server. Mã lỗi: {response.status_code}"
                )
                print(f"[-] Chi tiết: {response.text}")
                return

            # 3. Phân tích dữ liệu JSON trả về và in ra Console
            result = response.json()
            print("\n" + "=" * 60)
            print("         BÁO CÁO KẾT QUẢ CHẤM ĐIỂM IELTS SPEAKING AI")
            print("=" * 60)
            print(f" Mã phiên thi (Session ID) : {result.get('session_id')}")
            print(f" Tình trạng kết nối file   : THÀNH CÔNG")
            print("-" * 60)
            print(" ĐIỂM SỐ CHI TIẾT TỪNG TIÊU CHÍ (IELTS BANDS):")
            print(
                f"  - Phát âm (Pronunciation) : {result.get('pronunciation_score')}"
            )
            print(f"  - Độ trôi chảy (Fluency)  : {result.get('fluency_score')}")
            print(
                f"  - Vốn từ vựng (Lexical)   : {result.get('lexical_score')}"
            )
            print(f"  - Ngữ pháp (Grammar)      : {result.get('grammar_score')}")
            print("-" * 60)

            # In danh sách bằng chứng bóc tách theo Part và Câu hỏi
            evidences = result.get("evidences", [])
            print(f" DANH SÁCH BẰNG CHỨNG TRÍCH XUẤT VÀ PHÂN ĐOẠN ({len(evidences)} lỗi):")

            for idx, ev in enumerate(evidences, 1):
                print(f"\n  {idx}. Tiêu chí: {ev.get('criterion')}")
                print(f"     Phân đoạn thi: {ev.get('part')}")
                print(f"     Câu hỏi giám khảo: {ev.get('question')}")
                print(f"     Học viên nói sai : \"{ev.get('quote')}\"")
                print(f"     Loại lỗi hệ thống: {ev.get('error_type')}")
                print(f"     Gợi ý sửa đổi    : {ev.get('correction')}")
                print(f"     Giải thích sư phạm: {ev.get('explanation')}")

            print("-" * 60)
            print(" DANH SÁCH CÁC PHA TỰ SỬA LỖI ĐÃ GHI NHẬN (SELF-CORRECTION):")
            for sc in result.get("self_corrections", []):
                print(
                    f"  [+] Học viên lỡ nói '{sc.get('original')}' nhưng đã sửa lại thành '{sc.get('corrected')}' qua từ đệm '{sc.get('marker')}' ({sc.get('type')})"
                )

            print("-" * 60)
            print(" NHẬN XÉT TỔNG QUAN TỪ GIÁM KHẢO AI:")
            print(f"  {result.get('feedback_text')}")
            print("=" * 60 + "\n")

        except httpx.ConnectError:
            print(
                "[-] Lỗi: Không thể kết nối đến AI Server. Hãy đảm bảo bạn đã chạy file mock_ai_services.py ở port 8001."
            )
        except Exception as e:
            print(f"[-] Lỗi hệ thống: {str(e)}")


if __name__ == "__main__":
    run_speaking_assessment()
