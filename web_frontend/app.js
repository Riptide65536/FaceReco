const modeText = {
  0: "人脸识别模式",
  1: "人脸检测模式",
  2: "纯显示模式",
};

const views = {
  monitor: {
    title: "实时监控",
    subtitle: "四路视频、人脸检测、人脸识别、情绪识别与考勤记录",
    el: document.querySelector("#monitorView"),
  },
  cameras: {
    title: "摄像头配置",
    subtitle: "窗口、显示模式、视频源、保存配置与立刻应用",
    el: document.querySelector("#camerasView"),
  },
  faces: {
    title: "人脸录入及管理",
    subtitle: "样本采集、模型更新、模型重置与指定用户删除",
    el: document.querySelector("#facesView"),
  },
  logs: {
    title: "日志与考勤",
    subtitle: "记录查询、缺勤名单、考勤汇总与 CSV 报表导出",
    el: document.querySelector("#logsView"),
  },
};

const state = {
  auth: { account: "" },
  runtimeMode: "balanced",
  showFps: false,
  modelPending: false,
  customSignin: "",
  users: ["张三", "李四", "王五"],
  sampleCount: 0,
  trainingCount: 60,
  cameras: [
    { slot: 1, name: "实验室入口", source: "0", mode: 0, running: false, fps: 0 },
    { slot: 2, name: "走廊", source: "demo.mp4", mode: 1, running: false, fps: 0 },
    { slot: 3, name: "会议室", source: "rtsp://example/meeting", mode: 2, running: false, fps: 0 },
    { slot: 4, name: "备用源", source: "", mode: 0, running: false, fps: 0 },
  ],
  logs: [
    ["张三", "实验室入口", "2026-06-04 08:55:18", "中性", "上班打卡", "正常"],
    ["李四", "走廊", "2026-06-04 09:12:43", "开心", "上班打卡", "迟到"],
    ["王五", "会议室", "2026-06-04 12:01:09", "中性", "外出登记", "已记录"],
    ["张三", "实验室入口", "2026-06-04 18:08:32", "疲惫", "下班打卡", "正常"],
  ],
};

