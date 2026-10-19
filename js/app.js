/* ============================================================
   Coffee Bean Sorting System — Main Application Logic
   ============================================================ */

'use strict';

// ── State ────────────────────────────────────────────────────
const State = {
  running: false,
  paused: false,
  sessionStart: Date.now(),
  beansProcessed: 0,
  beansPerMin: 0,
  lastProcessTime: Date.now(),
  processingRate: [],

  sortCounts: { defect: 0, large: 0, medium: 0, small: 0, fine: 0 },
  sortCountsSession: { defect: 0, large: 0, medium: 0, small: 0, fine: 0 },

  qualityHistory: [],
  errorLog: [],
  errorCount: 0,
  alertBadgeCount: 0,

  lastBean: null,
  detectedBeans: [],
  captureCount: 0,

  systemHealth: {
    camera: 'online',
    feeder: 'online',
    ejector: 'online',
    compressor: 'online',
    conveyor: 'online',
    lighting: 'online'
  },

  chartData: {
    throughput: Array(20).fill(0),
    quality: Array(20).fill(0),
    errorRate: Array(20).fill(0),
  },

  settings: {
    autoSort: true,
    alertSound: false,
    sensitivity: 95,
    speedRPM: 180,
  }
};

// ── Constants ────────────────────────────────────────────────
const GRADES = {
  large:  { label: '8 mm (Large)',  color: '#3b82f6', icon: '🟤', minSize: 7.5, maxSize: 9.0 },
  medium: { label: '7 mm (Medium)', color: '#10b981', icon: '🟫', minSize: 6.5, maxSize: 7.5 },
  small:  { label: '6 mm (Small)',  color: '#f59e0b', icon: '🟡', minSize: 5.5, maxSize: 6.5 },
  fine:   { label: '5 mm (Fine)',   color: '#8b5cf6', icon: '⚪', minSize: 4.5, maxSize: 5.5 },
  defect: { label: 'Defective',     color: '#ef4444', icon: '❌', minSize: 0,   maxSize: 4.5 },
};

const QUALITY_MAP = {
  large:  { name: 'Premium',  color: '#10b981', grade: 'PREMIUM' },
  medium: { name: 'Grade A',  color: '#3b82f6', grade: 'GRADE A' },
  small:  { name: 'Grade B',  color: '#f59e0b', grade: 'GRADE B' },
  fine:   { name: 'Grade C',  color: '#8b5cf6', grade: 'GRADE C' },
  defect: { name: 'Defective',color: '#ef4444', grade: 'DEFECT'  },
};

const COLOR_PROFILES = [
  { name: 'Uniform Brown',  hex: '#6f4e37', score: 94, roast: 'Medium Roast' },
  { name: 'Dark Brown',     hex: '#3d2b1f', score: 88, roast: 'Dark Roast'   },
  { name: 'Light Brown',    hex: '#a0785a', score: 79, roast: 'Light Roast'  },
  { name: 'Uneven Roast',   hex: '#8B6544', score: 62, roast: 'Mixed'        },
  { name: 'Black/Burnt',    hex: '#1a0f08', score: 18, roast: 'Burnt'        },
  { name: 'Pale/Unroasted', hex: '#d4a76a', score: 32, roast: 'Raw'          },
];

const ERROR_TEMPLATES = [
  { type: 'warning', title: 'Low Air Pressure Detected', desc: 'Compressor pressure dropped to 0.31 MPa — below optimal 0.4 MPa. Check air supply line.', icon: '⚠️' },
  { type: 'critical', title: 'Missed Detection Event', desc: 'Bean passed vision zone without triggering detection. Possible occlusion or lighting issue.', icon: '🚨' },
  { type: 'warning', title: 'Sorting Bin Near Full', desc: 'Grade B (6 mm) bin at 82% capacity. Recommend emptying bin soon to prevent overflow.', icon: '📦' },
  { type: 'info', title: 'Camera Auto-Calibrated', desc: 'Vision system performed auto white-balance correction. Image quality optimized.', icon: 'ℹ️' },
  { type: 'critical', title: 'Ejector Valve Mis-fire', desc: 'Solenoid valve SV-03 response time exceeded 12ms threshold (actual: 14.2ms). Inspect valve.', icon: '🚨' },
  { type: 'warning', title: 'Feeder Jam Detected', desc: 'Singulator output rate dropped 40% below baseline. Possible bean jam in feed chute.', icon: '⚙️' },
  { type: 'info', title: 'Quality Threshold Updated', desc: 'System recalibrated defect detection sensitivity to 95.4% following reference sample scan.', icon: '🔧' },
  { type: 'warning', title: 'High Defect Rate', desc: 'Defective bean rate reached 6.2% in last 60s — above 5% alert threshold.', icon: '⚠️' },
  { type: 'info', title: 'LED Brightness Adjusted', desc: 'Lighting module auto-dimmed from 45,000 to 42,000 lux to compensate for ambient change.', icon: 'ℹ️' },
  { type: 'critical', title: 'Conveyor Speed Anomaly', desc: 'Belt speed deviation detected: ±12% from set point 180 RPM. Check motor drive.', icon: '🚨' },
];

// ── Utility ──────────────────────────────────────────────────
const rand = (min, max) => Math.random() * (max - min) + min;
const randInt = (min, max) => Math.floor(rand(min, max + 1));
const pick = arr => arr[Math.floor(Math.random() * arr.length)];
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const fmt = (n, d = 0) => Number(n).toFixed(d);
const fmtCount = n => n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);

function el(id) { return document.getElementById(id); }
function qs(sel, ctx = document) { return ctx.querySelector(sel); }
function qsa(sel, ctx = document) { return [...ctx.querySelectorAll(sel)]; }

