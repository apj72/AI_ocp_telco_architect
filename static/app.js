// -- Modals --

function showModal(id) {
  document.getElementById(id).hidden = false;
  if (id === "settings-modal") loadBackups();
}

function hideModal(id) {
  document.getElementById(id).hidden = true;
}

document.addEventListener("click", (e) => {
  if (e.target.classList.contains("modal")) {
    e.target.hidden = true;
  }
});

// -- Toast --

function toast(msg, type = "success") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function toastPersist(msg) {
  const el = document.createElement("div");
  el.className = "toast info";
  el.textContent = msg;
  document.body.appendChild(el);
  return el; // caller calls el.remove() when done
}

// -- Tabs --

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach((p) => {
    const isActive = p.id === `tab-${name}`;
    p.classList.toggle("active", isActive);
    p.hidden = !isActive;
  });
  history.replaceState(null, "", `#${name}`);
}

// Restore tab from URL hash on page load
if (location.hash) {
  const tab = location.hash.slice(1);
  const tabBtn = document.querySelector(`.tab[data-tab="${tab}"]`);
  if (tabBtn) switchTab(tab);
}

// -- Resizable table columns --

function initResizableHeaders(root) {
  root.querySelectorAll("th.resizable").forEach(th => {
    if (th.querySelector(".col-resize-handle")) return;
    const handle = document.createElement("span");
    handle.className = "col-resize-handle";
    th.style.position = "relative";
    th.appendChild(handle);
    let startX, startW;
    handle.addEventListener("mousedown", e => {
      e.preventDefault();
      startX = e.clientX;
      startW = th.offsetWidth;
      const onMove = ev => { th.style.width = Math.max(60, startW + ev.clientX - startX) + "px"; };
      const onUp = () => { document.removeEventListener("mousemove", onMove); document.removeEventListener("mouseup", onUp); };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  });
}

// -- API helpers --

async function apiPost(url, data) {
  const fd = new FormData();
  for (const [k, v] of Object.entries(data)) {
    fd.set(k, v);
  }
  const r = await fetch(url, { method: "POST", body: fd });
  const json = await r.json();
  if (!r.ok) throw new Error(json.detail || "Request failed");
  return json;
}

async function apiPut(url, data) {
  const fd = new FormData();
  for (const [k, v] of Object.entries(data)) {
    fd.set(k, v);
  }
  const r = await fetch(url, { method: "PUT", body: fd });
  const json = await r.json();
  if (!r.ok) throw new Error(json.detail || "Request failed");
  return json;
}

async function apiDelete(url) {
  const r = await fetch(url, { method: "DELETE" });
  if (!r.ok) {
    const json = await r.json();
    throw new Error(json.detail || "Delete failed");
  }
}

// -- Dashboard: new partner --

const npForm = document.getElementById("new-partner-form");
if (npForm) {
  npForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = document.getElementById("new-partner-error");
    err.hidden = true;
    try {
      await apiPost("/api/partners", { name: npForm.elements.name.value });
      location.reload();
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
    }
  });
}

// -- Settings: Jira config --

function openJiraSettings(pid, name, config) {
  document.getElementById("settings-jira-partner-name").textContent = name;
  document.getElementById("settings-jira-pid").value = pid;
  const form = document.getElementById("settings-jira-form");
  const mode = config && config.jira_mode ? config.jira_mode : "mcp";
  for (const el of form.elements) {
    if (el.name === "jira_mode") {
      el.checked = el.value === mode;
    } else if (el.name && el.name !== "pid") {
      el.value = config && config[el.name] ? config[el.name] : "";
    }
  }
  toggleJiraMode();
  hideModal("settings-modal");
  showModal("settings-jira-modal");
}

function toggleJiraMode() {
  const mode = document.querySelector('#settings-jira-form input[name="jira_mode"]:checked').value;
  document.getElementById("jira-mcp-fields").hidden = mode !== "mcp";
  document.getElementById("jira-apikey-fields").hidden = mode !== "api_key";
}

const sjForm = document.getElementById("settings-jira-form");
if (sjForm) {
  sjForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = document.getElementById("settings-jira-error");
    err.hidden = true;
    const pid = document.getElementById("settings-jira-pid").value;
    try {
      const data = {};
      for (const el of sjForm.elements) {
        if (!el.name || el.name === "pid") continue;
        if (el.type === "radio" && !el.checked) continue;
        data[el.name] = el.value;
      }
      await apiPost(`/api/partners/${pid}/jira-config`, data);
      hideModal("settings-jira-modal");
      toast("Jira configuration saved");
      setTimeout(() => location.reload(), 500);
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
    }
  });
}

async function deletePartner(pid) {
  try {
    await apiDelete(`/api/partners/${pid}`);
    location.reload();
  } catch (ex) { toast(ex.message, "error"); }
}

// -- Output path directory browser --

// -- Backups --

async function loadBackups() {
  const el = document.getElementById("backup-list");
  if (!el) return;
  try {
    const r = await fetch("/api/backups");
    const data = await r.json();
    const rows = data.backups || [];
    if (!rows.length) { el.innerHTML = '<span class="muted">No backups yet.</span>'; return; }
    el.innerHTML = '<table class="data-table" style="font-size:0.78rem"><thead><tr><th>File</th><th>Size</th><th>Type</th><th>Created</th><th></th></tr></thead><tbody>' +
      rows.map(b => `<tr>
        <td>${esc(b.filename)}</td>
        <td>${b.size_mb} MB</td>
        <td>${esc(b.type)}</td>
        <td>${esc(b.created_at.slice(0, 16).replace("T", " "))}</td>
        <td><a href="/api/backups/${encodeURIComponent(b.filename)}" download class="btn small" style="text-decoration:none;font-size:0.7rem">Download</a></td>
      </tr>`).join("") + '</tbody></table>';
  } catch { el.innerHTML = '<span class="muted">Failed to load backups.</span>'; }
}

async function createBackup() {
  const t = toastPersist("Creating backup…");
  try {
    const r = await fetch("/api/backups", { method: "POST" });
    const data = await r.json();
    t.remove();
    if (!r.ok) { toast(data.detail || "Backup failed", "error"); return; }
    toast(`Backup created: ${data.filename} (${data.size_mb} MB)`);
    loadBackups();
  } catch (e) { t.remove(); toast(String(e), "error"); }
}

async function restoreBackup(input) {
  const file = input.files[0];
  input.value = "";
  if (!file) return;
  if (!confirm("This will replace ALL data (database and workspace) with the backup contents.\\n\\nA safety backup of the current state will be created first.\\n\\nContinue?")) return;
  const t = toastPersist("Restoring from backup…");
  try {
    const form = new FormData();
    form.append("file", file);
    const r = await fetch("/api/restore", { method: "POST", body: form });
    const data = await r.json();
    t.remove();
    if (!r.ok) { toast(data.detail || "Restore failed", "error"); return; }
    toast("Restored successfully — reloading…");
    setTimeout(() => location.reload(), 1500);
  } catch (e) { t.remove(); toast(String(e), "error"); }
}

let _dirBrowserPath = "";

async function loadOutputPathSetting() {
  const el = document.getElementById("output-path-display");
  if (!el) return;
  try {
    const r = await fetch("/api/settings/output-path");
    const data = await r.json();
    el.value = data.path;
  } catch { el.value = "(unknown)"; }
}

async function openDirBrowser() {
  const el = document.getElementById("output-path-display");
  const startPath = el ? el.value : "";
  hideModal("settings-modal");
  showModal("dir-browser-modal");
  await browseTo(startPath);
}

