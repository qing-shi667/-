from __future__ import annotations

import base64
import json
import math
import os
import re
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
ARK_API_URL = os.environ.get(
    "ARK_API_URL",
    "https://ark.cn-beijing.volces.com/api/v3/responses",
)
ARK_VISION_MODEL = os.environ.get(
    "ARK_VISION_MODEL",
    "doubao-seed-2-0-pro-260215",
)
MAX_IMAGE_BYTES = int(os.environ.get("MAX_IMAGE_BYTES", str(12 * 1024 * 1024)))
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

APP_ROOT = Path(__file__).resolve().parent
if not (APP_ROOT / "index.html").exists() and (APP_ROOT.parent / "index.html").exists():
    APP_ROOT = APP_ROOT.parent
STATIC_FILES = {
    "/": (APP_ROOT / "index.html", "text/html; charset=utf-8"),
    "/index.html": (APP_ROOT / "index.html", "text/html; charset=utf-8"),
    "/calculator-original.html": (
        APP_ROOT / "calculator-original.html",
        "text/html; charset=utf-8",
    ),
    "/assets/chart.umd.min.js": (
        APP_ROOT / "assets" / "chart.umd.min.js",
        "text/javascript; charset=utf-8",
    ),
}

VISION_PROMPT = """读取牛顿环实验数据表，只提取环级数 k 和暗环直径 d(mm)。
只输出 JSON：{"rows":[{"k":10,"d":7.02}],"warnings":[]}。
k 必须是整数，d 必须是正数。不要猜测模糊数字；不确定的行写入 warnings，不要放进 rows。"""


def build_ark_vision_payload(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return {
        "model": ARK_VISION_MODEL,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime_type};base64,{encoded}",
                    },
                    {"type": "input_text", "text": VISION_PROMPT},
                ],
            }
        ],
    }


def extract_ark_output_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    texts: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                texts.append(content["text"])
    return "\n".join(texts)


def validate_vision_rows(parsed: dict[str, Any]) -> dict[str, Any]:
    measurements: dict[int, float] = {}
    for row in parsed.get("rows", []):
        if not isinstance(row, dict):
            continue
        try:
            k_float = float(row.get("k"))
            diameter = float(row.get("d"))
        except (TypeError, ValueError):
            continue
        if (
            not math.isfinite(k_float)
            or not k_float.is_integer()
            or not math.isfinite(diameter)
            or diameter <= 0
        ):
            continue
        measurements[int(k_float)] = diameter
    if len(measurements) < 3:
        raise ValueError("至少识别出 3 组有效的 k、d 数据，请重新拍摄清晰照片。")
    rows = [{"k": k, "d": measurements[k]} for k in sorted(measurements)]
    data_text = "\n".join(f"{row['k']} {row['d']:g}" for row in rows)
    warnings = parsed.get("warnings", [])
    return {
        "rows": rows,
        "data_text": data_text,
        "warnings": warnings if isinstance(warnings, list) else [],
    }


def call_ark_vision(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    api_key = os.environ.get("ARK_API_KEY", "").strip()
    if not api_key:
        return {
            "ok": False,
            "error": "missing_ark_api_key",
            "message": "Zeabur 后端未配置 ARK_API_KEY。",
        }
    payload = build_ark_vision_payload(image_bytes, mime_type)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        ARK_API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "error": "ark_request_failed",
            "message": str(exc),
        }
    text = extract_ark_output_text(data)
    if not text:
        return {
            "ok": False,
            "error": "unexpected_ark_response",
            "message": "豆包视觉模型没有返回文字结果。",
        }
    try:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("豆包视觉模型没有返回 JSON。")
        parsed = json.loads(match.group(0))
        validated = validate_vision_rows(parsed)
    except Exception as exc:
        return {
            "ok": False,
            "error": "vision_data_invalid",
            "message": str(exc),
        }
    return {"ok": True, **validated, "model": ARK_VISION_MODEL}


def run_vision_data(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    if mime_type not in ALLOWED_IMAGE_TYPES:
        return {
            "ok": False,
            "error": "unsupported_image_type",
            "message": "只支持 JPG、PNG 或 WebP 图片。",
        }
    if not image_bytes:
        return {
            "ok": False,
            "error": "empty_image",
            "message": "请选择或拍摄图片。",
        }
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return {
            "ok": False,
            "error": "image_too_large",
            "message": "图片不能超过 12 MB。",
        }
    return call_ark_vision(image_bytes, mime_type)


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


def extract_multipart_file(body: bytes, content_type: str) -> tuple[bytes, str]:
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
        headers = part[:header_end].decode("utf-8", errors="replace")
        mime_match = re.search(r"Content-Type:\s*([^\r\n]+)", headers, re.I)
        mime_type = (
            mime_match.group(1).strip().lower()
            if mime_match
            else "application/octet-stream"
        )
        file_bytes = part[header_end + 4 :]
        if file_bytes.endswith(b"\r\n"):
            file_bytes = file_bytes[:-2]
        return file_bytes, mime_type
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

    def send_static(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
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
        path = urlparse(self.path).path
        if path == "/api/health":
            self.send_json({"ok": True, "service": "newton-ring-zeabur-ai"})
            return
        static_file = STATIC_FILES.get(path)
        if static_file:
            self.send_static(*static_file)
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

        if path == "/api/vision-data":
            try:
                image_bytes, mime_type = extract_multipart_file(
                    body,
                    self.headers.get("Content-Type", ""),
                )
                result = run_vision_data(image_bytes, mime_type)
            except Exception as exc:
                self.send_json({"ok": False, "error": "bad_request", "message": str(exc)}, 400)
                return
            self.send_json(result, 200 if result.get("ok") else 400)
            return

        if path == "/api/ocr":
            self.send_json(
                {
                    "ok": False,
                    "error": "ocr_removed",
                    "message": "请升级前端并使用 AI 视觉识别。",
                },
                410,
            )
            return

        self.send_error(404)


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Newton Ring Zeabur AI backend: http://{HOST}:{PORT}/")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
