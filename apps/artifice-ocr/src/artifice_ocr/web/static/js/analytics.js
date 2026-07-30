// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: MIT

/*
 * Analytics tab. The desktop build draws these three panels by hand onto a
 * tk.Canvas, specifically to avoid a matplotlib dependency. The web build has
 * no such constraint — SVG is native to the browser — so the same three
 * panels (throughput, confidence histogram, recent-run timing) are built as
 * small inline SVG strings instead. Same data, same three-colour palette
 * (accent/gold/indigo), sharper rendering.
 */

const AnalyticsTab = (function () {
  const tilesEl = document.getElementById("analytics-tiles");
  const throughputEl = document.getElementById("chart-throughput");
  const confidenceEl = document.getElementById("chart-confidence");
  const recentEl = document.getElementById("chart-recent");

  function confColor(value) {
    if (value == null) return "var(--ink-faint)";
    if (value >= 80) return "var(--accent)";
    if (value >= 55) return "var(--gold)";
    return "var(--error)";
  }

  function tile(value, label, color) {
    return `<div class="tile">
      <div class="tile-value" style="color:${color};">${value}</div>
      <div class="tile-label">${escapeHtml(label)}</div>
    </div>`;
  }

  function renderTiles(stats) {
    const confidences = stats.confidences || [];
    const avgConf = confidences.length
      ? confidences.reduce((a, b) => a + b, 0) / confidences.length : null;
    const files = stats.files || 0;
    const elapsed = stats.elapsed || 0;

    tilesEl.innerHTML = [
      tile((stats.runs || 0).toLocaleString(), "Runs", "var(--accent)"),
      tile(files.toLocaleString(), "Documents", "var(--gold)"),
      tile((stats.failed || 0).toLocaleString(), "Failures",
           stats.failed ? "var(--error)" : "var(--accent)"),
      tile(avgConf == null ? "—" : `${avgConf.toFixed(0)}/100`, "Avg quality score", confColor(avgConf)),
      tile(!files ? "—" : `${(elapsed / files).toFixed(1)}s`, "Avg per doc", "var(--indigo)"),
    ].join("");
  }

  function emptyChart(el, message) {
    el.innerHTML = `<p class="dim" style="padding:1.2rem 0;">${escapeHtml(message)}</p>`;
  }

  function renderThroughput(stats) {
    const totals = stats.stage_totals || {};
    const rows = Object.entries(totals)
      .filter(([, acc]) => acc.n)
      .map(([name, acc]) => ({ name, rate: acc.elapsed ? acc.chars / acc.elapsed : 0, n: acc.n }));
    if (!rows.length) return emptyChart(throughputEl, "No completed stages yet.");

    const colors = { ocr: "var(--accent)", cleanup: "var(--gold)", translate: "var(--indigo)" };
    const peak = Math.max(...rows.map(r => r.rate)) || 1;
    const barH = 24, gap = 14, labelW = 84, w = 480;
    const h = rows.length * (barH + gap);

    const bars = rows.map((r, i) => {
      const y = i * (barH + gap);
      const bw = Math.max((w - labelW - 90) * (r.rate / peak), 2);
      return `
        <text x="0" y="${y + barH * 0.7}" class="chart-label">${escapeHtml(r.name)}</text>
        <rect x="${labelW}" y="${y}" width="${bw}" height="${barH}" rx="3"
              fill="${colors[r.name] || "var(--accent)"}"></rect>
        <text x="${w - 4}" y="${y + barH * 0.7}" text-anchor="end" class="chart-label dim">
          ${r.rate.toLocaleString(undefined, { maximumFractionDigits: 0 })} (${r.n} files)
        </text>`;
    }).join("");

    throughputEl.innerHTML =
      `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}">${bars}</svg>`;
  }

  function renderConfidenceHistogram(stats) {
    const confidences = stats.confidences || [];
    if (!confidences.length) return emptyChart(confidenceEl, "Quality scores will appear after your first run.");

    const buckets = [0, 0, 0, 0, 0];
    for (const c of confidences) buckets[Math.min(Math.floor(c / 20), 4)]++;
    const labels = ["0-19", "20-39", "40-59", "60-79", "80+"];
    const colors = ["var(--error)", "var(--error)", "var(--gold)", "var(--gold)", "var(--accent)"];
    const peak = Math.max(...buckets) || 1;

    const w = 460, h = 200, baseY = h - 26, chartH = baseY - 30, slot = w / 5;
    const bars = buckets.map((count, i) => {
      const barH = chartH * (count / peak);
      const bx = i * slot + slot * 0.18, bw = slot * 0.64;
      const countLabel = count
        ? `<text x="${bx + bw / 2}" y="${baseY - barH - 8}" text-anchor="middle" class="chart-label">${count}</text>`
        : "";
      return `
        <rect x="${bx}" y="${baseY - barH}" width="${bw}" height="${barH}" rx="2" fill="${colors[i]}"></rect>
        ${countLabel}
        <text x="${bx + bw / 2}" y="${baseY + 16}" text-anchor="middle" class="chart-label dim">${labels[i]}</text>`;
    }).join("");

    confidenceEl.innerHTML = `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}">${bars}</svg>`;
  }

  function renderRecentRuns(stats) {
    const recent = [...(stats.recent || [])].reverse(); // oldest -> newest
    if (!recent.length) return emptyChart(recentEl, "No finished runs yet.");

    const rates = recent.map(r => (r.total ? r.elapsed / r.total : 0));
    const peak = Math.max(...rates) || 1;
    const w = 900, h = 200, baseY = h - 30, chartH = baseY - 30;
    const slot = w / Math.max(rates.length, 1);

    const points = rates.map((rate, i) => {
      const x = slot * (i + 0.5);
      const y = baseY - chartH * (rate / peak);
      return [x, y, recent[i].failed];
    });
    const line = points.map(([x, y]) => `${x},${y}`).join(" ");
    const dots = points.map(([x, y, failed]) =>
      `<circle cx="${x}" cy="${y}" r="3.5" fill="${failed ? "var(--error)" : "var(--accent)"}"></circle>`
    ).join("");

    recentEl.innerHTML = `
      <svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}">
        <polyline points="${line}" fill="none" stroke="var(--rule-dark)" stroke-width="2"></polyline>
        ${dots}
        <text x="0" y="${h - 4}" class="chart-label dim">oldest of last ${recent.length}</text>
        <text x="${w}" y="${h - 4}" text-anchor="end" class="chart-label dim">newest</text>
        <text x="${w}" y="16" text-anchor="end" class="chart-label dim">peak ${peak.toFixed(1)}s/doc</text>
      </svg>`;
  }

  async function refresh() {
    const stats = await api("GET", "/api/analytics/stats");
    renderTiles(stats);
    if (!stats.runs) {
      emptyChart(throughputEl, "No runs yet — process some files to see analytics.");
      emptyChart(confidenceEl, "No runs recorded yet.");
      emptyChart(recentEl, "No runs recorded yet.");
      return;
    }
    renderThroughput(stats);
    renderConfidenceHistogram(stats);
    renderRecentRuns(stats);
  }

  document.getElementById("btn-analytics-refresh").onclick = refresh;
  TAB_ACTIVATE.analytics = refresh;

  return { refresh };
})();
