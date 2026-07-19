# Left OCR Data Fill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move OCR upload controls into the left calculator, fill AI-normalized `k d` data without calculating automatically, and deploy the correct Zeabur URL to GitHub Pages.

**Architecture:** `calculator-original.html` owns the visible OCR controls and data field. The parent `index.html` attaches the OCR action after the same-origin iframe loads, calls `/api/ocr`, updates the iframe status, and fills `dataInput` without calling `runFit()`.

**Tech Stack:** Static HTML/CSS/JavaScript, same-origin iframe DOM access, Zeabur HTTP API, Python `unittest` source-contract tests.

---

### Task 1: Add failing OCR placement and behavior tests

**Files:**
- Modify: `test_app.py`
- Test: `test_app.py`

- [ ] **Step 1: Replace the old OCR flow test with explicit placement and manual-calculation assertions**

```python
def test_ocr_controls_live_in_calculator_and_not_ai_panel(self):
    shell = (server.ROOT / "index.html").read_text(encoding="utf-8")
    calculator = (server.ROOT / "calculator-original.html").read_text(encoding="utf-8")
    self.assertNotIn('id="ocrImageInput"', shell)
    self.assertNotIn('id="ocrButton"', shell)
    self.assertIn('id="ocrImageInput"', calculator)
    self.assertIn('id="ocrButton"', calculator)
    self.assertIn('id="ocrStatus"', calculator)

def test_ocr_fill_does_not_start_calculation(self):
    html = (server.ROOT / "index.html").read_text(encoding="utf-8")
    fill_function = html.split("function fillCalculatorData", 1)[1].split("async function runOcr", 1)[0]
    self.assertIn('getElementById("dataInput")', fill_function)
    self.assertNotIn("runFit", fill_function)

def test_frontend_uses_deployed_zeabur_domain(self):
    html = (server.ROOT / "index.html").read_text(encoding="utf-8")
    self.assertIn("https://xn--11x61a012f.zeabur.app/api/chat", html)
    self.assertNotIn("your-zeabur-domain", html)
```

- [ ] **Step 2: Run the targeted tests and confirm they fail for missing left-side controls and automatic `runFit()`**

Run:

```powershell
& "C:\Users\ASUS\Desktop\物理竞赛\.venv-paddleocr\Scripts\python.exe" -m unittest test_app.NewtonRingAppTests.test_ocr_controls_live_in_calculator_and_not_ai_panel test_app.NewtonRingAppTests.test_ocr_fill_does_not_start_calculation -v
```

Expected: FAIL because OCR controls are still in `index.html` and `fillCalculatorData` still calls `runFit()`.

### Task 2: Move OCR controls and preserve manual calculation

**Files:**
- Modify: `calculator-original.html`
- Modify: `index.html`
- Test: `test_app.py`

- [ ] **Step 1: Add the OCR controls and status to the calculator data section**

Add before `dataInput`:

```html
<div class="ocr-tools">
    <input id="ocrImageInput" type="file" accept="image/*">
    <button id="ocrButton" type="button">OCR识别</button>
</div>
<div id="ocrStatus" class="ocr-status" aria-live="polite"></div>
```

Add restrained layout and success/error styles scoped to `.ocr-tools` and `.ocr-status`.

- [ ] **Step 2: Remove the right-side OCR row and attach the action through the loaded iframe**

In `index.html`, remove the `.ocr-row` markup and styles. Resolve the controls through `calculatorFrame.contentDocument`, attach `runOcr` on the iframe `load` event, and update status text in the left pane.

- [ ] **Step 3: Change fill behavior to data-only**

Use:

```javascript
function fillCalculatorData(dataText) {
  const doc = calculatorFrame.contentDocument;
  const input = doc?.getElementById("dataInput");
  if (!input) throw new Error("没有找到左侧计算页的数据输入框。");
  input.value = dataText;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}
```

Do not invoke `runFit()`.

- [ ] **Step 4: Run the complete test suite**

Run:

```powershell
& "C:\Users\ASUS\Desktop\物理竞赛\.venv-paddleocr\Scripts\python.exe" -m unittest test_app.py -v
```

Expected: all tests PASS.

### Task 3: Verify browser behavior and deploy

**Files:**
- Verify: `index.html`
- Verify: `calculator-original.html`

- [ ] **Step 1: Start the local static server and open the page**

Run:

```powershell
& "C:\Users\ASUS\Desktop\物理竞赛\.venv-paddleocr\Scripts\python.exe" -m http.server 8033
```

Expected: local page is available at `http://127.0.0.1:8033/`.

- [ ] **Step 2: Verify the visible layout and data-only behavior**

Confirm the OCR controls appear above the left data input, are absent from the right assistant, and filling test OCR data leaves `#result` empty until the calculation button is clicked.

- [ ] **Step 3: Commit only project changes**

```powershell
git add index.html calculator-original.html docs/superpowers/plans/2026-07-19-left-ocr-data-fill.md
git commit -m "feat: move OCR import into calculator"
```

- [ ] **Step 4: Push `main` and verify GitHub Pages**

```powershell
git push origin main
```

Open `https://qing-shi667.github.io/-/`, force refresh, confirm the loaded script contains the real Zeabur URL, then send a short AI test question.
