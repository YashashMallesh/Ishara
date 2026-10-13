// Swipe — Minimalist Touchless Presentation Controller

let currentSlideIndex = 1;
let slides = [];
let deckTitle = "Minimalist Vision Controller";
let isBlackout = false;
let isArmed = true;
let isPyAutoGUI = true;
let currentMode = 'hand';
let selectedTheme = 'dark';
let isPiPCollapsed = false;
let pdfDocCache = {};

// Setup PDF.js worker
if (window.pdfjsLib) {
  pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
}

// ============================================================
// Slide Deck Rendering & Navigation
// ============================================================
async function fetchDeck() {
  try {
    const res = await fetch('/api/slides');
    const data = await res.json();
    slides = data.slides || [];
    deckTitle = data.title || "Minimalist Vision Controller";
    document.getElementById('nav-deck-title').textContent = deckTitle;
    renderThumbnails();
    renderCurrentSlide();
  } catch (e) {
    console.error("Error fetching slides:", e);
  }
}

function renderThumbnails() {
  const strip = document.getElementById('slide-thumbnail-strip');
  strip.innerHTML = '';

  slides.forEach((slide, idx) => {
    const slideNum = idx + 1;
    const pill = document.createElement('button');
    pill.className = `thumb-pill px-2.5 py-1 rounded-md text-[11px] font-mono border transition-all ${
      slideNum === currentSlideIndex 
        ? 'active-thumb' 
        : 'border-neutral-800 bg-neutral-900 text-neutral-400 hover:text-white hover:border-neutral-700'
    }`;
    pill.textContent = String(slideNum).padStart(2, '0');
    pill.title = slide.title || `Slide ${slideNum}`;
    pill.onclick = () => goToSlide(slideNum);
    strip.appendChild(pill);
  });

  const total = slides.length || 1;
  document.getElementById('slide-counter-top').textContent = `${currentSlideIndex} / ${total}`;
  document.getElementById('slide-counter-bottom').textContent = `${currentSlideIndex} / ${total}`;
}

async function renderCurrentSlide() {
  if (!slides || slides.length === 0) return;
  const slide = slides[currentSlideIndex - 1];
  if (!slide) return;

  const stage = document.getElementById('presentation-stage');
  const viewport = document.getElementById('slide-viewport');
  const body = document.getElementById('slide-body');
  const canvasContainer = document.getElementById('canvas-container');
  const pdfCanvas = document.getElementById('pdf-canvas');
  const imgSlide = document.getElementById('image-slide-img');

  // Trigger smooth transition animation
  viewport.classList.remove('slide-transition-enter');
  void viewport.offsetWidth; // Force reflow
  viewport.classList.add('slide-transition-enter');

  // Reset themes
  stage.className = 'relative w-full aspect-[16/9] max-h-[75vh] rounded-2xl border border-neutral-800/80 shadow-2xl flex flex-col overflow-hidden select-none transition-all duration-300';
  const theme = slide.theme || 'dark';
  stage.classList.add(`theme-${theme}`);

  // 1. Custom Typography Slide
  if (slide.type === 'custom') {
    canvasContainer.classList.add('hidden');
    body.classList.remove('hidden');

    document.getElementById('slide-tag').textContent = slide.tag || `SLIDE ${String(currentSlideIndex).padStart(2, '0')}`;
    document.getElementById('slide-title').textContent = slide.title || 'Untitled Slide';
    
    const subtitleEl = document.getElementById('slide-subtitle');
    if (slide.subtitle) {
      subtitleEl.textContent = slide.subtitle;
      subtitleEl.classList.remove('hidden');
    } else {
      subtitleEl.classList.add('hidden');
    }

    const listEl = document.getElementById('slide-content-list');
    listEl.innerHTML = '';
    if (Array.isArray(slide.content) && slide.content.length > 0) {
      slide.content.forEach((line) => {
        const item = document.createElement('div');
        item.className = "flex items-start space-x-3";
        item.innerHTML = `
          <span class="h-1.5 w-1.5 rounded-full bg-neutral-400 mt-2 shrink-0"></span>
          <span class="leading-relaxed">${escapeHtml(line)}</span>
        `;
        listEl.appendChild(item);
      });
    }

  // 2. Image Slide
  } else if (slide.type === 'image') {
    body.classList.add('hidden');
    canvasContainer.classList.remove('hidden');
    pdfCanvas.classList.add('hidden');
    imgSlide.classList.remove('hidden');
    imgSlide.src = slide.src;
    document.getElementById('slide-tag').textContent = slide.tag || 'Image Slide';

  // 3. PDF Vector Slide
  } else if (slide.type === 'pdf') {
    body.classList.add('hidden');
    canvasContainer.classList.remove('hidden');
    imgSlide.classList.add('hidden');
    pdfCanvas.classList.remove('hidden');
    document.getElementById('slide-tag').textContent = slide.tag || `Page ${slide.page}`;
    renderPdfPage(slide.pdf_url, slide.page, pdfCanvas);
  }

  renderThumbnails();
}