async function browseTo(path) {
  const listing = document.getElementById("dir-listing");
  const crumb = document.getElementById("dir-breadcrumb");
  listing.innerHTML = '<span class="muted">Loading...</span>';
  try {
    const r = await fetch(`/api/browse-dirs?path=${encodeURIComponent(path || "")}`);
    const data = await r.json();
    if (!data.current) {
      listing.innerHTML = '<span class="muted">Could not browse directory</span>';
      return;
    }
    _dirBrowserPath = data.current;

    // Breadcrumb
    const parts = data.current.split("/").filter(Boolean);
    let html = '<span class="dir-crumb-item" onclick="browseTo(\'/\')">/</span>';
    let accum = "";
    for (const p of parts) {
      accum += "/" + p;
      const escapedPath = accum.replace(/'/g, "\\'");
      html += `<span class="dir-crumb-sep">/</span><span class="dir-crumb-item" onclick="browseTo('${escapedPath}')">${esc(p)}</span>`;
    }
    crumb.innerHTML = html;

    // Directory list
    let items = "";
    if (data.parent !== null) {
      const escapedParent = data.parent.replace(/'/g, "\\'");
      items += `<div class="dir-entry" onclick="browseTo('${escapedParent}')"><span class="dir-icon">&#8593;</span> ..</div>`;
    }
    for (const d of data.dirs) {
      const escapedDir = d.path.replace(/'/g, "\\'");
      items += `<div class="dir-entry" onclick="browseTo('${escapedDir}')"><span class="dir-icon">&#128193;</span> ${esc(d.name)}</div>`;
    }
    if (!items && data.parent === null) {
      items = '<span class="muted">No subdirectories</span>';
    }
    listing.innerHTML = items;
  } catch (ex) {
    listing.innerHTML = `<span class="error">${esc(ex.message)}</span>`;
  }
}

async function selectDir() {
  if (!_dirBrowserPath) return;
  try {
    const r = await fetch("/api/settings/output-path", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: _dirBrowserPath }),
    });
    if (!r.ok) throw new Error("Failed to save");
    hideModal("dir-browser-modal");
    const el = document.getElementById("output-path-display");
    if (el) el.value = _dirBrowserPath;
    showModal("settings-modal");
    toast("Output directory updated");
  } catch (ex) {
    toast(ex.message, "error");
  }
}

// Load output path when settings modal exists
if (document.getElementById("output-path-display")) {
  loadOutputPathSetting();
}

function togglePartnerJiraMode() {
  const mode = document.querySelector('#jira-form input[name="jira_mode"]:checked').value;
  document.getElementById("partner-jira-mcp-fields").hidden = mode !== "mcp";
  document.getElementById("partner-jira-apikey-fields").hidden = mode !== "api_key";
}

// -- Partner page --

// -- Generic form submit helper --
function bindForm(formId, url, modalId) {
  const form = document.getElementById(formId);
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const data = {};
      for (const el of form.elements) {
        if (el.name) data[el.name] = el.value;
      }
      await apiPost(url, data);
      if (modalId) hideModal(modalId);
      location.reload();
    } catch (ex) {
      toast(ex.message, "error");
    }
  });
}

if (typeof PARTNER_ID !== "undefined") {
  // Topic form
  bindForm("add-topic-form", `/api/partners/${PARTNER_ID}/topics`, "add-topic-modal");

  // Knowledge form
  bindForm("add-knowledge-form", `/api/partners/${PARTNER_ID}/knowledge`, "add-knowledge-modal");

  // Jira config form
  const jiraForm = document.getElementById("jira-form");
  if (jiraForm) {
    jiraForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const err = document.getElementById("jira-error");
      err.hidden = true;
      try {
        const data = {};
        for (const el of jiraForm.elements) {
          if (!el.name) continue;
          if (el.type === "radio" && !el.checked) continue;
          data[el.name] = el.value;
        }
        await apiPost(`/api/partners/${PARTNER_ID}/jira-config`, data);
        hideModal("jira-modal");
        toast("Jira configuration saved");
        setTimeout(() => location.reload(), 500);
      } catch (ex) {
        err.textContent = ex.message;
        err.hidden = false;
      }
    });
  }

  // Add ticket form
  const atForm = document.getElementById("add-ticket-form");
  if (atForm) {
    atForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const data = {};
        for (const el of atForm.elements) {
          if (el.name) data[el.name] = el.value;
        }
        await apiPost(`/api/partners/${PARTNER_ID}/tickets`, data);
        hideModal("add-ticket-modal");
        location.reload();
      } catch (ex) {
        toast(ex.message, "error");
      }
    });
  }

  // Add domain form
  const adForm = document.getElementById("add-domain-form");
  if (adForm) {
    adForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const data = {};
        for (const el of adForm.elements) {
          if (el.name) data[el.name] = el.value;
        }
        await apiPost(`/api/partners/${PARTNER_ID}/domains`, data);
        hideModal("add-domain-modal");
        location.reload();
      } catch (ex) {
        toast(ex.message, "error");
      }
    });
  }

  // Add release form
  const arForm = document.getElementById("add-release-form");
  if (arForm) {
    arForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const data = {};
        for (const el of arForm.elements) {
          if (el.name) data[el.name] = el.value;
        }
        await apiPost(`/api/partners/${PARTNER_ID}/releases`, data);
        hideModal("add-release-modal");
        location.reload();
      } catch (ex) {
        toast(ex.message, "error");
      }
    });
  }

  // Add operator form
  const aoForm = document.getElementById("add-operator-form");
  if (aoForm) {
    aoForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const data = {};
        for (const el of aoForm.elements) {
          if (el.name) data[el.name] = el.value;
        }
        await apiPost(`/api/partners/${PARTNER_ID}/operators`, data);
        hideModal("add-operator-modal");
        location.reload();
      } catch (ex) {
        toast(ex.message, "error");
      }
    });
  }

}

// -- Actions --

async function deleteItem(type, id) {
  if (!confirm(`Delete this ${type.replace(/-/g, " ").slice(0, -1)}?`)) return;
  try {
    await apiDelete(`/api/${type}/${id}`);
    location.reload();
  } catch (ex) {
    toast(ex.message, "error");
  }
}

async function updateTicket(tid, field, value) {
  try {
    await apiPut(`/api/tickets/${tid}`, { [field]: value });
    toast("Updated");
  } catch (ex) {
    toast(ex.message, "error");
  }
}

async function doImport() {
  if (!confirm("Sync ECOPS tickets from Jira? This may take a moment.")) return;
  const ind = toastPersist("Syncing from Jira…");
  try {
    const result = await apiPost(`/api/partners/${PARTNER_ID}/import`, {});
    ind.remove();
    const parts = [`${result.imported} new`];
    if (result.updated) parts.push(`${result.updated} updated`);
    if (result.skipped) parts.push(`${result.skipped} unchanged`);
    toast(`Synced: ${parts.join(", ")}`);
    setTimeout(() => location.reload(), 1000);
  } catch (ex) {
    ind.remove();
    toast(ex.message, "error");
  }
}

async function doGenerate() {
  const ind = toastPersist("Generating skill…");
  try {
    const result = await apiPost(`/api/partners/${PARTNER_ID}/generate`, {});
    ind.remove();
    document.getElementById("gen-path").textContent = result.path;
    document.getElementById("gen-cmd").textContent = result.install_cmd;
    showModal("generate-modal");
  } catch (ex) {
    ind.remove();
    toast(ex.message, "error");
  }
}

// -- Topics --

