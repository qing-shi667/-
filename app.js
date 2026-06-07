const state = {
  image: null,
  imageName: '',
  original: null,
  processed: null,
  mode: 'vehicle',
  view: 'result',
  metrics: null
};

const els = {
  fileInput: document.getElementById('fileInput'),
  dropzone: document.getElementById('dropzone'),
  canvas: document.getElementById('mainCanvas'),
  emptyState: document.getElementById('emptyState'),
  imageMeta: document.getElementById('imageMeta'),
  processBtn: document.getElementById('processBtn'),
  exportBtn: document.getElementById('exportBtn'),
  sensitivity: document.getElementById('sensitivity'),
  sensValue: document.getElementById('sensValue'),
  resetModules: document.getElementById('resetModules'),
  confidence: document.getElementById('confidence'),
  targetCount: document.getElementById('targetCount'),
  edgeDensity: document.getElementById('edgeDensity'),
  riskLevel: document.getElementById('riskLevel'),
  processTime: document.getElementById('processTime'),
  sceneSummary: document.getElementById('sceneSummary'),
  eventList: document.getElementById('eventList')
};

const ctx = els.canvas.getContext('2d');
const moduleIds = ['enhanceLight', 'frequencyBoost', 'edgeMap', 'overlayBoxes', 'trajectory'];

function getModules() {
  return Object.fromEntries(moduleIds.map(id => [id, document.getElementById(id).checked]));
}

function loadImage(file) {
  if (!file || !file.type.startsWith('image/')) return;
  const reader = new FileReader();
  reader.onload = () => {
    const img = new Image();
    img.onload = () => {
      state.image = img;
      state.imageName = file.name.replace(/\.[^.]+$/, '');
      fitCanvasToImage(img);
      ctx.drawImage(img, 0, 0, els.canvas.width, els.canvas.height);
      state.original = ctx.getImageData(0, 0, els.canvas.width, els.canvas.height);
      state.processed = null;
      els.emptyState.style.display = 'none';
      els.exportBtn.disabled = true;
      els.imageMeta.textContent = `${file.name} · ${img.naturalWidth}×${img.naturalHeight}`;
      clearMetrics();
      processImage();
    };
    img.src = reader.result;
  };
  reader.readAsDataURL(file);
}

function fitCanvasToImage(img) {
  const maxSide = 1600;
  const scale = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
  els.canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
  els.canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
}

function processImage() {
  if (!state.image || !state.original) return;
  const started = performance.now();
  const modules = getModules();
  let data = new ImageData(new Uint8ClampedArray(state.original.data), state.original.width, state.original.height);

  if (modules.enhanceLight) data = equalizeLuma(data);
  if (modules.frequencyBoost) data = highBoost(data);

  const edge = sobelMap(data);
  const boxes = modules.overlayBoxes ? findCandidates(data, edge) : [];
  const edgeRatio = edge.active / (edge.width * edge.height);
  const confidence = estimateConfidence(edgeRatio, boxes.length);
  const elapsed = Math.round(performance.now() - started);

  ctx.putImageData(data, 0, 0);
  if (modules.edgeMap) drawEdges(edge);
  if (modules.overlayBoxes) drawBoxes(boxes);
  if (modules.trajectory) drawTrajectory(boxes);
  drawWatermark(confidence);

  state.processed = ctx.getImageData(0, 0, els.canvas.width, els.canvas.height);
  state.metrics = { boxes, edgeRatio, confidence, elapsed };
  els.exportBtn.disabled = false;
  renderMetrics();
  renderView();
}

