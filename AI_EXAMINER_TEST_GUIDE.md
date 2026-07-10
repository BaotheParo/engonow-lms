# Hướng dẫn Chạy Thử nghiệm Thủ công Hệ thống AI Speaking Examiner

Tài liệu này hướng dẫn chi tiết cách chạy thủ công dịch vụ FastAPI và công cụ kiểm thử Python để thực hiện quy trình tự động chấm điểm IELTS Speaking (sử dụng Groq Whisper và Gemini 2.5 Flash) trên các tệp tin âm thanh học viên.

---

## 1. Chuẩn bị Môi trường Python

Hệ thống sử dụng Python 3.10+ và các thư viện trong thư mục ảo `venv` của dự án.

### Bước 1: Mở Terminal ở thư mục dự án
Đảm bảo bạn đang đứng ở thư mục gốc của dự án:
```bash
d:\Project CV\engonow-lms
```

### Bước 2: Kích hoạt môi trường ảo (Venv)
*   **Trên Windows (PowerShell):**
    ```powershell
    .\venv\Scripts\Activate.ps1
    ```
*   **Trên Windows (CMD):**
    ```cmd
    .\venv\Scripts\activate.bat
    ```
*   **Không kích hoạt (Sử dụng đường dẫn trực tiếp):**
    Bạn có thể chạy lệnh trực tiếp bằng cách thêm tiền tố `venv\Scripts\python` trước các lệnh chạy file `.py`.

---

## 2. Các Bước Thực thi và Quay Video Demo

Để chạy thử nghiệm và thực hiện quy trình chấm thi tự động, bạn cần mở hai cửa sổ Terminal song song:

### Bước 3: Khởi chạy FastAPI Server (Terminal 1)
Khởi chạy file server xử lý AI để mở endpoint cổng `8001`:
```bash
# Kích hoạt venv trước đó hoặc chạy trực tiếp:
venv\Scripts:python mock_ai_services.py
```
*   **Kết quả kỳ vọng:** Terminal sẽ thông báo Uvicorn đang chạy trên `http://0.0.0.0:8001`. Hãy giữ cửa sổ này chạy ngầm trong suốt quá trình test.

---

### Bước 4: Thực thi phân tích tệp âm thanh (Terminal 2)

Bạn có thể thay đổi tệp âm thanh muốn chấm điểm trực tiếp trong mã nguồn của file `real_audio_test.py` hoặc chạy trực tiếp bằng lệnh dưới đây.

#### Thay đổi File Audio chấm thi:
Mở file `real_audio_test.py` và sửa dòng khai báo tên file âm thanh tương ứng:
```python
# Mở real_audio_test.py và chỉnh sửa:
AUDIO_FILE_NAME = "tiw_mock_test.mp3"    # Bài thi 1 (Khá trôi chảy - 7.0+)
# hoặc
AUDIO_FILE_NAME = "tiw_mock_test_2.mp3"  # Bài thi 2 (Nhiều lỗi - 5.0)
# hoặc
AUDIO_FILE_NAME = "tiw_mock_test_3.mp3"  # Bài thi 3 (Độ dài trung bình - ~5.5-6.0)
```

#### Chạy script kiểm thử:
```bash
venv\Scripts\python real_audio_test.py
```

*   **Kết quả hiển thị trên Console:**
    *   Hệ thống đọc dữ liệu nhị phân của tệp âm thanh và đẩy lên cổng `8001`.
    *   Sau khoảng 15-30 giây (tùy thuộc vào thời lượng file âm thanh), màn hình console sẽ in ra bảng báo cáo điểm số chi tiết dạng:
    ```text
    ============================================================
             IELTS SPEAKING AI ASSESSMENT REPORT
    ============================================================
     Session ID          : 101
     Status              : SUCCESS
    ------------------------------------------------------------
     CRITERION BAND SCORES (IELTS BANDS):
      - Pronunciation    : 6.0
      - Fluency          : 6.0
      - Lexical Resource : 5.5
      - Grammar          : 5.5
    ------------------------------------------------------------
     EVALUATION EVIDENCES AND ERRORS EXTRACTED (10):
     ... [Danh sách 10 lỗi học thuật bóc tách thực tế kèm Quote và Giải thích] ...
    ```

---

## 3. Cấu trúc Hoạt động của Pipeline AI

1.  **Groq Whisper-large-v3:** Nhận dạng giọng nói ở mức độ chi tiết từng từ (Word-level timestamps) từ file MP3 học viên, tự động đo đạc khoảng lặng giữa các từ. Nếu phát hiện ngập ngừng nghỉ > 1.5 giây, nhãn ngắt nghỉ dạng `[2.2s pause]` sẽ được tự động chèn vào transcript.
2.  **Gemini 2.5 Flash:** Phân tích ngữ cảnh đoạn nói chứa nhãn ngắt nghỉ dựa theo bộ câu hỏi metadata được truyền lên từ Frontend, đối chiếu với tiêu chuẩn IELTS Band Descriptors để xếp điểm chi tiết và xuất ra danh sách lỗi cấu trúc.
