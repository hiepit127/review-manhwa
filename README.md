# Review Manhwa

Công cụ dựng video review manhwa, chạy trên Google Colab và thao tác bằng giao diện web. Luồng xử lý tham khảo [ManhwaForge](https://github.com/allwin-antony/ManhwaForge): cắt panel, đọc chữ, viết lời, đọc thành tiếng, ghép video. Phần giọng nói dùng bản open source [VieNeu-TTS v3 Turbo](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo).

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/hiepit127/review-manhwa/blob/main/notebooks/Review_Manhwa.ipynb)

Chỉ đưa file truyện bạn có quyền sử dụng. Tool không tải chương từ website.

## Chạy trên Colab

1. Mở notebook bằng nút phía trên.
2. Nếu repo private: Colab → **Secrets**, thêm `GITHUB_TOKEN` (quyền đọc nội dung repo) và bật **Notebook access**.
3. `Runtime` → `Change runtime type` → **T4 GPU**.
4. Chạy lần lượt hai ô cài đặt rồi ô mở giao diện.
5. Mở link Gradio (khung trong notebook hoặc link `gradio.live`).

Trong giao diện:

1. **Nguồn** — tải ảnh, PDF hoặc ZIP, hoặc dán từng trang vào ô ảnh rồi bấm `Thêm trang này`. Sau đó bấm `Tách panel`.
2. **Kịch bản** — dán API key xAI (tạo tại [console.x.ai](https://console.x.ai)), bấm `Viết kịch bản`. Model mặc định là `grok-4.7`. Sửa cột `Lời review` nếu câu chữ chưa ổn. Không có API thì bấm `Chia cảnh để viết tay`.
3. **Giọng và video** — chọn giọng VieNeu, `Nghe thử`, rồi `Xuất video`. Có thể đưa file giọng mẫu 3–8 giây để clone trong phiên làm việc.

API key chỉ nằm trong RAM của phiên, không ghi vào `manifest.json`. Lần đầu VieNeu tải model (vài trăm MB) từ Hugging Face.

## Pipeline

1. PDF, ảnh, ZIP, hoặc từng trang dán từ clipboard được xếp đúng thứ tự.
2. OpenCV tách panel theo rãnh trắng hoặc đen. Trang webtoon quá cao được cắt tiếp.
3. EasyOCR đọc chữ Hàn, Anh hoặc Việt. Xong bước này thì GPU được giải phóng.
4. xAI (`grok-4.7`) viết lời review tiếng Việt theo từng cảnh. Có thể trỏ sang API tương thích OpenAI khác.
5. VieNeu-TTS v3 Turbo đọc lời. Trên GPU Colab nó tự dùng PyTorch; không có GPU thì dùng ONNX trên CPU.
6. FFmpeg ghép khung 16:9 hoặc 9:16, phụ đề, Ken Burns khi cảnh chỉ còn một panel, và nhạc nền nếu có.

ManhwaForge dùng PaddleOCR, Ollama và Edge-TTS trên máy local. Bản này đổi ba chỗ đó để chạy được trong một session Colab cùng VieNeu: EasyOCR thay PaddleOCR, API viết lời thay Ollama, VieNeu-TTS v3 Turbo thay Edge-TTS. Prompt nằm ở `configs/review_vi.yaml`.

## Chạy local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Mở `http://127.0.0.1:7860`. Máy không có NVIDIA thì VieNeu chạy CPU và chậm hơn. `python app.py --doctor` in những thư viện còn thiếu.

```bash
pytest
```

## Video đã đăng

Video review của kênh Cỏ 3 Lá Audio nằm trong mục Releases.

- [Sống Sót Trong Trò Chơi Với Tư Cách Là Một Cuồng Nhân - Phần 1 (Chương 1-10)](https://github.com/hiepit127/review-manhwa/releases/tag/barbarian-phan-1)
- [Sống Sót Trong Trò Chơi Với Tư Cách Là Một Cuồng Nhân - Phần 2 (Chương 11-20)](https://github.com/hiepit127/review-manhwa/releases/tag/barbarian-phan-2)

## Ghi công

- VieNeu-TTS v3 Turbo của Phạm Nguyễn Ngọc Bảo, giấy phép Apache-2.0: [pnnbao97/VieNeu-TTS](https://github.com/pnnbao97/VieNeu-TTS), model [pnnbao-ump/VieNeu-TTS-v3-Turbo](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo). Bản v4 không open source nên không dùng ở đây.
- Kiến trúc recap của [allwin-antony/ManhwaForge](https://github.com/allwin-antony/ManhwaForge). Mã trong repo này được viết lại, không sao chép nguồn ManhwaForge.