async function renderPdfPage(url, pageNum, canvas) {
  try {
    let pdf = pdfDocCache[url];
    if (!pdf) {
      pdf = await pdfjsLib.getDocument(url).promise;
      pdfDocCache[url] = pdf;
    }
    const page = await pdf.getPage(pageNum);
    const container = document.getElementById('canvas-container');
    const scale = (container.clientHeight / page.getViewport({ scale: 1 }).height) * (window.devicePixelRatio || 1.5);
    const viewport = page.getViewport({ scale });

    canvas.height = viewport.height;
    canvas.width = viewport.width;

    const renderContext = {
      canvasContext: canvas.getContext('2d'),
      viewport: viewport
    };
    await page.render(renderContext).promise;
  } catch (err) {
    console.error("PDF render error:", err);
  }
}

let lastSlideChangeTime = 0;
const SLIDE_DEBOUNCE_MS = 900; // 900ms minimum between slide triggers (prevents rapid double-skipping)

function nextSlide() {
  const now = Date.now();
  if (now - lastSlideChangeTime < SLIDE_DEBOUNCE_MS) return;
  if (currentSlideIndex < slides.length) {
    lastSlideChangeTime = now;
    currentSlideIndex++;
    renderCurrentSlide();
    playClickAudio();
  }
}

function prevSlide() {
  const now = Date.now();
  if (now - lastSlideChangeTime < SLIDE_DEBOUNCE_MS) return;
  if (currentSlideIndex > 1) {
    lastSlideChangeTime = now;
    currentSlideIndex--;
    renderCurrentSlide();
    playClickAudio();
  }
}

function goToSlide(n) {
  const now = Date.now();
  if (now - lastSlideChangeTime < SLIDE_DEBOUNCE_MS && Math.abs(n - currentSlideIndex) <= 1) return;
  if (n >= 1 && n <= slides.length) {
    lastSlideChangeTime = now;
    currentSlideIndex = n;
    renderCurrentSlide();
    playClickAudio();
  }
}

function toggleBlackout() {
  isBlackout = !isBlackout;
  const overlay = document.getElementById('blackout-overlay');
  if (isBlackout) {
    overlay.classList.remove('hidden');
  } else {
    overlay.classList.add('hidden');
  }
}

function toggleFullscreen() {
  const stage = document.getElementById('presentation-stage');
  if (!document.fullscreenElement) {
    stage.requestFullscreen().catch(err => alert("Fullscreen error: " + err.message));
  } else {
    document.exitFullscreen();
  }
}

// Minimal audio feedback
function playClickAudio() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(600, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(800, ctx.currentTime + 0.04);
    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.04);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.04);
  } catch (e) {}
}

// ============================================================
// File Upload & Presentation Insertion
// ============================================================
function openInsertModal() {
  document.getElementById('insert-modal').classList.remove('hidden');
}

function closeInsertModal() {
  document.getElementById('insert-modal').classList.add('hidden');
  document.getElementById('upload-status').classList.add('hidden');
}

async function handleFileUpload(fileList) {
  if (!fileList || fileList.length === 0) return;
  const file = fileList[0];
  const formData = new FormData();
  formData.append('file', file);

  const statusBox = document.getElementById('upload-status');
  const statusText = document.getElementById('upload-status-text');
  statusBox.classList.remove('hidden');
  statusText.textContent = `Uploading & parsing ${file.name}...`;

  try {
    const res = await fetch('/api/upload', {
      method: 'POST',
      body: formData
    });
    const result = await res.json();

    if (result.success) {
      statusText.textContent = `Successfully loaded ${result.count || 1} slides!`;
      setTimeout(() => {
        closeInsertModal();
        fetchDeck();
        currentSlideIndex = 1;
      }, 600);
    } else {
      alert("Error: " + (result.error || "Failed to process presentation file."));
      statusBox.classList.add('hidden');
    }
  } catch (err) {
    alert("Upload failed: " + err.message);
    statusBox.classList.add('hidden');
  }
}

// Drag & drop dropzone support
const dropZone = document.querySelector('label[for="file-upload-input"]');
if (dropZone) {
  ['dragenter', 'dragover'].forEach(name => {
    dropZone.addEventListener(name, (e) => {
      e.preventDefault();
      dropZone.classList.add('border-white');
    });
  });
  ['dragleave', 'drop'].forEach(name => {
    dropZone.addEventListener(name, (e) => {
      e.preventDefault();
      dropZone.classList.remove('border-white');
    });
  });
  dropZone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    if (dt && dt.files) {
      handleFileUpload(dt.files);
    }
  });
}

