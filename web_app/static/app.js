const modeText = {
  0: "\u4eba\u8138\u8bc6\u522b\u6a21\u5f0f",
  1: "\u4eba\u8138\u68c0\u6d4b\u6a21\u5f0f",
  2: "\u7eaf\u663e\u793a\u6a21\u5f0f",
};

const views = {
  monitor: ["\u5b9e\u65f6\u76d1\u63a7", "\u56db\u8def\u89c6\u9891\u3001\u4eba\u8138\u68c0\u6d4b\u3001\u4eba\u8138\u8bc6\u522b\u3001\u60c5\u7eea\u8bc6\u522b\u4e0e\u8003\u52e4\u8bb0\u5f55"],
  cameras: ["\u6444\u50cf\u5934\u914d\u7f6e", "\u7a97\u53e3\u3001\u663e\u793a\u6a21\u5f0f\u3001\u89c6\u9891\u6e90\u3001\u4fdd\u5b58\u914d\u7f6e\u4e0e\u7acb\u523b\u5e94\u7528"],
  faces: ["\u4eba\u8138\u5f55\u5165\u53ca\u7ba1\u7406", "\u6837\u672c\u91c7\u96c6\u3001\u6a21\u578b\u66f4\u65b0\u3001\u6a21\u578b\u91cd\u7f6e\u4e0e\u6307\u5b9a\u7528\u6237\u5220\u9664"],
  logs: ["\u65e5\u5fd7\u4e0e\u8003\u52e4", "\u8bb0\u5f55\u67e5\u8be2\u3001\u7f3a\u52e4\u540d\u5355\u3001\u8003\u52e4\u6c47\u603b\u4e0e CSV \u62a5\u8868\u5bfc\u51fa"],
};

let appState = {
  authenticated: false,
  account: "",
  cameras: [],
  running: new Map(),
  users: [],
  modelPending: false,
  runtimeMode: "balanced",
  showFps: false,
  customAttendance: { active: false, label: "" },
};

let enrollTimer = null;
let statusTimer = null;
let trainingBusy = false;
let trainTimer = null;

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const type = response.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await response.json() : null;
  if (!response.ok || (data && data.ok === false)) {
    throw new Error((data && data.message) || `\u8bf7\u6c42\u5931\u8d25\uff1a${response.status}`);
  }
  return data;
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 2300);
}

function switchView(name) {
  $$(".nav-tab").forEach((btn) => btn.classList.toggle("active", btn.dataset.view === name));
  $$(".view").forEach((view) => view.classList.remove("active"));
  $(`#${name}View`).classList.add("active");
  $("#viewTitle").textContent = views[name][0];
  $("#viewSubtitle").textContent = views[name][1];
}

function setLocked(locked) {
  $("#loginGuard").classList.toggle("show", locked);
  $$(".workspace button, .workspace input, .workspace select").forEach((el) => { el.disabled = locked; });
  $(".topbar").querySelectorAll("button, input, select").forEach((el) => { el.disabled = locked; });
}

function normalizeStatus(data) {
  appState.authenticated = Boolean(data.authenticated);
  appState.account = data.account || "";
  appState.cameras = data.cameras || [];
  appState.running = new Map((data.runningCameras || []).map((item) => [Number(item.slot), item]));
  appState.users = data.users || [];
  appState.modelPending = Boolean(data.modelPending);
  appState.runtimeMode = data.runtimeMode || "balanced";
  appState.showFps = Boolean(data.showFps);
  appState.customAttendance = data.customAttendance || { active: false, label: "" };
}