const api = {
  async request(path, options = {}) {
    if (!window.FaceRecoApiBase) return null;
    const response = await fetch(`${window.FaceRecoApiBase}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!response.ok) throw new Error(`API ${path} ${response.status}`);
    return response.json();
  },
  login(account, password) {
    return this.request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ account, password }),
    });
  },
  saveCameras(cameras) {
    return this.request("/cameras/config", {
      method: "POST",
      body: JSON.stringify({ cameras }),
    });
  },
  applyCameras(cameras) {
    return this.request("/cameras/apply", {
      method: "POST",
      body: JSON.stringify({ cameras }),
    });
  },
  trainModel() {
    return this.request("/faces/train", { method: "POST" });
  },
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => el.classList.remove("show"), 2200);
}

function switchView(name) {
  $$(".nav-tab").forEach((btn) => btn.classList.toggle("active", btn.dataset.view === name));
  Object.entries(views).forEach(([key, view]) => view.el.classList.toggle("active", key === name));
  $("#viewTitle").textContent = views[name].title;
  $("#viewSubtitle").textContent = views[name].subtitle;
}

function updateStatus() {
  const running = state.cameras.filter((camera) => camera.running).length;
  $("#backendMode").textContent =
    state.runtimeMode === "realtime" ? "实时优先" : state.runtimeMode === "accurate" ? "高精度" : "平衡模式";
  $("#modelState").textContent = state.modelPending ? "待更新" : "最新";
  $("#userCount").textContent = String(state.users.length);
  $("#activeCount").textContent = `${running} / 4`;
  $("#sampleCount").textContent = `${state.sampleCount} / 20`;
  $("#trainingCount").textContent = String(state.trainingCount);
  $("#pendingFlag").textContent = state.modelPending ? "是" : "否";
  $("#captureProgress").style.width = `${Math.min(100, (state.sampleCount / 20) * 100)}%`;
}

function renderCameraConfig() {
  const root = $("#cameraConfig");
  root.innerHTML = "";
  state.cameras.forEach((camera) => {
    const card = document.createElement("article");
    card.className = "config-card";
    card.innerHTML = `
      <h2>win${camera.slot}</h2>
      <label class="field">
        <span>摄像头名称地址</span>
        <input data-key="name" data-slot="${camera.slot}" value="${camera.name}" />
      </label>
      <label class="field">
        <span>显示模式</span>
        <select data-key="mode" data-slot="${camera.slot}">
          <option value="0">人脸识别模式</option>
          <option value="1">人脸检测模式</option>
          <option value="2">纯显示模式</option>
        </select>
      </label>
      <label class="field">
        <span>视频源</span>
        <input data-key="source" data-slot="${camera.slot}" value="${camera.source}" />
      </label>
    `;
    $("select", card).value = String(camera.mode);
    root.appendChild(card);
  });
}

function syncConfigFromInputs() {
  $$("[data-key]", $("#cameraConfig")).forEach((input) => {
    const camera = state.cameras.find((item) => item.slot === Number(input.dataset.slot));
    if (!camera) return;
    camera[input.dataset.key] = input.dataset.key === "mode" ? Number(input.value) : input.value.trim();
  });
}

function updateTiles() {
  state.cameras.forEach((camera) => {
    const tile = $(`.video-tile[data-slot="${camera.slot}"]`);
    if (!tile) return;
    $(".tile-head span", tile).textContent = modeText[camera.mode];
    $(".tile-foot span:first-child", tile).textContent = camera.name || `win${camera.slot}`;
    const stateEl = $(".stream-state", tile);
    stateEl.textContent = camera.running ? "运行中" : "无信号";
    stateEl.classList.toggle("on", camera.running);
  });
}

function modeScale() {
  if (state.runtimeMode === "realtime") return { faceEvery: 0.8, fps: 30 };
  if (state.runtimeMode === "accurate") return { faceEvery: 1.8, fps: 15 };
  return { faceEvery: 1.2, fps: 18 };
}

function drawNoSignal(ctx, canvas, label) {
  ctx.fillStyle = "#0c1219";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = "#22303e";
  ctx.lineWidth = 2;
  ctx.strokeRect(28, 28, canvas.width - 56, canvas.height - 56);
  ctx.fillStyle = "#8fa2b3";
  ctx.font = "700 30px Microsoft YaHei UI, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("无信号", canvas.width / 2, canvas.height / 2 - 8);
  ctx.font = "16px Microsoft YaHei UI, sans-serif";
  ctx.fillText(label, canvas.width / 2, canvas.height / 2 + 26);
}

function drawStream(ctx, canvas, camera, now) {
  const w = canvas.width;
  const h = canvas.height;
  const t = now / 1000;
  const grad = ctx.createLinearGradient(0, 0, w, h);
  grad.addColorStop(0, "#101820");
  grad.addColorStop(0.45, "#152935");
  grad.addColorStop(1, "#223a3c");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  ctx.strokeStyle = "rgba(183, 205, 214, 0.16)";
  ctx.lineWidth = 1;
  for (let x = (t * 28 + camera.slot * 17) % 48; x < w; x += 48) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x - 110, h);
    ctx.stroke();
  }

  const { faceEvery, fps } = modeScale();
  const faceCount = camera.mode === 2 ? 0 : camera.slot % 2 === 0 ? 1 : 2;
  for (let i = 0; i < faceCount; i += 1) {
    const phase = t * faceEvery + i * 1.8 + camera.slot;
    const boxW = 82 + i * 12;
    const boxH = 106 + i * 8;
    const x = 90 + i * 220 + Math.sin(phase) * 26;
    const y = 72 + Math.cos(phase * 0.9) * 18;
    const hue = camera.mode === 0 ? "#78e0bd" : "#ffd166";
    ctx.strokeStyle = hue;
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, boxW, boxH);
    ctx.fillStyle = "rgba(9, 17, 24, 0.72)";
    ctx.fillRect(x, y - 28, 172, 24);
    ctx.fillStyle = hue;
    ctx.font = "700 15px Microsoft YaHei UI, sans-serif";
    const person = state.users[(i + camera.slot) % state.users.length] || "未识别";
    const label = camera.mode === 0 ? `${person}  ${86 + i * 4}%  中性` : "检测到人脸";
    ctx.fillText(label, x + 8, y - 11);
  }

  ctx.fillStyle = "rgba(9, 17, 24, 0.72)";
  ctx.fillRect(14, h - 40, 220, 26);
  ctx.fillStyle = "#d8e2ea";
  ctx.font = "700 15px Microsoft YaHei UI, sans-serif";
  ctx.fillText(`${camera.name || `win${camera.slot}`} · ${modeText[camera.mode]}`, 24, h - 22);

  if (state.showFps) {
    camera.fps = fps;
    ctx.fillStyle = "rgba(9, 17, 24, 0.72)";
    ctx.fillRect(w - 92, h - 40, 78, 26);
    ctx.fillStyle = "#7ee0bd";
    ctx.fillText(`${fps} FPS`, w - 82, h - 22);
  }
}

function animationLoop(now = performance.now()) {
  state.cameras.forEach((camera) => {
    const tile = $(`.video-tile[data-slot="${camera.slot}"]`);
    const canvas = $("canvas", tile);
    const ctx = canvas.getContext("2d", { alpha: false });
    if (camera.running) {
      drawStream(ctx, canvas, camera, now);
    } else {
      drawNoSignal(ctx, canvas, camera.name || `win${camera.slot}`);
    }
  });

  const enroll = $("#enrollCanvas");
  const enrollCtx = enroll.getContext("2d", { alpha: false });
  drawStream(enrollCtx, enroll, { slot: 9, name: "录入预览", mode: 1, running: true }, now);

  requestAnimationFrame(animationLoop);
}

function renderLogs(rows = state.logs) {
  const body = $("#logBody");
  body.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${row[0]}</td>
          <td>${row[1]}</td>
          <td>${row[2]}</td>
          <td>${row[3]}</td>
          <td>${row[4]}</td>
          <td>${row[5]}</td>
        </tr>
      `,
    )
    .join("");
}

function populateFilters() {
  const people = ["任何人员", ...new Set(state.users)];
  const places = ["任何地点", ...new Set(state.cameras.map((item) => item.name).filter(Boolean))];
  $("#filterPerson").innerHTML = people.map((item) => `<option>${item}</option>`).join("");
  $("#filterPlace").innerHTML = places.map((item) => `<option>${item}</option>`).join("");

  const now = new Date();
  const start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
  $("#startTime").value = start.toISOString().slice(0, 16);
  $("#endTime").value = now.toISOString().slice(0, 16);
}

function queryLogs() {
  const person = $("#filterPerson").value;
  const place = $("#filterPlace").value;
  const type = $("#filterType").value;
  const status = $("#filterStatus").value;
  const rows = state.logs.filter((row) => {
    if (person !== "任何人员" && row[0] !== person) return false;
    if (place !== "任何地点" && row[1] !== place) return false;
    if (type !== "任何类型" && row[4] !== type) return false;
    if (status !== "任何状态" && row[5] !== status) return false;
    return true;
  });
  renderLogs(rows);
  return rows;
}

function exportCsv(rows) {
  const header = ["姓名", "地点", "时间", "情绪", "考勤类型", "状态"];
  const csv = [header, ...rows]
    .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(","))
    .join("\n");
  const blob = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `attendance_report_${Date.now()}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function openCameraDialog(kind) {
  const dialog = $("#cameraDialog");
  $("#dialogTitle").textContent = kind === "delete" ? "删除摄像头" : "添加摄像头";
  $("#dialogName").disabled = kind === "delete";
  $("#dialogMode").disabled = kind === "delete";
  $("#dialogSource").disabled = kind === "delete";
  dialog.dataset.kind = kind;
  dialog.showModal();
}

function applyDialog() {
  const slot = Number($("#dialogSlot").value);
  const camera = state.cameras.find((item) => item.slot === slot);
  if (!camera) return;
  if ($("#cameraDialog").dataset.kind === "delete") {
    camera.running = false;
    camera.name = "";
    camera.source = "";
    toast(`已删除 win${slot} 摄像头`);
  } else {
    camera.name = $("#dialogName").value.trim() || `win${slot}`;
    camera.mode = Number($("#dialogMode").value);
    camera.source = $("#dialogSource").value.trim();
    camera.running = true;
    toast(`已添加 win${slot} 摄像头`);
  }
  renderCameraConfig();
  updateTiles();
  populateFilters();
  updateStatus();
}

function bindEvents() {
  $$(".nav-tab").forEach((btn) => btn.addEventListener("click", () => switchView(btn.dataset.view)));

  $("#runtimeMode").addEventListener("change", (event) => {
    state.runtimeMode = event.target.value;
    updateStatus();
    toast("识别策略已切换");
  });

  $("#fpsToggle").addEventListener("click", () => {
    state.showFps = !state.showFps;
    $("#fpsToggle").textContent = state.showFps ? "隐藏 FPS" : "显示 FPS";
  });

  $("#startAllBtn").addEventListener("click", () => {
    state.cameras.forEach((camera) => {
      if (camera.name || camera.source) camera.running = true;
    });
    updateTiles();
    updateStatus();
    toast("测试视频已开启");
  });

  $("#stopAllBtn").addEventListener("click", () => {
    state.cameras.forEach((camera) => {
      camera.running = false;
    });
    updateTiles();
    updateStatus();
    toast("全部视频已关闭");
  });

  $("#addCameraBtn").addEventListener("click", () => openCameraDialog("add"));
  $("#delCameraBtn").addEventListener("click", () => openCameraDialog("delete"));
  $("#dialogOk").addEventListener("click", applyDialog);

  $("#saveConfigBtn").addEventListener("click", async () => {
    syncConfigFromInputs();
    await api.saveCameras(state.cameras).catch(() => null);
    renderCameraConfig();
    updateTiles();
    toast("配置已保存");
  });

  $("#applyConfigBtn").addEventListener("click", async () => {
    syncConfigFromInputs();
    await api.applyCameras(state.cameras).catch(() => null);
    state.cameras.forEach((camera) => {
      camera.running = Boolean(camera.name || camera.source);
    });
    updateTiles();
    updateStatus();
    toast("配置已应用");
  });

  $("#signinBtn").addEventListener("click", () => {
    if (state.customSignin) {
      toast(`签到“${state.customSignin}”已经结束`);
      state.customSignin = "";
      $("#signinName").disabled = false;
      $("#signinBtn").textContent = "开始签到";
      $("#signinState").textContent = "自定义签到：未开启";
      return;
    }
    const name = $("#signinName").value.trim();
    if (!name) {
      toast("请先输入签到名称");
      return;
    }
    state.customSignin = name;
    $("#signinName").disabled = true;
    $("#signinBtn").textContent = "结束签到";
    $("#signinState").textContent = `自定义签到：进行中（${name}）`;
  });

  $("#captureBtn").addEventListener("click", () => {
    const name = $("#faceName").value.trim();
    if (!name) {
      toast("请先输入录入姓名");
      return;
    }
    state.sampleCount = 0;
    const timer = window.setInterval(() => {
      state.sampleCount += 2;
      if (state.sampleCount >= 20) {
        state.sampleCount = 20;
        state.modelPending = true;
        if (!state.users.includes(name)) state.users.push(name);
        window.clearInterval(timer);
        populateFilters();
        toast("采集完成，请更新模型");
      }
      updateStatus();
    }, 160);
  });

  $("#trainBtn").addEventListener("click", async () => {
    await api.trainModel().catch(() => null);
    state.trainingCount += state.sampleCount;
    state.sampleCount = 0;
    state.modelPending = false;
    updateStatus();
    toast("模型更新完成");
  });

  $("#resetModelBtn").addEventListener("click", () => {
    if (!confirm("确定重置所有人脸样本及识别模型？")) return;
    state.users = [];
    state.sampleCount = 0;
    state.trainingCount = 0;
    state.modelPending = false;
    populateFilters();
    updateStatus();
    toast("模型已重置");
  });

  $("#deleteFaceBtn").addEventListener("click", () => {
    const name = $("#faceName").value.trim();
    if (!name) {
      toast("请输入要删除的人脸姓名");
      return;
    }
    state.users = state.users.filter((item) => item !== name);
    state.modelPending = true;
    populateFilters();
    updateStatus();
    toast(`已删除 ${name}，模型待更新`);
  });

  $("#loginBtn").addEventListener("click", async () => {
    const account = $("#accountInput").value.trim();
    const password = $("#passwordInput").value;
    await api.login(account, password).catch(() => null);
    state.auth.account = account || "admin";
    toast(`欢迎使用，${state.auth.account}`);
  });

  $("#registerBtn").addEventListener("click", () => toast("注册窗口已打开"));
  $("#queryLogBtn").addEventListener("click", () => queryLogs());
  $("#clearLogBtn").addEventListener("click", () => {
    state.logs = [];
    renderLogs();
    toast("日志数据库已清空");
  });
  $("#absenceBtn").addEventListener("click", () => {
    const recorded = new Set(state.logs.map((row) => row[0]));
    const absent = state.users.filter((name) => !recorded.has(name));
    toast(absent.length ? `缺勤：${absent.join("、")}` : "无缺勤人员");
  });
  $("#summaryBtn").addEventListener("click", () => {
    const rows = queryLogs();
    toast(`当前筛选范围共 ${rows.length} 条记录`);
  });
  $("#exportBtn").addEventListener("click", () => exportCsv(queryLogs()));
}

function init() {
  renderCameraConfig();
  updateTiles();
  populateFilters();
  renderLogs();
  updateStatus();
  bindEvents();
  requestAnimationFrame(animationLoop);
}

init();