async function expandTopic(tid) {
  const view = document.getElementById("topic-detail-view");
  const grid = document.getElementById("topic-grid");
  if (!view) return;

  try {
    const r = await fetch(`/api/topics/${tid}`);
    const topic = await r.json();

    const tierLabel = (t) => ["", "T1 RH", "T2 K8s", "T3 Partner", "T4"][t] || "T4";
    const tierClass = (t) => `t${t}`;

    let html = `
      <div class="topic-detail" data-tid="${tid}">
        <div class="topic-detail-head">
          <div>
            <h2>${esc(topic.title)}</h2>
            <p class="muted">${esc(topic.description || "")}</p>
          </div>
          <div class="topic-detail-actions">
            <select class="inline-select" onchange="updateTopicStatus('${tid}', this.value)">
              ${["open","in_progress","resolved","parked"].map(s =>
                `<option value="${s}" ${s===topic.status?"selected":""}>${s.replace("_"," ")}</option>`
              ).join("")}
            </select>
            <button class="btn small" onclick="closeTopicDetail()">Close</button>
          </div>
        </div>
        <div class="topic-sections">
          ${topic.interactions && topic.interactions.length ? `
          <div class="topic-section">
            <h3>Interaction Log <span class="muted" style="font-weight:normal">(${topic.interactions.length})</span></h3>
            <div class="interaction-list">
              ${topic.interactions.map((ix, idx) => `
                <div class="interaction-entry">
                  <div class="interaction-head">
                    <span class="interaction-time">${ix.started_at.slice(0,16).replace('T',' ')}</span>
                    <span class="route-badge ${ix.routed_by}">${ix.routed_by}</span>
                  </div>
                  <div class="interaction-prompt"><strong>User:</strong> ${esc(ix.prompt)}</div>
                  ${ix.response ? `
                    <details class="interaction-response" ${idx === topic.interactions.length - 1 ? 'open' : ''}>
                      <summary>OpenAI response (${ix.response.length} chars)</summary>
                      <div class="interaction-response-body">${esc(ix.response)}</div>
                    </details>
                  ` : '<div class="muted" style="font-size:0.8rem">Awaiting response...</div>'}
                </div>
              `).join("")}
            </div>
          </div>
          ` : ''}
          <div class="topic-section">
            <h3>Notes</h3>
            <div class="add-note-form">
              <textarea id="new-note-content" placeholder="Add a research note..."></textarea>
              <select id="new-note-type">
                <option value="research">Research</option>
                <option value="question">Question</option>
                <option value="answer">Answer</option>
                <option value="decision">Decision</option>
                <option value="reference">Reference</option>
                <option value="conversation">Conversation</option>
              </select>
              <button class="btn small primary" onclick="addNote('${tid}')">Add</button>
            </div>
            <div class="note-list">
              ${topic.notes.map(n => `
                <div class="note-entry ${n.note_type === 'conversation' ? 'conversation' : ''}">
                  <div class="note-head">
                    <span class="note-type ${n.note_type}">${n.note_type}</span>
                    <span class="note-time">${n.created_at.slice(0,16).replace('T',' ')}</span>
                  </div>
                  <div class="note-content">${esc(n.content)}</div>
                  <button class="btn-promote" onclick="promoteToKnowledge('${tid}', \`${esc(n.content).replace(/`/g,"\\`")}\`)">Save to knowledge</button>
                  <button class="btn-del" onclick="deleteNote('${n.id}', '${tid}')">×</button>
                </div>
              `).join("")}
            </div>
          </div>
          <div class="topic-section">
            <h3>Sources</h3>
            <div class="source-list">
              ${topic.sources.map(s => `
                <div class="source-entry-wrap">
                  <div class="source-entry">
                    <span class="tier-badge ${tierClass(s.source_tier)}">${tierLabel(s.source_tier)}</span>
                    <a href="${esc(s.url)}" target="_blank">${esc(s.title || s.url)}</a>
                    ${s.content_extract ? `<button class="btn small" onclick="toggleExtract('src-${s.id}')">Preview</button>` : ""}
                    <button class="btn small" onclick="refetchSource('${s.id}', '${tid}')">Refetch</button>
                    <button class="btn-del" onclick="deleteSource('${s.id}', '${tid}')">×</button>
                  </div>
                  ${s.content_extract ? `<div id="src-${s.id}" class="source-extract" hidden>${esc(s.content_extract.slice(0, 1000))}${s.content_extract.length > 1000 ? "…" : ""}</div>` : ""}
                </div>
              `).join("")}
            </div>
            <div class="inline-add">
              <input type="url" id="new-source-url" placeholder="Paste URL — auto-fetches content and detects tier">
              <input type="text" id="new-source-title" placeholder="Title (auto-detected)">
              <button class="btn small" onclick="addSource('${tid}')">Add &amp; Fetch</button>
            </div>
          </div>
          <div class="topic-section">
            <h3>Results</h3>
            <div class="result-list">
              ${(topic.results || []).map(r => {
                const link = r.file_path
                  ? `/workspace/topics/${tid}/results/${encodeURIComponent(r.file_path.split('/').pop())}`
                  : r.url;
                return `
                <div class="result-entry">
                  <span class="result-type-badge ${r.result_type}">${r.result_type}</span>
                  ${link ? `<a href="${esc(link)}" target="_blank">${esc(r.title)}</a>` : `<span>${esc(r.title)}</span>`}
                  ${r.description ? `<span class="muted" style="font-size:0.8rem"> — ${esc(r.description)}</span>` : ""}
                  <button class="btn-del" onclick="deleteResult('${r.id}', '${tid}')">×</button>
                </div>`;
              }).join("")}
            </div>
            <div class="inline-add">
              <input type="text" id="new-result-title" placeholder="Result title">
              <select id="new-result-type">
                <option value="document">Document</option>
                <option value="presentation">Presentation</option>
                <option value="link">Link</option>
                <option value="answer">Answer</option>
                <option value="report">Report</option>
              </select>
              <input type="text" id="new-result-url" placeholder="URL or file path">
              <button class="btn small" onclick="addResult('${tid}')">Add</button>
            </div>
          </div>
          <div class="topic-section">
            <h3>Linked Tickets</h3>
            <div class="ticket-list">
              ${topic.tickets.map(t => `
                <div class="ticket-entry">
                  <span class="mono">${esc(t.ticket_key)}</span>
                  ${t.summary ? `<span class="jira-summary">${esc(t.summary)}</span>` : ""}
                  ${t.jira_status ? `<span class="jira-status-badge">${esc(t.jira_status)}</span>` : ""}
                  <span class="rel-badge">${t.relationship}</span>
                  ${topic.jira_configured && topic.jira_mode === "api_key" ?
                    `<button class="btn small" onclick="reviewTicket('${topic.partner_id}', '${esc(t.ticket_key)}', '${tid}')">Review</button>` : ""}
                  <button class="btn-del" onclick="unlinkTicket('${t.id}', '${tid}')">×</button>
                </div>
              `).join("")}
            </div>
            <div class="inline-add">
              <input type="text" id="new-ticket-key" placeholder="e.g. ECOPS-502">
              <select id="new-ticket-rel">
                <option value="related">Related</option><option value="created">Created</option>
                <option value="blocking">Blocking</option><option value="resolved_by">Resolved by</option>
              </select>
              <button class="btn small" onclick="linkTicket('${tid}')">Link</button>
            </div>
            ${topic.jira_configured && topic.jira_mode === "api_key" ? `
            <div class="jira-search-bar">
              <input type="text" id="jira-search-query" placeholder="Search Jira...">
              <button class="btn small" onclick="searchJira('${topic.partner_id}', '${tid}')">Search</button>
              <button class="btn small primary" onclick="openJiraCreate('${topic.partner_id}', '${tid}')">Create Ticket</button>
            </div>
            <div id="jira-search-results" class="jira-results" hidden></div>
            ` : topic.jira_configured && topic.jira_mode === "mcp" ? `
            <p class="muted" style="margin-top:0.5rem;font-size:0.78rem">Jira is in MCP mode — use the OpenAI Architect for live search/create</p>
            ` : ""}
            <div id="jira-review-container"></div>
          </div>
        </div>
        <div class="topic-danger-zone">
          <a href="#" onclick="event.preventDefault(); deleteTopic('${tid}')">Delete this topic</a>
        </div>
      </div>`;

    view.innerHTML = html;
    view.hidden = false;
    if (grid) grid.hidden = true;
  } catch (ex) {
    toast(ex.message, "error");
  }
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function closeTopicDetail() {
  const view = document.getElementById("topic-detail-view");
  const grid = document.getElementById("topic-grid");
  if (view) view.hidden = true;
  if (grid) grid.hidden = false;
}

async function refreshTopics() {
  try {
    const topics = await fetch(`/api/partners/${PARTNER_ID}/topics`).then(r => r.json());
    const grid = document.getElementById("topic-grid");
    if (!grid) return;
    if (!topics.length) {
      grid.innerHTML = '<p class="muted">No topics yet. Create a topic to start tracking research.</p>';
      return;
    }
    grid.innerHTML = topics.map(t => `
      <div class="topic-card" data-status="${esc(t.status)}" onclick="expandTopic('${t.id}')">
        <div class="topic-card-head">
          <h3>${esc(t.title)}</h3>
          <span class="topic-status ${esc(t.status)}">${esc(t.status.replace('_', ' '))}</span>
        </div>
        ${t.description ? `<p class="topic-desc">${esc(t.description)}</p>` : ''}
        <div class="topic-card-meta">
          <span>${t.note_count || 0} notes</span>
          <span>${(t.created_at || '').slice(0, 10)}</span>
          <a href="/partner/${PARTNER_SLUG}/topics/${t.id}" target="_blank" class="open-tab-link" onclick="event.stopPropagation()" title="Open in new tab">&#x2197;</a>
        </div>
      </div>
    `).join('');
    const view = document.getElementById("topic-detail-view");
    if (view && !view.hidden) {
      const tid = view.querySelector('.topic-detail')?.dataset?.tid;
      if (tid) expandTopic(tid);
    }
    toast("Topics refreshed");
  } catch (ex) { toast(ex.message, "error"); }
}

async function updateTopicStatus(tid, status) {
  try {
    await apiPut(`/api/topics/${tid}`, { status });
    toast("Status updated");
  } catch (ex) { toast(ex.message, "error"); }
}

async function deleteTopic(tid) {
  if (!confirm("Delete this topic and all its notes?")) return;
  try {
    await apiDelete(`/api/topics/${tid}`);
    location.reload();
  } catch (ex) { toast(ex.message, "error"); }
}

async function addNote(tid) {
  const content = document.getElementById("new-note-content").value.trim();
  const noteType = document.getElementById("new-note-type").value;
  if (!content) return;
  try {
    await apiPost(`/api/topics/${tid}/notes`, { content, note_type: noteType });
    expandTopic(tid);
  } catch (ex) { toast(ex.message, "error"); }
}

async function deleteNote(nid, tid) {
  try {
    await apiDelete(`/api/topic-notes/${nid}`);
    expandTopic(tid);
  } catch (ex) { toast(ex.message, "error"); }
}

async function addSource(tid) {
  const url = document.getElementById("new-source-url").value.trim();
  if (!url) return;
  const title = document.getElementById("new-source-title").value.trim();
  try {
    toast("Fetching content...");
    await apiPost(`/api/topics/${tid}/sources`, { url, title });
    expandTopic(tid);
  } catch (ex) { toast(ex.message, "error"); }
}

function toggleExtract(id) {
  const el = document.getElementById(id);
  if (el) el.hidden = !el.hidden;
}

async function refetchSource(sid, tid) {
  try {
    toast("Refetching...");
    await apiPost(`/api/topic-sources/${sid}/fetch`, {});
    toast("Content updated");
    expandTopic(tid);
  } catch (ex) { toast(ex.message, "error"); }
}

async function deleteSource(sid, tid) {
  try {
    await apiDelete(`/api/topic-sources/${sid}`);
    expandTopic(tid);
  } catch (ex) { toast(ex.message, "error"); }
}

async function addResult(tid) {
  const title = document.getElementById("new-result-title").value.trim();
  if (!title) return;
  const result_type = document.getElementById("new-result-type").value;
  const url = document.getElementById("new-result-url").value.trim();
  try {
    await apiPost(`/api/topics/${tid}/results`, { title, result_type, url });
    expandTopic(tid);
  } catch (ex) { toast(ex.message, "error"); }
}

async function deleteResult(rid, tid) {
  try {
    await apiDelete(`/api/topic-results/${rid}`);
    expandTopic(tid);
  } catch (ex) { toast(ex.message, "error"); }
}

function toggleConfigMenu() {
  const menu = document.getElementById("config-menu");
  if (menu) menu.hidden = !menu.hidden;
}

document.addEventListener("click", (e) => {
  const menu = document.getElementById("config-menu");
  if (menu && !menu.hidden && !e.target.closest(".config-dropdown")) {
    menu.hidden = true;
  }
});

async function linkTicket(tid) {
  const key = document.getElementById("new-ticket-key").value.trim();
  if (!key) return;
  const rel = document.getElementById("new-ticket-rel").value;
  try {
    await apiPost(`/api/topics/${tid}/tickets`, { ticket_key: key, relationship: rel });
    expandTopic(tid);
  } catch (ex) { toast(ex.message, "error"); }
}

async function unlinkTicket(ltid, tid) {
  try {
    await apiDelete(`/api/topic-tickets/${ltid}`);
    expandTopic(tid);
  } catch (ex) { toast(ex.message, "error"); }
}

function promoteToKnowledge(topicId, content) {
  const form = document.getElementById("add-knowledge-form");
  if (!form) return;
  form.elements.fact.value = content.slice(0, 200);
  form.elements.detail.value = content.length > 200 ? content : "";
  form.elements.topic_id.value = topicId;
  showModal("add-knowledge-modal");
}

// -- OCP Versions --

async function fetchOcpVersions() {
  const panel = document.getElementById("ocp-versions-panel");
  panel.hidden = false;
  panel.innerHTML = '<span class="muted">Fetching from OpenShift API...</span>';
  try {
    const r = await fetch("/api/ocp-versions");
    const versions = await r.json();
    if (!versions.length) {
      panel.innerHTML = '<span class="muted">No versions found</span>';
      return;
    }
    panel.innerHTML = `
      <div class="ocp-versions-grid">
        ${versions.map(v => `
          <div class="ocp-version-card">
            <h4>
              OCP ${esc(v.minor)}
              ${v.eus ? '<span class="release-status eus">EUS</span>' : '<span class="release-status ga">GA</span>'}
            </h4>
            <div class="ocp-meta">
              <span>Latest: ${esc(v.latest_z)}</span>
              <span>GA: ${esc(v.ga_date || '?')}</span>
              <span>EOL: ${esc(v.eol_date || '?')}</span>
              <span>${v.z_count} z-streams</span>
            </div>
            <div style="display:flex;gap:0.4rem">
              <button class="btn small" onclick="addOcpRelease('${esc(v.minor)}', '${esc(v.ga_date)}', '${esc(v.eol_date)}', '${esc(v.doc_url)}', ${v.eus})">Add as Release</button>
              <a href="${esc(v.doc_url)}" target="_blank" class="btn small">Docs</a>
            </div>
          </div>
        `).join("")}
      </div>`;
  } catch (ex) { toast(ex.message, "error"); }
}

async function addOcpRelease(minor, gaDate, eolDate, docUrl, eus) {
  try {
    await apiPost(`/api/partners/${PARTNER_ID}/releases`, {
      release_name: minor,
      ocp_version: minor,
      ga_date: gaDate,
      eol_date: eolDate,
      doc_url: docUrl,
      release_status: eus ? "eus" : "ga",
    });
    toast(`Added OCP ${minor}`);
    setTimeout(() => location.reload(), 500);
  } catch (ex) { toast(ex.message, "error"); }
}

// -- Filters --

function filterTopics(status, btn) {
  document.querySelectorAll("#tab-topics .filter-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  document.querySelectorAll(".topic-card").forEach(card => {
    card.style.display = (status === "all" || card.dataset.status === status) ? "" : "none";
  });
}

function filterKnowledge(category, btn) {
  document.querySelectorAll("#tab-knowledge .filter-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  document.querySelectorAll("#knowledge-table tbody tr").forEach(row => {
    row.style.display = (category === "all" || row.dataset.category === category) ? "" : "none";
  });
}

// -- Jira Live --

let _currentTopicId = null;

async function searchJira(pid, tid) {
  const q = document.getElementById("jira-search-query").value.trim();
  if (!q) return;
  const container = document.getElementById("jira-search-results");
  container.hidden = false;
  container.innerHTML = '<span class="muted">Searching...</span>';
  try {
    const results = await apiPost(`/api/partners/${pid}/jira-search`, { query: q });
    if (!results.length) {
      container.innerHTML = '<span class="muted">No results</span>';
      return;
    }
    container.innerHTML = results.map(r => `
      <div class="jira-result">
        <span class="mono">${esc(r.key)}</span>
        <span class="jira-summary">${esc(r.summary)}</span>
        <span class="jira-status-badge">${esc(r.status)}</span>
        <span class="jira-assignee">${esc(r.assignee)}</span>
        <button class="btn small" onclick="linkFromSearch('${tid}', '${esc(r.key)}', '${esc(r.url)}', \`${esc(r.summary).replace(/`/g,"\\`")}\`, '${esc(r.status)}')">Link</button>
        <button class="btn small" onclick="reviewTicket('${pid}', '${esc(r.key)}', '${tid}')">Review</button>
      </div>
    `).join("");
  } catch (ex) { toast(ex.message, "error"); }
}

