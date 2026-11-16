## Tải về

- **DichSub.exe**: bản 1 file, bấm đúp là chạy.
- **DichSub-Portable.zip**: bản portable, giải nén rồi mở `DichSub.exe` bên trong. Mọi dữ liệu nằm trong thư mục `data`, chép sang USB hay máy khác là dùng tiếp.

Đang dùng bản 3.1 trở lên: bấm nút "Có bản 4.0.1" ở góc trên app để tự cập nhật, giữ nguyên dữ liệu.

## Có gì mới trong 4.0.1

- **Báo cáo Agent**: chạy xong là tự mở bảng báo cáo cho tài liệu đang xem.
  - Tổng quan: số dòng đã dịch, dịch mới, đã thẩm định, đã sửa, còn cần xem, thời gian chạy, bộ nhớ học thêm.
  - Các điểm hiệu đính chia nhóm: danh xưng & nhân vật, cảnh giới, công pháp/pháp bảo/chiêu thức, địa danh/môn phái, xưng hô, dịch sai/sót, rút gọn, trau chuốt câu chữ. Mỗi mục ghi bản cũ, bản mới, lý do.
  - Bấm "Dòng N" để nhảy tới đúng câu trên timeline. Có nút Chép báo cáo, Giữ tất cả bản sửa, Thẩm định lại.
  - Mở lại bất cứ lúc nào: nút "Báo cáo Agent" trên đầu tài liệu hoặc trong mục Agent Editor.

## Có gì mới trong 4.0.0: AGENT EDITOR, biết "nhớ cốt truyện"

Hết cảnh tập 1 dịch một kiểu, tập 2 tên nhân vật, cảnh giới lại thành kiểu khác.

- **Bộ nhớ cốt truyện dùng chung cho cả bộ phim**: tên nhân vật, địa danh, môn phái, cảnh giới, chiêu thức, cách xưng hô giữa các nhân vật, tóm tắt từng tập. Lưu trong một file SQLite, mở bảng sửa trực tiếp, xuất/nhập ra file JSON để chia sẻ.
- **Tự nhận bộ phim và số tập theo tên file** (`Tap 05`, `E05`, `S01E05`, `第5集`...). Các tập cùng bộ tự dùng chung bộ nhớ.
- **Agent tự chạy luồng Đọc hiểu → Dịch có ngữ cảnh → Thẩm định & hiệu đính → Ghi nhớ tập**:
  - Đọc hiểu cả tập trước khi dịch, học tên mới. Tên đã có thì không bao giờ bị đổi, nên đồng bộ xuyên suốt hàng chục tập.
  - Dịch kèm sổ tay bộ phim, tóm tắt các tập trước, các câu trước và sau.
  - Tự rà soát: câu dịch sai, dịch sót, còn chữ nước ngoài, sai tên so với bộ nhớ, xưng hô lệch, câu quá dài so với thời gian hiện. Sửa xong ghi rõ lý do, giữ bản cũ để hoàn tác.
  - Dịch xong cả tập thì tóm tắt tập và cập nhật cốt truyện chung cho các tập sau.
- **Sửa trên timeline**: thanh timeline cả tập tô màu chưa dịch / đã dịch / cần xem / Agent đã sửa; bấm để nhảy tới câu, nút "Chỗ cần xem tiếp theo", lọc "Cần xem", Hoàn tác / Giữ / Bỏ qua ngay trên từng dòng.
- **Học từ bản dịch chuẩn** (nút "Chọn tập đã dịch chuẩn…" trong Agent Editor): chọn các tập đã dịch chuẩn có sẵn trong danh sách, hoặc thêm cặp file gốc + bản dịch (vd. `Tap 01.zh.srt` + `Tap 01.vi.srt`, app tự ghép theo số tập và thời gian). Agent đọc hết, so câu gốc với câu dịch để học đúng tên nhân vật, địa điểm, môn phái, cảnh giới, chiêu thức, xưng hô theo bản dịch đó, ghi là đã duyệt và sửa lại các tên AI tự đoán trước đó. Chỉ nhận tên thật sự xuất hiện trong bản dịch chuẩn.
- **Đổi tên một lần, sửa mọi tập**: sửa bản dịch của một tên trong bộ nhớ, app hỏi thay luôn trong các tập đã dịch.
- **Dùng AI Agent trên máy**: Claude Code, Codex, Antigravity (dùng tài khoản đã đăng nhập, không cần API key), cùng Gemini, OpenAI, DeepSeek, Groq, OpenRouter và AI chạy offline Ollama, LM Studio.
- "Kiểm tra lỗi ngay" chạy không tốn AI. Tạo phụ đề từ video / quét OCR rồi "Tự dịch" cũng đi qua Agent.

## Có gì mới trong 3.3.2

- Sửa lỗi HachimiMT báo "Chưa dùng được GPU" kèm `ImportError: DLL load failed while importing _sentencepiece`: bản exe để một DLL của sentencepiece sang thư mục khác khi đóng gói, nay app tự tìm đúng chỗ. Lỗi thư viện cũng không còn bị báo nhầm thành lỗi GPU.

## Có gì mới trong 3.3.1

- Nút riêng **"SRT → ASS nền đen"** trên thanh trên cùng (và trên màn hình chào): mở cửa sổ kéo thả file SRT, VTT, ASS, chọn cỡ chữ, độ đậm nền, dải che, xem trước, chuyển ngay không cần dịch.

## Có gì mới trong 3.3.0

- **Phụ đề nền đen**: mục Xuất file có lựa chọn "Nền đen dưới chữ", xuất phụ đề ra file .ASS có hộp đen sau chữ (SRT không chứa được màu nền). Chọn cỡ chữ, độ đậm nền, có khung xem trước.
- **Che chữ in sẵn**: phụ đề lấy từ tab Quét phụ đề được phủ dải đen đúng chỗ chữ Trung in sẵn của từng câu, bản dịch tiếng Việt nằm gọn trên đó. Phụ đề khác có thể che dải dưới khung hình 15/20/25%.
- **Chuyển SRT có sẵn sang ASS nền đen**: chọn hoặc kéo thả nhiều file SRT, VTT, ASS, chuyển ngay không cần dịch, lưu cạnh file gốc.

## Có gì mới trong 3.2.1

- Sửa lỗi: nếu bản cũ (3.0, 3.1) còn chạy ngầm thì mở bản mới vẫn hiện giao diện cũ, không thấy tab Giọng nói và Quét phụ đề. Giờ bản mới luôn mở đúng giao diện của nó; bản cũ đang rảnh (từ 3.2.1 trở đi) sẽ tự tắt nhường chỗ.

## Có gì mới trong 3.2.0

- Đổi tên thành **Dịch Sub & Book by Duy Anh**, file chạy `DichSub.exe`.
- Tab **Quét phụ đề (OCR)**: đọc phụ đề in sẵn trên hình (hardsub) ra file SRT đúng thời gian. Khoanh vùng chữ bằng chuột, thử đọc trước khi quét. Đọc được Trung (giản, phồn), Nhật, Anh, Hàn, Việt. Có thể tự dịch luôn sang tiếng Việt.
