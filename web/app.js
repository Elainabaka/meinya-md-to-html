(function(){
"use strict";
const $ = id => document.getElementById(id);
const api = () => (window.pywebview && window.pywebview.api) || null;
async function call(name, ...args){
  const a = api();
  if(!a) throw new Error("backend chưa sẵn sàng");
  return a[name](...args);
}

const state = {
  files: [], sel: -1, settings: {}, cacheMode: "beside", watch: true,
  zoom: 1, lastRev: -1, shownRev: -1, shownIndex: -1, scrollY: {},
  busy: false, filter: "", inline: false,
};

/* ---------- ui helpers ---------- */
function log(msg){
  const el = $("log");
  el.textContent += msg + "\n";
  el.scrollTop = el.scrollHeight;
}
function status(msg){ $("status").textContent = msg; }
function setBadge(kind, text){
  const b = $("prevBadge");
  if(!text){ b.hidden = true; b.textContent = ""; b.className = "badge"; return; }
  b.hidden = false; b.textContent = text; b.className = "badge " + (kind || "");
}
function toast(msg, opts){
  opts = opts || {};
  const box = document.createElement("div");
  box.className = "toast " + (opts.kind || "");
  const tx = document.createElement("span"); tx.className = "tx"; tx.textContent = msg;
  box.appendChild(tx);
  if(opts.action){
    const b = document.createElement("button");
    b.textContent = opts.action.label;
    b.onclick = () => { box.remove(); opts.action.fn(); };
    box.appendChild(b);
  }
  $("toasts").appendChild(box);
  setTimeout(() => box.remove(), opts.sticky ? 12000 : 4200);
}
function setEmpty(on){
  $("emptyState").classList.toggle("hide", !on);
  $("preview").style.visibility = on ? "hidden" : "visible";
}
function fmtKB(n){ n = Number(n)||0; return n >= 1024*1024 ? (n/1048576).toFixed(1)+" MB" : Math.max(1, Math.round(n/1024)) + " KB"; }

/* ---------- settings ---------- */
function settings(){
  return {
    title: $("optTitle").value.trim(),
    eyebrow: $("optEyebrow").value.trim() || "Tài liệu kỹ thuật",
    lang: $("optLang").value,
    date: $("optDate").value.trim(),
    no_toc: $("optNoToc").checked,
  };
}
function applySettings(s){
  s = s || {};
  if(s.eyebrow) $("optEyebrow").value = s.eyebrow;
  if(s.lang) $("optLang").value = s.lang;
  if(s.date) $("optDate").value = s.date;
  $("optNoToc").checked = !!s.no_toc;
}
let settingsTimer = null;
function onSettingsChanged(){
  clearTimeout(settingsTimer);
  settingsTimer = setTimeout(async () => {
    state.settings = settings();
    await showPreview(state.sel);
  }, 350);
}

/* ---------- file list ---------- */
function parentName(p){
  const parts = String(p||"").replace(/\\/g, "/").split("/");
  return parts.length > 1 ? parts[parts.length - 2] : "";
}
function renderList(){
  const ul = $("fileList");
  ul.innerHTML = "";
  const dirs = new Set(state.files.map(f => parentName(f.path)));
  const multiDir = dirs.size > 1;
  let shown = 0;
  state.files.forEach((f, i) => {
    if(state.filter && !f.name.toLowerCase().includes(state.filter)) return;
    shown++;
    const li = document.createElement("li");
    if(i === state.sel) li.className = "sel";
    const dot = document.createElement("span");
    dot.className = "dot " + (f.state || "pending");
    dot.title = ({fresh:"Đã cache", rendered:"Đã cache", stale:"Đang cập nhật…", pending:"Chờ render",
      missing:"File đã bị xoá/đổi tên", error:(f.msg || "Lỗi"), inline:"Chỉ xem tạm (không ghi được cache)"})[f.state] || "";
    const nm = document.createElement("span"); nm.className = "nm"; nm.textContent = f.name; nm.title = f.path;
    li.append(dot, nm);
    if(multiDir){
      const d = document.createElement("span"); d.className = "dir"; d.textContent = parentName(f.path);
      li.appendChild(d);
    }
    const rm = document.createElement("button");
    rm.className = "rm"; rm.textContent = "×"; rm.title = "Bỏ file";
    rm.onclick = async ev => {
      ev.stopPropagation();
      await call("remove_file", i);
      if(state.sel > i) state.sel--;
      if(state.sel === i){ state.sel = Math.min(i, state.files.length - 2); }
      await refresh({ preview: true });
    };
    li.appendChild(rm);
    li.onclick = () => select(i);
    ul.appendChild(li);
  });
  $("fileCount").textContent = state.files.length;
  $("listEmpty").style.display = (state.files.length && shown) ? "none" : "";
  updateFoot();
}
function updateFoot(){
  const total = state.files.length;
  const cached = state.files.filter(f => f.state === "fresh" || f.state === "rendered").length;
  $("queueFoot").textContent = total ? `${total} file · ${cached} đã cache` : "—";
}

/* ---------- preview ---------- */
async function showPreview(i, force){
  if(i < 0 || i >= state.files.length){
    state.shownIndex = -1; setEmpty(true); setBadge("", "");
    $("prevName").textContent = "—"; $("prevStats").textContent = "";
    $("crumb").textContent = "Chưa chọn file"; $("crumb").title = "";
    return;
  }
  let r;
  try { r = await call("preview_info", i, settings()); }
  catch(e){ toast("Lỗi preview: " + e.message, {kind:"err"}); return; }
  if(!r.ok){ setBadge("err", r.error || "Lỗi"); setEmpty(false); status(r.error || "Lỗi render."); return; }
  state.inline = !!r.inline;
  const f = state.files[i] || {};
  f.state = r.inline ? "inline" : (r.fallback ? "fresh" : (r.state || "fresh"));
  f.revision = r.revision;
  f.out = r.out; f.fallback = r.fallback;
  $("prevName").textContent = r.name;
  $("prevStats").textContent = r.stats ? "· " + r.stats : "";
  $("crumb").textContent = r.path; $("crumb").title = r.path;
  const frame = $("preview");
  if(r.inline){
    if(force || frame.srcdoc !== r.html){ frame.removeAttribute("src"); frame.srcdoc = r.html; }
  } else if(force || frame.getAttribute("src") !== r.url){
    frame.src = r.url;
  }
  state.shownIndex = i;
  const bumped = Number(r.revision) > state.shownRev;
  state.shownRev = Number(r.revision) || 0;
  setEmpty(false);
  if(r.fallback && !r.inline){
    setBadge("warn", "cache trong tool");
    status(`File .html cạnh file gốc không phải của tool → cache: ${r.out}`);
  } else if(r.inline){
    setBadge("warn", "chỉ xem tạm");
    status("Không ghi được cache (quyền thư mục?) — preview tạm trong bộ nhớ.");
  } else {
    setBadge("", "");
    status(`đã cache · ${fmtKB(f.out_size || f.size)} · ${(force || bumped) ? "vừa cập nhật" : "cache còn mới"}`);
  }
  renderList();
}
async function select(i){
  state.sel = i;
  renderList();
  if(i >= 0 && state.files[i]) status(state.files[i].path || "");
  await showPreview(i);
}

/* ---------- refresh / boot ---------- */
async function refresh(opts){
  opts = opts || {};
  let st;
  try { st = await call("initial_state"); }
  catch(e){ return; }
  state.files = st.files || [];
  state.settings = st.settings || {};
  state.cacheMode = st.cache_mode || "beside";
  state.watch = !!st.watch;
  state.lastRev = Number(st.revision) || 0;
  applySettings(state.settings);
  $("cmBeside").checked = state.cacheMode !== "tool";
  $("cmTool").checked = state.cacheMode === "tool";
  $("optWatch").checked = state.watch;
  $("ver").textContent = "v" + (st.version || "2.1.0");
  if(opts.selectLast && state.files.length) state.sel = state.files.length - 1;
  if(state.sel >= state.files.length) state.sel = state.files.length - 1;
  if(state.sel < 0 && state.files.length && !opts.selectLast) state.sel = state.files.length - 1;
  renderList();
  if(opts.preview === false){ setEmpty(state.sel < 0); }
  else await showPreview(state.sel);
}
window.__mdRefresh = async function(){ await refresh({ selectLast: true }); };

/* ---------- poll: live update + job progress ---------- */
function updateJob(job){
  const running = !!job.running;
  $("prog").hidden = !running;
  if(running){
    const pct = job.total ? Math.round((job.done || 0) / job.total * 100) : 0;
    $("progBar").style.width = pct + "%";
    status(`${job.kind === "export" ? "Đang xuất" : "Đang cache"} ${job.done || 0}/${job.total || 0} — ${job.current || ""}`);
    state.busy = true;
    return;
  }
  if(!state.busy) return;
  state.busy = false;
  $("progBar").style.width = "0%";
  if(job.finished){
    const n = (job.outputs || []).length, errs = (job.errors || []).length;
    const what = job.kind === "export" ? "xuất" : "cache";
    if(job.cancelled) toast(`Đã hủy ${what}.`, {kind:"err"});
    else if(errs) toast(`${what}: ${n} xong, ${errs} lỗi (xem Nhật ký).`, {kind:"err"});
    else toast(`Xong ${what} ${n} file.`, {kind:"ok"});
    (job.outputs || []).forEach(o => log((job.kind === "export" ? "Đã xuất: " : "Cache: ") + o));
    (job.errors || []).forEach(e => log("LỖI: " + e));
  }
  state.lastRev = -1;
}
async function poll(){
  if(!api()) return;
  let st;
  try { st = await call("watch_poll"); } catch(e){ return; }
  updateJob(st.job || {});
  const rev = Number(st.revision) || 0;
  if(rev === state.lastRev) return;
  state.lastRev = rev;
  (st.files || []).forEach((f, i) => { if(state.files[i]) Object.assign(state.files[i], f); });
  renderList();
  if(state.sel < 0 || !state.files[state.sel]) return;
  const f = state.files[state.sel];
  if(f.state === "missing"){ status(`File đã bị xoá hoặc đổi tên: ${f.name}`); return; }
  if(state.shownIndex === state.sel && Number(f.revision || 0) !== state.shownRev){
    await showPreview(state.sel);
  }
}

/* ---------- actions ---------- */
async function doAdd(){
  try { await call("add_files"); await refresh({ selectLast: true }); }
  catch(e){ toast("Lỗi thêm file: " + e.message, {kind:"err"}); }
}
async function doFolder(){
  try { await call("add_folder", $("optRec").checked); await refresh({ selectLast: true }); }
  catch(e){ toast("Lỗi thêm thư mục: " + e.message, {kind:"err"}); }
}
async function doClear(){
  try { await call("clear_files"); state.sel = -1; await refresh({ preview:true }); }
  catch(e){ toast("Lỗi: " + e.message, {kind:"err"}); }
}
async function doExport(){
  if(state.sel < 0){ toast("Chưa chọn file.", {kind:"err"}); return; }
  try {
    const r = await call("export_current", state.sel, settings());
    if(r.cancelled) return;
    if(!r.ok){ toast("Xuất lỗi: " + (r.error || ""), {kind:"err"}); return; }
    log("Đã xuất: " + r.path);
    toast("Đã xuất: " + r.path, {kind:"ok", action:{label:"Mở ↗", fn:() => call("open_in_browser", state.sel, settings()).catch(()=>{})}});
  } catch(e){ toast("Xuất lỗi: " + e.message, {kind:"err"}); }
}
async function doExportAll(){
  try {
    const r = await call("export_all", settings());
    if(r.cancelled) return;
    if(!r.ok){ toast("Xuất lỗi: " + (r.error || ""), {kind:"err"}); return; }
    log("Bắt đầu xuất tất cả…");
  } catch(e){ toast("Xuất lỗi: " + e.message, {kind:"err"}); }
}
async function doOpen(){
  if(state.sel < 0){ toast("Chưa chọn file.", {kind:"err"}); return; }
  try {
    const r = await call("open_in_browser", state.sel, settings());
    if(!r.ok) toast("Mở lỗi: " + (r.error || ""), {kind:"err"});
  } catch(e){ toast("Mở lỗi: " + e.message, {kind:"err"}); }
}
async function doReveal(){
  if(state.sel < 0){ toast("Chưa chọn file.", {kind:"err"}); return; }
  try { await call("reveal", state.sel); }
  catch(e){ toast("Lỗi: " + e.message, {kind:"err"}); }
}
async function doOpenOutput(){
  try {
    const r = await call("open_output");
    if(!r.ok) toast(r.error || "Chưa có thư mục xuất.", {kind:"err"});
  } catch(e){ toast("Lỗi: " + e.message, {kind:"err"}); }
}

/* ---------- zoom ---------- */
function setZoom(z){
  state.zoom = Math.min(2, Math.max(0.6, Math.round(z * 100) / 100));
  const f = $("preview");
  f.style.zoom = state.zoom;
  f.style.width = (100 / state.zoom) + "%";
  f.style.height = (100 / state.zoom) + "%";
  $("btnZoomReset").textContent = Math.round(state.zoom * 100) + "%";
}

/* ---------- theme ---------- */
function applyTheme(t){
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("mdhtml.theme", t); } catch(e){}
}

/* ---------- columns ---------- */
function initColumns(){
  const root = document.documentElement;
  try {
    const w1 = localStorage.getItem("mdhtml.w1"); if(w1) root.style.setProperty("--w1", w1);
    const w2 = localStorage.getItem("mdhtml.w2"); if(w2) root.style.setProperty("--w2", w2);
  } catch(e){}
  function drag(splitId, side, cssVar, storeKey, min, max){
    const el = $(splitId);
    el.addEventListener("mousedown", e => {
      e.preventDefault();
      const startX = e.clientX;
      const cur = parseInt(getComputedStyle(root).getPropertyValue(cssVar)) || 296;
      el.classList.add("drag");
      const move = ev => {
        let w = side === "left" ? cur + (ev.clientX - startX) : cur - (ev.clientX - startX);
        w = Math.max(min, Math.min(max, w));
        root.style.setProperty(cssVar, w + "px");
      };
      const up = () => {
        el.classList.remove("drag");
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", up);
        try { localStorage.setItem(storeKey, getComputedStyle(root).getPropertyValue(cssVar).trim()); } catch(e2){}
      };
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", up);
    });
    el.addEventListener("dblclick", () => {
      root.style.removeProperty(cssVar);
      try { localStorage.removeItem(storeKey); } catch(e2){}
    });
  }
  drag("split1", "left", "--w1", "mdhtml.w1", 220, 460);
  drag("split2", "right", "--w2", "mdhtml.w2", 230, 460);
}
function toggleCol(colId, splitId){
  const col = $(colId), split = $(splitId);
  col.classList.toggle("hide");
  split.classList.toggle("hide", col.classList.contains("hide"));
}

/* ---------- drag & drop (fallback text + native path qua __mdRefresh) ---------- */
function initDrop(){
  const dz = $("dropzone");
  ["dragenter","dragover"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("over"); }));
  ["dragleave","drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", async e => {
    const items = [...(e.dataTransfer.files || [])].filter(f => /\.md$/i.test(f.name));
    if(!items.length){ toast("Chỉ nhận file .md.", {kind:"err"}); return; }
    const reads = items.map(f => new Promise(res => {
      const r = new FileReader();
      r.onload = () => res({ name: f.name, text: String(r.result || "") });
      r.onerror = () => res(null);
      r.readAsText(f, "utf-8");
    }));
    const payload = (await Promise.all(reads)).filter(Boolean);
    if(!payload.length) return;
    try {
      const r = await call("add_dropped_files", payload);
      const n = (r && r.added) || 0;
      if(n) log(`Đã thêm ${n} file kéo-thả.`);
      await refresh({ selectLast: n > 0 });
    } catch(err){ toast("Lỗi nhận file: " + err.message, {kind:"err"}); }
  });
}