async function linkFromSearch(tid, key, url, summary, status) {
  try {
    await apiPost(`/api/topics/${tid}/tickets`, {
      ticket_key: key, ticket_url: url, relationship: "related",
      summary: summary, jira_status: status
    });
    expandTopic(tid);
  } catch (ex) { toast(ex.message, "error"); }
}

async function reviewTicket(pid, key, tid) {
  _currentTopicId = tid;
  const container = document.getElementById("jira-review-container");
  container.innerHTML = '<span class="muted">Loading...</span>';
  try {
    const r = await fetch(`/api/partners/${pid}/jira/issue/${key}`);
    if (!r.ok) throw new Error((await r.json()).detail || "Failed");
    const issue = await r.json();
    container.innerHTML = `
      <div class="jira-review-panel">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <h4>${esc(issue.key)}: ${esc(issue.summary)}</h4>
          <button class="btn-del" onclick="closeReview()">×</button>
        </div>
        <div class="jira-review-meta">
          <span>Status: <strong>${esc(issue.status)}</strong></span>
          <span>Priority: ${esc(issue.priority || "—")}</span>
          <span>Assignee: ${esc(issue.assignee || "Unassigned")}</span>
          <span>Reporter: ${esc(issue.reporter || "—")}</span>
          ${issue.resolution ? `<span>Resolution: ${esc(issue.resolution)}</span>` : ""}
          <span>Updated: ${esc(issue.updated)}</span>
        </div>
        ${issue.description ? `<div class="jira-review-desc">${esc(issue.description)}</div>` : ""}
        ${issue.comments.length ? `
          <div class="jira-comments-head">Comments (${issue.comments.length})</div>
          ${issue.comments.map(c => `
            <div class="jira-comment">
              <div class="jira-comment-meta">${esc(c.author)} · ${esc(c.created)}</div>
              <div>${esc(c.body)}</div>
            </div>
          `).join("")}
        ` : ""}
        <div class="jira-review-actions">
          <button class="btn small" onclick="saveReviewAsNote('${tid}', '${esc(issue.key)}', \`${esc(issue.summary).replace(/`/g,"\\`")}\`)">Save as Note</button>
          <a href="${esc(issue.url)}" target="_blank" class="btn small">Open in Jira</a>
        </div>
      </div>`;
  } catch (ex) {
    container.innerHTML = "";
    toast(ex.message, "error");
  }
}

