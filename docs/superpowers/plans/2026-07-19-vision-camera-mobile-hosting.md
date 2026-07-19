# Vision Camera Mobile Hosting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Tesseract OCR with direct Doubao image understanding, add camera/file capture and mobile view navigation, and serve the complete website from Zeabur for mainland-friendly access.

**Architecture:** The static frontend remains split between `index.html` and the same-origin calculator iframe. The Zeabur Python service serves those static files and exposes separate DeepSeek chat and Doubao vision endpoints; image extraction is validated server-side before the calculator field is updated.

**Tech Stack:** Static HTML/CSS/JavaScript, Python standard-library HTTP server, Volcengine Ark Responses API, DeepSeek Chat API, Docker, Chart.js.

---

### Task 1: Add pure vision request and response helpers

**Files:**
- Modify: `zeabur-backend/app.py`
- Modify: `test_app.py` (local test file, not committed)

- [ ] **Step 1: Write failing tests for Ark payload construction and output extraction**

```python
def test_ark_payload_sends_original_image_to_vision_model(self):
    backend = load_zeabur_backend()
    payload = backend.build_ark_vision_payload(b"image-bytes", "image/jpeg")
    self.assertEqual(payload["model"], "doubao-seed-2-0-pro-260215")
    content = payload["input"][0]["content"]
    self.assertEqual(content[0]["type"], "input_image")
    self.assertTrue(content[0]["image_url"].startswith("data:image/jpeg;base64,"))
    self.assertEqual(content[1]["type"], "input_text")

def test_extract_ark_output_text_reads_responses_api_shape(self):
    backend = load_zeabur_backend()
    data = {"output": [{"content": [{"type": "output_text", "text": '{"rows":[{"k":10,"d":7.02}]}'}]}]}
    self.assertIn('"rows"', backend.extract_ark_output_text(data))
```

- [ ] **Step 2: Run the targeted tests and verify RED**

Run:

```powershell
& "C:\Users\ASUS\Desktop\物理竞赛\.venv-paddleocr\Scripts\python.exe" -m unittest test_app.NewtonRingAppTests.test_ark_payload_sends_original_image_to_vision_model test_app.NewtonRingAppTests.test_extract_ark_output_text_reads_responses_api_shape -v
```

Expected: FAIL because the helper functions do not exist.

- [ ] **Step 3: Implement Ark configuration and pure helpers**

Add to `zeabur-backend/app.py`:

```python
import base64
import math

ARK_API_URL = os.environ.get("ARK_API_URL", "https://ark.cn-beijing.volces.com/api/v3/responses")
ARK_VISION_MODEL = os.environ.get("ARK_VISION_MODEL", "doubao-seed-2-0-pro-260215")
MAX_IMAGE_BYTES = int(os.environ.get("MAX_IMAGE_BYTES", str(12 * 1024 * 1024)))
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

VISION_PROMPT = """读取牛顿环实验数据表，只提取环级数 k 和暗环直径 d(mm)。
只输出 JSON：{"rows":[{"k":10,"d":7.02}],"warnings":[]}。
k 必须是整数，d 必须是正数。不要猜测模糊数字；不确定的行写入 warnings，不要放进 rows。"""

def build_ark_vision_payload(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return {
        "model": ARK_VISION_MODEL,
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_image", "image_url": f"data:{mime_type};base64,{encoded}"},
                {"type": "input_text", "text": VISION_PROMPT},
            ],
        }],
    }

def extract_ark_output_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    texts = []
    for item in data.get("output", []):
        for content in item.get("content", []) if isinstance(item, dict) else []:
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                texts.append(content["text"])
    return "\n".join(texts)
```

- [ ] **Step 4: Run the targeted tests and verify GREEN**

Expected: both tests PASS.

### Task 2: Validate visual rows and expose `/api/vision-data`

**Files:**
- Modify: `zeabur-backend/app.py`
- Modify: `test_app.py` (local only)

- [ ] **Step 1: Write failing validation tests**

```python
def test_validate_vision_rows_sorts_and_formats_measurements(self):
    backend = load_zeabur_backend()
    result = backend.validate_vision_rows({"rows": [{"k": 12, "d": 7.70}, {"k": 10, "d": 7.02}, {"k": 11, "d": 7.38}]})
    self.assertEqual(result["data_text"], "10 7.02\n11 7.38\n12 7.7")

def test_validate_vision_rows_rejects_fewer_than_three_rows(self):
    backend = load_zeabur_backend()
    with self.assertRaisesRegex(ValueError, "至少识别出 3 组"):
        backend.validate_vision_rows({"rows": [{"k": 10, "d": 7.02}]})
```

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL because `validate_vision_rows` is missing.

- [ ] **Step 3: Implement strict validation and Ark API call**

