// js/settings.js – Cấu hình ngưỡng (CN04): GET/PUT /api/settings (docs/api.md v1.2).
// Kiểm tra trước khi gửi giống validateAlertConfig của firmware; máy chủ kiểm tra lại lần nữa.
(() => {
  const BASE = typeof API_BASE === "string" ? API_BASE : "";
  const TZ = "Asia/Ho_Chi_Minh";
  const NUMBERS = ["temp_high", "temp_recover", "hum_high", "hum_recover", "lux_low", "lux_recover"];
  const RANGES = {
    temp_high: [-40, 80], temp_recover: [-40, 80],
    hum_high: [0, 100], hum_recover: [0, 100],
    lux_low: [0, 65535], lux_recover: [0, 65535],
  };
  const NAMES = {
    temp_high: "Ngưỡng cảnh báo nhiệt độ", temp_recover: "Ngưỡng hồi phục nhiệt độ",
    hum_high: "Ngưỡng cảnh báo độ ẩm", hum_recover: "Ngưỡng hồi phục độ ẩm",
    lux_low: "Ngưỡng thiếu sáng", lux_recover: "Ngưỡng hồi phục ánh sáng",
  };

  const $ = (id) => document.getElementById(id);
  const form = $("settings-form");
  const statusEl = $("settings-status");
  const errorsEl = $("settings-errors");
  let saved = null;
  let watchTimer = null;

  const fmtDT = (iso) => new Date(iso).toLocaleString("en-GB", {
    timeZone: TZ, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).replace(",", "");

  function fill(s) {
    for (const k of NUMBERS) form.elements[k].value = s[k];
    form.elements.light_alert_enabled.checked = !!s.light_alert_enabled;
  }

  function read() {
    const b = {};
    for (const k of NUMBERS) b[k] = form.elements[k].value === "" ? NaN : Number(form.elements[k].value);
    b.light_alert_enabled = form.elements.light_alert_enabled.checked;
    return b;
  }

  function validate(b) {
    const out = [];
    for (const k of NUMBERS) {
      const [lo, hi] = RANGES[k];
      if (!Number.isFinite(b[k])) out.push(`${NAMES[k]}: chưa nhập số`);
      else if (b[k] < lo || b[k] > hi) out.push(`${NAMES[k]} phải trong khoảng ${lo}…${hi}`);
    }
    if (out.length) return out;
    if (b.temp_recover >= b.temp_high) out.push("Ngưỡng hồi phục nhiệt độ phải nhỏ hơn ngưỡng cảnh báo");
    if (b.hum_recover >= b.hum_high) out.push("Ngưỡng hồi phục độ ẩm phải nhỏ hơn ngưỡng cảnh báo");
    if (b.lux_recover <= b.lux_low) out.push("Ngưỡng hồi phục ánh sáng phải lớn hơn ngưỡng thiếu sáng");
    return out;
  }

  function showErrors(list) {
    errorsEl.replaceChildren(...list.map((t) => Object.assign(document.createElement("li"), { textContent: t })));
    errorsEl.hidden = list.length === 0;
  }

  function showStatus(s, note) {
    const head = note ? `${note} ` : "";
    let device;
    if (s.applied_version == null) device = "Chưa có thiết bị nào xác nhận cấu hình.";
    else if (s.applied_version === s.version) device = "Thiết bị đã nhận và đang dùng bản này.";
    else device = `Thiết bị đang dùng phiên bản ${s.applied_version}; sẽ nhận bản mới ở lần gửi kế tiếp (khoảng 5 giây nếu đang online).`;
    statusEl.textContent = `${head}Phiên bản ${s.version}, lưu lúc ${fmtDT(s.updated_at)}. ${device}`;
    statusEl.className = s.applied_version === s.version ? "ok" : "";
  }

  // Sau khi lưu: theo dõi tới khi ESP32 xác nhận phiên bản mới (tối đa 1 phút)
  function watchApplied(version, started = Date.now()) {
    clearTimeout(watchTimer);
    watchTimer = setTimeout(async () => {
      try {
        const res = await fetch(`${BASE}/api/settings`, { cache: "no-store" });
        const s = await res.json();
        showStatus(s, "Đã lưu.");
        if (s.applied_version !== version && Date.now() - started < 60000) watchApplied(version, started);
      } catch (e) { /* app.js đã báo mất kết nối */ }
    }, 3000);
  }

  async function load() {
    try {
      const res = await fetch(`${BASE}/api/settings`, { cache: "no-store" });
      saved = await res.json();
      fill(saved);
      showStatus(saved);
    } catch (e) {
      statusEl.textContent = "Không tải được cấu hình từ máy chủ.";
    }
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = read();
    const problems = validate(body);
    showErrors(problems);
    if (problems.length) return;
    statusEl.textContent = "Đang lưu…";
    try {
      const res = await fetch(`${BASE}/api/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        const d = data.detail;
        showErrors(Array.isArray(d) ? d.map((x) => (typeof x === "string" ? x : `${(x.loc || []).slice(-1)[0]}: ${x.msg}`)) : [String(d)]);
        statusEl.textContent = "Chưa lưu.";
        return;
      }
      saved = data;
      fill(saved);
      showStatus(saved, data.changed ? "Đã lưu." : "Không có gì thay đổi.");
      if (data.changed) watchApplied(data.version);
    } catch (e) {
      statusEl.textContent = `Không lưu được: ${e.message}`;
    }
  });

  $("settings-reset").addEventListener("click", () => {
    if (saved) fill(saved);
    showErrors([]);
  });

  load();
})();