function closeReview() {
  document.getElementById("jira-review-container").innerHTML = "";
}

async function saveReviewAsNote(tid, key, summary) {
  try {
    await apiPost(`/api/topics/${tid}/notes`, {
      content: `Jira review: ${key} — ${summary}`,
      note_type: "reference"
    });
    toast("Saved as note");
    expandTopic(tid);
  } catch (ex) { toast(ex.message, "error"); }
}

function openJiraCreate(pid, tid) {
  _currentTopicId = tid;
  document.getElementById("jira-create-pid").value = pid;
  document.getElementById("jira-create-tid").value = tid;
  showModal("jira-create-modal");
}

const jcForm = document.getElementById("jira-create-form");
if (jcForm) {
  jcForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = document.getElementById("jira-create-error");
    err.hidden = true;
    const pid = document.getElementById("jira-create-pid").value;
    const tid = document.getElementById("jira-create-tid").value;
    try {
      const result = await apiPost(`/api/partners/${pid}/jira-create`, {
        summary: jcForm.elements.summary.value,
        description: jcForm.elements.description.value,
        issue_type: jcForm.elements.issue_type.value,
      });
      await apiPost(`/api/topics/${tid}/tickets`, {
        ticket_key: result.key, ticket_url: result.url,
        relationship: "created", summary: jcForm.elements.summary.value, jira_status: "Open"
      });
      hideModal("jira-create-modal");
      jcForm.reset();
      toast(`Created ${result.key}`);
      expandTopic(tid);
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
    }
  });
}

// -- Doc Sources --

if (typeof PARTNER_ID !== "undefined") {
  const dsForm = document.getElementById("add-doc-source-form");
  if (dsForm) {
    dsForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const statusEl = document.getElementById("doc-source-status");
      const btn = document.getElementById("add-doc-source-btn");
      statusEl.textContent = "Opening browser for login... Complete SSO in the browser window.";
      statusEl.hidden = false;
      btn.disabled = true;
      try {
        await apiPost(`/api/partners/${PARTNER_ID}/doc-sources/add-with-auth`, {
          url: dsForm.elements.url.value,
          name: dsForm.elements.name.value,
        });
        hideModal("add-doc-source-modal");
        toast("Doc source added with authentication");
        setTimeout(() => location.reload(), 500);
      } catch (ex) {
        statusEl.hidden = true;
        toast(ex.message, "error");
      } finally {
        btn.disabled = false;
      }
    });
  }
}

async function deleteDocSource(dsid) {
  if (!confirm("Delete this document source?")) return;
  try {
    await apiDelete(`/api/doc-sources/${dsid}`);
    toast("Doc source deleted");
    setTimeout(() => location.reload(), 500);
  } catch (ex) { toast(ex.message, "error"); }
}

async function browseDocSource(dsid, subPath = "") {
  const container = document.getElementById(`browse-${dsid}`);
  container.hidden = false;
  container.innerHTML = '<span class="muted">Browsing...</span>';
  try {
    const result = await apiPost(`/api/doc-sources/${dsid}/browse`, { sub_path: subPath });
    if (result.needs_reauth) {
      container.innerHTML = `
        <div style="padding:0.5rem 0">
          <p class="error" style="margin:0 0 0.5rem">Authentication expired. Please log in again.</p>
          <button class="btn primary small" onclick="reauthDocSource('${result.auth_source_id}', '${dsid}')">Re-authenticate</button>
        </div>`;
      return;
    }
    if (result.errors && result.errors.length) {
      container.innerHTML = `<p class="error">${esc(result.errors.join("; "))}</p>`;
      return;
    }
    let html = "";
    if (subPath) {
      const segments = subPath.split("/");
      let crumbs = `<a onclick="browseDocSource('${dsid}', '')">root</a>`;
      for (let i = 0; i < segments.length; i++) {
        const partial = segments.slice(0, i + 1).join("/");
        if (i < segments.length - 1) {
          crumbs += ` / <a onclick="browseDocSource('${dsid}', '${esc(partial)}')">${esc(segments[i])}</a>`;
        } else {
          crumbs += ` / ${esc(segments[i])}`;
        }
      }
      html += `<div class="doc-browse-path">${crumbs}</div>`;
    }
    if (result.folders && result.folders.length) {
      html += result.folders.map(f => `
        <div class="doc-browse-item">
          <span class="doc-icon">📁</span>
          <span class="doc-name"><a onclick="browseDocSource('${dsid}', '${esc(f.url || f.name)}')">${esc(f.name)}</a></span>
          ${f.items ? `<span class="doc-meta">${f.items} items</span>` : ""}
          <button class="btn small" onclick="learnFolder('${dsid}', '${esc(f.url || f.name)}', ${f.items || 0})">Learn</button>
        </div>
      `).join("");
    }
    if (result.files && result.files.length) {
      html += `<div style="margin:0.3rem 0">
        <button class="btn primary small" onclick="learnFolder('${dsid}', '${esc(subPath)}', ${result.files.length})">Learn new (${result.files.length} files)</button>
        <button class="btn small" onclick="learnFolder('${dsid}', '${esc(subPath)}', ${result.files.length}, false)" style="margin-left:0.3rem">Re-learn all</button>
      </div>`;
      html += result.files.map(f => {
        const size = f.size ? `${(f.size / 1024).toFixed(0)} KB` : "";
        const mod = f.modified ? f.modified.slice(0, 10) : "";
        return `
          <div class="doc-browse-item">
            <span class="doc-icon">${fileIcon(f.name)}</span>
            <span class="doc-name"><a href="${esc(f.url)}" target="_blank">${esc(f.name)}</a></span>
            <span class="doc-meta">${[size, mod].filter(Boolean).join(" · ")}</span>
            <button class="btn small" onclick="addDocToTopic('${esc(f.url)}', '${esc(f.name)}')">+ Topic</button>
          </div>`;
      }).join("");
    }
    if (!result.files.length && !result.folders.length) {
      html = '<span class="muted">No files found</span>';
    }
    container.innerHTML = html;
  } catch (ex) { toast(ex.message, "error"); }
}

