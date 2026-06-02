"use strict";

let diffEditor = null;
let monacoReady = false;
let apiReady = false;

const $ = (id) => document.getElementById(id);

function setStatus(text, busy) {
  $("status").textContent = text;
  $("spinner").classList.toggle("hidden", !busy);
}

/* ---------- 下载进度（轮询后端 get_progress 实时展示） ---------- */

let progressTimer = null;
let liveListKey = "";  // 实时列表的指纹，变化时才重绘，避免无谓刷新

// 文件列表缓存 + 当前搜索词（用于左侧列表的模糊过滤）
let lastFiles = [];
let searchQuery = "";
// 按状态类型筛选（chip 切换）：true=显示，false=隐藏
const typeFilter = { modified: true, added: true, removed: true };

function fmtBytes(n) {
  n = Number(n) || 0;
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  if (n < 1024 * 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + " MB";
  return (n / 1024 / 1024 / 1024).toFixed(2) + " GB";
}

function renderProgress(p) {
  const el = $("progress");
  if (!p || !p.active) {
    el.classList.add("hidden");
    el.textContent = "";
    return;
  }
  const head = [p.phase, p.name].filter(Boolean).join(" · ");
  if (p.kind === "compare") {
    // 对比阶段：展示「当前类 (已处理/总数 百分比)」
    let detail = "";
    if (p.count > 0) {
      const pct = Math.min(100, Math.floor((p.current / p.count) * 100));
      detail = ` — ${p.current} / ${p.count} (${pct}%)`;
    }
    el.textContent = `⚙ ${head}${detail}`;
  } else {
    // 下载阶段：展示「已下载/总量 百分比 · 速度」
    let detail;
    if (p.total > 0) {
      const pct = Math.min(100, Math.floor((p.downloaded / p.total) * 100));
      detail = `${fmtBytes(p.downloaded)} / ${fmtBytes(p.total)} (${pct}%)`;
    } else {
      detail = `${fmtBytes(p.downloaded)}`;
    }
    if (p.speed > 0) detail += ` · ${fmtBytes(p.speed)}/s`;
    el.textContent = `↓ ${head} — ${detail}`;
  }
  el.classList.remove("hidden");
}

function renderLiveSummary(p) {
  const files = (p && p.files) || [];
  let m = 0, a = 0, d = 0;
  files.forEach((f) => {
    if (f.status === "modified") m++;
    else if (f.status === "added") a++;
    else d++;
  });
  let head = "对比中…";
  if (p && p.active && p.count > 0) {
    head = `${p.phase || "对比中"} ${p.current}/${p.count}`;
  }
  $("summary").innerHTML =
    `<div><span class="live-dot"></span>${escapeHtml(head)}</div>` +
    `<div><span class="stat-modified">修改 ${m}</span> · ` +
    `<span class="stat-added">新增 ${a}</span> · ` +
    `<span class="stat-removed">删除 ${d}</span></div>`;
}

async function pollProgress() {
  try {
    const p = await window.pywebview.api.get_progress();
    renderProgress(p);
    // 对比阶段：实时把已发现的差异列到左侧树，并显示“仍在对比”标识
    if (p && p.kind === "compare" && Array.isArray(p.files)) {
      const key = p.files.length + ":" + (p.active ? "1" : "0");
      if (key !== liveListKey) {
        liveListKey = key;
        lastFiles = p.files;
        refreshFileList();
        renderLiveSummary(p);
      }
    }
  } catch (e) {
    /* 忽略单次轮询失败 */
  }
}

function startProgressPolling() {
  stopProgressPolling();
  progressTimer = setInterval(pollProgress, 250);
}

function stopProgressPolling() {
  if (progressTimer) {
    clearInterval(progressTimer);
    progressTimer = null;
  }
  renderProgress(null);
}

/* ---------- Monaco 加载（本地 vendor 优先，失败回退 CDN） ---------- */

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error("加载失败: " + src));
    document.head.appendChild(s);
  });
}

