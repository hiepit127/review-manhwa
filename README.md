# Review Manhwa

Công cụ dựng video review manhwa, chạy trên Google Colab và thao tác bằng giao diện web. Luồng xử lý tham khảo [ManhwaForge](https://github.com/allwin-antony/ManhwaForge): cắt panel, đọc chữ, viết lời, đọc thành tiếng, ghép video. Phần giọng nói dùng bản open source [VieNeu-TTS v3 Turbo](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo).

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/hiepit127/review-manhwa/blob/main/notebooks/Review_Manhwa.ipynb)

Chỉ dùng truyện bạn có quyền sử dụng. Có thể tải file, dán trang, hoặc lấy ảnh một chương từ link bạn được phép đọc.

## Kết nối Google Drive

Cùng cách với [Audio Full Truyện](https://github.com/hiepit127/generate-ytb-audio) (`colab/setup_colab.py` của repo đó):

1. **Gắn ổ.** Trên Colab, `google.colab.drive.mount("/content/drive")` hỏi quyền tài khoản Google. Drive thành thư mục `/content/drive/MyDrive`. Tool tạo, đọc và ghi file bằng đường dẫn thường. Drive tự đồng bộ. Không gọi API Google Drive, không có service account hay file credential trong repo.
2. **Thư mục.** Ô `DRIVE_DIR` trong notebook là gốc, mặc định `/content/drive/MyDrive/ReviewManhwa`. `prepare()` tạo thư mục rồi gán biến môi trường. App chỉ đọc các biến này:

   | Thư mục | Biến | Nội dung |
   |---|---|---|
   | `cache/jobs` | `RM_JOBS_DIR` | Panel, chữ OCR, audio, việc đang làm |
   | `cache/voices` | `RM_VOICES_DIR` | Giọng đã clone và đoạn mẫu |
   | `output` | `RM_OUTPUT_DIR` | Video mp4, phụ đề srt, wav đọc thử |
   | `hf-cache` | `HF_HOME` | Trọng số VieNeu |

   Drive không dùng được symlink của Hugging Face, nên tool đặt `HF_HUB_DISABLE_SYMLINKS=1` và `HF_HUB_DISABLE_XET=1`. Bỏ chọn `MODEL_ON_DRIVE` nếu Drive gần đầy: model nằm ở `/content/hf-cache` của phiên đó.
3. **Secret.** Repo private thì Colab Secrets có `GITHUB_TOKEN` (quyền đọc nội dung). Token chỉ đi trong header của lệnh git, không ghi vào `.git/config`, không in ra notebook. API viết lời chỉ dùng xAI. Secret tên `XAI_API_KEY` (tạo tại [console.x.ai](https://console.x.ai)), bật **Notebook access**. `prepare()` đọc secret bằng `google.colab.userdata.get` và đưa vào biến môi trường của tiến trình. Key không in ra notebook, không hiện trên giao diện, không ghi vào Drive hay `manifest.json`.
4. **Khi nào lưu trên máy.** Phiên không gắn được Drive, hoặc thư mục đã chọn không ghi được, thì dữ liệu vào `cache/` và `output/` cạnh mã nguồn. Cùng file và cùng cách tách thì lần sau dùng lại cache, khỏi OCR lại.

Đổi gốc bằng ô `DRIVE_DIR`, bằng `RM_DRIVE_ROOT` (đường dẫn tuyệt đối, hoặc tên thư mục trong My Drive), hoặc trong accordion **Đổi thư mục gốc**.

## Chạy trên Colab

1. Mở notebook bằng nút phía trên.
2. `Runtime` → `Change runtime type` → **T4 GPU**.
3. Colab → **Secrets** (biểu tượng khóa ở thanh bên trái): thêm `GITHUB_TOKEN` nếu repo private, và `XAI_API_KEY`. Bật **Notebook access**, rồi khởi động lại runtime nếu vừa thêm secret.
4. **Runtime → Run all.** Ô 2 gắn Drive. Ô 4 tạo thư mục và cài thư viện. Ô 5 mở giao diện.
5. Giao diện hiện trong khung notebook. Ô 5 in một dòng `Mở giao diện:` — đó là link mở từ máy khác. Link Gradio (`*.gradio.live`) được thử vài lần. Nếu đường hầm frpc của Gradio không tạo được, app chuyển sang Cloudflare (`*.trycloudflare.com`), rồi tới URL proxy của Colab.

Trong giao diện, thanh trên cùng hiện đang lưu ở đâu. Làm lần lượt bốn bước:

1. **Nguồn** — dán link chương rồi bấm `Lấy truyện`, hoặc tải ảnh, PDF, ZIP, hoặc dán từng trang. Sau đó bấm `Tách panel`. Ảnh lấy về nằm trong `cache/jobs/<job>/source`. Việc cũ nằm ở **Việc đã lưu**.
2. **Kịch bản** — bấm `Viết kịch bản`. Lời viết bằng xAI (`grok-4.7`). API key lấy từ Colab Secrets `XAI_API_KEY` (hoặc biến môi trường / `.env` khi chạy local), không có ô nhập key. Dòng trạng thái báo đã thấy key, hoặc nhắc thêm secret đó. Nút `Viết kịch bản` tắt khi chưa có key. Sửa cột `Lời review` nếu câu chữ chưa ổn. Không có API thì bấm `Chia cảnh, tôi viết tay`.
3. **Giọng** — chọn giọng đã có trong danh sách, rồi bấm `Nghe giọng này`. Giọng mới tạo ở màn **Tạo giọng**.
4. **Video** — `Nghe thử câu kịch bản` đọc câu đầu. `Xuất video` ghép file và chép vào thư mục output. Đường dẫn hiện ở ô `File đã lưu`.

Màn **Đọc** cũng chỉ chọn giọng đã có, nghe nhanh, rồi dán chữ. `Đọc đoạn này` lưu wav trong thư mục output.

Màn **Tạo giọng** là chỗ duy nhất để clone. Kéo thả file hoặc ghi âm 3–8 giây, đặt tên, chọn ngôn ngữ (mặc định Việt Nam) và lĩnh vực nếu muốn, nhập câu nghe thử, tick xác nhận quyền dùng giọng, rồi `Tạo giọng`. Giọng ghi vào `cache/voices`. Nghe lại, đổi tên hoặc xóa ở cột **Giọng đã lưu** trên cùng màn đó.

API key chỉ nằm trong biến môi trường của phiên, không ghi vào `manifest.json` và không in ra log. Lần đầu VieNeu tải model (vài trăm MB) từ Hugging Face.

## Pipeline

1. PDF, ảnh, ZIP, hoặc từng trang dán từ clipboard được xếp đúng thứ tự.
2. OpenCV tách panel theo rãnh trắng hoặc đen. Trang webtoon quá cao được cắt tiếp.
3. EasyOCR đọc chữ Hàn, Anh hoặc Việt. Xong bước này thì GPU được giải phóng.
4. xAI (`grok-4.7`) viết lời review tiếng Việt theo từng cảnh.
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

Mở `http://127.0.0.1:7860`. Máy không có NVIDIA thì VieNeu chạy CPU và chậm hơn. Cache nằm ở `cache/`, video ở `output/`, trừ khi trỏ sang chỗ khác.

Đường dẫn và API key có thể ghi trong `.env` cạnh mã nguồn (file này không commit). App đọc biến thư mục từ file này. Khi không có Colab Secret và biến môi trường chưa được gán, `XAI_API_KEY` trong cùng file được đưa vào môi trường của tiến trình. Giá trị key không in ra log.

```
RM_DRIVE_ROOT=/đường/dẫn/ReviewManhwa
XAI_API_KEY=
```

Tạo sẵn cây thư mục, hoặc xem các bước mà không ghi file:

```bash
python colab/setup_colab.py prepare --base /đường/dẫn/ReviewManhwa
python colab/setup_colab.py all --dry-run --base /tmp/review-manhwa
```

`prepare` tạo thư mục trong tiến trình của chính lệnh đó. `python app.py` lần sau đọc `RM_DRIVE_ROOT` từ `.env` hoặc từ biến đã export. `python app.py --doctor` in thư viện còn thiếu và thư mục đang lưu. Cổng còn bị giữ thì chạy `python scripts/close_port.py` hoặc `scripts/close_port.sh`.

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
