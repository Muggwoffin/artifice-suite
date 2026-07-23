(() => {
  'use strict';

  const API = '/api/v1';

  const $ = (id) => document.getElementById(id);
  const escapeHtml = (s) => (s ?? '').toString().replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));

  // ------------------------------------------------------------------ toast

  function toast(message, kind = 'accent') {
    const container = $('toast-container');
    const el = document.createElement('div');
    el.className = `toast ${kind}`;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => {
      el.classList.add('toast-out');
      setTimeout(() => el.remove(), 220);
    }, 3600);
  }

  async function api(path, options = {}) {
    const resp = await fetch(`${API}${path}`, options);
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const body = await resp.json();
        detail = body.detail || detail;
      } catch (_) { /* no json body */ }
      throw new Error(detail);
    }
    if (resp.status === 204) return null;
    return resp.json();
  }

  // ------------------------------------------------------------------ tabs

  function initTabs() {
    document.querySelectorAll('.tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
        document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
        tab.classList.add('active');
        $(`panel-${tab.dataset.tab}`).classList.add('active');
        if (tab.dataset.tab === 'library') loadLibrary();
      });
    });
  }

  // ----------------------------------------------------------------- theme

  function initTheme() {
    const stored = localStorage.getItem('pt-theme');
    if (stored) document.documentElement.setAttribute('data-theme', stored);
    $('btn-theme-toggle').addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme')
        || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('pt-theme', next);
    });
  }

  // ------------------------------------------------------------ formatting

  function formatClock(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m}:${r.toString().padStart(2, '0')}`;
  }

  function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleString();
  }

  function statusPill(status) {
    return `<span class="status-pill ${status}">${status}</span>`;
  }

  // ------------------------------------------------------------- dropzone

  let selectedFile = null;

  function initUploadForm() {
    const dropzone = $('dropzone');
    const fileInput = $('file-input');
    const dropzoneText = $('dropzone-text');
    const btnStart = $('btn-start');
    const btnClear = $('btn-clear-file');

    const setFile = (file) => {
      selectedFile = file;
      if (file) {
        dropzoneText.innerHTML = `<span class="picked">${escapeHtml(file.name)}</span> selected`;
        btnStart.disabled = false;
        btnClear.disabled = false;
      } else {
        dropzoneText.textContent = 'Drop an audio file here, or click to browse';
        btnStart.disabled = true;
        btnClear.disabled = true;
      }
    };

    dropzone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => setFile(fileInput.files[0] || null));

    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('drag'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag'));
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('drag');
      const file = e.dataTransfer.files[0];
      if (file) setFile(file);
    });

    btnClear.addEventListener('click', () => { fileInput.value = ''; setFile(null); });

    btnStart.addEventListener('click', startTranscription);
  }

  async function startTranscription() {
    if (!selectedFile) return;
    const btnStart = $('btn-start');
    const statusEl = $('upload-status');
    btnStart.disabled = true;
    statusEl.textContent = 'Uploading…';

    const params = new URLSearchParams();
    const language = $('opt-language').value.trim();
    const minSpeakers = $('opt-min-speakers').value;
    const maxSpeakers = $('opt-max-speakers').value;
    if (language) params.set('language', language);
    if (minSpeakers) params.set('min_speakers', minSpeakers);
    if (maxSpeakers) params.set('max_speakers', maxSpeakers);

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const resp = await fetch(`${API}/transcribe?${params.toString()}`, {
        method: 'POST',
        body: formData,
      });
      if (!resp.ok) throw new Error(`Upload failed (${resp.status})`);
      const created = await resp.json();
      toast(`Queued: ${selectedFile.name}`, 'accent');
      trackActiveJob(created.job_id, selectedFile.name);
      $('file-input').value = '';
      selectedFile = null;
      $('dropzone-text').textContent = 'Drop an audio file here, or click to browse';
      $('btn-clear-file').disabled = true;
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      statusEl.textContent = '';
      btnStart.disabled = !selectedFile;
    }
  }

  // -------------------------------------------------------------- active jobs

  const activeJobs = new Map(); // jobId -> { filename, status, progress, created_at }
  const pollTimers = new Map();

  function trackActiveJob(jobId, filename) {
    activeJobs.set(jobId, {
      id: jobId, filename, status: 'queued', progress_percentage: 0, created_at: new Date().toISOString(),
    });
    renderActiveJobs();
    pollJob(jobId);
  }

  function pollJob(jobId) {
    if (pollTimers.has(jobId)) return;
    const tick = async () => {
      try {
        const job = await api(`/jobs/${jobId}`);
        activeJobs.set(jobId, job);
        renderActiveJobs();
        if (job.status === 'completed' || job.status === 'failed') {
          clearInterval(pollTimers.get(jobId));
          pollTimers.delete(jobId);
          if (job.status === 'completed') {
            toast(`Finished: ${job.filename}`, 'accent');
          } else {
            toast(`Failed: ${job.filename} — ${job.error_message || 'unknown error'}`, 'error');
          }
          if ($('panel-library').classList.contains('active')) loadLibrary();
        }
      } catch (err) {
        clearInterval(pollTimers.get(jobId));
        pollTimers.delete(jobId);
      }
    };
    pollTimers.set(jobId, setInterval(tick, 2000));
    tick();
  }

  function renderActiveJobs() {
    const body = $('active-body');
    const jobs = Array.from(activeJobs.values());
    const running = jobs.filter((j) => j.status === 'queued' || j.status === 'processing');
    $('active-count').textContent = `${running.length} running`;

    if (jobs.length === 0) {
      body.innerHTML = '<tr><td colspan="5" class="dim" style="text-align:center;">No active jobs yet.</td></tr>';
      return;
    }

    body.innerHTML = jobs.slice().reverse().map((j) => `
      <tr>
        <td>${escapeHtml(j.filename)}</td>
        <td class="c">${statusPill(j.status)}</td>
        <td class="c">
          <span class="mini-progress"><div style="width:${j.progress_percentage || 0}%"></div></span>
          <span class="dim">${Math.round(j.progress_percentage || 0)}%</span>
        </td>
        <td>${formatDate(j.created_at)}</td>
        <td class="c"><button class="btn" data-view-job="${j.id}" ${j.status === 'completed' ? '' : 'disabled'}>View</button></td>
      </tr>
    `).join('');

    body.querySelectorAll('[data-view-job]').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelector('.tab[data-tab="library"]').click();
        selectJob(btn.dataset.viewJob);
      });
    });
  }

  // ------------------------------------------------------------------ library

  let libraryJobs = [];

  async function loadLibrary() {
    const body = $('library-body');
    try {
      libraryJobs = await api('/jobs');
    } catch (err) {
      body.innerHTML = `<tr><td colspan="4" class="dim" style="text-align:center;">${escapeHtml(err.message)}</td></tr>`;
      return;
    }
    renderLibrary();
  }

  function renderLibrary() {
    const body = $('library-body');
    if (libraryJobs.length === 0) {
      body.innerHTML = '<tr><td colspan="4" class="dim" style="text-align:center;">No transcriptions yet.</td></tr>';
      return;
    }
    body.innerHTML = libraryJobs.map((j) => {
      const errorHtml = j.error_message
        ? `<div class="job-error-msg">${escapeHtml(j.error_message)}</div>`
        : '';
      return `
      <tr class="clickable ${j.id === currentJobId ? 'selected' : ''}" data-row-job="${j.id}">
        <td>${escapeHtml(j.filename)}${errorHtml}</td>
        <td class="c">${statusPill(j.status)}</td>
        <td>${formatDate(j.created_at)}</td>
        <td class="c"><button class="btn danger" data-delete-job="${j.id}">Delete</button></td>
      </tr>`;
    }).join('');

    body.querySelectorAll('[data-row-job]').forEach((row) => {
      row.addEventListener('click', (e) => {
        if (e.target.closest('[data-delete-job]')) return;
        const job = libraryJobs.find((j) => j.id === row.dataset.rowJob);
        if (job && job.status !== 'completed') {
          toast(`Job is ${job.status}, not completed yet.`, 'warning');
          return;
        }
        selectJob(row.dataset.rowJob);
      });
    });
    body.querySelectorAll('[data-delete-job]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteJob(btn.dataset.deleteJob);
      });
    });
  }

  // --------------------------------------------------------------- transcript

  let currentJobId = null;
  let currentSegments = [];
  let segmentEdits = new Map(); // index -> { originalText, editedText }
  let diffMode = false;

  async function selectJob(jobId) {
    try {
      const [job, transcript, speakers] = await Promise.all([
        api(`/jobs/${jobId}`),
        api(`/jobs/${jobId}/transcript`),
        api(`/jobs/${jobId}/speakers`),
      ]);
      currentJobId = jobId;
      currentSegments = transcript.segments;
      segmentEdits.clear();
      diffMode = false;
      renderLibrary();
      renderTranscript(job, transcript, speakers);
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  function renderTranscript(job, transcript, speakers) {
    $('transcript-empty').classList.add('hidden');
    $('transcript-card').classList.remove('hidden');

    $('transcript-title').textContent = job.filename;
    const pill = $('transcript-status-pill');
    pill.className = `status-pill ${job.status}`;
    pill.textContent = job.status;

    const audio = $('audio-player');
    audio.src = `${API}/jobs/${job.id}/audio`;

    // Speaker rename rows, keyed by the raw speaker_label so PATCH targets
    // the right mapping even after a custom name has replaced it everywhere.
    const rowsEl = $('speaker-rows');
    if (speakers.speakers.length === 0) {
      rowsEl.innerHTML = '<p class="dim">No speakers detected.</p>';
    } else {
      rowsEl.innerHTML = speakers.speakers.map((s, i) => `
        <div class="speaker-row">
          <span class="speaker-swatch" style="background:${swatchColor(i)}"></span>
          <input type="text" data-speaker-label="${escapeHtml(s.speaker_label)}" value="${escapeHtml(s.custom_name)}">
        </div>
      `).join('');
    }

    // Segments, clickable to seek + auto-highlighted during playback + editable.
    const segEl = $('segments');
    if (transcript.segments.length === 0) {
      segEl.innerHTML = '<p class="dim">No segments.</p>';
    } else {
      segEl.innerHTML = transcript.segments.map((s, i) => {
        const edit = segmentEdits.get(i);
        const displayText = edit ? edit.editedText : s.text;
        const editedClass = edit ? ' edited' : '';
        return `
        <div class="segment${editedClass}" data-seg-index="${i}" data-start="${s.start_time}">
          <span class="seg-time">${formatClock(s.start_time)}</span>
          <div class="seg-body">
            <div class="seg-speaker">${escapeHtml(s.speaker_label)}</div>
            <div class="seg-text" contenteditable="true" data-seg-text="${i}">${escapeHtml(displayText)}</div>
          </div>
          ${edit ? '<span class="seg-edited-badge" title="Edited">edited</span>' : ''}
        </div>`;
      }).join('');

      // Click to seek audio
      segEl.querySelectorAll('[data-seg-index]').forEach((el) => {
        el.addEventListener('click', (e) => {
          if (e.target.closest('[contenteditable]')) return;
          audio.currentTime = parseFloat(el.dataset.start);
          audio.play().catch(() => {});
        });
      });

      // Track edits on blur
      segEl.querySelectorAll('[data-seg-text]').forEach((el) => {
        el.addEventListener('blur', () => {
          const idx = parseInt(el.dataset.segText, 10);
          const original = transcript.segments[idx].text;
          const edited = el.textContent.trim();
          if (edited !== original) {
            segmentEdits.set(idx, { originalText: original, editedText: edited });
          } else {
            segmentEdits.delete(idx);
          }
          updateEditToolbar();
        });

        // Prevent segment click when editing
        el.addEventListener('click', (e) => e.stopPropagation());

        // Enter in contenteditable should blur (save), not insert newline
        el.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            el.blur();
          }
        });
      });
    }

    document.querySelectorAll('[data-export]').forEach((btn) => {
      btn.onclick = () => window.open(`${API}/jobs/${job.id}/export?format=${btn.dataset.export}`, '_blank');
    });
    $('btn-delete-job').onclick = () => deleteJob(job.id);
    $('btn-save-speakers').onclick = () => saveSpeakers(job.id);
    initEditToolbar();
    updateEditToolbar();
  }

  const SWATCHES = ['#2f7d45', '#bf9b30', '#9a3324', '#3d5a80', '#7a4fa0', '#c06d2f'];
  function swatchColor(i) { return SWATCHES[i % SWATCHES.length]; }

  // --------------------------------------------------------- editing / diff

  function initEditToolbar() {
    $('btn-save-edits').onclick = saveEdits;
    $('btn-revert-edits').onclick = revertEdits;
    $('btn-diff-toggle').onclick = toggleDiff;
  }

  function updateEditToolbar() {
    const hasEdits = segmentEdits.size > 0;
    $('btn-save-edits').disabled = !hasEdits;
    $('btn-revert-edits').disabled = !hasEdits;
  }

  async function saveEdits() {
    if (!currentJobId || segmentEdits.size === 0) return;
    const updates = [];
    for (const [idx, edit] of segmentEdits) {
      const segId = currentSegments[idx]?.id;
      if (segId) {
        updates.push({ segment_id: segId, text: edit.editedText });
      }
    }
    if (updates.length === 0) return;
    try {
      await api(`/jobs/${currentJobId}/segments`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates }),
      });
      toast(`Saved ${updates.length} edit(s)`, 'accent');
      // Update originals to match saved state
      for (const [idx, edit] of segmentEdits) {
        currentSegments[idx].text = edit.editedText;
      }
      segmentEdits.clear();
      updateEditToolbar();
      refreshSegmentsDisplay();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  function revertEdits() {
    segmentEdits.clear();
    updateEditToolbar();
    refreshSegmentsDisplay();
    toast('Reverted all edits', 'accent');
  }

  function refreshSegmentsDisplay() {
    if (!currentJobId || currentSegments.length === 0) return;
    const segEl = $('segments');
    segEl.querySelectorAll('[data-seg-text]').forEach((el) => {
      const idx = parseInt(el.dataset.segText, 10);
      const edit = segmentEdits.get(idx);
      el.textContent = edit ? edit.editedText : currentSegments[idx].text;
      const seg = el.closest('.segment');
      if (seg) {
        seg.classList.toggle('edited', !!edit);
        const badge = seg.querySelector('.seg-edited-badge');
        if (edit && !badge) {
          const b = document.createElement('span');
          b.className = 'seg-edited-badge';
          b.title = 'Edited';
          b.textContent = 'edited';
          seg.appendChild(b);
        } else if (!edit && badge) {
          badge.remove();
        }
      }
    });
  }

  function toggleDiff() {
    diffMode = !diffMode;
    const btn = $('btn-diff-toggle');
    btn.classList.toggle('active', diffMode);
    const segEl = $('segments');
    const textEls = segEl.querySelectorAll('[data-seg-text]');
    textEls.forEach((el) => {
      const idx = parseInt(el.dataset.segText, 10);
      const edit = segmentEdits.get(idx);
      const seg = el.closest('.segment');
      if (diffMode && edit) {
        el.innerHTML = computeDiffHtml(edit.originalText, edit.editedText);
        if (seg) seg.classList.add('diff-active');
      } else {
        el.textContent = edit ? edit.editedText : currentSegments[idx].text;
        if (seg) seg.classList.remove('diff-active');
      }
    });
  }

  function computeDiffHtml(original, edited) {
    const origWords = original.split(/(\s+)/);
    const editWords = edited.split(/(\s+)/);
    // Simple longest-common-subsequence for word-level diff
    const lcs = buildLCS(origWords, editWords);
    let oi = 0, ei = 0, li = 0;
    let html = '';
    while (oi < origWords.length || ei < editWords.length) {
      if (li < lcs.length && oi < origWords.length && origWords[oi] === lcs[li]
          && ei < editWords.length && editWords[ei] === lcs[li]) {
        html += escapeHtml(lcs[li]);
        oi++; ei++; li++;
      } else if (oi < origWords.length && (li >= lcs.length || origWords[oi] !== lcs[li])) {
        html += `<span class="diff-del">${escapeHtml(origWords[oi])}</span>`;
        oi++;
      } else if (ei < editWords.length && (li >= lcs.length || editWords[ei] !== lcs[li])) {
        html += `<span class="diff-add">${escapeHtml(editWords[ei])}</span>`;
        ei++;
      } else {
        break;
      }
    }
    return html;
  }

  function buildLCS(a, b) {
    const m = a.length, n = b.length;
    const dp = Array.from({ length: m + 1 }, () => new Uint16Array(n + 1));
    for (let i = 1; i <= m; i++) {
      for (let j = 1; j <= n; j++) {
        dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1
          : Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
    // Backtrack
    const result = [];
    let i = m, j = n;
    while (i > 0 && j > 0) {
      if (a[i - 1] === b[j - 1]) { result.unshift(a[i - 1]); i--; j--; }
      else if (dp[i - 1][j] > dp[i][j - 1]) i--;
      else j--;
    }
    return result;
  }

  async function saveSpeakers(jobId) {
    const inputs = document.querySelectorAll('[data-speaker-label]');
    const payload = {
      speakers: Array.from(inputs).map((input) => ({
        speaker_label: input.dataset.speakerLabel,
        custom_name: input.value.trim() || input.dataset.speakerLabel,
      })),
    };
    try {
      await api(`/jobs/${jobId}/speakers`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      toast('Speaker names saved', 'accent');
      selectJob(jobId);
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function deleteJob(jobId) {
    if (!confirm('Delete this job and its audio file? This cannot be undone.')) return;
    try {
      await api(`/jobs/${jobId}`, { method: 'DELETE' });
      activeJobs.delete(jobId);
      toast('Job deleted', 'accent');
      if (currentJobId === jobId) {
        currentJobId = null;
        $('transcript-card').classList.add('hidden');
        $('transcript-empty').classList.remove('hidden');
      }
      renderActiveJobs();
      loadLibrary();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  // --------------------------------------------------------- audio highlight

  function initAudioHighlight() {
    const audio = $('audio-player');
    audio.addEventListener('timeupdate', () => {
      if (!currentSegments.length) return;
      const t = audio.currentTime;
      let activeIndex = -1;
      for (let i = 0; i < currentSegments.length; i++) {
        if (t >= currentSegments[i].start_time && t < currentSegments[i].end_time) { activeIndex = i; break; }
      }
      document.querySelectorAll('.segment').forEach((el) => el.classList.remove('active'));
      if (activeIndex >= 0) {
        const el = document.querySelector(`[data-seg-index="${activeIndex}"]`);
        if (el) el.classList.add('active');
      }
    });
  }

  // ------------------------------------------------------------ config load

  async function loadConfig() {
    try {
      const cfg = await api('/config');
      const badge = $('opt-model-size');
      badge.textContent = `${cfg.whisper_model} (${cfg.device})`;
    } catch (_) { /* config endpoint unavailable */ }
  }

  // ------------------------------------------------------------ health check

  function setDot(id, status) {
    const el = $(id);
    if (el) { el.className = 'health-dot ' + status; }
  }

  function setStatusDot(id, status) {
    const el = $(id);
    if (el) { el.className = 'health-status ' + status; }
  }

  function showHealthError(msg) {
    const box = $('health-error-box');
    $('health-error-text').textContent = msg;
    box.classList.remove('hidden');
  }

  function hideHealthError() {
    $('health-error-box').classList.add('hidden');
  }

  function mapModelState(state) {
    // untested -> warn, loaded -> ok, failed -> error
    if (state === 'loaded') return 'ok';
    if (state === 'failed') return 'error';
    return 'warn'; // untested
  }

  async function loadHealth() {
    try {
      const h = await api('/health/detailed');
      const e = h.engine;

      // Status bar dots — use 3-state mapping
      setDot('health-db', h.database.status === 'ok' ? 'ok' : 'error');
      setDot('health-whisper', mapModelState(e.whisper_model.state));
      setDot('health-diarize', mapModelState(e.diarization_model.state));
      setDot('health-gpu', e.gpu ? 'ok' : 'warn');

      // Detail panel — Whisper
      const whisperLabel = e.whisper_model.state === 'loaded'
        ? `${e.whisper_model.name} (loaded)`
        : e.whisper_model.state === 'failed'
          ? `${e.whisper_model.name} (failed)`
          : `${e.whisper_model.name} (not loaded)`;
      $('health-whisper-name').textContent = whisperLabel;
      setStatusDot('health-whisper-status', mapModelState(e.whisper_model.state));

      // Diarization
      const diarizeLabel = e.diarization_model.state === 'loaded'
        ? 'Loaded'
        : e.diarization_model.state === 'failed'
          ? 'Failed'
          : 'Not loaded';
      $('health-diarize-status').textContent = diarizeLabel;
      setStatusDot('health-diarize-dot', mapModelState(e.diarization_model.state));

      // Alignment
      const langs = e.alignment_models.loaded_languages;
      const alignLabel = e.alignment_models.state === 'loaded'
        ? `${langs.join(', ')} (loaded)`
        : e.alignment_models.state === 'failed'
          ? 'Failed'
          : 'Not loaded';
      $('health-align-langs').textContent = alignLabel;
      setStatusDot('health-align-dot', mapModelState(e.alignment_models.state));

      // Device
      $('health-device').textContent = e.device.toUpperCase();
      setStatusDot('health-device-dot', 'ok');

      // GPU / VRAM
      if (e.gpu) {
        $('health-gpu-name').textContent = e.gpu.name;
        $('health-vram').textContent = `${e.gpu.vram_used_mb} / ${e.gpu.vram_total_mb} MB`;
        setStatusDot('health-gpu-dot', 'ok');
        const vramPct = e.gpu.vram_used_mb / e.gpu.vram_total_mb;
        setStatusDot('health-vram-dot', vramPct > 0.9 ? 'error' : vramPct > 0.7 ? 'warn' : 'ok');
      } else {
        $('health-gpu-name').textContent = 'N/A (CPU mode)';
        $('health-vram').textContent = 'N/A';
        setStatusDot('health-gpu-dot', 'warn');
        setStatusDot('health-vram-dot', 'warn');
      }

      // HF Token
      $('health-hf-token').textContent = e.hf_token_configured ? 'Configured' : 'Missing';
      setStatusDot('health-hf-dot', e.hf_token_configured ? 'ok' : 'error');

      // Database
      $('health-db-status').textContent = h.database.status === 'ok' ? 'Connected' : 'Error';
      setStatusDot('health-db-dot', h.database.status === 'ok' ? 'ok' : 'error');

      // Error display
      if (e.last_error) {
        showHealthError(e.last_error);
      } else {
        hideHealthError();
      }

    } catch (_) {
      setDot('health-db', 'error');
      setDot('health-whisper', 'error');
      setDot('health-diarize', 'error');
      setDot('health-gpu', 'error');
    }
  }

  async function preloadModels() {
    const btn = $('btn-load-models');
    btn.classList.add('loading');
    btn.textContent = 'Loading…';
    hideHealthError();

    try {
      const result = await api('/health/preload', { method: 'POST' });
      if (result.ok) {
        toast('Models loaded successfully', 'accent');
      } else {
        toast(`Model load failed: ${result.error}`, 'error');
        showHealthError(result.error);
      }
    } catch (err) {
      toast(`Preload failed: ${err.message}`, 'error');
      showHealthError(err.message);
    } finally {
      btn.classList.remove('loading');
      btn.textContent = 'Load Models';
      loadHealth();
    }
  }

  function initHealthPanel() {
    $('btn-health-details').addEventListener('click', () => {
      const panel = $('health-panel');
      const wasHidden = panel.classList.contains('hidden');
      panel.classList.toggle('hidden');
      if (wasHidden) loadHealth();
    });
    $('btn-health-close').addEventListener('click', () => {
      $('health-panel').classList.add('hidden');
    });
    $('btn-load-models').addEventListener('click', preloadModels);
  }

  // ---------------------------------------------------------------- startup

  document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initTheme();
    initUploadForm();
    initAudioHighlight();
    initHealthPanel();
    loadConfig();
    loadHealth();
    $('btn-library-refresh').addEventListener('click', loadLibrary);
  });
})();
