# Newton Ring AI Backend for Zeabur

Deploy this folder as a Zeabur service. It exposes:

- `GET /api/health`
- `POST /api/chat`
- `POST /api/ocr`

Required environment variables:

- `DEEPSEEK_API_KEY`: your DeepSeek API key

Optional environment variables:

- `DEEPSEEK_MODEL`: defaults to `deepseek-v4-flash`
- `DEEPSEEK_API_URL`: defaults to `https://api.deepseek.com/chat/completions`
- `ALLOWED_ORIGIN`: set to your GitHub Pages origin for stricter CORS, or keep `*`

Start command:

```bash
python app.py
```

If Zeabur asks for a build mode, choose Dockerfile so the OCR system package
`tesseract-ocr` is installed.