function updateStatusPanel() {
  $("#loginState").textContent = appState.authenticated ? appState.account || "\u5df2\u767b\u5f55" : "\u672a\u767b\u5f55";
  $("#backendMode").textContent = appState.runtimeMode === "realtime" ? "\u5b9e\u65f6\u4f18\u5148" : appState.runtimeMode === "accurate" ? "\u9ad8\u7cbe\u5ea6" : "\u5e73\u8861\u6a21\u5f0f";
  $("#modelState").textContent = appState.modelPending ? "\u5f85\u66f4\u65b0" : "\u6700\u65b0";
  $("#userCount").textContent = String(appState.users.length);
  $("#activeCount").textContent = `${appState.running.size} / 4`;
  $("#runtimeMode").value = appState.runtimeMode;
  $("#fpsToggle").textContent = appState.showFps ? "\u9690\u85cf FPS" : "\u663e\u793a FPS";
  if (appState.customAttendance.active) {
    $("#signinState").textContent = `\u81ea\u5b9a\u4e49\u7b7e\u5230\uff1a\u8fdb\u884c\u4e2d\uff08${appState.customAttendance.label}\uff09`;
    $("#signinBtn").textContent = "\u7ed3\u675f\u7b7e\u5230";
    $("#signinName").disabled = true;
  } else {
    $("#signinState").textContent = "\u81ea\u5b9a\u4e49\u7b7e\u5230\uff1a\u672a\u5f00\u542f";
    $("#signinBtn").textContent = "\u5f00\u59cb\u7b7e\u5230";
    $("#signinName").disabled = !appState.authenticated;
  }
  setLocked(!appState.authenticated);
  updateMonitorMeta();
}

function updateMonitorMeta() {
  for (const [slot, running] of appState.running.entries()) {
    const tile = $(`.video-tile[data-slot="${slot}"]`);
    if (!tile) continue;
    const foot = $(".tile-foot span:first-child", tile);
    if (!foot) continue;
    const people = running && running.meta && Array.isArray(running.meta.people) ? running.meta.people.filter(Boolean) : [];
    const camera = appState.cameras.find((item) => Number(item.slot) === Number(slot));
    foot.textContent = people.length ? people.join("\u3001") : ((camera && camera.name) || `win${slot}`);
  }
}

function renderMonitor() {
  const root = $("#monitorGrid");
  root.innerHTML = "";
  for (const camera of appState.cameras) {
    const running = appState.running.get(Number(camera.slot));
    const tile = document.createElement("article");
    tile.className = "video-tile";
    tile.dataset.slot = camera.slot;
    const streamText = running ? "\u8fde\u63a5\u89c6\u9891\u6d41\u4e2d" : "\u65e0\u4fe1\u53f7";
    const stateText = running ? "\u8fd0\u884c\u4e2d" : "\u65e0\u4fe1\u53f7";
    const people = running && running.meta && Array.isArray(running.meta.people) ? running.meta.people.filter(Boolean) : [];
    const footText = people.length ? people.join("\u3001") : (camera.name || `win${camera.slot}`);
    tile.innerHTML = `
      <div class="tile-head"><strong>win${camera.slot}</strong><span>${modeText[camera.displayMode] || camera.displayModeText || "\u672a\u77e5\u6a21\u5f0f"}</span></div>
      <div class="video-frame">
        <img alt="win${camera.slot} video stream" />
        <div class="video-empty">${streamText}</div>
      </div>
      <div class="tile-foot"><span>${footText}</span><span class="stream-state ${running ? "on" : ""}">${stateText}</span></div>
    `;
    root.appendChild(tile);
    if (running) setStreamImage(camera.slot);
  }
}

function setStreamImage(slot) {
  const tile = $(`.video-tile[data-slot="${slot}"]`);
  if (!tile) return;
  const img = $("img", tile);
  const empty = $(".video-empty", tile);
  img.onload = () => { img.classList.add("active"); empty.classList.add("hidden"); };
  img.onerror = () => { img.classList.remove("active"); empty.classList.remove("hidden"); empty.textContent = "\u89c6\u9891\u6d41\u672a\u8fde\u63a5"; };
  img.src = `/video/${slot}?t=${Date.now()}`;
}

function clearStreamImages() {
  $$(".video-frame img").forEach((img) => { img.removeAttribute("src"); img.classList.remove("active"); });
  $$(".video-empty").forEach((el) => el.classList.remove("hidden"));
}