async function reauthDocSource(authSourceId, dsid) {
  const container = document.getElementById(`browse-${dsid}`);
  container.innerHTML = '<span class="muted">Opening browser for re-authentication...</span>';
  try {
    await apiPost(`/api/auth-sources/${authSourceId}/recapture`, {});
    toast("Re-authenticated successfully");
    browseDocSource(dsid);
  } catch (ex) {
    toast(ex.message, "error");
    container.innerHTML = `<p class="error">Re-authentication failed: ${esc(ex.message)}</p>`;
  }
}

async function learnFolder(dsid, folderPath, fileCount, incremental = true) {
  const container = document.getElementById(`browse-${dsid}`);
  const origHtml = container.innerHTML;
  container.innerHTML = `<div class="learn-progress"><span class="muted">Scanning folders...</span></div>`;
  const prog = container.querySelector(".learn-progress");
  try {
    const body = new URLSearchParams({ folder_path: folderPath, incremental: incremental ? "true" : "false" });
    const resp = await fetch(`/api/doc-sources/${dsid}/learn`, { method: "POST", body });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let finalResult = null;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const ev = JSON.parse(line);
        if (ev.type === "scanning") {
          prog.innerHTML = `<span class="muted">Scanning: ${esc(ev.folder)}...</span>`;
        } else if (ev.type === "start") {
          let msg = `Found ${ev.total} new files.`;
          if (ev.skipped_existing) msg += ` ${ev.skipped_existing} already learned.`;
          msg += " Starting extraction...";
          prog.innerHTML = `<span class="muted">${msg}</span>`;
        } else if (ev.type === "progress") {
          const pct = Math.round((ev.current / ev.total) * 100);
          prog.innerHTML = `
            <div style="margin-bottom:0.3rem"><strong>${ev.current}/${ev.total}</strong> (${pct}%) — ${esc(ev.name)}</div>
            <div style="background:#333;border-radius:4px;height:6px;overflow:hidden">
              <div style="background:var(--accent,#4dabf7);height:100%;width:${pct}%;transition:width 0.3s"></div>
            </div>`;
        } else if (ev.type === "auth_error") {
          prog.innerHTML = `
            <p class="error" style="margin:0 0 0.5rem">Authentication expired.</p>
            <button class="btn primary small" onclick="reauthDocSource('${ev.auth_source_id}', '${dsid}')">Re-authenticate</button>`;
          return;
        } else if (ev.type === "done") {
          finalResult = ev;
        }
      }
    }
    if (finalResult) {
      let msg = `Learned ${finalResult.learned} documents`;
      if (finalResult.skipped_existing) msg += `, ${finalResult.skipped_existing} already known`;
      if (finalResult.skipped) msg += `, ${finalResult.skipped} errors`;
      toast(msg);
      if (finalResult.errors && finalResult.errors.length) {
        console.warn("Learn errors:", finalResult.errors);
      }
      refreshLearnedBadge(dsid);
    }
    container.innerHTML = origHtml;
  } catch (ex) {
    toast(ex.message, "error");
    container.innerHTML = origHtml;
  }
}

async function refreshLearnedBadge(dsid) {
  try {
    const docs = await fetch(`/api/doc-sources/${dsid}/learned`).then(r => r.json());
    const badge = document.getElementById(`learned-badge-${dsid}`);
    if (badge) {
      badge.className = "skill-badge generated";
      badge.textContent = `${docs.length} docs learned`;
    }
  } catch (e) { /* ignore */ }
}

async function viewLearned(dsid) {
  const container = document.getElementById(`browse-${dsid}`);
  container.hidden = false;
  container.innerHTML = '<span class="muted">Loading learned docs...</span>';
  try {
    const docs = await fetch(`/api/doc-sources/${dsid}/learned`).then(r => r.json());
    if (!docs.length) {
      container.innerHTML = '<span class="muted">No learned documents.</span>';
      return;
    }
    let html = `<div style="margin-bottom:0.5rem;display:flex;justify-content:space-between;align-items:center">
      <span class="muted">${docs.length} learned documents</span>
      <button class="btn small" onclick="browseDocSource('${dsid}')">Back to browse</button>
    </div>`;
    html += `<table class="data-table"><thead><tr><th>Name</th><th>Folder</th><th>Size</th><th>Learned</th><th></th></tr></thead><tbody>`;
    for (const d of docs) {
      const size = d.file_size ? `${(d.file_size / 1024).toFixed(0)} KB` : "—";
      const date = d.learned_at ? d.learned_at.slice(0, 16).replace("T", " ") : "—";
      html += `<tr>
        <td><a href="${esc(d.url)}" target="_blank" style="color:var(--accent);text-decoration:none">${esc(d.name)}</a></td>
        <td class="mono" style="font-size:0.75rem">${esc(d.folder_path)}</td>
        <td class="mono" style="font-size:0.75rem">${size}</td>
        <td class="mono" style="font-size:0.75rem">${date}</td>
        <td><button class="btn-del" onclick="deleteLearned('${d.id}', '${dsid}')">×</button></td>
      </tr>`;
    }
    html += "</tbody></table>";
    container.innerHTML = html;
  } catch (ex) {
    container.innerHTML = `<p class="error">${esc(ex.message)}</p>`;
  }
}

async function deleteLearned(lid, dsid) {
  await fetch(`/api/learned-docs/${lid}`, { method: "DELETE" });
  viewLearned(dsid);
  refreshLearnedBadge(dsid);
}

function fileIcon(name) {
  const ext = name.split(".").pop().toLowerCase();
  if (["pdf"].includes(ext)) return "📄";
  if (["doc", "docx"].includes(ext)) return "📝";
  if (["xls", "xlsx"].includes(ext)) return "📊";
  if (["ppt", "pptx"].includes(ext)) return "📋";
  if (["png", "jpg", "jpeg", "gif"].includes(ext)) return "🖼️";
  return "📎";
}

function addDocToTopic(url, title) {
  // Pre-fill the topic source add form in the currently expanded topic
  const view = document.getElementById("topic-detail-view");
  if (view && !view.hidden) {
    const urlInput = document.getElementById("new-source-url");
    const titleInput = document.getElementById("new-source-title");
    if (urlInput) urlInput.value = url;
    if (titleInput) titleInput.value = title;
    switchTab("topics");
    toast("URL copied to topic source form — click Add & Fetch");
    return;
  }
  // No topic open — copy to clipboard
  navigator.clipboard.writeText(url).then(() => {
    toast("URL copied — open a topic and paste as source");
  }).catch(() => {
    toast(`URL: ${url}`, "success");
  });
}

// -- Processing Queue --

