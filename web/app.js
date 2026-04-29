// AskMom Recipes — frontend logic. Plain JS, no framework.

const API = window.ASKMOM_CONFIG.API_BASE_URL;

const dropZone = document.getElementById("drop-zone");
const photoInput = document.getElementById("photo-input");
const photoPreview = document.getElementById("photo-preview");
const photoPreviewImg = document.getElementById("photo-preview-img");
const photoRemove = document.getElementById("photo-remove");
const textInput = document.getElementById("text-input");
const preferences = document.getElementById("preferences");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const recipeGrid = document.getElementById("recipe-grid");
const refineBar = document.getElementById("refine-bar");

let selectedFile = null;
let currentSessionId = null;

// --- Photo handling ---

dropZone.addEventListener("click", () => photoInput.click());
photoInput.addEventListener("change", (e) => {
  if (e.target.files.length) selectFile(e.target.files[0]);
});

["dragenter", "dragover"].forEach((ev) =>
  dropZone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((ev) =>
  dropZone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
  })
);
dropZone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) selectFile(file);
});

photoRemove.addEventListener("click", (e) => {
  e.stopPropagation();
  selectedFile = null;
  photoPreview.hidden = true;
  photoInput.value = "";
});

function selectFile(file) {
  selectedFile = file;
  photoPreviewImg.src = URL.createObjectURL(file);
  photoPreview.hidden = false;
}

// --- Submit ---

submitBtn.addEventListener("click", async () => {
  const text = textInput.value.trim();
  if (!selectedFile && !text) {
    showStatus("Add a photo, type some ingredients, or both.");
    return;
  }

  setLoading(true);
  try {
    let photoKey = null;
    if (selectedFile) {
      photoKey = await uploadPhoto(selectedFile);
    }

    const result = await postJSON("/ingredients", {
      photo_key: photoKey,
      text: text || null,
      preferences: preferences.value,
    });

    currentSessionId = result.session_id;
    renderResults(result);
  } catch (err) {
    showStatus(`Something went wrong: ${err.message}`);
  } finally {
    setLoading(false);
  }
});

// --- Refine ---

refineBar.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-refine]");
  if (!btn || !currentSessionId) return;

  setLoading(true);
  try {
    const result = await postJSON("/refine", {
      session_id: currentSessionId,
      instruction: btn.dataset.refine,
    });
    renderResults(result);
  } catch (err) {
    showStatus(`Couldn't refine: ${err.message}`);
  } finally {
    setLoading(false);
  }
});

// --- API helpers ---

async function uploadPhoto(file) {
  // Step 1: ask the API for a pre-signed PUT URL.
  const { upload_url, photo_key } = await postJSON("/upload-url", {
    content_type: file.type,
  });

  // Step 2: PUT the file directly to S3.
  const res = await fetch(upload_url, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
  });
  if (!res.ok) throw new Error(`Upload failed (${res.status})`);
  return photo_key;
}

async function postJSON(path, body) {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${text}`);
  }
  return res.json();
}

// --- UI helpers ---

function setLoading(loading) {
  submitBtn.disabled = loading;
  submitBtn.textContent = loading ? "Thinking..." : "Suggest recipes";
  if (loading) {
    animateStatus([
      "Looking at your ingredients...",
      "Asking AskMom for ideas...",
      "Checking what's good for you...",
      "Plating up your recipes...",
    ]);
  } else {
    stopStatusAnimation();
    statusEl.hidden = true;
  }
}

let _statusTimer = null;
function animateStatus(messages) {
  stopStatusAnimation();
  let i = 0;
  showStatus(messages[0]);
  _statusTimer = setInterval(() => {
    i = (i + 1) % messages.length;
    showStatus(messages[i]);
  }, 4000);
}

function stopStatusAnimation() {
  if (_statusTimer) {
    clearInterval(_statusTimer);
    _statusTimer = null;
  }
}

function showStatus(msg) {
  statusEl.textContent = msg;
  statusEl.hidden = false;
}

function renderResults(result) {
  resultsEl.hidden = false;
  recipeGrid.innerHTML = "";
  (result.recipes || []).forEach((r) => {
    recipeGrid.appendChild(renderRecipeCard(r));
  });
  statusEl.hidden = true;
}

function renderRecipeCard(r) {
  const el = document.createElement("article");
  el.className = "recipe-card";
  el.innerHTML = `
    <h3>${escapeHtml(r.name || "Untitled")}</h3>
    <p class="hook">${escapeHtml(r.hook || "")}</p>
    ${r.minutes ? `<p><strong>⏱️</strong> ${r.minutes} min</p>` : ""}
    ${
      (r.ingredients_you_have || []).length
        ? `<p><strong>You have:</strong> ${r.ingredients_you_have.map(escapeHtml).join(", ")}</p>`
        : ""
    }
    ${
      (r.ingredients_to_grab || []).length
        ? `<p><strong>Grab:</strong> ${r.ingredients_to_grab.map(escapeHtml).join(", ")}</p>`
        : ""
    }
    ${
      (r.steps || []).length
        ? `<ol>${r.steps.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ol>`
        : ""
    }
    ${r.why_good_for_you ? `<p>💚 ${escapeHtml(r.why_good_for_you)}</p>` : ""}
    ${r.origin_note ? `<p>🌍 ${escapeHtml(r.origin_note)}</p>` : ""}
  `;
  return el;
}

function escapeHtml(s) {
  return String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c]
  );
}