/* ---------- events ---------- */
function initEvents(){
  $("btnAdd").onclick = doAdd;
  $("btnFolder").onclick = doFolder;
  $("btnClear").onclick = doClear;
  $("btnExport").onclick = doExport;
  $("btnExportAll").onclick = doExportAll;
  $("btnReveal").onclick = doReveal;
  $("btnOpenFolder").onclick = doOpenOutput;
  $("btnOpen").onclick = doOpen;
  $("btnReload").onclick = () => showPreview(state.sel, true);
  $("btnZoomIn").onclick = () => setZoom(state.zoom + 0.1);
  $("btnZoomOut").onclick = () => setZoom(state.zoom - 0.1);
  $("btnZoomReset").onclick = () => setZoom(1);
  $("btnTheme").onclick = () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  $("btnHide1").onclick = () => toggleCol("colFiles", "split1");
  $("btnHide3").onclick = () => toggleCol("colOpts", "split2");
  $("logHead").onclick = () => {
    const col = $("colOpts");
    col.classList.toggle("log-collapsed");
    $("logToggle").textContent = col.classList.contains("log-collapsed") ? "mở" : "thu gọn";
  };
  ["optTitle","optEyebrow","optDate"].forEach(id => $(id).addEventListener("input", onSettingsChanged));
  ["optLang","optNoToc"].forEach(id => $(id).addEventListener("change", onSettingsChanged));
  ["cmBeside","cmTool"].forEach(id => $(id).addEventListener("change", async e => {
    if(!e.target.checked) return;
    try { await call("set_options", e.target.value, null); state.cacheMode = e.target.value; await refresh(); }
    catch(err){ toast("Lỗi đổi cache: " + err.message, {kind:"err"}); }
  }));
  $("optWatch").addEventListener("change", async e => {
    try { await call("set_options", null, e.target.checked); state.watch = e.target.checked; log("Tự cập nhật: " + (e.target.checked ? "bật" : "tắt")); }
    catch(err){ toast("Lỗi: " + err.message, {kind:"err"}); }
  });
  $("filter").addEventListener("input", e => { state.filter = e.target.value.trim().toLowerCase(); renderList(); });

  document.addEventListener("keydown", e => {
    const mod = e.ctrlKey || e.metaKey;
    const tag = (e.target && e.target.tagName) || "";
    const inField = tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA";
    const k = e.key.toLowerCase();
    if(mod && k === "o"){ e.preventDefault(); e.shiftKey ? doFolder() : doAdd(); return; }
    if(mod && k === "e"){ e.preventDefault(); e.shiftKey ? doExportAll() : doExport(); return; }
    if(mod && k === "k"){ e.preventDefault(); $("filter").focus(); $("filter").select(); return; }
    if(mod && (e.key === "=" || e.key === "+")){ e.preventDefault(); setZoom(state.zoom + 0.1); return; }
    if(mod && e.key === "-"){ e.preventDefault(); setZoom(state.zoom - 0.1); return; }
    if(mod && e.key === "0"){ e.preventDefault(); setZoom(1); return; }
    if(mod && e.key === "1"){ e.preventDefault(); toggleCol("colFiles", "split1"); return; }
    if(mod && e.key === "3"){ e.preventDefault(); toggleCol("colOpts", "split2"); return; }
    if(e.key === "F5"){ e.preventDefault(); showPreview(state.sel, true); return; }
    if(e.key === "Escape" && e.target === $("filter")){
      $("filter").value = ""; state.filter = ""; renderList(); $("filter").blur(); return;
    }
    if(!inField && (e.key === "ArrowDown" || e.key === "ArrowUp")){
      if(!state.files.length) return;
      e.preventDefault();
      const i = Math.max(0, Math.min(state.files.length - 1, state.sel + (e.key === "ArrowDown" ? 1 : -1)));
      select(i);
    }
  });
}

/* ---------- iframe scroll bridge ---------- */
function initFrame(){
  const frame = $("preview");
  frame.addEventListener("load", () => {
    const y = state.scrollY[state.shownIndex] || 0;
    if(!y) return;
    try { frame.contentWindow.postMessage({ t: "mdhtml:scroll", y: y }, "*"); } catch(e){}
  });
  window.addEventListener("message", e => {
    const d = e.data || {};
    if(d.t === "mdhtml:at" && state.shownIndex >= 0){
      state.scrollY[state.shownIndex] = Number(d.y) || 0;
    }
  });
}

/* ---------- boot ---------- */
window.addEventListener("pywebviewready", async () => {
  initColumns();
  initEvents();
  initDrop();
  initFrame();
  let saved = null;
  try { saved = localStorage.getItem("mdhtml.theme"); } catch(e){}
  applyTheme(saved || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  setZoom(1);
  await refresh({ preview: true });
  const st = await call("initial_state").catch(() => null);
  log("Tool MD to HTML v" + ((st && st.version) || "2.1.0") + " — cache tự động, không cần Convert.");
  setInterval(poll, 1200);
});
})();