async function loadMonaco() {
  const bases = window.__MONACO_BASES__ || [];
  let loadedBase = null;
  for (const base of bases) {
    try {
      await loadScript(base + "/loader.js");
      loadedBase = base;
      break;
    } catch (e) {
      console.warn(e.message);
    }
  }
  if (!loadedBase) throw new Error("无法加载 Monaco 编辑器（本地与 CDN 均失败）");

  return new Promise((resolve, reject) => {
    window.require.config({ paths: { vs: loadedBase } });
    window.require(["vs/editor/editor.main"], () => {
      diffEditor = monaco.editor.createDiffEditor($("editor"), {
        theme: "vs-dark",
        automaticLayout: true,
        readOnly: true,
        renderSideBySide: true,
        ignoreTrimWhitespace: false,
        fontSize: 12,
      });
      monacoReady = true;
      resolve();
    }, reject);
  });
}

/* ---------- pywebview API 就绪 ---------- */

// 需要持久化的字段（与输入控件 id 对应）
const TEXT_FIELDS = ["old", "new", "repo", "user", "filter", "decompiler"];

function collectSettings() {
  const s = {};
  TEXT_FIELDS.forEach((id) => { s[id] = $(id).value; });
  s.ignoreMeta = $("ignoreMeta").checked;
  s.insecure = $("insecure").checked;
  return s;
}

function applySettings(s) {
  if (!s) return;
  TEXT_FIELDS.forEach((id) => {
    if (s[id] !== undefined && s[id] !== null) $(id).value = s[id];
  });
  if (typeof s.ignoreMeta === "boolean") $("ignoreMeta").checked = s.ignoreMeta;
  if (typeof s.insecure === "boolean") $("insecure").checked = s.insecure;
}

async function getDefaultRepo() {
  try {
    return await window.pywebview.api.default_repo();
  } catch (e) {
    return "";
  }
}

async function persistSettings() {
  try {
    await window.pywebview.api.save_settings(collectSettings());
  } catch (e) { /* ignore */ }
}

window.addEventListener("pywebviewready", async () => {
  apiReady = true;
  try {
    const res = await window.pywebview.api.load_settings();
    if (res && res.ok) applySettings(res.settings);
  } catch (e) {
    const repo = await getDefaultRepo();
    if (repo && !$("repo").value) $("repo").value = repo;
  }
  maybeEnable();
});

function swapJars() {
  const oldEl = $("old");
  const newEl = $("new");
  const tmp = oldEl.value;
  oldEl.value = newEl.value;
  newEl.value = tmp;
  persistSettings();
  setStatus("已交换旧版 / 新版", false);
}

async function saveRepo() {
  await persistSettings();
  setStatus("已保存当前所有设置", false);
}

async function resetRepo() {
  const repo = await getDefaultRepo();
  $("repo").value = repo || "";
  await persistSettings();
  setStatus("已恢复为公共仓库地址", false);
}

function maybeEnable() {
  if (monacoReady && apiReady) {
    $("compareBtn").disabled = false;
    setStatus("就绪", false);
  }
}

/* ---------- 比较 ---------- */