function zhStatus(message) {
  const table = {
    "opening camera": "\u6b63\u5728\u6253\u5f00\u6444\u50cf\u5934",
    "camera open failed": "\u6444\u50cf\u5934\u65e0\u6cd5\u6253\u5f00",
    "capturing samples": "\u6b63\u5728\u91c7\u96c6\u6837\u672c",
    "capture finished, please update model": "\u91c7\u96c6\u5b8c\u6210\uff0c\u8bf7\u66f4\u65b0\u6a21\u578b",
    "no face captured": "\u672a\u91c7\u96c6\u5230\u4eba\u8138",
    "preparing samples": "\u6b63\u5728\u51c6\u5907\u6837\u672c",
    "loading samples": "\u6b63\u5728\u8bfb\u53d6\u6837\u672c",
    "training model": "\u6b63\u5728\u66f4\u65b0\u6a21\u578b",
    "model updated": "\u6a21\u578b\u66f4\u65b0\u5b8c\u6210",
    "training data error": "\u8bad\u7ec3\u6570\u636e\u5f02\u5e38",
    "model update failed": "\u6a21\u578b\u66f4\u65b0\u5931\u8d25",
  };
  return table[String(message || "")] || message || "";
}

function showEnrollStream(active) {
  const img = $("#enrollPreview");
  const empty = $("#enrollEmpty");
  if (!img || !empty) return;
  if (active) {
    img.onload = () => { img.classList.add("active"); empty.classList.add("hidden"); };
    img.onerror = () => { img.classList.remove("active"); empty.classList.remove("hidden"); empty.textContent = "\u5f55\u5165\u89c6\u9891\u6d41\u672a\u8fde\u63a5"; };
    img.src = `/video/enroll?t=${Date.now()}`;
    empty.textContent = "\u6b63\u5728\u6253\u5f00\u5f55\u5165\u6444\u50cf\u5934";
    return;
  }
  img.removeAttribute("src");
  img.classList.remove("active");
  empty.classList.remove("hidden");
  empty.textContent = "\u5f55\u5165\u9884\u89c8\u5c06\u5728\u91c7\u96c6\u65f6\u542f\u7528";
}

function renderCameraConfig() {
  const root = $("#cameraConfig");
  root.innerHTML = "";
  for (const camera of appState.cameras) {
    const card = document.createElement("article");
    card.className = "config-card";
    card.innerHTML = `
      <h2>win${camera.slot}</h2>
      <label class="field"><span>\u6444\u50cf\u5934\u540d\u79f0\u5730\u5740</span><input data-key="name" data-slot="${camera.slot}" value="${camera.name || ""}" /></label>
      <label class="field">
        <span>\u663e\u793a\u6a21\u5f0f</span>
        <select data-key="displayMode" data-slot="${camera.slot}">
          <option value="0">\u4eba\u8138\u8bc6\u522b\u6a21\u5f0f</option>
          <option value="1">\u4eba\u8138\u68c0\u6d4b\u6a21\u5f0f</option>
          <option value="2">\u7eaf\u663e\u793a\u6a21\u5f0f</option>
        </select>
      </label>
      <label class="field"><span>\u89c6\u9891\u6e90</span><input data-key="source" data-slot="${camera.slot}" value="${camera.source || ""}" /></label>
      <div class="button-row">
        <button class="primary" data-action="start" data-slot="${camera.slot}">\u5f00\u542f</button>
        <button class="danger ghost" data-action="stop" data-slot="${camera.slot}">\u5173\u95ed</button>
      </div>
    `;
    $("select", card).value = String(camera.displayMode || 0);
    root.appendChild(card);
  }
}

function getConfigInputs() {
  const bySlot = new Map(appState.cameras.map((item) => [Number(item.slot), { ...item }]));
  $$("[data-key]", $("#cameraConfig")).forEach((input) => {
    const slot = Number(input.dataset.slot);
    const item = bySlot.get(slot);
    if (!item) return;
    item[input.dataset.key] = input.dataset.key === "displayMode" ? Number(input.value) : input.value.trim();
  });
  return Array.from(bySlot.values());
}

function renderUsers() {
  const select = $("#userSelect");
  select.innerHTML = appState.users.length ? appState.users.map((user) => `<option value="${user.name}">${user.name}</option>`).join("") : `<option value="">\u6682\u65e0\u5df2\u767b\u8bb0\u4eba\u5458</option>`;
}

async function refreshStatus({ render = true } = {}) {
  const data = await api("/api/status");
  normalizeStatus(data);
  updateStatusPanel();
  if (render) {
    renderMonitor();
    renderCameraConfig();
    renderUsers();
    await loadLogFilters().catch(() => {});
  }
}

