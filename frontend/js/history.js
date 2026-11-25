// js/history.js – Biểu đồ lịch sử (CN03), dữ liệu bất thường (CN06), lịch sử cảnh báo (CN05),
// nút xuất CSV (CN07). Cả bốn dùng chung một khoảng thời gian và một lựa chọn nguồn dữ liệu.
// API: GET /api/history, GET /api/alerts, GET /api/export.csv (docs/api.md v1.2).
(() => {
  const BASE = typeof API_BASE === "string" ? API_BASE : "";
  const TZ = "Asia/Ho_Chi_Minh";
  const PARAMS = {
    temperature: { label: "Nhiệt độ", unit: "°C", color: "--temperature", digits: 1 },
    humidity: { label: "Độ ẩm", unit: "%RH", color: "--humidity", digits: 1 },
    lux: { label: "Độ rọi", unit: "lux", color: "--lux", digits: 0 },
  };
  const FLAG_TEXT = {
    read_error: "Lỗi đọc cảm biến",
    missing: "Thiếu giá trị",
    out_of_range: "Ngoài miền đo",
    spike: "Đột biến",
    stuck: "Nghi kẹt",
  };
  const NOT_PLOTTED = new Set(["read_error", "missing", "out_of_range"]); // vẽ thành chỗ ngắt
  const SOURCE_TAG = { demo: "DEMO", sim: "GIẢ LẬP" };
  const ALERT_UNIT = { temp_high: "°C", hum_high: "%RH", lux_low: "lux" };
  const END_TEXT = {
    recovered: "Đã hồi phục",
    light_disabled: "Tắt xét ánh sáng",
    source_changed: "Hết demo",
  };
  const AGGREGATE_ABOVE_MS = 3 * 3600e3; // khoảng dài hơn 3 giờ: gộp trung bình mỗi phút cho nhẹ
  const REFRESH_MS = 30000;

  const $ = (id) => document.getElementById(id);
  const form = $("range-form");
  const info = $("history-info");
  const charts = {};
  let timer = null;
  let busy = false;

  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const fmtTime = (iso) => new Date(iso).toLocaleTimeString("vi-VN", { timeZone: TZ });
  const DT_PARTS = new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  });
  const fmtDT = (iso) => { // "25/11 12:42:13"
    const v = Object.fromEntries(DT_PARTS.formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
    return `${v.day}/${v.month} ${v.hour}:${v.minute}:${v.second}`;
  };
  const fmtVal = (v, p) => (v == null ? "—" : `${Number(v).toFixed(PARAMS[p].digits)} ${PARAMS[p].unit}`);
  const fmtDuration = (s) => {
    s = Math.round(s);
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    if (h) return `${h} giờ ${m} phút`;
    if (m) return `${m} phút ${sec} giây`;
    return `${sec} giây`;
  };
  // "2026-11-26T08:00" cho ô datetime-local, theo giờ máy (người dùng ở Việt Nam)
  const toLocalInput = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

  function cell(text, cls) {
    const td = document.createElement("td");
    td.textContent = text;
    if (cls) td.className = cls;
    return td;
  }
  function tag(text) {
    const s = document.createElement("span");
    s.className = "tag";
    s.textContent = text;
    return s;
  }

  // ------------------------------------------------------------ tham số truy vấn
  function mode() {
    return form.querySelector('input[name="range"]:checked').value;
  }

  function query() {
    const q = new URLSearchParams();
    if (mode() === "custom") {
      const from = $("range-from").value, to = $("range-to").value;
      if (!from || !to) return null;
      q.set("from", from); // không có múi giờ: máy chủ hiểu là giờ Việt Nam
      q.set("to", to);
    } else {
      q.set("range", mode());
    }
    q.set("source", $("show-all").checked ? "all" : "real");
    return q;
  }

  async function getJSON(path) {
    const res = await fetch(BASE + path, { cache: "no-store" });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { msg = (await res.json()).detail || msg; } catch (e) { /* không phải JSON */ }
      throw new Error(msg);
    }
    return res.json();
  }

  // ------------------------------------------------------------ biểu đồ
  function buildSeries(items, p, gapMs) {
    const real = [], other = [], flagged = [];
    const last = { real: null, other: null };
    for (const it of items) {
      const t = Date.parse(it.received_at);
      const key = it.source === "real" ? "real" : "other";
      const arr = key === "real" ? real : other;
      if (last[key] !== null && t - last[key] > gapMs) arr.push({ x: last[key] + 1, y: null }); // ngắt đường
      last[key] = t;
      const v = it[p], f = it.flags[p];
      arr.push({ x: t, y: v == null || NOT_PLOTTED.has(f) ? null : v });
      if (v != null && (f === "spike" || f === "stuck")) {
        flagged.push({ x: t, y: v, flag: f });
      }
    }
    return { real, other, flagged };
  }

  // Gộp trung bình theo phút; phút không có số liệu hợp lệ thành chỗ ngắt
  function perMinute(points, gapMs) {
    const out = [];
    let bucket = null, sum = 0, n = 0, lastT = null;
    const flush = () => {
      if (bucket === null) return;
      out.push({ x: bucket + 30000, y: n ? sum / n : null });
    };
    for (const pt of points) {
      const b = Math.floor(pt.x / 60000) * 60000;
      if (b !== bucket) {
        flush();
        if (bucket !== null && b - bucket > Math.max(gapMs, 60000)) out.push({ x: bucket + 60001, y: null });
        bucket = b; sum = 0; n = 0;
      }
      if (pt.y !== null) { sum += pt.y; n += 1; }
      lastT = pt.x;
    }
    flush();
    return lastT === null ? [] : out;
  }

  function drawCharts(h) {
    const gapMs = h.gap_threshold_s * 1000;
    const span = Date.parse(h.to) - Date.parse(h.from);
    const aggregate = span > AGGREGATE_ABOVE_MS;
    const ink = css("--ink"), muted = css("--muted"), line = css("--line"), fault = css("--banner-bg");
    for (const [p, meta] of Object.entries(PARAMS)) {
      const s = buildSeries(h.items, p, gapMs);
      const real = aggregate ? perMinute(s.real, gapMs) : s.real;
      const other = aggregate ? perMinute(s.other, gapMs) : s.other;
      const color = css(meta.color);
      const datasets = [
        { label: "Đo thật", data: real, borderColor: color, backgroundColor: color },
        { label: "Demo / giả lập", data: other, borderColor: muted, backgroundColor: muted, borderDash: [5, 4] },
        {
          label: "Bất thường", data: s.flagged, showLine: false, pointRadius: 5, pointHoverRadius: 7,
          pointBorderWidth: 2, pointBackgroundColor: css("--surface"), pointBorderColor: fault,
          borderColor: fault, backgroundColor: css("--surface"),
        },
      ];
      for (const d of datasets.slice(0, 2)) Object.assign(d, { borderWidth: 1.6, pointRadius: 0, spanGaps: false, tension: 0 });

      const canvas = document.querySelector(`.chart[data-param="${p}"] canvas`);
      const options = {
        animation: false,
        parsing: false,
        normalized: true,
        maintainAspectRatio: false,
        interaction: { mode: "nearest", axis: "x", intersect: false },
        scales: {
          x: {
            type: "time",
            min: Date.parse(h.from),
            max: Date.parse(h.to),
            time: { tooltipFormat: "dd/MM HH:mm:ss", displayFormats: { minute: "HH:mm", hour: "HH:mm", day: "dd/MM" } },
            ticks: { color: muted, maxRotation: 0, autoSkipPadding: 16 },
            grid: { color: line },
          },
          y: { ticks: { color: muted }, grid: { color: line }, title: { display: true, text: meta.unit, color: muted } },
        },
        plugins: {
          legend: {
            labels: { color: ink, boxWidth: 14, filter: (item, data) => data.datasets[item.datasetIndex].data.length > 0 },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const d = ctx.raw;
                const base = `${ctx.dataset.label}: ${fmtVal(d.y, p)}`;
                return d.flag ? `${base} – ${FLAG_TEXT[d.flag]}` : aggregate && ctx.datasetIndex < 2 ? `${base} (trung bình phút)` : base;
              },
            },
          },
        },
      };
      if (charts[p]) {
        charts[p].data.datasets = datasets;
        charts[p].options = options;
        charts[p].update("none");
      } else {
        charts[p] = new Chart(canvas, { type: "line", data: { datasets }, options });
      }
    }
    return aggregate;
  }

  // ------------------------------------------------------------ dữ liệu bất thường
  function reasonFor(it, p) {
    const parts = (it.flag_reason || "").split("; ");
    return parts.find((s) => s.startsWith(PARAMS[p].label)) || FLAG_TEXT[it.flags[p]] || "";
  }

  function renderAnomalies(h) {
    const gapMs = h.gap_threshold_s * 1000;
    const runs = [], open = {};
    const counts = {};
    for (const it of h.items) {
      const t = Date.parse(it.received_at);
      for (const p of Object.keys(PARAMS)) {
        const f = it.flags[p];
        const run = open[p];
        if (f !== "ok") counts[f] = (counts[f] || 0) + 1;
        if (run && f === run.flag && it.source === run.source && t - run.lastT <= gapMs) {
          run.end = it; run.n += 1; run.lastT = t;
          if (it[p] != null) run.values.push(it[p]);
          continue;
        }
        if (run) { runs.push(run); open[p] = null; }
        if (f !== "ok") {
          open[p] = { p, flag: f, source: it.source, start: it, end: it, n: 1, lastT: t, values: it[p] != null ? [it[p]] : [] };
        }
      }
    }
    runs.push(...Object.values(open).filter(Boolean));
    runs.sort((a, b) => Date.parse(b.start.received_at) - Date.parse(a.start.received_at));

    const chips = $("anomaly-summary");
    chips.replaceChildren();
    for (const [f, text] of Object.entries(FLAG_TEXT)) {
      if (!counts[f]) continue;
      const c = document.createElement("span");
      c.className = `chip flag-${f}`;
      c.textContent = `${text}: ${counts[f]} mẫu`;
      chips.appendChild(c);
    }

    const body = $("anomaly-rows");
    body.replaceChildren();
    if (!runs.length) {
      const tr = document.createElement("tr");
      tr.appendChild(cell("Không có dữ liệu bất thường trong khoảng này.", "empty")).colSpan = 5;
      body.appendChild(tr);
      return 0;
    }
    for (const r of runs.slice(0, 300)) {
      const tr = document.createElement("tr");
      const when = r.n === 1 ? fmtDT(r.start.received_at)
        : `${fmtDT(r.start.received_at)} → ${fmtTime(r.end.received_at)} (${r.n} mẫu)`;
      const whenCell = cell(when);
      if (SOURCE_TAG[r.source]) whenCell.prepend(tag(SOURCE_TAG[r.source]), " ");
      tr.appendChild(whenCell);
      tr.appendChild(cell(PARAMS[r.p].label));
      const lo = Math.min(...r.values), hi = Math.max(...r.values);
      tr.appendChild(cell(!r.values.length ? "—" : lo === hi ? fmtVal(lo, r.p)
        : `${fmtVal(lo, r.p)} – ${fmtVal(hi, r.p)}`, "num"));
      tr.appendChild(cell(FLAG_TEXT[r.flag] || r.flag, `flag flag-${r.flag}`));
      tr.appendChild(cell(reasonFor(r.start, r.p)));
      body.appendChild(tr);
    }
    return runs.length;
  }

  // ------------------------------------------------------------ lịch sử cảnh báo
  function renderAlerts(a) {
    const body = $("alert-rows");
    body.replaceChildren();
    if (!a.items.length) {
      const tr = document.createElement("tr");
      tr.appendChild(cell("Không có sự kiện cảnh báo trong khoảng này.", "empty")).colSpan = 7;
      body.appendChild(tr);
      return;
    }
    for (const e of a.items) {
      const unit = ALERT_UNIT[e.type] || "";
      const tr = document.createElement("tr");
      tr.className = `alert-${e.status}`;
      const kind = cell(e.label);
      if (SOURCE_TAG[e.source]) kind.prepend(tag(SOURCE_TAG[e.source]), " ");
      tr.appendChild(kind);
      tr.appendChild(cell(fmtDT(e.started_at)));
      tr.appendChild(cell(e.ended_at ? fmtDT(e.ended_at) : "đang diễn ra"));
      tr.appendChild(cell(fmtDuration(e.duration_s), "num"));
      tr.appendChild(cell(`${e.start_value} / ${e.peak_value} ${unit}`, "num"));
      tr.appendChild(cell(`${e.type === "lux_low" ? "<" : ">"} ${e.threshold} ${unit}`, "num"));
      const status = e.status === "open" ? "Đang cảnh báo"
        : e.status === "unknown" ? "Chưa xác định" : END_TEXT[e.end_reason] || "Đã kết thúc";
      tr.appendChild(cell(status, `status status-${e.status}`));
      body.appendChild(tr);
    }
  }

  // ------------------------------------------------------------ tải và làm mới
  async function load() {
    clearTimeout(timer);
    const q = query();
    if (!q) {
      info.textContent = "Chọn thời điểm bắt đầu và kết thúc rồi bấm Xem.";
      return;
    }
    $("export-csv").href = `${BASE}/api/export.csv?${q}`;
    if (busy) return;
    busy = true;
    try {
      const [h, a] = await Promise.all([getJSON(`/api/history?${q}`), getJSON(`/api/alerts?${q}`)]);
      const aggregate = drawCharts(h);
      const nRuns = renderAnomalies(h);
      renderAlerts(a);
      const gaps = h.items.reduce((n, it, i) => n + (i && Date.parse(it.received_at) - Date.parse(h.items[i - 1].received_at) > h.gap_threshold_s * 1000 ? 1 : 0), 0);
      const parts = [
        `${h.count} mẫu ${h.source === "all" ? "(gồm cả demo/giả lập)" : "đo thật"} từ ${fmtDT(h.from)} đến ${fmtDT(h.to)}`,
        `${gaps} khoảng mất dữ liệu`,
        `${nRuns} nhóm bất thường`,
        `${a.count} sự kiện cảnh báo`,
      ];
      if (aggregate) parts.push("biểu đồ gộp trung bình mỗi phút");
      if (h.truncated) parts.push("QUÁ NHIỀU ĐIỂM – chỉ hiện 50.000 mẫu đầu, hãy chọn khoảng ngắn hơn");
      if (!h.count) parts.splice(0, 1, `Không có mẫu ${h.source === "all" ? "nào" : "đo thật nào"} trong khoảng này`);
      info.textContent = `${parts.join(" · ")} · cập nhật ${fmtTime(new Date().toISOString())}`;
    } catch (err) {
      info.textContent = `Không tải được dữ liệu: ${err.message}`;
    } finally {
      busy = false;
      if (mode() !== "custom") timer = setTimeout(load, REFRESH_MS);
    }
  }

  form.addEventListener("change", (ev) => {
    if (ev.target.name === "range") {
      const custom = mode() === "custom";
      $("custom-range").hidden = !custom;
      if (custom && !$("range-from").value) {
        const now = new Date();
        $("range-to").value = toLocalInput(now);
        $("range-from").value = toLocalInput(new Date(now.getTime() - 6 * 3600e3));
      }
      if (custom) return; // chờ bấm Xem
    }
    if (ev.target.id === "range-from" || ev.target.id === "range-to") return;
    load();
  });
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    load();
  });

  // Nút "Xem lại" từ chỗ khác (ví dụ lưu ngưỡng xong) có thể gọi hàm này
  window.reloadHistory = load;
  load();
})();
