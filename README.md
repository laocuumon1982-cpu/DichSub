# Dịch Việt by Duy Anh

Dịch phụ đề (SRT, ASS, VTT) và sách, truyện (EPUB, Word, PDF, TXT, MOBI, PRC, AZW3...) sang tiếng Việt, và tạo phụ đề từ video, âm thanh bằng Whisper. Chạy trên Windows.

**[Tải bản mới nhất](https://github.com/laocuumon1982-cpu/DichSub/releases/latest)**: `DichViet.exe` (1 file) hoặc `DichViet-Portable.zip` (portable).

- Dịch bằng GTX / Edge (miễn phí), Gemini, OpenAI, DeepSeek, Groq, OpenRouter, Ollama, LM Studio, HachimiMT (Trung → Việt, offline).
- Giọng nói ra phụ đề: Whisper chạy trên máy (GPU NVIDIA / CPU), Groq Whisper, OpenAI Whisper.
- Giữ timeline phụ đề, giữ chương và định dạng sách, lưu tiến độ để dịch tiếp, tự cập nhật từ GitHub.

Hướng dẫn chi tiết: [HUONG_DAN.txt](HUONG_DAN.txt).

## Phát hành bản mới

1. Sửa `APP_VERSION` trong `dich_viet.py` (ví dụ `3.2.0`) và ghi chú trong `RELEASE_NOTES.md`.
2. Tạo tag cùng số: `git tag v3.2.0 && git push origin v3.2.0`.
3. GitHub Actions tự build `DichViet.exe` và `DichViet-Portable.zip` rồi đăng lên Releases. App đang dùng sẽ thấy nút "Có bản 3.2.0".

Tự build trên máy: cài Python 3.12 rồi chạy `Tao_file_EXE.bat`.

Ghi chú: cách gọi GTX/Edge tham khảo rockbenben/subtitle-translator (MIT). Model HachimiMT của ngocdang83 (CC-BY-4.0). Whisper của OpenAI (MIT), faster-whisper của SYSTRAN (MIT).