async function login() {
  await api("/api/login", { method: "POST", body: JSON.stringify({ account: $("#accountInput").value.trim(), password: $("#passwordInput").value }) });
  toast("\u767b\u5f55\u6210\u529f");
  await refreshStatus();
  await queryLogs().catch(() => {});
}

async function registerAccount() {
  await api("/api/register", { method: "POST", body: JSON.stringify({ account: $("#registerAccount").value.trim(), password: $("#registerPassword").value, adminPassword: $("#registerAdminPassword").value }) });
  toast("\u6ce8\u518c\u6210\u529f\uff0c\u8bf7\u4f7f\u7528\u65b0\u8d26\u53f7\u767b\u5f55");
  $("#registerBox").classList.add("hidden");
}

async function saveConfig() {
  const cameras = getConfigInputs();
  const data = await api("/api/cameras/config", { method: "POST", body: JSON.stringify({ cameras }) });
  appState.cameras = data.cameras || cameras;
  renderCameraConfig();
  renderMonitor();
  toast("\u914d\u7f6e\u5df2\u4fdd\u5b58");
}

async function startCamera(slot, config = null) {
  const item = config || getConfigInputs().find((camera) => Number(camera.slot) === Number(slot));
  await api(`/api/cameras/${slot}/start`, { method: "POST", body: JSON.stringify(item || {}) });
  await refreshStatus();
}
async function stopCamera(slot) { await api(`/api/cameras/${slot}/stop`, { method: "POST" }); await refreshStatus(); }
async function applyConfig() { await saveConfig(); for (const camera of appState.cameras) await startCamera(camera.slot, camera); toast("\u914d\u7f6e\u5df2\u5e94\u7528"); }
async function startAll() { await saveConfig(); await api("/api/cameras/start-all", { method: "POST" }); await refreshStatus(); }
async function stopAll() { clearStreamImages(); await api("/api/cameras/stop-all", { method: "POST" }); await refreshStatus(); }
async function setRuntime() { await api("/api/runtime", { method: "POST", body: JSON.stringify({ runtimeMode: $("#runtimeMode").value, showFps: appState.showFps }) }); await refreshStatus(); }
async function toggleFps() { await api("/api/runtime", { method: "POST", body: JSON.stringify({ runtimeMode: appState.runtimeMode, showFps: !appState.showFps }) }); await refreshStatus(); }

async function toggleSignin() {
  if (appState.customAttendance.active) { await api("/api/custom-attendance/stop", { method: "POST" }); toast("\u7b7e\u5230\u5df2\u7ed3\u675f"); }
  else {
    const label = $("#signinName").value.trim();
    if (!label) return toast("\u8bf7\u5148\u8f93\u5165\u7b7e\u5230\u540d\u79f0");
    await api("/api/custom-attendance/start", { method: "POST", body: JSON.stringify({ label }) });
    toast("\u7b7e\u5230\u5df2\u5f00\u59cb");
  }
  await refreshStatus({ render: false });
}

async function captureFace() {
  const username = $("#faceName").value.trim();
  if (!username) return toast("\u8bf7\u5148\u8f93\u5165\u5f55\u5165\u59d3\u540d");
  showEnrollStream(true);
  await api("/api/enroll/capture", { method: "POST", body: JSON.stringify({ username, source: $("#enrollSource").value.trim() || 0, target: 50 }) });
  toast("\u5f00\u59cb\u91c7\u96c6\u6837\u672c");
  pollEnroll();
}

function pollEnroll() {
  clearInterval(enrollTimer);
  enrollTimer = setInterval(async () => {
    try {
      const data = await api("/api/enroll/status");
      const enroll = data.enroll || {};
      const captured = Number(enroll.captured || 0);
      const target = Number(enroll.target || 50);
      $("#sampleCount").textContent = `${captured} / ${target}`;
      $("#enrollStatus").textContent = zhStatus(enroll.message) || "\u7a7a\u95f2";
      $("#captureProgress").style.width = `${Math.min(100, (captured / Math.max(1, target)) * 100)}%`;
      if (!enroll.running) { clearInterval(enrollTimer); showEnrollStream(false); toast(zhStatus(enroll.message) || "\u91c7\u96c6\u5b8c\u6210"); await refreshStatus(); }
    } catch (err) { clearInterval(enrollTimer); showEnrollStream(false); toast(err.message); }
  }, 700);
}