```python
def validate_vision_rows(parsed: dict[str, Any]) -> dict[str, Any]:
    measurements: dict[int, float] = {}
    for row in parsed.get("rows", []):
        if not isinstance(row, dict):
            continue
        try:
            k_float = float(row.get("k"))
            d = float(row.get("d"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(k_float) or not k_float.is_integer() or not math.isfinite(d) or d <= 0:
            continue
        measurements[int(k_float)] = d
    if len(measurements) < 3:
        raise ValueError("至少识别出 3 组有效的 k、d 数据，请重新拍摄清晰照片。")
    rows = [{"k": k, "d": measurements[k]} for k in sorted(measurements)]
    data_text = "\n".join(f"{row['k']} {row['d']:g}" for row in rows)
    return {"rows": rows, "data_text": data_text, "warnings": parsed.get("warnings", [])}
```

Add the API call and image workflow:

```python
def call_ark_vision(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    api_key = os.environ.get("ARK_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "error": "missing_ark_api_key", "message": "Zeabur 后端未配置 ARK_API_KEY。"}
    body = json.dumps(build_ark_vision_payload(image_bytes, mime_type), ensure_ascii=False).encode("utf-8")
    req = request.Request(
        ARK_API_URL,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": "ark_request_failed", "message": str(exc)}
    text = extract_ark_output_text(data)
    if not text:
        return {"ok": False, "error": "unexpected_ark_response", "message": "豆包视觉模型没有返回文字结果。"}
    try:
        parsed = json.loads(re.search(r"\{[\s\S]*\}", text).group(0))
        validated = validate_vision_rows(parsed)
    except Exception as exc:
        return {"ok": False, "error": "vision_data_invalid", "message": str(exc)}
    return {"ok": True, **validated, "model": ARK_VISION_MODEL}

def run_vision_data(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    if mime_type not in ALLOWED_IMAGE_TYPES:
        return {"ok": False, "error": "unsupported_image_type", "message": "只支持 JPG、PNG 或 WebP 图片。"}
    if not image_bytes:
        return {"ok": False, "error": "empty_image", "message": "请选择或拍摄图片。"}
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return {"ok": False, "error": "image_too_large", "message": "图片不能超过 12 MB。"}
    return call_ark_vision(image_bytes, mime_type)
```

- [ ] **Step 4: Change multipart extraction to return bytes and MIME type**

Return `(file_bytes, mime_type)` by reading the part-level `Content-Type` header and route requests explicitly:

```python
def extract_multipart_file(body: bytes, content_type: str) -> tuple[bytes, str]:
    boundary_match = re.search(r"boundary=([^;]+)", content_type)
    if not boundary_match:
        raise ValueError("缺少 multipart boundary。")
    boundary = boundary_match.group(1).strip().strip('"').encode("utf-8")
    for part in body.split(b"--" + boundary):
        if b"Content-Disposition:" not in part or b"filename=" not in part:
            continue
        header_end = part.find(b"\r\n\r\n")
        headers = part[:header_end].decode("utf-8", errors="replace")
        mime_match = re.search(r"Content-Type:\s*([^\r\n]+)", headers, re.I)
        mime_type = mime_match.group(1).strip().lower() if mime_match else "application/octet-stream"
        return part[header_end + 4:].rstrip(b"\r\n-"), mime_type
    raise ValueError("没有找到上传图片。")

if path == "/api/vision-data":
    image_bytes, mime_type = extract_multipart_file(body, self.headers.get("Content-Type", ""))
    result = run_vision_data(image_bytes, mime_type)
    self.send_json(result, 200 if result.get("ok") else 400)
    return
if path == "/api/ocr":
    self.send_json({"ok": False, "error": "ocr_removed", "message": "请升级前端并使用 AI 视觉识别。"}, 410)
    return
```

- [ ] **Step 5: Run the full test suite**

Run:

```powershell
& "C:\Users\ASUS\Desktop\物理竞赛\.venv-paddleocr\Scripts\python.exe" -m unittest test_app.py -v
```

Expected: all backend and existing calculator tests PASS.

### Task 3: Add camera, file selection, preview, and AI fill

**Files:**
- Modify: `calculator-original.html`
- Modify: `index.html`
- Modify: `test_app.py` (local only)

- [ ] **Step 1: Write failing frontend contract tests**

```python
def test_calculator_has_camera_file_and_preview_controls(self):
    html = (server.ROOT / "calculator-original.html").read_text(encoding="utf-8")
    self.assertIn('id="cameraInput"', html)
    self.assertIn('capture="environment"', html)
    self.assertIn('id="imageFileInput"', html)
    self.assertIn('id="imagePreview"', html)
    self.assertIn('id="visionButton"', html)

def test_frontend_uses_vision_endpoint_without_ocr(self):
    html = (server.ROOT / "index.html").read_text(encoding="utf-8")
    self.assertIn("/api/vision-data", html)
    self.assertNotIn("/api/ocr", html)
    self.assertIn('location.hostname.endsWith("github.io")', html)
    self.assertNotIn("runFit", html.split("function fillCalculatorData", 1)[1].split("async function runVision", 1)[0])
```

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL because the new controls and endpoint are absent.

