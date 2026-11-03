# Dịch Sub & Book by Duy Anh

Dịch phụ đề (SRT, ASS, VTT) và sách, truyện (EPUB, Word, PDF, TXT, MOBI, PRC, AZW3...) sang tiếng Việt, tạo phụ đề từ giọng nói bằng Whisper và quét phụ đề in sẵn trong video (OCR). Chạy trên Windows.

**[Tải bản mới nhất](https://github.com/laocuumon1982-cpu/DichSub/releases/latest)**: `DichSub.exe` (1 file) hoặc `DichSub-Portable.zip` (portable).

- Dịch bằng GTX / Edge (miễn phí), Gemini, OpenAI, DeepSeek, Groq, OpenRouter, Ollama, LM Studio, HachimiMT (Trung → Việt, offline).
- Giọng nói ra phụ đề: Whisper chạy trên máy (GPU NVIDIA / CPU), Groq Whisper, OpenAI Whisper.
- Quét phụ đề in sẵn (hardsub) ra SRT bằng RapidOCR: Trung, Nhật, Anh, Hàn, Việt.
- Giữ timeline phụ đề, giữ chương và định dạng sách, lưu tiến độ để dịch tiếp, tự cập nhật từ GitHub.

Hướng dẫn chi tiết: [HUONG_DAN.txt](HUONG_DAN.txt).

## Phát hành bản mới

1. Sửa `APP_VERSION` trong `dich_viet.py` (ví dụ `3.2.0`) và ghi chú trong `RELEASE_NOTES.md`.
2. Đẩy lên nhánh `main`. GitHub Actions thấy số phiên bản mới sẽ tự build `DichSub.exe` và `DichSub-Portable.zip` rồi đăng lên Releases (tag `v3.2.0`). App đang dùng sẽ thấy nút "Có bản 3.2.0".
3. Đẩy lên mà không đổi số phiên bản thì không phát hành gì. Muốn build thử: tab Actions, chọn "Build Windows", bấm "Run workflow" (file nằm trong Artifacts).

Tự build trên máy: cài Python 3.12 rồi chạy `Tao_file_EXE.bat`.

Ghi chú: cách gọi GTX/Edge tham khảo rockbenben/subtitle-translator (MIT). Model HachimiMT của ngocdang83 (CC-BY-4.0). Whisper của OpenAI (MIT), faster-whisper của SYSTRAN (MIT). RapidOCR và model PaddleOCR (Apache-2.0). Danh sách từ tiếng Anh `en_words.txt.gz` lấy từ wordninja (MIT).