// ============================================================
// Custom Slide Creator Modal
// ============================================================
function openCustomSlideModal() {
  document.getElementById('custom-slide-modal').classList.remove('hidden');
}

function closeCustomSlideModal() {
  document.getElementById('custom-slide-modal').classList.add('hidden');
}

function selectTheme(theme) {
  selectedTheme = theme;
  document.querySelectorAll('.theme-opt').forEach(btn => {
    if (btn.getAttribute('data-theme') === theme) {
      btn.classList.add('border-white');
    } else {
      btn.classList.remove('border-white');
    }
  });
}

async function saveCustomSlide() {
  const tag = document.getElementById('cs-tag').value.trim() || 'Custom Slide';
  const title = document.getElementById('cs-title').value.trim();
  const subtitle = document.getElementById('cs-subtitle').value.trim();
  const rawBullets = document.getElementById('cs-bullets').value.trim();

  if (!title) {
    alert("Please enter a slide title.");
    return;
  }

  const content = rawBullets ? rawBullets.split('\n').map(l => l.replace(/^[•\-\*]\s*/, '').trim()).filter(Boolean) : [];

  const newSlide = {
    id: slides.length + 1,
    type: "custom",
    tag,
    title,
    subtitle,
    content,
    theme: selectedTheme
  };

  slides.push(newSlide);

  // Sync with backend
  await fetch('/api/slides', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slides })
  });

  closeCustomSlideModal();
  currentSlideIndex = slides.length;
  renderThumbnails();
  renderCurrentSlide();

  // Reset form
  document.getElementById('cs-tag').value = '';
  document.getElementById('cs-title').value = '';
  document.getElementById('cs-subtitle').value = '';
  document.getElementById('cs-bullets').value = '';
}

async function resetDefaultDeck() {
  if (confirm("Reset presentation to default slides?")) {
    await fetch('/api/slides', { method: 'DELETE' });
    toggleSettingsModal();
    fetchDeck();
  }
}

// ============================================================
// Vision Mode, Armed State & PiP
// ============================================================
async function setMode(mode) {
  try {
    const res = await fetch('/api/toggle_mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode })
    });
    const data = await res.json();
    applyModeUI(data.mode);
  } catch (e) {
    console.error(e);
  }
}

function applyModeUI(mode) {
  currentMode = mode;
  const handBtn = document.getElementById('mode-hand-btn');
  const eyeBtn = document.getElementById('mode-eye-btn');

  if (mode === 'hand') {
    handBtn.className = "px-3 py-1 rounded-md transition-all text-neutral-200 bg-neutral-800 shadow-sm flex items-center space-x-1.5";
    eyeBtn.className = "px-3 py-1 rounded-md transition-all text-neutral-400 hover:text-neutral-200 flex items-center space-x-1.5";
  } else {
    eyeBtn.className = "px-3 py-1 rounded-md transition-all text-neutral-200 bg-neutral-800 shadow-sm flex items-center space-x-1.5";
    handBtn.className = "px-3 py-1 rounded-md transition-all text-neutral-400 hover:text-neutral-200 flex items-center space-x-1.5";
  }
}

async function toggleArmed() {
  try {
    const res = await fetch('/api/toggle_armed', { method: 'POST' });
    const data = await res.json();
    applyArmedUI(data.armed);
  } catch (e) {
    console.error(e);
  }
}

function applyArmedUI(armed) {
  isArmed = armed;
  const dot = document.getElementById('armed-dot');
  const text = document.getElementById('armed-text');
  if (armed) {
    dot.className = "h-2 w-2 rounded-full bg-emerald-400";
    text.textContent = "Armed";
    text.className = "text-neutral-300";
  } else {
    dot.className = "h-2 w-2 rounded-full bg-rose-400";
    text.textContent = "Locked";
    text.className = "text-rose-400";
  }
}

async function togglePyAutoGUI() {
  try {
    const res = await fetch('/api/toggle_pyautogui', { method: 'POST' });
    const data = await res.json();
    isPyAutoGUI = data.enable_pyautogui;
    const txt = document.getElementById('pyautogui-text');
    txt.textContent = isPyAutoGUI ? "OS Keys: ON" : "OS Keys: OFF";
  } catch (e) {
    console.error(e);
  }
}

function togglePiPCollapse() {
  isPiPCollapsed = !isPiPCollapsed;
  const pip = document.getElementById('pip-camera');
  const icon = document.getElementById('pip-toggle-icon');
  if (isPiPCollapsed) {
    pip.classList.add('pip-collapsed');
    icon.className = "fa-solid fa-chevron-up text-[10px]";
  } else {
    pip.classList.remove('pip-collapsed');
    icon.className = "fa-solid fa-chevron-down text-[10px]";
  }
}

