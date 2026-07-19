# 视觉识图、移动导航与统一部署设计

## 目标

改进牛顿环实验网站的图片数据导入、手机端布局和中国大陆访问体验：

- 不再使用 Tesseract OCR，直接把实验照片交给豆包视觉模型识别。
- 手机端可立即调用后置摄像头拍照，也可从相册或文件中选图。
- 视觉模型返回环级数 `k` 和暗环直径 `d`，网页自动填入实验数据框，但不自动计算。
- 桌面端保留测量计算与 AI 助手双栏；手机端使用顶部导航切换两个视图。
- Zeabur 同时提供网页和 API，GitHub 仅作为源代码仓库，降低大陆网络对 GitHub Pages 的依赖。

## 模型与密钥

- 图片识别模型：`doubao-seed-2-0-pro-260215`
- 方舟接口：`https://ark.cn-beijing.volces.com/api/v3/responses`
- 图片请求格式：Responses API 的 `input_image` + `input_text`
- Zeabur 环境变量：
  - `ARK_API_KEY`：只保存在 Zeabur，不写入仓库或前端。
  - `ARK_VISION_MODEL=doubao-seed-2-0-pro-260215`
  - `ARK_API_URL=https://ark.cn-beijing.volces.com/api/v3/responses`
- 右侧问答继续使用现有 `DEEPSEEK_API_KEY` 和 `deepseek-v4-flash`。

## 前端交互

### 拍照与选图

测量计算页面提供三个明确操作：

1. “拍照”：使用独立的 `input[type=file]`，配置 `accept=image/*` 和 `capture=environment`，在手机端直接调用后置摄像头。
2. “选择图片”：使用不带 `capture` 的图片文件输入，可从相册或文件中选择。
3. “AI识别并填入”：仅在已有图片时可用，将当前图片上传给后端。

选择或拍摄后显示图片预览、文件名和更换操作。图片识别期间禁用提交按钮并显示进度；失败时保留原实验数据。

### 数据填入

后端只接受模型返回的结构化数据。每行必须包含有限数值 `k`、`d`，至少三组数据才允许填入。成功后覆盖 `dataInput`，显示识别行数和“请人工核对后手动计算”，不调用 `runFit()`。

### 响应式布局

- 宽屏：保持测量计算和 AI 助手左右双栏。
- 手机端：页面顶部显示粘性导航“测量计算 / AI助手”，默认打开“测量计算”，一次只显示一个视图。
- 切换视图只改变可见性，不重建 iframe 或聊天区域，因此已输入数据、计算结果和对话记录保持不变。
- 手机端计算 iframe 与 AI 面板使用可用视口高度并各自滚动，避免当前的超长页面和嵌套错位。

## 后端数据流

1. 浏览器向 `/api/vision-data` 上传图片。
2. 后端校验文件存在、MIME 类型和大小上限。
3. 后端将图片编码为 Data URL，连同严格 JSON 提示发送给豆包 Responses API。
4. 提示要求模型读取牛顿环实验表格，只返回 `k`、`d`，不得猜测模糊数字。
5. 后端解析模型输出，验证数值、去除无效行，并返回 `data_text`、`rows` 和可选警告。
6. 前端填入数据框，等待用户手动计算。

现有 `/api/chat` 保持不变。旧 `/api/ocr` 可在过渡期返回弃用提示，前端不再调用。

## 统一部署

Zeabur 服务从根目录直接提供：

- `/`：`index.html`
- `/calculator-original.html`：计算页面
- `/assets/chart.umd.min.js`：本地 Chart.js
- `/api/health`、`/api/chat`、`/api/vision-data`：后端 API

Docker 镜像不再安装 Tesseract，也不再需要 `pytesseract`。Chart.js 不从境外 CDN 加载。主要访问地址改为 `https://牛顿环.zeabur.app/`，GitHub Pages 仅保留为备用入口。

## 错误处理与安全

- API Key 只从环境变量读取，日志不得输出 Key 或完整图片数据。
- 限制图片大小，拒绝非图片上传。
- 模型返回非 JSON、少于三行或含非法数值时，不覆盖现有数据。
- 方舟请求失败时返回可读中文错误；DeepSeek 问答不受影响。
- 前端所有状态消息使用文本写入，不插入模型返回的 HTML。

## 验证

- 单元测试覆盖图片请求构造、方舟响应解析、数据验证、文件类型与大小限制。
- 前端测试覆盖拍照/选图双入口、手机导航、视图状态保留和禁止自动计算。
- 桌面与手机浏览器截图检查无重叠、无溢出。
- 使用真实实验照片验证视觉模型输出并人工核对 `k d`。
- 部署后从 `https://牛顿环.zeabur.app/` 验证网页、视觉识别、手动计算和 DeepSeek 问答。