function _renderFolderGroupedDocs(docs, renderActions) {
  const folders = {};
  for (const d of docs) {
    const fp = d.folder_path || "(root)";
    (folders[fp] = folders[fp] || []).push(d);
  }
  let html = "";
  for (const fp of Object.keys(folders).sort()) {
    const shortName = fp.split("/").pop() || fp;
    const fDocs = folders[fp];
    html += `<details class="queue-folder" open>
      <summary class="queue-folder-head"><span class="folder-icon">&#x1F4C1;</span> ${esc(shortName)} <span class="muted">(${fDocs.length})</span>
        <span class="queue-folder-path muted mono">${esc(fp)}</span></summary>
      <table class="data-table queue-table"><thead><tr><th class="resizable">Name</th><th>Size</th><th>Modified</th><th>Learned</th><th></th></tr></thead><tbody>`;
    for (const d of fDocs) {
      const size = d.file_size ? `${(d.file_size / 1024).toFixed(0)} KB` : "—";
      const modified = d.modified_at ? d.modified_at.slice(0, 10) : "—";
      const learned = d.learned_at ? d.learned_at.slice(0, 10) : "—";
      html += `<tr id="doc-row-${d.id}">
        <td><a href="${esc(d.url)}" target="_blank" style="color:var(--accent);text-decoration:none">${esc(d.name)}</a></td>
        <td class="mono" style="font-size:0.75rem">${size}</td>
        <td class="mono" style="font-size:0.75rem">${modified}</td>
        <td class="mono" style="font-size:0.75rem">${learned}</td>
        <td style="white-space:nowrap">${renderActions(d)}</td>
      </tr>`;
    }
    html += "</tbody></table></details>";
  }
  return html;
}

async function showQueue() {
  const container = document.getElementById("queue-container");
  const pqc = document.getElementById("processing-queue-container");
  if (!container) return;
  if (pqc) pqc.hidden = true;
  container.hidden = false;
  container.innerHTML = '<span class="muted">Loading...</span>';
  try {
    const docs = await fetch(`/api/partners/${PARTNER_ID}/learned-docs/queue?status=backlog`).then(r => r.json());
    let html = `<div class="queue-head">
      <h3>Review Queue</h3>
      <button class="btn small" onclick="hideQueue()">Close</button>
    </div>`;
    if (!docs.length) {
      html += `<p class="muted">No documents awaiting review.</p>`;
    } else {
      html += `<p class="muted" style="margin-bottom:0.5rem">${docs.length} documents to review. Click Approve or Ignore — the button changes colour to confirm your choice.</p>`;
      html += _renderFolderGroupedDocs(docs, d =>
        `<button class="btn small" id="btn-approve-${d.id}" onclick="markDoc('${d.id}', 'approved')">Approve</button>
         <button class="btn small" id="btn-ignore-${d.id}" onclick="markDoc('${d.id}', 'ignored')">Ignore</button>`
      );
    }
    container.innerHTML = html;
    requestAnimationFrame(() => initResizableHeaders(container));
  } catch (ex) { toast(ex.message, "error"); }
}

async function markDoc(lid, status) {
  const approveBtn = document.getElementById(`btn-approve-${lid}`);
  const ignoreBtn = document.getElementById(`btn-ignore-${lid}`);
  if (!approveBtn || !ignoreBtn) return;
  try {
    await apiPut(`/api/learned-docs/${lid}/status`, { status });
    // Reset both buttons to neutral first
    approveBtn.classList.remove("queue-decided-approve", "queue-decided-ignore");
    ignoreBtn.classList.remove("queue-decided-approve", "queue-decided-ignore");
    if (status === "approved") {
      approveBtn.classList.add("queue-decided-approve");
      ignoreBtn.classList.remove("queue-decided-ignore");
    } else {
      ignoreBtn.classList.add("queue-decided-ignore");
      approveBtn.classList.remove("queue-decided-approve");
    }
    refreshQueueBadge();
  } catch (ex) { toast(ex.message, "error"); }
}

function hideQueue() {
  const c = document.getElementById("queue-container");
  if (c) { c.hidden = true; c.innerHTML = ""; }
}

async function showProcessingQueue() {
  const container = document.getElementById("processing-queue-container");
  const qc = document.getElementById("queue-container");
  if (!container) return;
  if (qc) qc.hidden = true;
  container.hidden = false;
  container.innerHTML = '<span class="muted">Loading...</span>';
  try {
    const docs = await fetch(`/api/partners/${PARTNER_ID}/learned-docs/queue?status=approved`).then(r => r.json());
    let html = `<div class="queue-head">
      <h3>Processing Queue <span class="muted" style="font-weight:normal;font-size:0.85rem">(${docs.length} approved)</span></h3>
      <button class="btn small" onclick="hideProcessingQueue()">Close</button>
    </div>`;
    if (!docs.length) {
      html += `<p class="muted">No approved documents. Use Review Queue to approve documents for processing.</p>`;
    } else {
      html += _renderFolderGroupedDocs(docs, d =>
        `<button class="btn small" onclick="setDocStatus('${d.id}', 'backlog')">Back to review</button>`
      );
    }
    container.innerHTML = html;
    requestAnimationFrame(() => initResizableHeaders(container));
  } catch (ex) { toast(ex.message, "error"); }
}

function hideProcessingQueue() {
  const c = document.getElementById("processing-queue-container");
  if (c) { c.hidden = true; c.innerHTML = ""; }
}

async function setDocStatus(lid, status) {
  try {
    await apiPut(`/api/learned-docs/${lid}/status`, { status });
    // Refresh whichever view is open
    const qc = document.getElementById("queue-container");
    const pqc = document.getElementById("processing-queue-container");
    if (qc && !qc.hidden) showQueue();
    if (pqc && !pqc.hidden) showProcessingQueue();
    refreshQueueBadge();
  } catch (ex) { toast(ex.message, "error"); }
}

async function refreshQueueBadge() {
  try {
    const docs = await fetch(`/api/partners/${PARTNER_ID}/learned-docs/queue?status=backlog`).then(r => r.json());
    const badge = document.getElementById("queue-badge");
    if (badge) badge.textContent = docs.length || "";
  } catch (e) { /* ignore */ }
}

// -- Knowledge Review --

async function setKnowledgeStatus(kid, status) {
  try {
    await apiPut(`/api/knowledge/${kid}`, { status });
    toast(`Knowledge → ${status}`);
    location.reload();
  } catch (ex) { toast(ex.message, "error"); }
}

function filterKnowledgeStatus(status, btn) {
  document.querySelectorAll("#knowledge-status-filters .filter-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  document.querySelectorAll("#knowledge-table tbody tr").forEach(row => {
    row.style.display = (status === "all" || row.dataset.status === status) ? "" : "none";
  });
}

// -- Auth Sources --

async function deleteAuthSource(aid) {
  if (!confirm("Delete this auth source?")) return;
  try {
    await apiDelete(`/api/auth-sources/${aid}`);
    toast("Auth source deleted");
    setTimeout(() => location.reload(), 500);
  } catch (ex) { toast(ex.message, "error"); }
}

if (typeof PARTNER_ID !== "undefined") {
  const asForm = document.getElementById("add-auth-source-form");
  if (asForm) {
    asForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const data = {};
        for (const el of asForm.elements) {
          if (el.name) data[el.name] = el.value;
        }
        await apiPost(`/api/partners/${PARTNER_ID}/auth-sources`, data);
        toast("Auth source added");
        setTimeout(() => location.reload(), 500);
      } catch (ex) { toast(ex.message, "error"); }
    });
  }
}

async function suggestDomains() {
  try {
    const r = await fetch(`/api/partners/${PARTNER_ID}/suggest-domains`);
    const data = await r.json();
    const suggestions = data.suggestions || [];
    if (!suggestions.length) {
      toast("No domain suggestions found from ticket summaries", "error");
      return;
    }
    const existing = Array.from(document.querySelectorAll("#tab-domains .mono")).map(
      (el) => el.textContent.trim()
    );
    const newOnes = suggestions.filter((s) => !existing.includes(s));
    if (!newOnes.length) {
      toast("All suggested domains already exist");
      return;
    }
    if (!confirm(`Create ${newOnes.length} suggested domains?\n\n${newOnes.join("\n")}`)) return;
    for (const name of newOnes) {
      await apiPost(`/api/partners/${PARTNER_ID}/domains`, { name, description: "" });
    }
    toast(`Created ${newOnes.length} domains`);
    setTimeout(() => location.reload(), 500);
  } catch (ex) {
    toast(ex.message, "error");
  }
}