async function trainModel() {
  if (trainingBusy) return;
  trainingBusy = true;
  $("#trainBtn").disabled = true;
  try {
    clearStreamImages();
    toast("\u6b63\u5728\u66f4\u65b0\u6a21\u578b\uff0c\u8bf7\u7a0d\u5019");
    await api("/api/model/train", { method: "POST" });
    pollTrainStatus();
  } catch (err) {
    trainingBusy = false;
    $("#trainBtn").disabled = false;
    toast(err.message);
  }
}

function pollTrainStatus() {
  clearInterval(trainTimer);
  trainTimer = setInterval(async () => {
    try {
      const data = await api("/api/model/train/status");
      const training = data.training || {};
      $("#enrollStatus").textContent = training.running ? "\u6b63\u5728\u66f4\u65b0\u6a21\u578b" : (zhStatus(training.message) || "\u7a7a\u95f2");
      if (!training.running) {
        clearInterval(trainTimer);
        trainingBusy = false;
        $("#trainBtn").disabled = false;
        toast(training.success === false ? `\u6a21\u578b\u66f4\u65b0\u5931\u8d25\uff1a${zhStatus(training.message) || ""}` : "\u6a21\u578b\u66f4\u65b0\u5b8c\u6210");
        await refreshStatus();
      }
    } catch (err) {
      clearInterval(trainTimer);
      trainingBusy = false;
      $("#trainBtn").disabled = false;
      toast(err.message);
    }
  }, 900);
}

async function resetModel() {
  if (!confirm("\u786e\u5b9a\u91cd\u7f6e\u6240\u6709\u4eba\u8138\u6837\u672c\u53ca\u8bc6\u522b\u6a21\u578b\uff1f")) return;
  clearStreamImages();
  await api("/api/model/reset", { method: "POST" });
  $("#captureProgress").style.width = "0%";
  toast("\u6a21\u578b\u5df2\u91cd\u7f6e");
  await refreshStatus();
}

async function deleteFace() {
  const username = $("#userSelect").value || $("#faceName").value.trim();
  if (!username) return toast("\u8bf7\u9009\u62e9\u6216\u8f93\u5165\u8981\u5220\u9664\u7684\u4eba\u8138");
  await api("/api/users/delete", { method: "POST", body: JSON.stringify({ username }) });
  toast(`\u5df2\u5220\u9664 ${username}\uff0c\u8bf7\u66f4\u65b0\u6a21\u578b`);
  await refreshStatus();
}

function logQueryParams() {
  const params = new URLSearchParams();
  [["name", "#filterPerson"], ["location", "#filterPlace"], ["attendanceType", "#filterType"], ["status", "#filterStatus"], ["start", "#startTime"], ["end", "#endTime"]].forEach(([key, selector]) => {
    const value = $(selector).value;
    if (value) params.set(key, value);
  });
  return params.toString();
}

async function queryLogs() {
  const data = await api(`/api/logs?${logQueryParams()}`);
  const rows = data.rows || [];
  $("#logBody").innerHTML = rows.map((row) => `<tr><td>${row.name || ""}</td><td>${row.location || ""}</td><td>${row.time || ""}</td><td>${row.emotion || ""}</td><td>${row.attendanceType || ""}</td><td>${row.status || ""}</td></tr>`).join("");
  return rows;
}

async function loadLogFilters() {
  if (!appState.authenticated) return;
  const data = await api("/api/logs/filters");
  fillSelect("#filterPerson", ["\u4efb\u4f55\u4eba\u5458", ...(data.names || [])]);
  fillSelect("#filterPlace", ["\u4efb\u4f55\u5730\u70b9", ...(data.places || [])]);
  fillSelect("#filterType", ["\u4efb\u4f55\u7c7b\u578b", "\u4e0a\u73ed\u6253\u5361", "\u4e0b\u73ed\u6253\u5361", "\u5916\u51fa\u767b\u8bb0", "\u91cd\u590d\u8bc6\u522b", "\u672a\u8bc6\u522b", ...(data.attendanceTypes || [])]);
  const now = new Date();
  const start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
  if (!$("#startTime").value) $("#startTime").value = start.toISOString().slice(0, 16);
  if (!$("#endTime").value) $("#endTime").value = now.toISOString().slice(0, 16);
}