function setText(id, val) { const e = el(id); if (e) e.textContent = val; }
function setWidth(id, pct) { const e = el(id); if (e) e.style.width = pct + '%'; }
function setHTML(id, html) { const e = el(id); if (e) e.innerHTML = html; }

// ── Toast Notifications ──────────────────────────────────────
function showToast(msg, type = 'info', duration = 3500) {
  const icons = { success: '✅', warning: '⚠️', danger: '🚨', info: 'ℹ️' };
  const container = el('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || 'ℹ️'}</span>
    <span class="toast-msg">${msg}</span>
    <span class="toast-close" onclick="this.parentElement.remove()">✕</span>
  `;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transform = 'translateX(20px)'; toast.style.transition = 'all 0.3s'; setTimeout(() => toast.remove(), 300); }, duration);
}

// ── Navigation ───────────────────────────────────────────────
function navigate(pageId) {
  qsa('.nav-item').forEach(n => n.classList.remove('active'));
  qsa('.page-content').forEach(p => p.classList.remove('active'));

  const navItem = qs(`[data-page="${pageId}"]`);
  const page = el(pageId);

  if (navItem) navItem.classList.add('active');
  if (page) page.classList.add('active');

  const titles = {
    'page-overview':    ['Overview', 'System Overview'],
    'page-detection':   ['Bean Detection', 'Feature 1 — Detection & Image Acquisition'],
    'page-assessment':  ['Quality Assessment', 'Feature 2 — AI-Powered Quality Assessment'],
    'page-sorting':     ['Sorting', 'Feature 3 — Automated Sorting & Recommendation'],
    'page-errors':      ['Error Monitoring', 'Feature 4 — Sorting Error Monitoring'],
    'page-dashboard':   ['Dashboard', 'Feature 5 — Quality Monitoring & Decision Support'],
  };

  const t = titles[pageId] || ['System', 'Coffee Bean Sorting System'];
  setText('header-title', t[0]);
  setText('header-breadcrumb', t[1]);
}

// ── Clock ────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  setText('clock', `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`);
}

// ── Uptime ───────────────────────────────────────────────────
function updateUptime() {
  const s = Math.floor((Date.now() - State.sessionStart) / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = n => String(n).padStart(2, '0');
  setText('uptime', `${pad(h)}:${pad(m)}:${pad(sec)}`);
}

// ── System Start / Stop ──────────────────────────────────────
function startSystem() {
  State.running = true;
  State.paused = false;
  State.sessionStart = Date.now();

  updateSystemStatus('online');
  setText('btn-start-label', 'Running...');
  el('btn-start')?.setAttribute('disabled', true);

  showToast('Sorting system started successfully', 'success');
  addError({ type: 'info', title: 'System Started', desc: 'All subsystems initialized. Vision, feeder, and ejector online.', icon: 'ℹ️' });

  // Start simulation loops
  startDetectionLoop();
  startChartUpdates();
}

function stopSystem() {
  State.running = false;
  updateSystemStatus('offline');
  setText('btn-start-label', 'Start System');
  el('btn-start')?.removeAttribute('disabled');
  showToast('System stopped', 'warning');
  addError({ type: 'info', title: 'System Stopped', desc: 'Sorting operation halted by operator. All actuators deactivated.', icon: 'ℹ️' });
}

function updateSystemStatus(status) {
  const dot = el('system-status-dot');
  const val = el('system-status-val');
  if (!dot || !val) return;
  dot.className = 'status-dot';
  if (status === 'online') {
    dot.classList.add('');
    val.textContent = 'RUNNING';
    val.className = 'status-value';
  } else if (status === 'offline') {
    dot.classList.add('offline');
    val.textContent = 'STOPPED';
    val.className = 'status-value';
    val.style.color = 'var(--text-muted)';
  }
}

// ── Bean Detection Simulation ─────────────────────────────────
function generateBean() {
  const types = ['large', 'large', 'large', 'medium', 'medium', 'medium', 'medium', 'small', 'small', 'fine', 'defect'];
  const type = pick(types);
  const grade = GRADES[type];
  const quality = QUALITY_MAP[type];
  const color = pick(COLOR_PROFILES);
  const size = rand(grade.minSize, grade.maxSize);
  const confidence = type === 'defect' ? rand(88, 99) : rand(91, 99.5);
  const weight = rand(size * 0.18, size * 0.28);
  const density = rand(0.78, 0.92);

  return {
    id: Date.now(),
    type, grade, quality, color, size: +fmt(size, 1),
    confidence: +fmt(confidence, 1),
    weight: +fmt(weight, 2),
    density: +fmt(density, 2),
    defects: type === 'defect' ? pick(['Black bean', 'Broken', 'Sour bean', 'Insect damage', 'Mold']) : 'None',
    timestamp: new Date().toLocaleTimeString(),
  };
}

let detectionInterval = null;

function startDetectionLoop() {
  if (detectionInterval) clearInterval(detectionInterval);
  const interval = 1800 / (State.settings.speedRPM / 100);
  detectionInterval = setInterval(() => {
    if (!State.running || State.paused) return;
    processBean(generateBean());
  }, interval);
}

function processBean(bean) {
  State.beansProcessed++;
  State.sortCounts[bean.type]++;
  State.sortCountsSession[bean.type]++;
  State.lastBean = bean;
  State.detectedBeans.unshift(bean);
  if (State.detectedBeans.length > 50) State.detectedBeans.pop();
  State.captureCount++;

  State.qualityHistory.push({ time: Date.now(), type: bean.type, confidence: bean.confidence });
  if (State.qualityHistory.length > 200) State.qualityHistory.shift();

  // Update throughput data
  State.chartData.throughput.push(State.beansProcessed);
  State.chartData.throughput.shift();

  const defectPct = (State.sortCounts.defect / State.beansProcessed) * 100;
  State.chartData.errorRate.push(+defectPct.toFixed(1));
  State.chartData.errorRate.shift();

  const goodPct = ((State.beansProcessed - State.sortCounts.defect) / State.beansProcessed) * 100;
  State.chartData.quality.push(+goodPct.toFixed(1));
  State.chartData.quality.shift();

  // Occasionally fire an error
  if (Math.random() < 0.04) {
    const tmpl = pick(ERROR_TEMPLATES);
    addError(tmpl);
  }

  // Update all relevant UI
  updateDetectionUI(bean);
  updateAssessmentUI(bean);
  updateSortingUI(bean);
  updateStatsUI();
  updateDashboardUI();
}

// ── Feature 1: Detection UI ───────────────────────────────────
function updateDetectionUI(bean) {
  // Update camera canvas with bean animation
  drawCameraFrame(bean);

  // Update detection stats
  setText('det-count', fmtCount(State.beansProcessed));
  setText('det-capture', fmtCount(State.captureCount));
  setText('det-fps', fmt(rand(58, 62), 0));
  setText('det-rate', fmt(State.beansProcessed / Math.max(1, (Date.now() - State.sessionStart) / 60000), 0));

  // Latest bean result
  const confClass = bean.confidence > 90 ? 'high' : bean.confidence > 75 ? 'medium' : 'low';
  setHTML('latest-bean-result', `
    <div class="bean-result-card">
      <div class="bean-preview">${bean.grade.icon}</div>
      <div class="bean-details">
        <div class="bean-name">${bean.quality.name} — ${bean.grade.label}</div>
        <div class="bean-props">
          <span class="bean-prop">⌀ ${bean.size} mm</span>
          <span class="bean-prop">⚖️ ${bean.weight} g</span>
          <span class="bean-prop">🎨 ${bean.color.name}</span>
          <span class="bean-prop">🔥 ${bean.color.roast}</span>
          ${bean.defects !== 'None' ? `<span class="bean-prop text-danger">⚠️ ${bean.defects}</span>` : ''}
        </div>
        <div class="confidence-bar">
          <div class="conf-label"><span>AI Confidence</span><span>${bean.confidence}%</span></div>
          <div class="conf-track"><div class="conf-fill ${confClass}" style="width:${bean.confidence}%"></div></div>
        </div>
      </div>
    </div>
  `);

  // Recent beans table
  updateRecentBeansTable();
}

let cameraCtx = null;
let cameraAnimFrame = 0;
let beanAnimBeans = [];

function initCameraCanvas() {
  const canvas = el('camera-canvas');
  if (!canvas) return;
  cameraCtx = canvas.getContext('2d');
  canvas.width = canvas.offsetWidth || 640;
  canvas.height = canvas.offsetHeight || 400;
  drawIdleFrame();
}

function drawIdleFrame() {
  if (!cameraCtx) return;
  const w = cameraCtx.canvas.width;
  const h = cameraCtx.canvas.height;
  cameraCtx.fillStyle = '#0a0e1a';
  cameraCtx.fillRect(0, 0, w, h);
  // Grid lines
  cameraCtx.strokeStyle = 'rgba(37,99,235,0.08)';
  cameraCtx.lineWidth = 1;
  for (let x = 0; x < w; x += 40) { cameraCtx.beginPath(); cameraCtx.moveTo(x, 0); cameraCtx.lineTo(x, h); cameraCtx.stroke(); }
  for (let y = 0; y < h; y += 40) { cameraCtx.beginPath(); cameraCtx.moveTo(0, y); cameraCtx.lineTo(w, y); cameraCtx.stroke(); }
  // Center text
  cameraCtx.fillStyle = 'rgba(100,116,139,0.5)';
  cameraCtx.font = '14px Inter, sans-serif';
  cameraCtx.textAlign = 'center';
  cameraCtx.fillText('Camera Feed — Press START to activate', w / 2, h / 2);
}

function drawCameraFrame(bean) {
  if (!cameraCtx) { initCameraCanvas(); }
  const canvas = cameraCtx.canvas;
  const w = canvas.width;
  const h = canvas.height;

  // Conveyor background
  cameraCtx.fillStyle = '#0d1520';
  cameraCtx.fillRect(0, 0, w, h);

  // Draw LED lighting effect
  const grad = cameraCtx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, 'rgba(200,220,255,0.04)');
  grad.addColorStop(0.5, 'rgba(200,220,255,0.08)');
  grad.addColorStop(1, 'rgba(200,220,255,0.02)');
  cameraCtx.fillStyle = grad;
  cameraCtx.fillRect(0, 0, w, h);

  // Grid
  cameraCtx.strokeStyle = 'rgba(37,99,235,0.1)';
  cameraCtx.lineWidth = 0.5;
  for (let x = 0; x < w; x += 50) { cameraCtx.beginPath(); cameraCtx.moveTo(x, 0); cameraCtx.lineTo(x, h); cameraCtx.stroke(); }
  for (let y = 0; y < h; y += 50) { cameraCtx.beginPath(); cameraCtx.moveTo(0, y); cameraCtx.lineTo(w, y); cameraCtx.stroke(); }

  // Scan line
  const scanY = ((Date.now() / 1500) % 1) * h;
  const scanGrad = cameraCtx.createLinearGradient(0, scanY - 20, 0, scanY + 20);
  scanGrad.addColorStop(0, 'transparent');
  scanGrad.addColorStop(0.5, 'rgba(37,99,235,0.35)');
  scanGrad.addColorStop(1, 'transparent');
  cameraCtx.fillStyle = scanGrad;
  cameraCtx.fillRect(0, scanY - 20, w, 40);

  // Add new bean to animation list
  beanAnimBeans.push({ bean, x: -30, y: h / 2, speed: rand(3, 6), opacity: 1 });

  // Draw all animating beans
  beanAnimBeans = beanAnimBeans.filter(b => b.x < w + 40 && b.opacity > 0);
  beanAnimBeans.forEach(b => {
    b.x += b.speed;
    const isCenter = b.x > w * 0.35 && b.x < w * 0.65;
    const r = Math.max(4, b.bean.size * 4);

    if (isCenter) {
      // Detection box
      cameraCtx.strokeStyle = b.bean.type === 'defect' ? '#ef4444' : '#10b981';
      cameraCtx.lineWidth = 1.5;
      cameraCtx.setLineDash([4, 3]);
      cameraCtx.strokeRect(b.x - r - 8, b.y - r - 8, (r + 8) * 2, (r + 8) * 2);
      cameraCtx.setLineDash([]);

      // Confidence label
      cameraCtx.fillStyle = b.bean.type === 'defect' ? 'rgba(239,68,68,0.8)' : 'rgba(16,185,129,0.8)';
      cameraCtx.fillRect(b.x - r - 8, b.y - r - 24, 90, 16);
      cameraCtx.fillStyle = 'white';
      cameraCtx.font = '9px JetBrains Mono, monospace';
      cameraCtx.textAlign = 'left';
      cameraCtx.fillText(`${b.bean.quality.grade} ${b.bean.confidence}%`, b.x - r - 5, b.y - r - 12);

      // Size label below
      cameraCtx.fillStyle = 'rgba(0,0,0,0.7)';
      cameraCtx.fillRect(b.x - 20, b.y + r + 8, 44, 14);
      cameraCtx.fillStyle = '#f59e0b';
      cameraCtx.font = '9px JetBrains Mono, monospace';
      cameraCtx.textAlign = 'center';
      cameraCtx.fillText(`⌀${b.bean.size}mm`, b.x + 2, b.y + r + 19);
    }

    // Bean circle
    const beanGrad = cameraCtx.createRadialGradient(b.x - r * 0.3, b.y - r * 0.3, 0, b.x, b.y, r);
    beanGrad.addColorStop(0, b.bean.type === 'defect' ? '#5a2020' : '#a0785a');
    beanGrad.addColorStop(1, b.bean.type === 'defect' ? '#1a0808' : '#3d2010');
    cameraCtx.beginPath();
    cameraCtx.arc(b.x, b.y + rand(-5, 5), r, 0, Math.PI * 2);
    cameraCtx.fillStyle = beanGrad;
    cameraCtx.fill();

    // Highlight
    cameraCtx.beginPath();
    cameraCtx.arc(b.x - r * 0.3, b.y - r * 0.25, r * 0.3, 0, Math.PI * 2);
    cameraCtx.fillStyle = 'rgba(255,255,255,0.12)';
    cameraCtx.fill();
  });

  // Frame corners
  const cornerColor = 'rgba(37,99,235,0.6)';
  const cs = 16;
  cameraCtx.strokeStyle = cornerColor;
  cameraCtx.lineWidth = 2;
  [[0, 0, cs, 0, 0, cs], [w, 0, w - cs, 0, w, cs], [0, h, cs, h, 0, h - cs], [w, h, w - cs, h, w, h - cs]].forEach(([x1,y1,x2,y2,x3,y3]) => {
    cameraCtx.beginPath(); cameraCtx.moveTo(x2, y2); cameraCtx.lineTo(x1, y1); cameraCtx.lineTo(x3, y3); cameraCtx.stroke();
  });
  cameraCtx.textAlign = 'left';

  // Update HUD
  setText('hud-count', `BEANS: ${State.beansProcessed}`);
}

function updateRecentBeansTable() {
  const tbody = el('recent-beans-tbody');
  if (!tbody) return;
  const rows = State.detectedBeans.slice(0, 8).map(b => `
    <tr>
      <td class="td-mono">${b.id % 10000}</td>
      <td>${b.grade.icon} ${b.quality.name}</td>
      <td><span class="font-mono" style="color:${b.grade.color}">${b.size} mm</span></td>
      <td style="color:${b.color.hex || '#a0785a'}">${b.color.name}</td>
      <td>${b.confidence}%</td>
      <td><span class="status-pill ${b.type === 'defect' ? 'danger' : 'success'}">${b.type === 'defect' ? 'Rejected' : 'Sorted'}</span></td>
      <td class="td-mono text-muted">${b.timestamp}</td>
    </tr>
  `).join('');
  tbody.innerHTML = rows || '<tr><td colspan="7" class="text-muted" style="text-align:center;padding:20px">No beans detected yet</td></tr>';
}

// ── Feature 2: Assessment UI ──────────────────────────────────
function updateAssessmentUI(bean) {
  // Grade badge
  const el_badge = el('quality-grade-badge');
  if (el_badge) {
    el_badge.textContent = bean.quality.grade;
    el_badge.className = `quality-grade-badge grade-${bean.type === 'defect' ? 'defect' : bean.type === 'large' ? 'premium' : bean.type === 'medium' ? 'grade-a' : bean.type === 'small' ? 'grade-b' : 'grade-c'}`;
  }

  // Ring value
  setText('ring-value', fmt(bean.confidence, 0) + '%');

  // Draw ring
  drawConfidenceRing(bean.confidence, bean.quality.color);

  // Attributes
  const colorScore = bean.color.score;
  const sizeScore = clamp((bean.size - 4) / 5 * 100, 0, 100);
  const defectScore = bean.type === 'defect' ? 15 : rand(85, 99);
  const uniformityScore = rand(78, 98);
  const moistureScore = rand(75, 95);

  setWidth('attr-color', colorScore);
  setWidth('attr-size', sizeScore);
  setWidth('attr-defect', defectScore);
  setWidth('attr-uniformity', uniformityScore);
  setWidth('attr-moisture', moistureScore);

  setText('attr-color-val', bean.color.name);
  setText('attr-size-val', `${bean.size} mm`);
  setText('attr-defect-val', bean.type === 'defect' ? bean.defects : 'Clean');
  setText('attr-uniformity-val', fmt(uniformityScore, 0) + '%');
  setText('attr-moisture-val', fmt(moistureScore, 0) + '%');

  // Color swatch
  const swatch = el('color-swatch');
  if (swatch) { swatch.style.background = bean.color.hex; swatch.title = bean.color.name; }

  // Recommendation
  const recMap = {
    large:  { action: '✅ Route to Premium Bin', note: 'Excellent quality. Suitable for specialty grade export.', cls: 'success' },
    medium: { action: '✅ Route to Grade A Bin', note: 'Good quality. Suitable for premium commercial blends.', cls: 'success' },
    small:  { action: '🟡 Route to Grade B Bin', note: 'Acceptable quality. Standard commercial grade.', cls: 'warning' },
    fine:   { action: '🟠 Route to Grade C Bin', note: 'Below standard. Industrial or blending use.', cls: 'warning' },
    defect: { action: '❌ Eject to Defect Bin',  note: `Defect detected: ${bean.defects}. Remove from production stream.`, cls: 'danger' },
  };
  const rec = recMap[bean.type];
  const recEl = el('ai-recommendation');
  if (recEl) {
    recEl.innerHTML = `
      <div class="card-badge ${rec.cls}" style="font-size:0.82rem; padding:6px 12px; display:inline-block; margin-bottom:8px">${rec.action}</div>
      <p style="font-size:0.75rem; color:var(--text-muted); line-height:1.5">${rec.note}</p>
    `;
  }

  // Assessment history
  updateAssessmentHistory();
}

function drawConfidenceRing(pct, color = '#10b981') {
  const canvas = el('ring-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const size = 120;
  canvas.width = size; canvas.height = size;
  const cx = size / 2, cy = size / 2, r = 50;

  ctx.clearRect(0, 0, size, size);

  // Track
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.lineWidth = 10;
  ctx.stroke();

  // Fill
  const angle = (pct / 100) * Math.PI * 2 - Math.PI / 2;
  ctx.beginPath();
  ctx.arc(cx, cy, r, -Math.PI / 2, angle);
  ctx.strokeStyle = color;
  ctx.lineWidth = 10;
  ctx.lineCap = 'round';
  ctx.shadowColor = color;
  ctx.shadowBlur = 12;
  ctx.stroke();
  ctx.shadowBlur = 0;
}

function updateAssessmentHistory() {
  const list = el('assessment-history');
  if (!list) return;
  const items = State.qualityHistory.slice(-8).reverse();
  list.innerHTML = items.map(q => {
    const g = QUALITY_MAP[q.type];
    return `
      <div style="display:flex; align-items:center; gap:10px; padding:7px 0; border-bottom:1px solid var(--border)">
        <div style="width:8px;height:8px;border-radius:50%;background:${g.color};flex-shrink:0"></div>
        <span style="flex:1;font-size:0.72rem;color:var(--text-secondary)">${g.name}</span>
        <span style="font-size:0.7rem;color:var(--text-muted);font-family:monospace">${q.confidence}%</span>
      </div>
    `;
  }).join('') || '<p class="text-muted text-xs" style="padding:10px 0">No assessment history</p>';
}

// ── Feature 3: Sorting UI ─────────────────────────────────────
function updateSortingUI(bean) {
  // Highlight active bin
  qsa('.sort-bin').forEach(b => b.classList.remove('active'));
  const activeBin = el(`bin-${bean.type}`);
  if (activeBin) {
    activeBin.classList.add('active');
    setTimeout(() => activeBin.classList.remove('active'), 600);
  }

  // Update counts
  Object.entries(State.sortCounts).forEach(([k, v]) => {
    setText(`bin-count-${k}`, v);
    const total = State.beansProcessed || 1;
    const pct = (v / total) * 100;
    const fill = el(`bin-fill-${k}`);
    if (fill) fill.style.width = pct + '%';
    setText(`bin-pct-${k}`, fmt(pct, 1) + '%');
  });

  // Animate conveyor bean
  addConveyorBean(bean);

  // Update sorting table
  updateSortingTable();

  // Ejector stats
  const totalEjected = State.sortCounts.defect;
  const ejectionRate = State.beansProcessed > 0 ? (totalEjected / State.beansProcessed * 100) : 0;
  setText('ejection-rate', fmt(ejectionRate, 1) + '%');
  setText('total-ejected', fmtCount(totalEjected));
  setText('valve-fires', fmtCount(totalEjected));
  const goodYield = 100 - ejectionRate;
  setText('good-yield', fmt(goodYield, 1) + '%');
  setWidth('yield-bar', goodYield);
}

function addConveyorBean(bean) {
  const track = el('conveyor-track');
  if (!track) return;
  const beanEl = document.createElement('div');
  beanEl.className = 'conveyor-bean';
  beanEl.textContent = bean.grade.icon;
  beanEl.style.top = `${randInt(20, 50)}%`;
  track.appendChild(beanEl);
  beanEl.addEventListener('animationend', () => beanEl.remove());
}

function updateSortingTable() {
  const tbody = el('sorting-table-tbody');
  if (!tbody) return;
  const total = State.beansProcessed || 1;
  const rows = Object.entries(State.sortCounts).map(([k, v]) => {
    const g = GRADES[k];
    const q = QUALITY_MAP[k];
    const pct = ((v / total) * 100);
    return `
      <tr>
        <td><span style="color:${g.color}; font-size:16px">${g.icon}</span></td>
        <td style="color:${g.color}; font-weight:600">${g.label}</td>
        <td><span style="color:${q.color}">${q.grade}</span></td>
        <td class="td-mono">${v}</td>
        <td>
          <div style="display:flex; align-items:center; gap:8px">
            <div class="progress-track" style="flex:1; margin:0"><div class="progress-fill" style="background:${g.color}; width:${pct}%"></div></div>
            <span class="td-mono" style="width:44px; text-align:right">${fmt(pct, 1)}%</span>
          </div>
        </td>
        <td><span class="status-pill ${k === 'defect' ? 'danger' : 'success'}">${k === 'defect' ? 'Ejected' : 'Collected'}</span></td>
      </tr>
    `;
  }).join('');
  tbody.innerHTML = rows;
}

// ── Feature 4: Error Monitoring ───────────────────────────────
function addError(tmpl) {
  const err = {
    ...tmpl,
    id: Date.now(),
    time: new Date().toLocaleTimeString(),
    resolved: false,
  };
  State.errorLog.unshift(err);
  if (State.errorLog.length > 50) State.errorLog.pop();
  State.errorCount++;
  if (tmpl.type === 'critical' || tmpl.type === 'warning') {
    State.alertBadgeCount++;
    const badge = el('error-badge');
    if (badge) badge.textContent = State.alertBadgeCount;
  }
  updateErrorUI();
  if (tmpl.type === 'critical') showToast(tmpl.title, 'danger');
}

function resolveAlert(id) {
  const err = State.errorLog.find(e => e.id === id);
  if (err) { err.resolved = true; updateErrorUI(); }
}

function updateErrorUI() {
  const list = el('alert-list');
  if (!list) return;
  const items = State.errorLog.slice(0, 15).map(e => `
    <div class="alert-item ${e.resolved ? 'resolved' : e.type}">
      <div class="alert-icon">${e.icon}</div>
      <div class="alert-body">
        <div class="alert-title">${e.title}</div>
        <div class="alert-desc">${e.desc}</div>
        <div class="alert-meta">
          <span>ID: ERR-${String(e.id).slice(-4)}</span>
          <span class="card-badge ${e.type === 'critical' ? 'danger' : e.type === 'warning' ? 'warning' : 'info'}" style="font-size:0.6rem; padding:1px 6px">${e.type.toUpperCase()}</span>
          ${e.resolved ? '<span style="color:var(--success)">✔ Resolved</span>' : ''}
        </div>
      </div>
      <div style="display:flex; flex-direction:column; align-items:flex-end; gap:6px; flex-shrink:0">
        <span class="alert-time">${e.time}</span>
        ${!e.resolved ? `<button class="alert-action" onclick="resolveAlert(${e.id})">Resolve</button>` : ''}
      </div>
    </div>
  `).join('') || '<p class="text-muted text-xs" style="padding:20px; text-align:center">No alerts recorded</p>';
  list.innerHTML = items;

  // Update error stats
  const criticals = State.errorLog.filter(e => e.type === 'critical' && !e.resolved).length;
  const warnings  = State.errorLog.filter(e => e.type === 'warning'  && !e.resolved).length;
  setText('active-criticals', criticals);
  setText('active-warnings', warnings);
  setText('total-errors', State.errorCount);

  // Update error rate
  const errRate = State.beansProcessed > 0 ? ((State.sortCounts.defect / State.beansProcessed) * 100) : 0;
  setText('error-rate-val', fmt(errRate, 1) + '%');

  updateErrorChart();
}

function updateErrorChart() {
  const chartEl = el('error-timeline-chart');
  if (!chartEl) return;
  const data = State.errorLog.slice(0, 20).reverse();
  chartEl.innerHTML = data.map(e => {
    const colors = { critical: '#ef4444', warning: '#f59e0b', info: '#06b6d4' };
    return `<div style="display:flex; align-items:center; gap:8px; padding:4px 0; font-size:0.68rem; border-bottom:1px solid var(--border)">
      <div style="width:8px;height:8px;border-radius:50%;background:${colors[e.type]};flex-shrink:0"></div>
      <span style="flex:1;color:var(--text-secondary)">${e.title}</span>
      <span style="color:var(--text-muted);font-family:monospace">${e.time}</span>
    </div>`;
  }).join('') || '<p class="text-muted text-xs" style="text-align:center;padding:20px">Monitoring active — no events</p>';
}

// ── Feature 5: Dashboard UI ───────────────────────────────────
function updateDashboardUI() {
  const total = State.beansProcessed || 1;
  const defectPct = (State.sortCounts.defect / total) * 100;
  const goodPct   = 100 - defectPct;
  const elapsed   = (Date.now() - State.sessionStart) / 60000;
  const bpm = elapsed > 0 ? (total / elapsed) : 0;

  // Hero stats
  setText('dash-total',   fmtCount(total));
  setText('dash-good',    fmt(goodPct, 1) + '%');
  setText('dash-rate',    fmt(bpm, 0));
  setText('dash-defect',  fmt(defectPct, 1) + '%');

  // Grade distribution bars
  Object.entries(State.sortCounts).forEach(([k, v]) => {
    const pct = (v / total) * 100;
    const fill = el(`dash-grade-${k}`);
    const pctEl = el(`dash-pct-${k}`);
    const cntEl = el(`dash-cnt-${k}`);
    if (fill) fill.style.width = pct + '%';
    if (pctEl) pctEl.textContent = fmt(pct, 1) + '%';
    if (cntEl) cntEl.textContent = v;
  });

  // Draw main chart
  drawMainChart();
  drawDonutChart();

  // Performance metrics
  setText('perf-accuracy', fmt(rand(94, 99), 1) + '%');
  setText('perf-throughput', fmt(bpm, 0) + ' b/min');
  setText('perf-uptime', (() => { const s = Math.floor((Date.now() - State.sessionStart) / 1000); return `${Math.floor(s/3600)}h ${Math.floor((s%3600)/60)}m`; })());
  setText('perf-yield', fmt(goodPct, 1) + '%');
  setText('perf-processed', fmtCount(total));
  setText('perf-defects', fmtCount(State.sortCounts.defect));

  // System health
  updateHealthPanel();
}

let mainChartCtx = null;
let donutCtx = null;

function drawMainChart() {
  const canvas = el('main-throughput-chart');
  if (!canvas) return;
  if (!mainChartCtx) {
    canvas.width = canvas.offsetWidth || 600;
    canvas.height = 160;
    mainChartCtx = canvas.getContext('2d');
  }
  const ctx = mainChartCtx;
  const w = canvas.width, h = canvas.height;

  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = 'transparent';
  ctx.fillRect(0, 0, w, h);

  const data = State.chartData.quality;
  const maxVal = 100;
  const step = w / (data.length - 1);

  // Grid
  ctx.strokeStyle = 'rgba(255,255,255,0.05)';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = (i / 4) * h;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  }

  // Quality fill
  ctx.beginPath();
  ctx.moveTo(0, h);
  data.forEach((v, i) => ctx.lineTo(i * step, h - (v / maxVal) * (h - 10)));
  ctx.lineTo(w, h);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, 'rgba(16,185,129,0.25)');
  grad.addColorStop(1, 'rgba(16,185,129,0.02)');
  ctx.fillStyle = grad;
  ctx.fill();

  // Quality line
  ctx.beginPath();
  data.forEach((v, i) => {
    const x = i * step;
    const y = h - (v / maxVal) * (h - 10);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = '#10b981';
  ctx.lineWidth = 2;
  ctx.stroke();

  // Error rate line (red)
  const errData = State.chartData.errorRate;
  ctx.beginPath();
  errData.forEach((v, i) => {
    const x = i * step;
    const y = h - (v / maxVal) * (h - 10);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = 'rgba(239,68,68,0.7)';
  ctx.lineWidth = 1.5;
  ctx.setLineDash([4, 3]);
  ctx.stroke();
  ctx.setLineDash([]);

  // Labels
  ctx.fillStyle = 'rgba(100,116,139,0.8)';
  ctx.font = '9px Inter, sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText('100%', 4, 12);
  ctx.fillText('50%', 4, h / 2);
  ctx.fillText('0%', 4, h - 4);
}

function drawDonutChart() {
  const canvas = el('donut-chart');
  if (!canvas) return;
  if (!donutCtx) {
    canvas.width = 160; canvas.height = 160;
    donutCtx = canvas.getContext('2d');
  }
  const ctx = donutCtx;
  const total = State.beansProcessed || 1;
  const cx = 80, cy = 80, r = 62, innerR = 44;

  ctx.clearRect(0, 0, 160, 160);

  const segments = [
    { key: 'large',  color: '#3b82f6' },
    { key: 'medium', color: '#10b981' },
    { key: 'small',  color: '#f59e0b' },
    { key: 'fine',   color: '#8b5cf6' },
    { key: 'defect', color: '#ef4444' },
  ];

  let startAngle = -Math.PI / 2;
  segments.forEach(s => {
    const v = State.sortCounts[s.key];
    if (!v) return;
    const sweep = (v / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.arc(cx, cy, r, startAngle, startAngle + sweep);
    ctx.arc(cx, cy, innerR, startAngle + sweep, startAngle, true);
    ctx.closePath();
    ctx.fillStyle = s.color;
    ctx.fill();
    startAngle += sweep;
  });

  // Center text
  const goodPct = total > 0 ? (((total - State.sortCounts.defect) / total) * 100) : 0;
  ctx.fillStyle = '#f1f5f9';
  ctx.font = 'bold 18px JetBrains Mono, monospace';
  ctx.textAlign = 'center';
  ctx.fillText(fmt(goodPct, 0) + '%', cx, cy + 6);
  ctx.fillStyle = '#64748b';
  ctx.font = '9px Inter, sans-serif';
  ctx.fillText('Good Yield', cx, cy + 20);
}

function updateHealthPanel() {
  const components = [
    { id: 'health-camera',     label: 'Industrial Camera',  icon: '📷', val: `${fmt(rand(58,62),0)} fps`,     status: 'online' },
    { id: 'health-lighting',   label: 'LED Lighting',       icon: '💡', val: `${fmt(rand(43,50),0)} klux`,    status: 'online' },
    { id: 'health-feeder',     label: 'Vibratory Feeder',   icon: '⚙️', val: `${fmt(rand(175,185),0)} RPM`,   status: 'online' },
    { id: 'health-conveyor',   label: 'Conveyor Belt',      icon: '🔄', val: `${fmt(rand(0.9,1.1),1)} m/s`,   status: 'online' },
    { id: 'health-compressor', label: 'Air Compressor',     icon: '💨', val: `${fmt(rand(0.55,0.75),2)} MPa`, status: State.running ? 'online' : 'offline' },
    { id: 'health-ejector',    label: 'Solenoid Valves',    icon: '🔧', val: `${fmt(rand(8,11),0)} ms resp`,  status: 'online' },
    { id: 'health-processing', label: 'Image Processor',    icon: '🖥️', val: `${fmt(rand(28,55),0)}% CPU`,    status: 'online' },
    { id: 'health-power',      label: 'Power Supply',       icon: '⚡', val: `${fmt(rand(210,230),0)} V`,     status: 'online' },
  ];

  const container = el('health-panel');
  if (!container) return;
  container.innerHTML = components.map(c => `
    <div class="health-item">
      <span class="health-icon">${c.icon}</span>
      <div class="health-info">
        <div class="health-name">${c.label}</div>
        <div class="health-val" style="color:${c.status === 'online' ? 'var(--success)' : 'var(--text-muted)'}">${c.val}</div>
      </div>
      <div class="status-dot ${c.status === 'online' ? '' : 'offline'}" style="flex-shrink:0"></div>
    </div>
  `).join('');
}

// ── Stats UI ──────────────────────────────────────────────────
function updateStatsUI() {
  const total = State.beansProcessed;
  const elapsed = (Date.now() - State.sessionStart) / 60000;
  const bpm = elapsed > 0 ? (total / elapsed) : 0;
  const defectPct = total > 0 ? (State.sortCounts.defect / total * 100) : 0;
  const goodPct = 100 - defectPct;

  // Sidebar info
  setText('sidebar-processed', fmtCount(total));
  setText('sidebar-rate', fmt(bpm, 0) + '/min');
  setText('sidebar-yield', fmt(goodPct, 1) + '%');

  // Header stats (if shown)
  setText('hdr-processed', fmtCount(total));
}

// ── Chart Update Timer ────────────────────────────────────────
function startChartUpdates() {
  setInterval(() => {
    if (!State.running) return;
    drawMainChart();
    drawDonutChart();
  }, 2000);
}

// ── Settings ──────────────────────────────────────────────────
function initSettings() {
  const toggle = el('toggle-autosort');
  if (toggle) {
    toggle.classList.toggle('on', State.settings.autoSort);
    toggle.addEventListener('click', () => {
      State.settings.autoSort = !State.settings.autoSort;
      toggle.classList.toggle('on', State.settings.autoSort);
      showToast(`Auto-sort ${State.settings.autoSort ? 'enabled' : 'disabled'}`, 'info');
    });
  }

  const speedSlider = el('speed-slider');
  if (speedSlider) {
    speedSlider.value = State.settings.speedRPM;
    speedSlider.addEventListener('input', () => {
      State.settings.speedRPM = +speedSlider.value;
      setText('speed-val', speedSlider.value + ' RPM');
      if (State.running) startDetectionLoop();
    });
  }

  const sensSlider = el('sensitivity-slider');
  if (sensSlider) {
    sensSlider.value = State.settings.sensitivity;
    sensSlider.addEventListener('input', () => {
      State.settings.sensitivity = +sensSlider.value;
      setText('sensitivity-val', sensSlider.value + '%');
    });
  }
}

// ── Export CSV ────────────────────────────────────────────────
function exportCSV() {
  const headers = ['ID', 'Type', 'Grade', 'Size(mm)', 'Weight(g)', 'Color', 'Confidence', 'Defects', 'Timestamp'];
  const rows = State.detectedBeans.map(b =>
    [b.id, b.quality.name, b.quality.grade, b.size, b.weight, b.color.name, b.confidence + '%', b.defects, b.timestamp].join(',')
  );
  const csv = [headers.join(','), ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `coffee_sort_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  showToast('Report exported as CSV', 'success');
}

function resetSession() {
  if (!confirm('Reset all session data? This cannot be undone.')) return;
  State.beansProcessed = 0;
  State.sortCounts = { defect: 0, large: 0, medium: 0, small: 0, fine: 0 };
  State.errorLog = [];
  State.errorCount = 0;
  State.alertBadgeCount = 0;
  State.qualityHistory = [];
  State.detectedBeans = [];
  State.chartData = { throughput: Array(20).fill(0), quality: Array(20).fill(0), errorRate: Array(20).fill(0) };
  State.sessionStart = Date.now();
  beanAnimBeans = [];
  const badge = el('error-badge');
  if (badge) badge.textContent = '0';
  updateStatsUI();
  updateErrorUI();
  updateDashboardUI();
  updateRecentBeansTable();
  updateSortingTable();
  showToast('Session data reset', 'info');
}

// ── Init ──────────────────────────────────────────────────────
function init() {
  // Clock & uptime
  setInterval(updateClock, 1000);
  setInterval(updateUptime, 1000);
  updateClock();

  // Nav listeners
  qsa('.nav-item[data-page]').forEach(item => {
    item.addEventListener('click', () => navigate(item.dataset.page));
  });

  // Start button
  const btnStart = el('btn-start');
  if (btnStart) btnStart.addEventListener('click', startSystem);

  const btnStop = el('btn-stop');
  if (btnStop) btnStop.addEventListener('click', stopSystem);

  const btnExport = el('btn-export');
  if (btnExport) btnExport.addEventListener('click', exportCSV);

  const btnReset = el('btn-reset');
  if (btnReset) btnReset.addEventListener('click', resetSession);

  // Camera init
  initCameraCanvas();
  initSettings();

  // Default page
  navigate('page-overview');

  // Initial draws
  drawDonutChart();
  drawMainChart();
  updateErrorUI();
  updateDashboardUI();
  updateSortingTable();
  updateRecentBeansTable();

  // Sidebar live values
  setInterval(() => {
    if (!State.running) return;
    setText('sidebar-pressure', fmt(rand(0.45, 0.72), 2) + ' MPa');
    setText('sidebar-temp', fmt(rand(22, 28), 1) + '°C');
  }, 3000);

  setText('sidebar-pressure', '0.00 MPa');
  setText('sidebar-temp', '—');

  showToast('System ready. Press START to begin sorting.', 'info', 4000);
}

document.addEventListener('DOMContentLoaded', init);
