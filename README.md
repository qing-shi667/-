# 牛顿环曲率半径测量网页

这是 GitHub Pages 版本的牛顿环曲率半径测量与不确定度评定页面。

## OCR 拍照识别

页面已加入“选择照片 / 打开摄像头 / 拍照识别”入口。

GitHub Pages 是静态托管，不能直接运行 Python 版 PaddleOCR。要使用拍照识别，需要在本机启动配套的 OCR 服务：

```powershell
.\run_ocr_web.bat
```

启动后，在线页面会请求 `http://127.0.0.1:6677/api/ocr` 调用本机 PaddleOCR，并把识别到的 `环级数 k + 暗环直径 d(mm)` 自动导入实验数据框。

如果没有启动本机 OCR 服务，页面仍可正常手动输入数据并计算。
