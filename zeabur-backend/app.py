from __future__ import annotations

import json
import os
import re
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import request
from urllib.parse import urlparse


HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
DEEPSEEK_API_URL = os.environ.get(
    "DEEPSEEK_API_URL",
    "https://api.deepseek.com/chat/completions",
)
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
OCR_LANG = os.environ.get("OCR_LANG", "eng+chi_sim")


def build_messages(
    question: str,
    calculation: dict[str, Any] | None,
    history: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "你是牛顿环测透镜曲率半径实验的中文教学助手。"
                "回答要准确、简洁，优先解释实验原理、数据处理、误差来源和报告写法。"
            ),
        }
    ]
    if calculation:
        messages.append(
            {
                "role": "system",
                "content": "当前网页计算上下文："
                + json.dumps(calculation, ensure_ascii=False)[:3500],
            }
        )
    for item in (history or [])[-6:]:
        role = item.get("role")
        content = item.get("content", "")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:1200]})
    messages.append({"role": "user", "content": question})
    return messages


def call_deepseek(messages: list[dict[str, str]]) -> dict[str, Any]:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return {
            "ok": False,
            "error": "missing_api_key",
            "message": "Zeabur 后端未配置 DEEPSEEK_API_KEY。",
        }

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": 0,
        "thinking": {"type": "disabled"},
        "stream": False,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        DEEPSEEK_API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "error": "deepseek_request_failed",
            "message": str(exc),
        }

    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        answer = ""
    if not answer:
        return {
            "ok": False,
            "error": "unexpected_deepseek_response",
            "message": json.dumps(data, ensure_ascii=False)[:1000],
        }
    return {"ok": True, "answer": answer, "model": DEEPSEEK_MODEL}


def ask_deepseek(
    question: str,
    calculation: dict[str, Any] | None,
    history: list[dict[str, str]] | None,
) -> dict[str, Any]:
    question = question.strip()
    if not question:
        return {"ok": False, "error": "empty_question", "message": "请输入问题。"}
    return call_deepseek(build_messages(question, calculation, history))


def extract_data_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        raise ValueError("AI 未返回 JSON。")
    parsed = json.loads(match.group(0))
    data_text = str(parsed.get("data_text", "")).strip()
    if not data_text:
        rows = parsed.get("rows", [])
        lines = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            k_value = row.get("k")
            d_value = row.get("d")
            if k_value is not None and d_value is not None:
                lines.append(f"{k_value} {d_value}")
        data_text = "\n".join(lines).strip()
    if not data_text:
        raise ValueError("AI 未提取出 k d 数据。")
    return {"data_text": data_text, "rows": parsed.get("rows", [])}


def normalize_ocr_data(ocr_text: str) -> dict[str, Any]:
    if not ocr_text.strip():
        return {"ok": False, "error": "empty_ocr_text", "message": "OCR 未识别到文字。"}

    messages = [
        {
            "role": "system",
            "content": (
                "你负责把牛顿环实验表格 OCR 文本整理为可计算数据。"
                "只输出 JSON，不要解释。JSON 格式："
                '{"data_text":"10 7.02\\n11 7.38","rows":[{"k":10,"d":7.02}]}. '
                "data_text 每行只能是：环级数k 空格 暗环直径d(mm)。"
                "忽略表头、单位、序号、空白和无关文字；无法确定的行不要输出。"
            ),
        },
        {"role": "user", "content": ocr_text[:5000]},
    ]
    result = call_deepseek(messages)
    if not result.get("ok"):
        return result
    try:
        normalized = extract_data_json(result["answer"])
    except Exception as exc:
        return {"ok": False, "error": "normalization_failed", "message": str(exc)}
    return {
        "ok": True,
        "raw_text": ocr_text,
        "data_text": normalized["data_text"],
        "rows": normalized.get("rows", []),
        "model": result.get("model"),
    }


def run_ocr(image_bytes: bytes) -> dict[str, Any]:
    if not image_bytes:
        return {"ok": False, "error": "empty_image", "message": "请上传图片。"}
    try:
        import pytesseract
        from PIL import Image
    except Exception as exc:
        return {
            "ok": False,
            "error": "ocr_dependency_missing",
            "message": f"OCR 依赖未安装：{exc}",
        }

    suffix = ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as image_file:
        image_file.write(image_bytes)
        image_path = Path(image_file.name)
    try:
        with Image.open(image_path) as image:
            gray = image.convert("L")
            text = pytesseract.image_to_string(gray, lang=OCR_LANG)
    except Exception as exc:
        return {"ok": False, "error": "ocr_failed", "message": str(exc)}
    finally:
        image_path.unlink(missing_ok=True)
    return normalize_ocr_data(text)


def extract_multipart_file(body: bytes, content_type: str) -> bytes:
    match = re.search(r"boundary=([^;]+)", content_type)
    if not match:
        raise ValueError("缺少 multipart boundary。")
    boundary = match.group(1).strip().strip('"').encode("utf-8")
    for part in body.split(b"--" + boundary):
        if b"Content-Disposition:" not in part or b"filename=" not in part:
            continue
        header_end = part.find(b"\r\n\r\n")
        if header_end < 0:
            continue
        file_bytes = part[header_end + 4 :]
        return file_bytes.rstrip(b"\r\n-")
    raise ValueError("没有找到上传图片。")


class Handler(BaseHTTPRequestHandler):
    server_version = "NewtonRingZeaburAI/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), format % args))

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/api/health":
            self.send_json({"ok": True, "service": "newton-ring-zeabur-ai"})
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
        except Exception as exc:
            self.send_json({"ok": False, "error": "bad_request", "message": str(exc)}, 400)
            return

        if path == "/api/chat":
            try:
                payload = json.loads(body.decode("utf-8"))
            except Exception as exc:
                self.send_json({"ok": False, "error": "bad_request", "message": str(exc)}, 400)
                return
            result = ask_deepseek(
                question=str(payload.get("question", "")),
                calculation=payload.get("calculation") if isinstance(payload.get("calculation"), dict) else None,
                history=payload.get("history") if isinstance(payload.get("history"), list) else [],
            )
            self.send_json(result, 200 if result.get("ok") else 400)
            return

        if path == "/api/ocr":
            content_type = self.headers.get("Content-Type", "")
            try:
                if content_type.startswith("application/json"):
                    payload = json.loads(body.decode("utf-8"))
                    result = normalize_ocr_data(str(payload.get("ocr_text", "")))
                else:
                    image_bytes = extract_multipart_file(body, content_type)
                    result = run_ocr(image_bytes)
            except Exception as exc:
                self.send_json({"ok": False, "error": "bad_request", "message": str(exc)}, 400)
                return
            self.send_json(result, 200 if result.get("ok") else 400)
            return

        self.send_error(404)


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Newton Ring Zeabur AI backend: http://{HOST}:{PORT}/")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