function equalizeLuma(imageData) {
  const { data } = imageData;
  const hist = new Array(256).fill(0);
  for (let i = 0; i < data.length; i += 4) {
    const y = Math.round(0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]);
    hist[y]++;
  }
  const clipLimit = Math.round((data.length / 4) * 0.012);
  let excess = 0;
  for (let i = 0; i < hist.length; i++) {
    if (hist[i] > clipLimit) {
      excess += hist[i] - clipLimit;
      hist[i] = clipLimit;
    }
  }
  const redistribute = Math.floor(excess / 256);
  for (let i = 0; i < hist.length; i++) hist[i] += redistribute;

  const cdf = new Array(256);
  cdf[0] = hist[0];
  for (let i = 1; i < hist.length; i++) cdf[i] = cdf[i - 1] + hist[i];
  const total = cdf[255] || 1;
  const out = new ImageData(new Uint8ClampedArray(data), imageData.width, imageData.height);

  for (let i = 0; i < out.data.length; i += 4) {
    const r = out.data[i], g = out.data[i + 1], b = out.data[i + 2];
    const y = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
    const target = (cdf[y] / total) * 255;
    const gain = target / Math.max(18, y);
    out.data[i] = clamp(r * (0.72 + gain * 0.28));
    out.data[i + 1] = clamp(g * (0.72 + gain * 0.28));
    out.data[i + 2] = clamp(b * (0.72 + gain * 0.28));
  }
  return out;
}

function highBoost(imageData) {
  const blurred = boxBlur(imageData, 1);
  const out = new ImageData(new Uint8ClampedArray(imageData.data), imageData.width, imageData.height);
  const amount = 0.86;
  for (let i = 0; i < out.data.length; i += 4) {
    out.data[i] = clamp(imageData.data[i] + (imageData.data[i] - blurred.data[i]) * amount);
    out.data[i + 1] = clamp(imageData.data[i + 1] + (imageData.data[i + 1] - blurred.data[i + 1]) * amount);
    out.data[i + 2] = clamp(imageData.data[i + 2] + (imageData.data[i + 2] - blurred.data[i + 2]) * amount);
  }
  return out;
}

function boxBlur(imageData, radius) {
  const { width, height, data } = imageData;
  const out = new ImageData(width, height);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let r = 0, g = 0, b = 0, count = 0;
      for (let dy = -radius; dy <= radius; dy++) {
        for (let dx = -radius; dx <= radius; dx++) {
          const xx = Math.min(width - 1, Math.max(0, x + dx));
          const yy = Math.min(height - 1, Math.max(0, y + dy));
          const idx = (yy * width + xx) * 4;
          r += data[idx]; g += data[idx + 1]; b += data[idx + 2]; count++;
        }
      }
      const idx = (y * width + x) * 4;
      out.data[idx] = r / count;
      out.data[idx + 1] = g / count;
      out.data[idx + 2] = b / count;
      out.data[idx + 3] = 255;
    }
  }
  return out;
}

function sobelMap(imageData) {
  const { width, height, data } = imageData;
  const gray = new Uint8ClampedArray(width * height);
  const mag = new Uint8ClampedArray(width * height);
  for (let i = 0, j = 0; i < data.length; i += 4, j++) {
    gray[j] = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
  }
  const sens = Number(els.sensitivity.value);
  const threshold = Math.max(28, 118 - sens);
  let active = 0;
  for (let y = 1; y < height - 1; y++) {
    for (let x = 1; x < width - 1; x++) {
      const i = y * width + x;
      const gx = -gray[i - width - 1] + gray[i - width + 1] - 2 * gray[i - 1] + 2 * gray[i + 1] - gray[i + width - 1] + gray[i + width + 1];
      const gy = -gray[i - width - 1] - 2 * gray[i - width] - gray[i - width + 1] + gray[i + width - 1] + 2 * gray[i + width] + gray[i + width + 1];
      const value = Math.min(255, Math.hypot(gx, gy));
      if (value > threshold) {
        mag[i] = value;
        active++;
      }
    }
  }
  return { width, height, mag, active };
}

function findCandidates(imageData, edge) {
  const { width, height, data } = imageData;
  const grid = 12;
  const cellW = Math.max(24, Math.floor(width / grid));
  const cellH = Math.max(24, Math.floor(height / grid));
  const boxes = [];
  for (let gy = 1; gy < grid - 1; gy++) {
    for (let gx = 0; gx < grid; gx++) {
      const x0 = gx * cellW;
      const y0 = gy * cellH;
      let score = 0;
      let warm = 0;
      let dark = 0;
      for (let y = y0; y < Math.min(height, y0 + cellH); y += 3) {
        for (let x = x0; x < Math.min(width, x0 + cellW); x += 3) {
          const idx = (y * width + x) * 4;
          const e = edge.mag[y * width + x] || 0;
          const r = data[idx], g = data[idx + 1], b = data[idx + 2];
          score += e;
          warm += Math.max(0, r - b);
          dark += Math.max(0, 105 - (r + g + b) / 3);
        }
      }
      const area = (cellW * cellH) / 9;
      const normalized = score / area + warm / area * 0.13 + dark / area * (state.mode === 'inspect' ? 0.45 : 0.08);
      const limit = state.mode === 'inspect' ? 34 : 48;
      if (normalized > limit) {
        boxes.push({
          x: x0 + cellW * 0.08,
          y: y0 + cellH * 0.12,
          w: cellW * 0.84,
          h: cellH * 0.76,
          score: normalized
        });
      }
    }
  }
  return mergeBoxes(boxes).sort((a, b) => b.score - a.score).slice(0, state.mode === 'flow' ? 14 : 8);
}