function fillSelect(selector, values) {
  const seen = new Set();
  $(selector).innerHTML = values.filter((value) => {
    if (!value || seen.has(value)) return false;
    seen.add(value);
    return true;
  }).map((value) => `<option>${value}</option>`).join("");
}

async function clearLogs() { if (!confirm("\u786e\u5b9a\u6e05\u7a7a\u65e5\u5fd7\u6570\u636e\u5e93\uff1f")) return; await api("/api/logs/clear", { method: "POST" }); $("#logBody").innerHTML = ""; toast("\u65e5\u5fd7\u5df2\u6e05\u7a7a"); }
async function absence() { const day = ($("#startTime").value || new Date().toISOString()).slice(0, 10); const data = await api(`/api/logs/absence?day=${encodeURIComponent(day)}`); const rows = data.rows || []; toast(rows.length ? `${day} \u7f3a\u52e4\uff1a${rows.join("\u3001")}` : `${day} \u65e0\u7f3a\u52e4\u4eba\u5458`); }
async function summary() { const data = await api(`/api/logs/summary?${logQueryParams()}`); toast(`\u5f53\u524d\u7b5b\u9009\u8303\u56f4\u5171 ${data.total || 0} \u6761\u8bb0\u5f55`); }
function exportLogs() { window.location.href = `/api/logs/export?${logQueryParams()}`; }

function bindEvents() {
  $$(".nav-tab").forEach((btn) => btn.addEventListener("click", () => switchView(btn.dataset.view)));
  $("#loginBtn").addEventListener("click", () => login().catch((err) => toast(err.message)));
  $("#registerToggleBtn").addEventListener("click", () => $("#registerBox").classList.toggle("hidden"));
  $("#registerBtn").addEventListener("click", () => registerAccount().catch((err) => toast(err.message)));
  $("#refreshBtn").addEventListener("click", () => refreshStatus().catch((err) => toast(err.message)));
  $("#runtimeMode").addEventListener("change", () => setRuntime().catch((err) => toast(err.message)));
  $("#fpsToggle").addEventListener("click", () => toggleFps().catch((err) => toast(err.message)));
  $("#startAllBtn").addEventListener("click", () => startAll().catch((err) => toast(err.message)));
  $("#stopAllBtn").addEventListener("click", () => stopAll().catch((err) => toast(err.message)));
  $("#saveConfigBtn").addEventListener("click", () => saveConfig().catch((err) => toast(err.message)));
  $("#applyConfigBtn").addEventListener("click", () => applyConfig().catch((err) => toast(err.message)));
  $("#signinBtn").addEventListener("click", () => toggleSignin().catch((err) => toast(err.message)));
  $("#captureBtn").addEventListener("click", () => captureFace().catch((err) => toast(err.message)));
  $("#trainBtn").addEventListener("click", () => trainModel().catch((err) => toast(err.message)));
  $("#resetModelBtn").addEventListener("click", () => resetModel().catch((err) => toast(err.message)));
  $("#deleteFaceBtn").addEventListener("click", () => deleteFace().catch((err) => toast(err.message)));
  $("#queryLogBtn").addEventListener("click", () => queryLogs().catch((err) => toast(err.message)));
  $("#clearLogBtn").addEventListener("click", () => clearLogs().catch((err) => toast(err.message)));
  $("#absenceBtn").addEventListener("click", () => absence().catch((err) => toast(err.message)));
  $("#summaryBtn").addEventListener("click", () => summary().catch((err) => toast(err.message)));
  $("#exportBtn").addEventListener("click", exportLogs);
  $("#cameraConfig").addEventListener("click", (event) => {
    const btn = event.target.closest("button[data-action]");
    if (!btn) return;
    const slot = Number(btn.dataset.slot);
    const run = btn.dataset.action === "start" ? startCamera(slot) : stopCamera(slot);
    run.catch((err) => toast(err.message));
  });
}

async function init() {
  bindEvents();
  try { await refreshStatus(); if (appState.authenticated) await queryLogs().catch(() => {}); }
  catch (err) { setLocked(true); }
  statusTimer = setInterval(() => { if (!appState.authenticated || trainingBusy) return; refreshStatus({ render: false }).catch(() => {}); }, 5000);
}

init();
