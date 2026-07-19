# Newton Ring AI Backend for Zeabur

Deploy the repository root with the root `Dockerfile`. The service exposes:

- `GET /`
- `GET /api/health`
- `POST /api/chat`
- `POST /api/vision-data`

Required environment variables:

- `DEEPSEEK_API_KEY`: your DeepSeek API key
- `ARK_API_KEY`: your Volcengine Ark API key

Optional environment variables:

- `DEEPSEEK_MODEL`: defaults to `deepseek-v4-flash`
- `DEEPSEEK_API_URL`: defaults to `https://api.deepseek.com/chat/completions`
- `ARK_VISION_MODEL`: defaults to `doubao-seed-2-0-pro-260215`
- `ARK_API_URL`: defaults to `https://ark.cn-beijing.volces.com/api/v3/responses`
- `ALLOWED_ORIGIN`: set to your GitHub Pages origin for stricter CORS, or keep `*`

Start command:

```bash
python app.py
```

If Zeabur asks for a build mode, choose the repository root Dockerfile. The
container serves the website and APIs from the same domain.