- [ ] **Step 3: Replace OCR controls in the calculator**

```html
<div class="image-import-actions">
  <label class="file-action" for="cameraInput">拍照</label>
  <input class="visually-hidden" id="cameraInput" type="file" accept="image/*" capture="environment">
  <label class="file-action secondary" for="imageFileInput">选择图片</label>
  <input class="visually-hidden" id="imageFileInput" type="file" accept="image/jpeg,image/png,image/webp">
  <button id="visionButton" type="button" disabled>AI识别并填入</button>
</div>
<figure class="image-preview" id="imagePreviewWrap" hidden>
  <img id="imagePreview" alt="待识别实验数据图片">
  <figcaption id="imageFileName"></figcaption>
</figure>
<div id="visionStatus" class="vision-status" aria-live="polite"></div>
```

- [ ] **Step 4: Update parent orchestration**

Track one selected file and reuse the same upload path for camera and gallery:

```javascript
const API_BASE_URL = location.hostname.endsWith("github.io")
  ? "https://xn--11x61a012f.zeabur.app"
  : "";
const AI_BACKEND_URL = `${API_BASE_URL}/api/chat`;
const VISION_BACKEND_URL = `${API_BASE_URL}/api/vision-data`;

let selectedImageFile = null;
let selectedImageUrl = "";

function selectVisionImage(file) {
  const { preview, previewWrap, fileName, visionButton, status } = getVisionControls();
  if (!file) return;
  selectedImageFile = file;
  if (selectedImageUrl) URL.revokeObjectURL(selectedImageUrl);
  selectedImageUrl = URL.createObjectURL(file);
  preview.src = selectedImageUrl;
  fileName.textContent = file.name || "现场拍摄照片";
  previewWrap.hidden = false;
  visionButton.disabled = false;
  setVisionStatus(status, "图片已准备，可以开始 AI 识别。");
}

function setupVisionImport() {
  const controls = getVisionControls();
  if (!controls.visionButton || controls.visionButton.dataset.bound === "true") return;
  controls.visionButton.dataset.bound = "true";
  controls.cameraInput.addEventListener("change", () => selectVisionImage(controls.cameraInput.files?.[0]));
  controls.imageFileInput.addEventListener("change", () => selectVisionImage(controls.imageFileInput.files?.[0]));
  controls.visionButton.addEventListener("click", runVision);
}

async function runVision() {
  const { visionButton, status } = getVisionControls();
  if (!selectedImageFile || visionButton.disabled) return;
  visionButton.disabled = true;
  try {
    setVisionStatus(status, "正在由豆包视觉模型读取实验数据...");
    const formData = new FormData();
    formData.append("image", selectedImageFile);
    const response = await fetch(VISION_BACKEND_URL, { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.message || "AI 图片识别失败");
    fillCalculatorData(data.data_text);
    setVisionStatus(status, `已填入 ${data.rows.length} 组数据，请核对后手动计算。`, "success");
  } catch (error) {
    setVisionStatus(status, error.message, "error");
  } finally {
    visionButton.disabled = false;
  }
}
```

- [ ] **Step 5: Run frontend tests and full tests**

Expected: all tests PASS.

### Task 4: Add responsive mobile navigation

**Files:**
- Modify: `index.html`
- Modify: `test_app.py` (local only)

- [ ] **Step 1: Write failing navigation tests**

```python
def test_mobile_navigation_switches_calculator_and_assistant(self):
    html = (server.ROOT / "index.html").read_text(encoding="utf-8")
    self.assertIn('role="tablist"', html)
    self.assertIn('data-view="calculator"', html)
    self.assertIn('data-view="assistant"', html)
    self.assertIn('data-mobile-view="calculator"', html)
    self.assertIn("switchMobileView", html)
    self.assertIn("100dvh", html)
```

- [ ] **Step 2: Run test and verify RED**

Expected: FAIL because no mobile tab navigation exists.

- [ ] **Step 3: Add tab markup and state-preserving switch logic**

```html
<nav class="mobile-tabs" role="tablist" aria-label="功能导航">
  <button class="mobile-tab active" role="tab" aria-selected="true" data-view="calculator">测量计算</button>
  <button class="mobile-tab" role="tab" aria-selected="false" data-view="assistant">AI助手</button>
</nav>
<main class="app" data-mobile-view="calculator">
```

`switchMobileView(view)` only updates state and accessibility attributes:

