// SPDX-FileCopyrightText: 2026 Maurice Casey
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/*
 * Review screen: approve/reject/edit each suggested change before it's
 * written to disk.
 *
 * This replaces `src/review.py`'s `cli_review()`, which blocks on `input()`
 * in a terminal loop — that cannot work inside a web server request, since
 * there is no terminal attached to answer it. The server instead stops the
 * run at `awaiting_review` and waits here for a second request
 * (`POST /api/run/{id}/review`) once the user has looked at every change.
 */

const ReviewUI = (function () {
  const list = document.getElementById("review-list");
  const card = document.getElementById("card-review");
  const countEl = document.getElementById("review-count");

  let items = [];
  let docId = null;

  function render() {
    const approved = items.filter(i => i.approved).length;
    countEl.textContent = `${approved} of ${items.length} approved`;

    list.innerHTML = items.map((item, i) => `
      <div class="review-item ${item.approved ? "" : "rejected"}">
        <div class="review-item-head">
          <span>Paragraph ${item.paragraph_index + 1}</span>
          <span>${escapeHtml(item.status)}</span>
        </div>
        <div class="review-item-body">
          <div class="original">${highlightRanges(item.original_text, item.diff.original_ranges)}</div>
          <textarea class="edited-text" data-i="${i}" rows="2">${escapeHtml(item.edited_text)}</textarea>
        </div>
        <div class="review-item-actions">
          <button class="btn ${item.approved ? "on" : ""}" data-action="approve" data-i="${i}">Approve</button>
          <button class="btn ${item.approved ? "" : "on"}" data-action="reject" data-i="${i}">Reject</button>
        </div>
      </div>
    `).join("");
  }

  list.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const i = parseInt(btn.dataset.i, 10);
    items[i].approved = btn.dataset.action === "approve";
    render();
  });

  list.addEventListener("input", (e) => {
    if (!e.target.classList.contains("edited-text")) return;
    items[parseInt(e.target.dataset.i, 10)].edited_text = e.target.value;
  });

  document.getElementById("btn-approve-all").addEventListener("click", () => {
    items.forEach(i => { i.approved = true; });
    render();
  });
  document.getElementById("btn-reject-all").addEventListener("click", () => {
    items.forEach(i => { i.approved = false; });
    render();
  });

  document.getElementById("btn-finalize").addEventListener("click", async () => {
    const decisions = items.map(i => ({
      paragraph_index: i.paragraph_index,
      approved: i.approved,
      replacement_text: i.approved ? i.edited_text : null,
    }));
    try {
      await api("POST", `/api/run/${docId}/review`, { decisions });
      card.style.display = "none";
      await PersonaeApp.onRunFinished(docId);
    } catch (err) {
      window.ArtificeToast.error("Could not finalize: " + err.message);
    }
  });

  async function open(id) {
    docId = id;
    const data = await api("GET", `/api/run/${id}/review`);
    items = data.items;

    if (!items.length) {
      // Nothing the model changed needs a human decision — finalize with no
      // decisions recorded, same as running with review disabled.
      await api("POST", `/api/run/${id}/review`, { decisions: [] });
      await PersonaeApp.onRunFinished(id);
      return;
    }

    card.style.display = "block";
    render();
  }

  return { open };
})();

window.ReviewUI = ReviewUI;