function toggleSettingsModal() {
  const modal = document.getElementById('settings-modal');
  modal.classList.toggle('hidden');
  if (!modal.classList.contains('hidden')) {
    loadVisionSettings();
  }
}

async function loadVisionSettings() {
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    if (data.swipe_cooldown) {
      document.getElementById('cfg-swipe-cooldown').value = data.swipe_cooldown;
      document.getElementById('cfg-swipe-cooldown-val').textContent = data.swipe_cooldown + 's';
    }
    if (data.swipe_threshold) {
      document.getElementById('cfg-swipe-thresh').value = data.swipe_threshold;
      document.getElementById('cfg-swipe-thresh-val').textContent = data.swipe_threshold;
    }
    if (data.hand_cooldown) {
      document.getElementById('cfg-cooldown').value = data.hand_cooldown;
      document.getElementById('cfg-cooldown-val').textContent = data.hand_cooldown + 's';
    }
    if (data.lock_hold) {
      document.getElementById('cfg-lock-hold').value = data.lock_hold;
      document.getElementById('cfg-lock-hold-val').textContent = data.lock_hold + 's';
    }
    if (data.eye_hold_seconds) {
      document.getElementById('cfg-eye-hold').value = data.eye_hold_seconds;
      document.getElementById('cfg-eye-hold-val').textContent = data.eye_hold_seconds + 's';
    }
  } catch (e) {
    console.error("Error loading settings:", e);
  }
}

async function saveVisionSettings() {
  const swipe_cooldown = parseFloat(document.getElementById('cfg-swipe-cooldown').value);
  const swipe_threshold = parseFloat(document.getElementById('cfg-swipe-thresh').value);
  const lock_hold = parseFloat(document.getElementById('cfg-lock-hold').value);
  const hand_cooldown = parseFloat(document.getElementById('cfg-cooldown').value);
  const eye_hold_seconds = parseFloat(document.getElementById('cfg-eye-hold').value);

  await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ swipe_cooldown, swipe_threshold, lock_hold, hand_cooldown, eye_hold_seconds })
  });
  toggleSettingsModal();
}

// ============================================================
// Real-time Telemetry & Events
// ============================================================
async function pollTelemetry() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();

    if (data.mode !== currentMode) applyModeUI(data.mode);
    if (data.armed !== isArmed) applyArmedUI(data.armed);

    document.getElementById('pip-fps').textContent = `${Math.round(data.fps)} fps`;

    const gesture = data.gesture || 'Ready';
    document.getElementById('pip-gesture-name').textContent = gesture;

    const prog = Math.round((data.progress || 0) * 100);
    document.getElementById('pip-progress-bar').style.width = `${prog}%`;
    document.getElementById('pip-action-badge').textContent = `${data.held_time || 0}s`;

  } catch (e) {}
}

function setupEventSource() {
  const evtSource = new EventSource('/api/events');

  evtSource.addEventListener('action', (e) => {
    try {
      const data = JSON.parse(e.data);
      const action = data.action || '';
      if (action.includes("Next slide")) {
        nextSlide();
      } else if (action.includes("Previous slide") || action.includes("Prev")) {
        prevSlide();
      } else if (action.includes("First slide")) {
        goToSlide(1);
      } else if (action.includes("Black screen")) {
        toggleBlackout();
      }
    } catch (err) {
      console.error(err);
    }
  });

  evtSource.addEventListener('deck_update', (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.slides) {
        slides = data.slides;
        deckTitle = data.title || deckTitle;
        document.getElementById('nav-deck-title').textContent = deckTitle;
        renderThumbnails();
        renderCurrentSlide();
      }
    } catch (err) {
      console.error(err);
    }
  });

  evtSource.addEventListener('status_change', (e) => {
    try {
      const data = JSON.parse(e.data);
      if (typeof data.armed !== 'undefined') applyArmedUI(data.armed);
    } catch (err) {}
  });

  evtSource.addEventListener('mode_change', (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.mode) applyModeUI(data.mode);
    } catch (err) {}
  });
}

// Keyboard Listeners
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') nextSlide();
  else if (e.key === 'ArrowLeft' || e.key === 'PageUp') prevSlide();
  else if (e.key === 'b' || e.key === 'B') toggleBlackout();
  else if (e.key === 'f' || e.key === 'F') toggleFullscreen();
  else if (e.key === 'Home') goToSlide(1);
  else if (e.key === 'End') goToSlide(slides.length);
});

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

window.addEventListener('DOMContentLoaded', () => {
  fetchDeck();
  setupEventSource();
  setInterval(pollTelemetry, 120);
});