function mergeBoxes(boxes) {
  const merged = [];
  for (const box of boxes) {
    const hit = merged.find(item => overlap(item, box) > 0.18);
    if (hit) {
      const x1 = Math.min(hit.x, box.x);
      const y1 = Math.min(hit.y, box.y);
      const x2 = Math.max(hit.x + hit.w, box.x + box.w);
      const y2 = Math.max(hit.y + hit.h, box.y + box.h);
      hit.x = x1; hit.y = y1; hit.w = x2 - x1; hit.h = y2 - y1;
      hit.score = Math.max(hit.score, box.score);
    } else {
      merged.push({ ...box });
    }
  }
  return merged;
}

function overlap(a, b) {
  const x1 = Math.max(a.x, b.x);
  const y1 = Math.max(a.y, b.y);
  const x2 = Math.min(a.x + a.w, b.x + b.w);
  const y2 = Math.min(a.y + a.h, b.y + b.h);
  const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
  return inter / Math.max(1, Math.min(a.w * a.h, b.w * b.h));
}

function drawEdges(edge) {
  const image = ctx.getImageData(0, 0, edge.width, edge.height);
  const color = state.mode === 'inspect' ? [224, 82, 82] : state.mode === 'flow' ? [25, 185, 210] : [31, 117, 255];
  for (let i = 0; i < edge.mag.length; i++) {
    const m = edge.mag[i];
    if (m > 0) {
      const idx = i * 4;
      const alpha = Math.min(0.58, m / 430);
      image.data[idx] = clamp(image.data[idx] * (1 - alpha) + color[0] * alpha);
      image.data[idx + 1] = clamp(image.data[idx + 1] * (1 - alpha) + color[1] * alpha);
      image.data[idx + 2] = clamp(image.data[idx + 2] * (1 - alpha) + color[2] * alpha);
    }
  }
  ctx.putImageData(image, 0, 0);
}

function drawBoxes(boxes) {
  ctx.save();
  ctx.lineWidth = Math.max(2, els.canvas.width / 520);
  ctx.font = `${Math.max(12, Math.round(els.canvas.width / 82))}px Microsoft YaHei, sans-serif`;
  boxes.forEach((box, index) => {
    const label = state.mode === 'inspect' ? '病害候选' : state.mode === 'flow' ? '交通目标' : '车辆/行人';
    const color = state.mode === 'inspect' ? '#e05252' : index % 2 ? '#19b9d2' : '#1f75ff';
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    roundRect(ctx, box.x, box.y, box.w, box.h, 4);
    ctx.stroke();
    const text = `${label} ${(Math.min(0.96, box.score / 120)).toFixed(2)}`;
    const tw = ctx.measureText(text).width + 12;
    ctx.fillRect(box.x, Math.max(0, box.y - 24), tw, 22);
    ctx.fillStyle = '#ffffff';
    ctx.fillText(text, box.x + 6, Math.max(16, box.y - 7));
  });
  ctx.restore();
}