```javascript
function switchMobileView(view) {
  if (!['calculator', 'assistant'].includes(view)) return;
  app.dataset.mobileView = view;
  document.querySelectorAll('.mobile-tab').forEach((tab) => {
    const active = tab.dataset.view === view;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
  });
}

document.querySelectorAll('.mobile-tab').forEach((tab) => {
  tab.addEventListener('click', () => switchMobileView(tab.dataset.view));
});
```

- [ ] **Step 4: Add mobile layout CSS**

At `max-width: 1050px`, use explicit viewport-sized panels:

```css
@media (max-width: 1050px) {
  body { overflow: hidden; }
  .mobile-tabs { display: grid; grid-template-columns: 1fr 1fr; height: 52px; position: sticky; top: 0; z-index: 10; }
  .app { width: 100%; height: calc(100dvh - 52px); margin: 0; display: block; }
  .calculator-frame, .assistant { width: 100%; height: 100%; min-height: 0; border-radius: 0; }
  .assistant { overflow: auto; }
  .app[data-mobile-view="calculator"] .assistant { display: none; }
  .app[data-mobile-view="assistant"] .calculator-frame { display: none; }
}
```

- [ ] **Step 5: Run full tests**

Expected: all tests PASS.

### Task 5: Serve static assets from Zeabur and remove Tesseract

**Files:**
- Create: `assets/chart.umd.min.js`
- Modify: `calculator-original.html`
- Modify: `zeabur-backend/app.py`
- Modify: `zeabur-backend/requirements.txt`
- Modify: `Dockerfile`
- Modify: `zeabur-backend/README.md`
- Modify: `test_app.py` (local only)

- [ ] **Step 1: Write failing static-hosting tests**

```python
def test_calculator_uses_local_chart_asset(self):
    html = (server.ROOT / "calculator-original.html").read_text(encoding="utf-8")
    self.assertIn('src="assets/chart.umd.min.js"', html)
    self.assertNotIn("cdn.jsdelivr.net", html)

def test_docker_copies_static_site_without_tesseract(self):
    dockerfile = (server.ROOT / "Dockerfile").read_text(encoding="utf-8")
    self.assertIn("COPY index.html calculator-original.html ./", dockerfile)
    self.assertIn("COPY assets ./assets", dockerfile)
    self.assertNotIn("tesseract", dockerfile.lower())
```

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL for CDN usage and missing Docker copies.

- [ ] **Step 3: Vendor Chart.js**

Download the currently used Chart.js UMD production bundle to `assets/chart.umd.min.js` and change the calculator script source to the local relative path.

- [ ] **Step 4: Serve an allowlisted static map**

Map only explicit paths and send static bytes:

```python
STATIC_FILES = {
    "/": (Path(__file__).with_name("index.html"), "text/html; charset=utf-8"),
    "/index.html": (Path(__file__).with_name("index.html"), "text/html; charset=utf-8"),
    "/calculator-original.html": (Path(__file__).with_name("calculator-original.html"), "text/html; charset=utf-8"),
    "/assets/chart.umd.min.js": (Path(__file__).with_name("assets") / "chart.umd.min.js", "text/javascript; charset=utf-8"),
}

def send_static(self, path: Path, content_type: str) -> None:
    body = path.read_bytes()
    self.send_response(200)
    self.send_header("Content-Type", content_type)
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)
```

- [ ] **Step 5: Simplify Docker and requirements**

Use this root Dockerfile shape and a comment-only requirements file:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY zeabur-backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY zeabur-backend/app.py .
COPY index.html calculator-original.html ./
COPY assets ./assets
CMD ["python", "app.py"]
```

```text
# The production service uses only the Python standard library.
```

- [ ] **Step 6: Run the complete test suite and `git diff --check`**

Expected: all tests PASS and no whitespace errors.

### Task 6: Browser verification and deployment

**Files:**
- Verify all changed files

- [ ] **Step 1: Run locally and verify desktop**

Open the Zeabur-style local server. Confirm desktop uses two columns, camera/file controls show a preview, visual data fill leaves the result empty, and AI chat still works.

- [ ] **Step 2: Verify mobile viewport**

At a 390 x 844 viewport, confirm tabs switch views, no text overlaps, the selected image and calculator values survive switching, and only one main panel is visible.

- [ ] **Step 3: Commit only project files**

Commit backend vision support, frontend camera/navigation, local Chart.js, Docker, and docs. Do not commit API keys, `server.py`, `test_app.py`, or `__pycache__`.

- [ ] **Step 4: Update GitHub and Zeabur**

Push or upload all changed project files. In Zeabur verify `ARK_API_KEY`, `ARK_VISION_MODEL`, and `ARK_API_URL`, then wait for the new deployment.

- [ ] **Step 5: Verify production**

Open `https://牛顿环.zeabur.app/` without GitHub Pages, run a real experimental photo through the visual model, compare every `k d` row to the image, manually calculate, and test DeepSeek chat.
