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
    if (resp.headers.get('content-type')?.includes('application/json')) {
      return resp.json();
    }
    return resp;
  }

  // ----------------------------------------------------------- keyboard shortcuts

  function initKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      // Ctrl+S or Ctrl+Enter: save edits
      if ((e.ctrlKey && e.key === 's') || (e.ctrlKey && e.key === 'Enter')) {
        e.preventDefault();
        saveEdits();
      }
      // Ctrl+Z: revert edits
      if (e.ctrlKey && e.key === 'z') {
        if (!e.target.closest('[contenteditable]')) {
          e.preventDefault();
          revertEdits();
        }
      }
      // /: focus global search (when not in an input)
      if (e.key === '/' && !e.target.closest('input, textarea, [contenteditable]')) {
        e.preventDefault();
        const searchInput = $('global-search-input');
        if (searchInput) { searchInput.focus(); searchInput.select(); }
      }
      // Escape: close modals
      if (e.key === 'Escape') {
        closeSearchModal();
        $('history-panel')?.classList.add('hidden');
      }
      // Alt+S: split segment at cursor
      if (e.altKey && e.key === 's') {
        e.preventDefault();
        splitSegment();
      }
      // Alt+M: merge segment with next
      if (e.altKey && e.key === 'm') {
        e.preventDefault();
        mergeSegment();
      }
      // Tab/Shift+Tab: navigate between editable segments
      if (e.key === 'Tab' && e.target.closest('[data-seg-text]')) {
        e.preventDefault();
        const segs = [...document.querySelectorAll('[data-seg-text]')];
        const idx = segs.indexOf(e.target);
        if (idx >= 0) {
          const next = e.shiftKey ? segs[Math.max(0, idx - 1)] : segs[Math.min(segs.length - 1, idx + 1)];
          next.focus();
          // Move cursor to end
          const range = document.createRange();
          range.selectNodeContents(next);
          range.collapse(false);
          const sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
        }
      }
      // Arrow Up/Down: navigate between segments from the focused contenteditable
      if ((e.key === 'ArrowUp' || e.key === 'ArrowDown') && !e.ctrlKey && !e.altKey && !e.metaKey) {
        const focused = e.target.closest('[data-seg-text]');
        if (!focused) return;
        const all = [...document.querySelectorAll('[data-seg-text]')];
        const idx = all.indexOf(focused);
        if (idx < 0) return;
        e.preventDefault();
        const next = e.key === 'ArrowDown' ? all[Math.min(all.length - 1, idx + 1)] : all[Math.max(0, idx - 1)];
        next.focus();
        const range = document.createRange();
        range.selectNodeContents(next);
        range.collapse(e.key === 'ArrowUp');
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        next.closest('[data-seg-index]')?.scrollIntoView({ block: 'nearest' });
      }
    });
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
    const prefersDark = matchMedia('(prefers-color-scheme: dark)').matches;
    const initial = stored || (prefersDark ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', initial);
    const btn = $('btn-theme-toggle');
    btn.textContent = initial === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19';
    btn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') || 'light';
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('pt-theme', next);
      btn.textContent = next === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19';
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

    // Batch upload
    $('btn-batch-upload').addEventListener('click', () => {
      $('batch-file-input').click();
    });
    $('batch-file-input').addEventListener('change', async (e) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;
      const btn = $('btn-batch-upload');
      btn.disabled = true;
      btn.textContent = 'Uploading...';
      let queued = 0;
      for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);
        try {
          const resp = await fetch(`${API}/transcribe`, { method: 'POST', body: formData });
          if (resp.ok) {
            const created = await resp.json();
            trackActiveJob(created.job_id, file.name);
            queued++;
          }
        } catch (_) { /* skip failed */ }
      }
      btn.disabled = false;
      btn.textContent = 'Batch Upload';
      toast(`Queued ${queued} file(s)`, 'accent');
      e.target.value = '';
    });
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

  const activeJobs = new Map();
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
      body.innerHTML = `<tr><td colspan="5" class="dim" style="text-align:center;">${escapeHtml(err.message)}</td></tr>`;
      return;
    }
    renderLibrary();
  }

  function renderLibrary() {
    const body = $('library-body');
    if (libraryJobs.length === 0) {
      body.innerHTML = '<tr><td colspan="5" class="dim" style="text-align:center;">No transcriptions yet.</td></tr>';
      return;
    }
    body.innerHTML = libraryJobs.map((j) => {
      const errorHtml = j.error_message
        ? `<div class="job-error-msg">${escapeHtml(j.error_message)}</div>`
        : '';
      const interviewee = j.interviewee || '';
      return `
      <tr class="clickable ${j.id === currentJobId ? 'selected' : ''}" data-row-job="${j.id}">
        <td>${escapeHtml(j.filename)}${errorHtml}</td>
        <td class="c">${statusPill(j.status)}</td>
        <td>${formatDate(j.created_at)}</td>
        <td class="meta-cell">${escapeHtml(interviewee)}</td>
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
  let segmentEdits = new Map();
  let diffMode = false;
  let inTranscriptSearchTerm = '';

  async function selectJob(jobId) {
    if (segmentEdits.size > 0) {
      if (!confirm('You have unsaved edits. Discard changes?')) return;
    }
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
      inTranscriptSearchTerm = '';
      renderLibrary();
      renderTranscript(job, transcript, speakers);
      fillMetadataForm(job);
      loadWaveform();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  function fillMetadataForm(job) {
    $('meta-interviewee').value = job.interviewee || '';
    $('meta-interviewer').value = job.interviewer || '';
    $('meta-date').value = job.interview_date || '';
    $('meta-location').value = job.location || '';
    $('meta-project').value = job.project_name || '';
    $('meta-collection').value = job.collection_id || '';
    $('meta-access').value = job.access_restrictions || '';
    $('meta-vocabulary').value = job.custom_vocabulary || '';
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

    // Speaker rename rows
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

    // Map speaker labels to swatch colors
    const speakerColorMap = {};
    speakers.speakers.forEach((s, i) => {
      speakerColorMap[s.custom_name] = swatchColor(i);
    });

    // Metadata badge
    const badgeParts = [job.interviewee, job.interview_date, job.project_name].filter(Boolean);
    $('meta-badge').textContent = badgeParts.length ? badgeParts.join(' \u00b7 ') : '';

    // Segments
    const segEl = $('segments');
    if (transcript.segments.length === 0) {
      segEl.innerHTML = '<p class="dim">No segments.</p>';
    } else {
      segEl.innerHTML = transcript.segments.map((s, i) => {
        const edit = segmentEdits.get(i);
        const displayText = edit ? edit.editedText : s.text;
        const editedClass = edit ? ' edited' : '';
        const tags = s.tags || [];
        const spColor = speakerColorMap[s.speaker_label] || 'transparent';
        return `
        <div class="segment speaker-border${editedClass}" data-seg-index="${i}" data-seg-id="${escapeHtml(s.id)}" data-start="${s.start_time}" style="--speaker-color:${spColor}">
          <span class="seg-time">${formatClock(s.start_time)}</span>
          <div class="seg-body">
            <div class="seg-speaker" style="color:${spColor}">${escapeHtml(s.speaker_label)}</div>
            <div class="seg-text" contenteditable="true" data-seg-text="${i}">${escapeHtml(displayText)}</div>
            <div class="seg-tags" data-tags-for="${i}">
              ${tags.map((t) => `<span class="seg-tag" data-tag="${escapeHtml(t)}">${escapeHtml(t)}</span>`).join('')}
              <span class="seg-tag-add" data-add-tag="${i}">+ tag</span>
            </div>
          </div>
          ${edit ? '<span class="seg-edited-badge" title="Edited">edited</span>' : ''}
        </div>`;
      }).join('');

      // Click to seek
      segEl.querySelectorAll('[data-seg-index]').forEach((el) => {
        el.addEventListener('click', (e) => {
          if (e.target.closest('[contenteditable], .seg-tag, .seg-tag-add')) return;
          audio.currentTime = parseFloat(el.dataset.start);
          audio.play().catch(() => {});
        });
      });

      // Track edits on blur
      segEl.querySelectorAll('[data-seg-text]').forEach((el) => {
        el.addEventListener('blur', () => {
          const idx = parseInt(el.dataset.segText, 10);
          const seg = currentSegments[idx];
          if (!seg) return;
          const original = seg.text;
          const edited = el.textContent.trim();
          if (edited !== original) {
            segmentEdits.set(idx, { originalText: original, editedText: edited });
          } else {
            segmentEdits.delete(idx);
          }
          updateEditToolbar();
        });
        el.addEventListener('click', (e) => e.stopPropagation());
        el.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') { e.preventDefault(); el.blur(); }
        });
      });

      // Tag add
      segEl.querySelectorAll('[data-add-tag]').forEach((btn) => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const idx = parseInt(btn.dataset.addTag, 10);
          const seg = currentSegments[idx];
          if (!seg) return;
          const tag = prompt('Add tag (e.g. anecdote, reflection):');
          if (tag && tag.trim()) {
            const tags = seg.tags || [];
            if (!tags.includes(tag.trim())) {
              tags.push(tag.trim());
              updateSegmentTags(idx, tags);
            }
          }
        });
      });

      // Tag remove
      segEl.querySelectorAll('[data-tag]').forEach((el) => {
        el.addEventListener('click', (e) => {
          e.stopPropagation();
          const tagEl = e.target;
          const segEl2 = tagEl.closest('[data-seg-index]');
          if (!segEl2) return;
          const idx = parseInt(segEl2.dataset.segIndex, 10);
          const seg = currentSegments[idx];
          if (!seg) return;
          const tag = tagEl.dataset.tag;
          const tags = (seg.tags || []).filter((t) => t !== tag);
          updateSegmentTags(idx, tags);
        });
      });
    }

    // Stats footer
    const segments = transcript.segments;
    const totalWords = segments.reduce((sum, s) => sum + (s.text ? s.text.split(/\s+/).filter(Boolean).length : 0), 0);
    const totalDuration = segments.length ? (segments[segments.length - 1].end_time - segments[0].start_time) : 0;
    let speakerChanges = 0;
    for (let i = 1; i < segments.length; i++) {
      if (segments[i].speaker_label !== segments[i - 1].speaker_label) speakerChanges++;
    }
    $('transcript-stats').textContent =
      `${segments.length} segment${segments.length !== 1 ? 's' : ''} \u00b7 ` +
      `${totalWords.toLocaleString()} word${totalWords !== 1 ? 's' : ''} \u00b7 ` +
      `${formatClock(totalDuration)} duration \u00b7 ` +
      `${speakerChanges} speaker change${speakerChanges !== 1 ? 's' : ''}`;

    // Export buttons
    document.querySelectorAll('[data-export]').forEach((btn) => {
      btn.onclick = () => window.open(`${API}/jobs/${job.id}/export?format=${btn.dataset.export}`, '_blank');
    });
    $('btn-delete-job').onclick = () => deleteJob(job.id);
    $('btn-save-speakers').onclick = () => saveSpeakers(job.id);
    $('btn-save-metadata').onclick = () => saveMetadata(job.id);
    initEditToolbar();
    updateEditToolbar();

    // In-transcript search
    $('library-search-input').oninput = (e) => {
      inTranscriptSearchTerm = e.target.value.trim().toLowerCase();
      highlightInTranscript(inTranscriptSearchTerm);
    };
    $('library-search-input').value = '';
    $('search-hit-info').textContent = '';
  }

  async function updateSegmentTags(idx, tags) {
    const seg = currentSegments[idx];
    if (!seg) return;
    try {
      await api(`/jobs/${currentJobId}/segments/${seg.id}/tags`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags }),
      });
      seg.tags = tags;
      // Re-render tags
      const container = document.querySelector(`[data-tags-for="${idx}"]`);
      if (container) {
        container.innerHTML = tags.map((t) =>
          `<span class="seg-tag" data-tag="${escapeHtml(t)}">${escapeHtml(t)}</span>`
        ).join('') +
        `<span class="seg-tag-add" data-add-tag="${idx}">+ tag</span>`;
        // Re-bind
        container.querySelectorAll('[data-add-tag]').forEach((btn) => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const i = parseInt(btn.dataset.addTag, 10);
            const s = currentSegments[i];
            if (!s) return;
            const t = prompt('Add tag:');
            if (t && t.trim()) {
              const ts = s.tags || [];
              if (!ts.includes(t.trim())) { ts.push(t.trim()); updateSegmentTags(i, ts); }
            }
          });
        });
        container.querySelectorAll('[data-tag]').forEach((el) => {
          el.addEventListener('click', (e) => {
            e.stopPropagation();
            const segEl = el.closest('[data-seg-index]');
            if (!segEl) return;
            const i = parseInt(segEl.dataset.segIndex, 10);
            const s = currentSegments[i];
            if (!s) return;
            updateSegmentTags(i, (s.tags || []).filter((t) => t !== el.dataset.tag));
          });
        });
      }
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  function highlightInTranscript(term) {
    const textEls = document.querySelectorAll('[data-seg-text]');
    let hitCount = 0;
    textEls.forEach((el) => {
      const idx = parseInt(el.dataset.segText, 10);
      const seg = currentSegments[idx];
      if (!seg) return;
      const edit = segmentEdits.get(idx);
      const baseText = edit ? edit.editedText : seg.text;
      if (!term) {
        el.textContent = baseText;
        el.closest('.segment')?.classList.remove('search-active');
        return;
      }
      const lower = baseText.toLowerCase();
      const pos = lower.indexOf(term);
      if (pos >= 0) {
        hitCount++;
        const before = escapeHtml(baseText.slice(0, pos));
        const match = escapeHtml(baseText.slice(pos, pos + term.length));
        const after = escapeHtml(baseText.slice(pos + term.length));
        el.innerHTML = `${before}<span class="search-hl">${match}</span>${after}`;
        el.closest('.segment')?.classList.add('search-active');
      } else {
        el.textContent = baseText;
        el.closest('.segment')?.classList.remove('search-active');
      }
    });
    $('search-hit-info').textContent = term ? `${hitCount} hit(s)` : '';
  }

  const SWATCHES = ['#2f7d45', '#bf9b30', '#9a3324', '#3d5a80', '#7a4fa0', '#c06d2f'];
  function swatchColor(i) { return SWATCHES[i % SWATCHES.length]; }

  // --------------------------------------------------------- metadata save

  async function saveMetadata(jobId) {
    const data = {
      interviewee: $('meta-interviewee').value.trim() || null,
      interviewer: $('meta-interviewer').value.trim() || null,
      interview_date: $('meta-date').value.trim() || null,
      location: $('meta-location').value.trim() || null,
      project_name: $('meta-project').value.trim() || null,
      collection_id: $('meta-collection').value.trim() || null,
      access_restrictions: $('meta-access').value.trim() || null,
      custom_vocabulary: $('meta-vocabulary').value.trim() || null,
    };
    try {
      await api(`/jobs/${jobId}/metadata`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      toast('Metadata saved', 'accent');
      if ($('panel-library').classList.contains('active')) loadLibrary();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  // --------------------------------------------------------- editing / diff

  function initEditToolbar() {
    $('btn-save-edits').onclick = saveEdits;
    $('btn-revert-edits').onclick = revertEdits;
    $('btn-diff-toggle').onclick = toggleDiff;
    $('btn-history-toggle').onclick = toggleHistory;
    $('btn-history-close').onclick = () => $('history-panel')?.classList.add('hidden');
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
    if (segmentEdits.size === 0) return;
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

  // segment split/merge

  async function splitSegment() {
    const activeSeg = document.querySelector('.segment.active');
    if (!activeSeg) return;
    const sel = window.getSelection();
    if (!sel.rangeCount) return;
    const textEl = activeSeg.querySelector('[data-seg-text]');
    if (!textEl || !sel.containsNode(textEl, true)) return;
    const range = sel.getRangeAt(0);
    const preCaret = range.cloneRange();
    preCaret.selectNodeContents(textEl);
    preCaret.setEnd(range.startContainer, range.startOffset);
    const pos = preCaret.toString().length;
    if (pos <= 0 || pos >= textEl.textContent.length) {
      toast('Move cursor inside the text to split', 'warning');
      return;
    }
    const segId = activeSeg.dataset.segId;
    try {
      const result = await api(`/jobs/${currentJobId}/segments/${segId}/split`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ split_position: pos }),
      });
      // Reload transcript data
      const [job, transcript, speakers] = await Promise.all([
        api(`/jobs/${currentJobId}`),
        api(`/jobs/${currentJobId}/transcript`),
        api(`/jobs/${currentJobId}/speakers`),
      ]);
      currentSegments = transcript.segments;
      segmentEdits.clear();
      diffMode = false;
      renderTranscript(job, transcript, speakers);
      fillMetadataForm(job);
      loadWaveform();
      toast('Segment split', 'accent');
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function mergeSegment() {
    const activeSeg = document.querySelector('.segment.active');
    if (!activeSeg) return;
    const segId = activeSeg.dataset.segId;
    const idx = parseInt(activeSeg.dataset.segIndex, 10);
    if (idx >= currentSegments.length - 1) {
      toast('No next segment to merge with', 'warning');
      return;
    }
    try {
      const result = await api(`/jobs/${currentJobId}/segments/${segId}/merge`, {
        method: 'POST',
      });
      // Reload transcript data
      const [job, transcript, speakers] = await Promise.all([
        api(`/jobs/${currentJobId}`),
        api(`/jobs/${currentJobId}/transcript`),
        api(`/jobs/${currentJobId}/speakers`),
      ]);
      currentSegments = transcript.segments;
      segmentEdits.clear();
      diffMode = false;
      renderTranscript(job, transcript, speakers);
      fillMetadataForm(job);
      loadWaveform();
      toast('Segments merged', 'accent');
    } catch (err) {
      toast(err.message, 'error');
    }
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
        el.textContent = edit ? edit.editedText : (currentSegments[idx]?.text || '');
        if (seg) seg.classList.remove('diff-active');
      }
    });
  }

  async function toggleHistory() {
    const panel = $('history-panel');
    if (!panel.classList.contains('hidden')) {
      panel.classList.add('hidden');
      return;
    }
    // Check if a segment is selected
    const activeSeg = document.querySelector('.segment.active');
    if (!activeSeg) {
      toast('Click a segment first, then open History', 'warning');
      return;
    }
    const segId = activeSeg.dataset.segId;
    if (!segId) return;
    try {
      const data = await api(`/jobs/${currentJobId}/segments/${segId}/history`);
      const list = $('history-list');
      if (data.versions.length === 0) {
        list.innerHTML = '<p class="dim">No edit history for this segment.</p>';
      } else {
        list.innerHTML = data.versions.map((v) => `
          <div class="history-version">
            <div class="hist-time">${formatDate(v.edited_at)}</div>
            <div class="hist-before">${escapeHtml(v.text_before)}</div>
            <div class="hist-after">${escapeHtml(v.text_after)}</div>
          </div>
        `).join('');
      }
      panel.classList.remove('hidden');
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  function computeDiffHtml(original, edited) {
    const origWords = original.split(/(\s+)/);
    const editWords = edited.split(/(\s+)/);
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
      } else { break; }
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
      updateWaveformCursor(t);
    });
  }

  // ------------------------------------------------------------ waveform

  let waveformPeaks = null;
  let waveformDuration = 0;

  async function loadWaveform() {
    const canvas = $('waveform-canvas');
    if (!canvas) return;
    if (!currentJobId) { canvas.style.display = 'none'; return; }
    canvas.style.display = 'block';

    // Get audio duration from the player
    const audio = $('audio-player');
    if (!audio.src) return;

    try {
      const resp = await fetch(audio.src);
      const blob = await resp.blob();
      const arrayBuffer = await blob.arrayBuffer();
      const ctx = new (window.OfflineAudioContext || window.webkitOfflineAudioContext)(1, 44100, 44100);
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
      waveformDuration = audioBuffer.duration;
      const raw = audioBuffer.getChannelData(0);
      // Downsample to canvas width
      const w = canvas.clientWidth || canvas.parentElement.clientWidth || 600;
      canvas.width = w;
      canvas.height = 80;
      const step = Math.floor(raw.length / w);
      waveformPeaks = [];
      for (let i = 0; i < w; i++) {
        let max = 0;
        for (let j = 0; j < step; j++) {
          const val = Math.abs(raw[i * step + j] || 0);
          if (val > max) max = val;
        }
        waveformPeaks.push(max);
      }
      drawWaveform(0);

      // Click to seek
      canvas.onclick = (e) => {
        const rect = canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const pct = x / canvas.width;
        audio.currentTime = pct * waveformDuration;
      };
    } catch (_) {
      canvas.style.display = 'none';
    }
  }

  function drawWaveform(currentTime) {
    const canvas = $('waveform-canvas');
    if (!canvas || !waveformPeaks) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
      || matchMedia('(prefers-color-scheme: dark)').matches;

    ctx.clearRect(0, 0, w, h);

    // Background
    ctx.fillStyle = isDark ? '#1f1b16' : '#efebdf';
    ctx.fillRect(0, 0, w, h);

    // Draw segments as region highlights
    if (currentSegments.length > 0 && waveformDuration > 0) {
      currentSegments.forEach((seg) => {
        const sx = (seg.start_time / waveformDuration) * w;
        const ex = (seg.end_time / waveformDuration) * w;
        ctx.fillStyle = 'rgba(47, 125, 69, 0.08)';
        ctx.fillRect(sx, 0, ex - sx, h);
      });
    }

    // Draw waveform
    const center = h / 2;
    ctx.strokeStyle = isDark ? '#4aa066' : '#2f7d45';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (let i = 0; i < waveformPeaks.length; i++) {
      const x = (i / waveformPeaks.length) * w;
      const amp = waveformPeaks[i] * (center - 4);
      if (i === 0) ctx.moveTo(x, center - amp);
      ctx.lineTo(x, center - amp);
    }
    ctx.stroke();

    // Mirror bottom half
    ctx.beginPath();
    for (let i = 0; i < waveformPeaks.length; i++) {
      const x = (i / waveformPeaks.length) * w;
      const amp = waveformPeaks[i] * (center - 4);
      if (i === 0) ctx.moveTo(x, center + amp);
      ctx.lineTo(x, center + amp);
    }
    ctx.stroke();

    // Playback cursor
    if (currentTime > 0 && waveformDuration > 0) {
      const cx = (currentTime / waveformDuration) * w;
      ctx.strokeStyle = '#bf9b30';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx, 0);
      ctx.lineTo(cx, h);
      ctx.stroke();
    }
  }

  let waveformAnimFrame = null;

  function updateWaveformCursor(t) {
    if (waveformAnimFrame) cancelAnimationFrame(waveformAnimFrame);
    waveformAnimFrame = requestAnimationFrame(() => drawWaveform(t));
  }

  // ------------------------------------------------------------ global search

  function initGlobalSearch() {
    const input = $('global-search-input');
    let debounceTimer = null;
    input.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        const q = input.value.trim();
        if (q.length >= 2) {
          performSearch(q);
        }
      }, 350);
    });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const q = input.value.trim();
        if (q.length >= 2) performSearch(q);
      }
    });
  }

  async function performSearch(q) {
    try {
      const data = await api(`/search?q=${encodeURIComponent(q)}`);
      showSearchResults(data, q);
    } catch (err) {
      toast(`Search failed: ${err.message}`, 'error');
    }
  }

  function showSearchResults(data, query) {
    const modal = $('search-modal');
    const list = $('search-results-list');
    const count = $('search-result-count');
    count.textContent = `${data.total} result(s)`;

    if (data.results.length === 0) {
      list.innerHTML = '<p class="dim">No results found.</p>';
    } else {
      list.innerHTML = data.results.map((r) => {
        const meta = [r.interviewee, r.interview_date, r.project_name].filter(Boolean).join(' — ');
        const highlighted = r.text.replace(
          new RegExp(escapeRegex(query), 'gi'),
          (m) => `<span class="hl">${escapeHtml(m)}</span>`
        );
        return `
        <div class="search-result-item" data-search-job="${escapeHtml(r.job_id)}" data-search-seg="${escapeHtml(r.segment_id)}" data-search-time="${r.start_time}">
          <div class="search-result-meta">
            <span><strong>${escapeHtml(r.filename)}</strong></span>
            <span>${escapeHtml(r.speaker_label)}</span>
            <span>${formatClock(r.start_time)}</span>
            ${meta ? `<span>${escapeHtml(meta)}</span>` : ''}
          </div>
          <div class="search-result-text">${highlighted}</div>
        </div>`;
      }).join('');

      list.querySelectorAll('.search-result-item').forEach((el) => {
        el.addEventListener('click', () => {
          const jobId = el.dataset.searchJob;
          const segId = el.dataset.searchSeg;
          const time = parseFloat(el.dataset.searchTime);
          closeSearchModal();
          // Switch to library tab and select job
          document.querySelector('.tab[data-tab="library"]').click();
          selectJob(jobId);
          // Seek to time after render
          setTimeout(() => {
            const audio = $('audio-player');
            audio.currentTime = time;
            audio.play().catch(() => {});
            // Highlight segment
            document.querySelectorAll('[data-seg-id]').forEach((s) => {
              if (s.dataset.segId === segId) {
                s.classList.add('active');
                s.scrollIntoView({ behavior: 'smooth', block: 'center' });
              }
            });
          }, 300);
        });
      });
    }

    modal.classList.remove('hidden');
  }

  function escapeRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function closeSearchModal() {
    $('search-modal')?.classList.add('hidden');
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
    if (state === 'loaded') return 'ok';
    if (state === 'failed') return 'error';
    return 'warn';
  }

  async function loadHealth() {
    try {
      const h = await api('/health/detailed');
      const e = h.engine;

      setDot('health-db', h.database.status === 'ok' ? 'ok' : 'error');
      setDot('health-whisper', mapModelState(e.whisper_model.state));
      setDot('health-diarize', mapModelState(e.diarization_model.state));
      setDot('health-gpu', e.gpu ? 'ok' : 'warn');

      const whisperLabel = e.whisper_model.state === 'loaded'
        ? `${e.whisper_model.name} (loaded)`
        : e.whisper_model.state === 'failed'
          ? `${e.whisper_model.name} (failed)`
          : `${e.whisper_model.name} (not loaded)`;
      $('health-whisper-name').textContent = whisperLabel;
      setStatusDot('health-whisper-status', mapModelState(e.whisper_model.state));

      const diarizeLabel = e.diarization_model.state === 'loaded'
        ? 'Loaded' : e.diarization_model.state === 'failed' ? 'Failed' : 'Not loaded';
      $('health-diarize-status').textContent = diarizeLabel;
      setStatusDot('health-diarize-dot', mapModelState(e.diarization_model.state));

      const langs = e.alignment_models.loaded_languages;
      const alignLabel = e.alignment_models.state === 'loaded'
        ? `${langs.join(', ')} (loaded)`
        : e.alignment_models.state === 'failed' ? 'Failed' : 'Not loaded';
      $('health-align-langs').textContent = alignLabel;
      setStatusDot('health-align-dot', mapModelState(e.alignment_models.state));

      $('health-device').textContent = e.device.toUpperCase();
      setStatusDot('health-device-dot', 'ok');

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

      $('health-hf-token').textContent = e.hf_token_configured ? 'Configured' : 'Missing';
      setStatusDot('health-hf-dot', e.hf_token_configured ? 'ok' : 'error');

      $('health-db-status').textContent = h.database.status === 'ok' ? 'Connected' : 'Error';
      setStatusDot('health-db-dot', h.database.status === 'ok' ? 'ok' : 'error');

      if (e.last_error) { showHealthError(e.last_error); } else { hideHealthError(); }
    } catch (_) {
      ['health-db', 'health-whisper', 'health-diarize', 'health-gpu'].forEach((id) => setDot(id, 'error'));
    }
  }

  async function preloadModels() {
    const btn = $('btn-load-models');
    btn.classList.add('loading');
    btn.textContent = 'Loading…';
    hideHealthError();
    try {
      const result = await api('/health/preload', { method: 'POST' });
      if (result.ok) { toast('Models loaded successfully', 'accent'); }
      else { toast(`Model load failed: ${result.error}`, 'error'); showHealthError(result.error); }
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
    $('btn-health-close').addEventListener('click', () => { $('health-panel').classList.add('hidden'); });
    $('btn-load-models').addEventListener('click', preloadModels);
  }

  // ---------------------------------------------------------------- startup

  document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initTheme();
    initUploadForm();
    initAudioHighlight();
    initHealthPanel();
    initGlobalSearch();
    initKeyboardShortcuts();
    loadConfig();
    loadHealth();
    $('btn-library-refresh').addEventListener('click', loadLibrary);
    $('btn-search-close').addEventListener('click', closeSearchModal);
    // Close search on overlay click
    $('search-modal').addEventListener('click', (e) => {
      if (e.target === $('search-modal')) closeSearchModal();
    });
  });
})();