function drawTrajectory(boxes) {
  if (!boxes.length) return;
  ctx.save();
  ctx.lineWidth = Math.max(2, els.canvas.width / 640);
  boxes.slice(0, 5).forEach((box, idx) => {
    const cx = box.x + box.w / 2;
    const cy = box.y + box.h / 2;
    ctx.strokeStyle = idx % 2 ? 'rgba(25,185,210,0.86)' : 'rgba(31,117,255,0.92)';
    ctx.beginPath();
    ctx.moveTo(cx - box.w * 0.8, cy + box.h * 0.7);
    ctx.quadraticCurveTo(cx - box.w * 0.28, cy + box.h * 0.18, cx, cy);
    ctx.stroke();
    ctx.fillStyle = ctx.strokeStyle;
    ctx.beginPath();
    ctx.arc(cx, cy, 4, 0, Math.PI * 2);
    ctx.fill();
  });
  if (state.mode === 'vehicle') {
    ctx.fillStyle = boxes.length > 3 ? 'rgba(224,82,82,0.94)' : 'rgba(31,117,255,0.92)';
    ctx.fillRect(22, 22, 220, 34);
    ctx.fillStyle = '#fff';
    ctx.font = '18px Microsoft YaHei, sans-serif';
    ctx.fillText(boxes.length > 3 ? '前方碰撞风险升高' : '跟踪状态稳定', 34, 45);
  }
  ctx.restore();
}

function drawWatermark(confidence) {
  ctx.save();
  ctx.fillStyle = 'rgba(12, 22, 24, 0.64)';
  ctx.fillRect(els.canvas.width - 190, els.canvas.height - 40, 170, 26);
  ctx.fillStyle = '#ffffff';
  ctx.font = '13px Microsoft YaHei, sans-serif';
  ctx.fillText(`交安眼 · ${Math.round(confidence * 100)}%`, els.canvas.width - 178, els.canvas.height - 22);
  ctx.restore();
}

function renderMetrics() {
  if (!state.metrics) return;
  const { boxes, edgeRatio, confidence, elapsed } = state.metrics;
  const risk = riskText(confidence, boxes.length, edgeRatio);
  els.confidence.textContent = `${Math.round(confidence * 100)}%`;
  els.targetCount.textContent = boxes.length;
  els.edgeDensity.textContent = `${(edgeRatio * 100).toFixed(1)}%`;
  els.riskLevel.textContent = risk;
  els.processTime.textContent = `${elapsed}ms`;
  els.sceneSummary.textContent = summaryText(boxes.length, edgeRatio, confidence);
  els.eventList.innerHTML = eventsForMode(boxes.length, edgeRatio, confidence).map(item => `<li>${item}</li>`).join('');
}

function clearMetrics() {
  els.confidence.textContent = '--';
  els.targetCount.textContent = '--';
  els.edgeDensity.textContent = '--';
  els.riskLevel.textContent = '--';
  els.processTime.textContent = '--';
  els.sceneSummary.textContent = '导入图片后生成场景分析摘要';
  els.eventList.innerHTML = '<li>等待图片输入</li>';
}

function summaryText(count, edgeRatio, confidence) {
  if (state.mode === 'vehicle') return `检测到 ${count} 个候选交通目标，当前跟踪置信度 ${(confidence * 100).toFixed(0)}%，适合生成前向风险提示。`;
  if (state.mode === 'flow') return `路口画面候选目标 ${count} 个，边缘密度 ${(edgeRatio * 100).toFixed(1)}%，可用于车流量与排队态势估计。`;
  return `巡检图像边缘/暗纹密度 ${(edgeRatio * 100).toFixed(1)}%，已突出裂缝、坑槽等疑似病害区域。`;
}

function eventsForMode(count, edgeRatio, confidence) {
  if (state.mode === 'vehicle') {
    return [
      `目标跟踪框：${count} 个`,
      confidence > 0.72 ? '动态模板可更新：置信度达标' : '动态模板保持：置信度不足',
      count > 3 ? '预警事件：前向目标密集，请复核距离' : '预警事件：未触发高危告警'
    ];
  }
  if (state.mode === 'flow') {
    return [
      `交通目标候选：${count} 个`,
      `流量估计：${count > 8 ? '高' : count > 4 ? '中' : '低'}`,
      '导出结果可作为报表截图或后续标注素材'
    ];
  }
  return [
    `疑似病害区域：${count} 个`,
    `边缘密度：${(edgeRatio * 100).toFixed(1)}%`,
    edgeRatio > 0.12 ? '巡检建议：优先复核高亮区域' : '巡检建议：未发现高密度病害纹理'
  ];
}

function riskText(confidence, count, edgeRatio) {
  const score = confidence * 0.6 + Math.min(1, count / 12) * 0.25 + Math.min(1, edgeRatio * 4) * 0.15;
  if (score > 0.74) return '高';
  if (score > 0.52) return '中';
  return '低';
}