// -- Architect Terminal --

let _term = null, _termWs = null, _fitAddon = null;

function startTerminal() {
  if (_term) return;
  const container = document.getElementById("terminal-container");
  if (!container) return;

  if (typeof Terminal === "undefined") {
    toast("xterm.js not loaded — check internet connection", "error");
    return;
  }

  _term = new Terminal({
    cursorBlink: true,
    fontSize: 14,
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    theme: {
      background: "#0f1218",
      foreground: "#e8ebf0",
      cursor: "#5b8cff",
      selectionBackground: "#2a3040",
    },
  });

  _fitAddon = new FitAddon.FitAddon();
  _term.loadAddon(_fitAddon);
  _term.open(container);
  _fitAddon.fit();
  _term.focus();

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  _termWs = new WebSocket(`${proto}//${location.host}/ws/terminal/${PARTNER_ID}`);
  _termWs.binaryType = "arraybuffer";

  _termWs.onopen = () => {
    const dims = { type: "resize", cols: _term.cols, rows: _term.rows };
    _termWs.send(JSON.stringify(dims));
  };

  _termWs.onmessage = (e) => {
    if (e.data instanceof ArrayBuffer) {
      _term.write(new Uint8Array(e.data));
    } else {
      _term.write(e.data);
    }
  };

  _termWs.onclose = () => {
    _term.write("\r\n\x1b[90m[session ended]\x1b[0m\r\n");
  };

  _term.onData((data) => {
    if (_termWs && _termWs.readyState === WebSocket.OPEN) {
      _termWs.send(new TextEncoder().encode(data));
    }
  });

  new ResizeObserver(() => {
    if (_fitAddon && _term) {
      _fitAddon.fit();
      if (_termWs && _termWs.readyState === WebSocket.OPEN) {
        _termWs.send(JSON.stringify({ type: "resize", cols: _term.cols, rows: _term.rows }));
      }
    }
  }).observe(container);

  document.getElementById("architect-start-btn").hidden = true;
  document.getElementById("architect-stop-btn").hidden = false;
  _startTopicPolling();
}

let _topicPollTimer = null;
function _startTopicPolling() {
  _stopTopicPolling();
  _pollActiveTopic();
  _topicPollTimer = setInterval(_pollActiveTopic, 5000);
}
function _stopTopicPolling() {
  if (_topicPollTimer) { clearInterval(_topicPollTimer); _topicPollTimer = null; }
  const el = document.getElementById("active-topic-indicator");
  if (el) { el.hidden = true; el.textContent = ""; }
}
async function _pollActiveTopic() {
  const el = document.getElementById("active-topic-indicator");
  if (!el || !_term) return;
  try {
    const r = await fetch(`/api/partners/${PARTNER_ID}/active-topic`);
    const data = await r.json();
    if (data.active) {
      el.innerHTML = `<span class="active-topic-label">Topic:</span> <a href="#" onclick="event.preventDefault(); expandTopic('${data.topic_id}')">${esc(data.title)}</a>`;
      el.hidden = false;
    } else {
      el.hidden = true;
    }
  } catch(e) { /* ignore polling errors */ }
}

function stopTerminal() {
  if (_termWs) { _termWs.close(); _termWs = null; }
  if (_term) { _term.dispose(); _term = null; }
  _fitAddon = null;
  _stopTopicPolling();
  document.getElementById("terminal-container").innerHTML = "";
  document.getElementById("architect-start-btn").hidden = false;
  document.getElementById("architect-stop-btn").hidden = true;
}

async function sendToArchitect(prompt) {
  const wasRunning = !!_term;
  if (!_term) startTerminal();
  document.querySelector(".architect-hero").scrollIntoView({ behavior: "smooth" });
  const delay = wasRunning ? 200 : 4000;
  await new Promise(r => setTimeout(r, delay));
  if (_termWs && _termWs.readyState === WebSocket.OPEN) {
    _termWs.send(new TextEncoder().encode(prompt + "\n"));
  } else {
    toast("Architect terminal not connected", "error");
  }
}

async function processQueue() {
  try {
    const docs = await fetch(`/api/partners/${PARTNER_ID}/learned-docs/queue?status=approved`).then(r => r.json());
    if (!docs.length) { toast("No approved documents to process", "info"); return; }
    await sendToArchitect(
      `Process all ${docs.length} approved documents in the knowledge queue. ` +
      `Check the approved queue, extract knowledge from each document, create pending knowledge entries, ` +
      `and mark each document as processed. Follow the "Processing learned documents" instructions in your skill file.`
    );
  } catch (ex) { toast(ex.message, "error"); }
}

// -- Operator version pins --

let _pinsOperatorId = null;

async function openVersionPins(oid, name) {
  _pinsOperatorId = oid;
  document.getElementById("pins-operator-name").textContent = name;
  await _refreshPins();
  showModal("operator-pins-modal");
}

async function _refreshPins() {
  const container = document.getElementById("pins-table-container");
  if (!RELEASES || !RELEASES.length) {
    container.innerHTML = '<p class="muted">No releases defined yet. Add releases first.</p>';
    return;
  }
  const pins = await fetch(`/api/operators/${_pinsOperatorId}/pins`).then(r => r.json());
  const pinsByRelease = Object.fromEntries(pins.map(p => [p.release_id, p]));

  let html = '<table class="data-table"><thead><tr><th>Release</th><th>OCP Version</th><th>Pinned Version</th><th></th></tr></thead><tbody>';
  for (const rel of RELEASES) {
    const pin = pinsByRelease[rel.id];
    html += `<tr>
      <td class="mono">${esc(rel.release_name)}</td>
      <td>${esc(rel.ocp_version || "—")}</td>
      <td><input type="text" class="inline-input" id="pin-${rel.id}"
          value="${esc(pin ? pin.pinned_version : "")}"
          placeholder="e.g. 4.17.0-202501..."
          style="width:100%;box-sizing:border-box"></td>
      <td>
        <button class="btn small" onclick="savePin('${rel.id}')">Save</button>
        ${pin ? `<button class="btn-del" onclick="deletePin('${pin.id}', '${rel.id}')">×</button>` : ""}
      </td>
    </tr>`;
  }
  html += "</tbody></table>";
  container.innerHTML = html;
}

async function savePin(releaseId) {
  const version = document.getElementById(`pin-${releaseId}`)?.value.trim();
  try {
    const data = new URLSearchParams({ release_id: releaseId, pinned_version: version || "" });
    await fetch(`/api/operators/${_pinsOperatorId}/pins`, { method: "POST", body: data });
    await _refreshPins();
    toast("Saved");
  } catch (ex) { toast(ex.message, "error"); }
}

async function deletePin(pinId) {
  try {
    await fetch(`/api/operator-pins/${pinId}`, { method: "DELETE" });
    await _refreshPins();
  } catch (ex) { toast(ex.message, "error"); }
}

// -- Table search + sort --

function filterTable(input) {
  const q = input.value.toLowerCase();
  const table = document.getElementById(input.dataset.target);
  if (!table) return;
  for (const row of table.querySelectorAll("tbody tr")) {
    row.hidden = q ? ![...row.cells].some(c => c.textContent.toLowerCase().includes(q)) : false;
  }
}

function sortTable(th) {
  const table = th.closest("table");
  const col = [...th.parentElement.children].indexOf(th);
  const asc = th.dataset.sort !== "asc";
  // Clear other headers
  for (const h of th.parentElement.children) delete h.dataset.sort;
  th.dataset.sort = asc ? "asc" : "desc";
  const tbody = table.querySelector("tbody");
  [...tbody.querySelectorAll("tr")]
    .sort((a, b) => {
      const at = a.cells[col]?.textContent.trim() || "";
      const bt = b.cells[col]?.textContent.trim() || "";
      return asc ? at.localeCompare(bt, undefined, { numeric: true }) : bt.localeCompare(at, undefined, { numeric: true });
    })
    .forEach(r => tbody.appendChild(r));
}