async function doCompare() {
  if (!apiReady) { setStatus("后端未就绪", false); return; }
  const payload = {
    old: $("old").value,
    new: $("new").value,
    repo: $("repo").value,
    user: $("user").value,
    password: $("password").value,
    decompiler: $("decompiler").value,
    filter: $("filter").value,
    ignoreMeta: $("ignoreMeta").checked,
    insecure: $("insecure").checked,
  };
  if (!payload.old || !payload.new) {
    setStatus("请填写两个 JAR 来源", false);
    return;
  }
  // 记住本次使用的所有设置（密码除外），下次打开自动填充
  persistSettings();

  $("compareBtn").disabled = true;
  setStatus("正在下载并比较…", true);
  $("filelist").innerHTML = "";
  $("summary").innerHTML = '<div class="hint">比较中…</div>';
  liveListKey = "";
  lastFiles = [];
  startProgressPolling();

  try {
    const res = await window.pywebview.api.compare(payload);
    stopProgressPolling();  // 比较完成，停止轮询后用最终结果渲染（避免被末次轮询覆盖）
    if (!res.ok) {
      $("summary").innerHTML =
        '<div class="hint">出错：' + escapeHtml(res.error || "未知错误") + "</div>";
      setStatus("比较失败", false);
      return;
    }
    renderSummary(res.summary);
    lastFiles = res.files;
    refreshFileList();
    const fv = $("filter").value.trim();
    const s = res.summary;
    const changes = s.modified + s.added + s.removed;
    if (s.oldCount === 0 && s.newCount === 0 && fv) {
      setStatus(`过滤条件 “${fv}” 未匹配到任何文件，请修改或清空过滤后重试`, false);
    } else if (changes === 0) {
      setStatus(fv ? `完成：过滤 “${fv}” 范围内无差异` : "完成：两个 JAR 内容一致", false);
    } else {
      setStatus(`完成：修改 ${s.modified} · 新增 ${s.added} · 删除 ${s.removed}`, false);
    }
  } catch (e) {
    $("summary").innerHTML = '<div class="hint">异常：' + escapeHtml(String(e)) + "</div>";
    setStatus("比较异常", false);
  } finally {
    stopProgressPolling();
    $("compareBtn").disabled = false;
  }
}

function renderSummary(s) {
  $("summary").innerHTML =
    `<div>旧包文件 ${s.oldCount} · 新包文件 ${s.newCount}</div>` +
    `<div><span class="stat-modified">修改 ${s.modified}</span> · ` +
    `<span class="stat-added">新增 ${s.added}</span> · ` +
    `<span class="stat-removed">删除 ${s.removed}</span> · 未变 ${s.unchanged}</div>`;
}

const STATUS_BADGE = { modified: "M", added: "A", removed: "D" };

/* ---------- 模糊匹配（VS Code 风格：按序匹配字符） ---------- */
// 输入查询的字符必须在目标字符串中按相同顺序依次出现（忽略大小写、空白）
function fuzzyMatchIndices(text, query) {
  if (!query) return [];
  const t = String(text).toLowerCase();
  const q = String(query).toLowerCase().replace(/\s+/g, "");
  if (!q) return [];
  const idx = [];
  let ti = 0;
  for (let qi = 0; qi < q.length; qi++) {
    const c = q[qi];
    const pos = t.indexOf(c, ti);
    if (pos < 0) return null;
    idx.push(pos);
    ti = pos + 1;
  }
  return idx;
}

function fuzzyMatch(text, query) {
  return fuzzyMatchIndices(text, query) !== null;
}

// 把匹配字符包裹 <mark>，其余 escapeHtml
function highlightFuzzy(text, query) {
  const idx = fuzzyMatchIndices(text, query);
  if (!idx || !idx.length) return escapeHtml(text);
  const set = new Set(idx);
  let out = "";
  for (let i = 0; i < text.length; i++) {
    out += set.has(i)
      ? `<mark>${escapeHtml(text[i])}</mark>`
      : escapeHtml(text[i]);
  }
  return out;
}

/* 把扁平文件列表构建成目录树 */
function buildTree(files) {
  const root = { name: "", children: {}, files: [] };
  files.forEach((f) => {
    const parts = f.path.split("/");
    let cur = root;
    for (let i = 0; i < parts.length - 1; i++) {
      const d = parts[i];
      cur.children[d] = cur.children[d] || { name: d, children: {}, files: [] };
      cur = cur.children[d];
    }
    cur.files.push({ name: parts[parts.length - 1], path: f.path, status: f.status });
  });
  return root;
}