function estimateConfidence(edgeRatio, count) {
  const base = 0.48 + Math.min(0.28, edgeRatio * 1.8) + Math.min(0.2, count * 0.018);
  return Math.max(0.35, Math.min(0.94, base));
}

function renderView() {
  if (!state.original) return;
  if (state.view === 'source') {
    ctx.putImageData(state.original, 0, 0);
    return;
  }
  if (state.view === 'result' || !state.processed) {
    ctx.putImageData(state.processed || state.original, 0, 0);
    return;
  }
  ctx.putImageData(state.original, 0, 0);
  const splitX = Math.floor(els.canvas.width / 2);
  const result = state.processed;
  const half = ctx.createImageData(els.canvas.width - splitX, els.canvas.height);
  for (let y = 0; y < els.canvas.height; y++) {
    for (let x = splitX; x < els.canvas.width; x++) {
      const src = (y * els.canvas.width + x) * 4;
      const dst = (y * half.width + (x - splitX)) * 4;
      half.data[dst] = result.data[src];
      half.data[dst + 1] = result.data[src + 1];
      half.data[dst + 2] = result.data[src + 2];
      half.data[dst + 3] = 255;
    }
  }
  ctx.putImageData(half, splitX, 0);
  ctx.save();
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(splitX, 0);
  ctx.lineTo(splitX, els.canvas.height);
  ctx.stroke();
  ctx.fillStyle = 'rgba(22,32,35,0.72)';
  ctx.fillRect(18, 18, 72, 26);
  ctx.fillRect(splitX + 18, 18, 88, 26);
  ctx.fillStyle = '#fff';
  ctx.font = '13px Microsoft YaHei, sans-serif';
  ctx.fillText('原图', 38, 36);
  ctx.fillText('处理后', splitX + 36, 36);
  ctx.restore();
}

function exportImage() {
  if (!state.processed) return;
  ctx.putImageData(state.processed, 0, 0);
  els.canvas.toBlob(blob => {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${state.imageName || 'jiaoyanyan'}_processed.png`;
    link.click();
    URL.revokeObjectURL(link.href);
    renderView();
  }, 'image/png');
}

function roundRect(context, x, y, w, h, r) {
  context.beginPath();
  context.moveTo(x + r, y);
  context.arcTo(x + w, y, x + w, y + h, r);
  context.arcTo(x + w, y + h, x, y + h, r);
  context.arcTo(x, y + h, x, y, r);
  context.arcTo(x, y, x + w, y, r);
  context.closePath();
}

function clamp(value) {
  return Math.max(0, Math.min(255, Math.round(value)));
}

els.fileInput.addEventListener('change', event => loadImage(event.target.files[0]));
els.processBtn.addEventListener('click', processImage);
els.exportBtn.addEventListener('click', exportImage);
els.sensitivity.addEventListener('input', () => {
  els.sensValue.textContent = els.sensitivity.value;
  if (state.image) processImage();
});

els.dropzone.addEventListener('dragover', event => {
  event.preventDefault();
  els.dropzone.classList.add('dragging');
});
els.dropzone.addEventListener('dragleave', () => els.dropzone.classList.remove('dragging'));
els.dropzone.addEventListener('drop', event => {
  event.preventDefault();
  els.dropzone.classList.remove('dragging');
  loadImage(event.dataTransfer.files[0]);
});

document.querySelectorAll('[data-mode]').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('[data-mode]').forEach(item => item.classList.remove('active'));
    button.classList.add('active');
    state.mode = button.dataset.mode;
    if (state.image) processImage();
  });
});

document.querySelectorAll('[data-view]').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('[data-view]').forEach(item => item.classList.remove('active'));
    button.classList.add('active');
    state.view = button.dataset.view;
    renderView();
  });
});

moduleIds.forEach(id => {
  document.getElementById(id).addEventListener('change', () => {
    if (state.image) processImage();
  });
});

els.resetModules.addEventListener('click', () => {
  moduleIds.forEach(id => document.getElementById(id).checked = true);
  els.sensitivity.value = 62;
  els.sensValue.textContent = '62';
  if (state.image) processImage();
});