/* 合并单链目录：com/example/app → 一行（类似 VS Code compact folders） */
function compactTree(node) {
  Object.values(node.children).forEach(compactTree);
  const merged = {};
  Object.values(node.children).forEach((child) => {
    let n = child;
    while (Object.keys(n.children).length === 1 && n.files.length === 0) {
      const only = Object.values(n.children)[0];
      n = { name: n.name + "/" + only.name, children: only.children, files: only.files };
    }
    merged[n.name] = n;
  });
  node.children = merged;
}

function countChanges(node) {
  let n = node.files.length;
  Object.values(node.children).forEach((c) => { n += countChanges(c); });
  return n;
}

function renderNode(node, container, depth, query) {
  Object.keys(node.children).sort().forEach((name) => {
    const child = node.children[name];
    const row = document.createElement("div");
    row.className = "tree-row tree-dir";
    row.style.paddingLeft = (depth * 12 + 6) + "px";
    // 目录名（合并后可能形如 com/example/app）也参与高亮
    row.innerHTML =
      `<span class="twisty">▾</span>` +
      `<span class="dir-name">${query ? highlightFuzzy(name, query) : escapeHtml(name)}</span>` +
      `<span class="dir-count">${countChanges(child)}</span>`;
    const kids = document.createElement("div");
    kids.className = "tree-kids";
    row.addEventListener("click", () => {
      row.classList.toggle("collapsed");
      kids.classList.toggle("hidden");
    });
    container.appendChild(row);
    container.appendChild(kids);
    renderNode(child, kids, depth + 1, query);
  });

  node.files
    .sort((a, b) => a.name.localeCompare(b.name))
    .forEach((f) => {
      const item = document.createElement("div");
      item.className = "tree-row tree-file " + f.status;
      item.style.paddingLeft = (depth * 12 + 16) + "px";
      item.innerHTML =
        `<span class="badge">${STATUS_BADGE[f.status]}</span>` +
        `<span class="name">${query ? highlightFuzzy(f.name, query) : escapeHtml(f.name)}</span>`;
      item.title = f.path;
      item.addEventListener("click", () => selectFile(item, f.path));
      container.appendChild(item);
    });
}

function renderFileList(files, filterValue, query, totalBeforeSearch, hiddenAllByType) {
  const list = $("filelist");
  list.innerHTML = "";
  if (!files.length) {
    let msg;
    if (query) {
      msg = `搜索 “${escapeHtml(query)}” 无匹配（当前类型可见 ${totalBeforeSearch || 0} 个）`;
    } else if (hiddenAllByType) {
      msg = "当前类型筛选下没有差异，点击上方 chip 显示其他类型";
    } else if (filterValue) {
      msg = `过滤 “${escapeHtml(filterValue)}” 下无差异/无匹配`;
    } else {
      msg = "无差异";
    }
    list.innerHTML = `<div class="group-title">${msg}</div>`;
    return;
  }
  const root = buildTree(files);
  compactTree(root);
  renderNode(root, list, 0, query || "");
}

/* 根据 lastFiles + searchQuery + typeFilter 刷新左侧列表（并同步计数） */
function refreshFileList() {
  // 1) 按状态类型筛选
  const typed = lastFiles.filter((f) => typeFilter[f.status]);
  // 2) 再叠加模糊搜索
  const q = searchQuery;
  const filtered = q ? typed.filter((f) => fuzzyMatch(f.path, q)) : typed;

  const hiddenAllByType = lastFiles.length > 0 && typed.length === 0;
  renderFileList(filtered, $("filter").value.trim(), q, typed.length, hiddenAllByType);

  const cnt = $("searchCount");
  if (q) {
    cnt.textContent = `${filtered.length} / ${typed.length}`;
    cnt.classList.remove("hidden");
  } else {
    cnt.classList.add("hidden");
  }

  // 3) 更新 chip 上的计数（基于原始全集 lastFiles）
  let m = 0, a = 0, d = 0;
  lastFiles.forEach((f) => {
    if (f.status === "modified") m++;
    else if (f.status === "added") a++;
    else if (f.status === "removed") d++;
  });
  const setCount = (k, v) => {
    const el = document.querySelector(`#typeFilter .chip-count[data-count="${k}"]`);
    if (el) el.textContent = v;
  };
  setCount("modified", m);
  setCount("added", a);
  setCount("removed", d);
}

/* ---------- 选择文件 → 内嵌 diff ---------- */

async function selectFile(itemEl, path) {
  document.querySelectorAll(".tree-file.active")
    .forEach((el) => el.classList.remove("active"));
  itemEl.classList.add("active");

  setStatus("加载 diff…", true);
  try {
    const res = await window.pywebview.api.get_diff(path);
    if (!res.ok) {
      setStatus("加载失败：" + (res.error || ""), false);
      return;
    }
    $("editorHeader").textContent = res.displayName || path;
    $("placeholder").classList.add("hidden");

    const lang = res.renderable ? res.language : "plaintext";
    const oldText = res.renderable ? res.old : (res.note || "");
    const newText = res.renderable ? res.new : (res.note || "");

    const originalModel = monaco.editor.createModel(oldText, lang);
    const modifiedModel = monaco.editor.createModel(newText, lang);
    const prev = diffEditor.getModel();
    diffEditor.setModel({ original: originalModel, modified: modifiedModel });
    if (prev) {
      prev.original && prev.original.dispose();
      prev.modified && prev.modified.dispose();
    }
    setStatus(res.renderable ? "就绪" : "该文件无法文本对比", false);
  } catch (e) {
    setStatus("异常：" + String(e), false);
  }
}

/* ---------- 工具 ---------- */

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------- 事件绑定 ---------- */

window.addEventListener("DOMContentLoaded", async () => {
  $("compareBtn").disabled = true;
  $("compareBtn").addEventListener("click", doCompare);
  $("advBtn").addEventListener("click", () => $("advPanel").classList.toggle("hidden"));
  $("saveRepoBtn").addEventListener("click", saveRepo);
  $("resetRepoBtn").addEventListener("click", resetRepo);
  $("swapBtn").addEventListener("click", swapJars);
  ["old", "new", "filter"].forEach((id) =>
    $(id).addEventListener("keydown", (e) => { if (e.key === "Enter") doCompare(); }));

  // 左侧列表模糊搜索（轻量防抖，避免实时对比期间频繁重绘）
  let searchTimer = null;
  $("search").addEventListener("input", (e) => {
    const v = e.target.value;
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      searchQuery = (v || "").trim();
      refreshFileList();
    }, 80);
  });
  $("search").addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.target.value = ""; searchQuery = ""; refreshFileList(); }
  });

  // 状态类型 chip：点击切换显示/隐藏；右键“仅显示当前类型”
  document.querySelectorAll("#typeFilter .chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const k = btn.dataset.type;
      typeFilter[k] = !typeFilter[k];
      btn.classList.toggle("active", typeFilter[k]);
      // 全部关闭时回退为全部开启，避免“什么都看不到”
      if (!typeFilter.modified && !typeFilter.added && !typeFilter.removed) {
        Object.keys(typeFilter).forEach((kk) => { typeFilter[kk] = true; });
        document.querySelectorAll("#typeFilter .chip").forEach((b) => b.classList.add("active"));
      }
      refreshFileList();
    });
    btn.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      Object.keys(typeFilter).forEach((kk) => { typeFilter[kk] = kk === btn.dataset.type; });
      document.querySelectorAll("#typeFilter .chip").forEach((b) =>
        b.classList.toggle("active", b.dataset.type === btn.dataset.type));
      refreshFileList();
    });
  });

  setStatus("加载编辑器内核…", true);
  try {
    await loadMonaco();
    maybeEnable();
    if (!apiReady) setStatus("等待后端…", true);
  } catch (e) {
    setStatus(String(e.message || e), false);
  }
});
