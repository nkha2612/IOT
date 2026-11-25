const API_BASE = "";            // rỗng khi mở qua backend; Live Server: "http://127.0.0.1:8000"
const POLL_MS = 3000;
const TZ = "Asia/Ho_Chi_Minh";
const UNITS = { temperature: "°C", humidity: "%RH", lux: "lux" };
const FLAG_LABEL = {
  read_error: "Lỗi đọc cảm biến",
  missing: "Thiếu giá trị",
  out_of_range: "Ngoài miền đo",
  spike: "Đột biến",
  stuck: "Nghi kẹt cảm biến",
};

const fmtTime = (iso) => new Date(iso).toLocaleTimeString("vi-VN", { timeZone: TZ });
const SOURCE_LABEL = { demo: "DEMO", sim: "GIẢ LẬP" };
const ALERT_UNIT = { temp_high: "°C", hum_high: "%RH", lux_low: "lux" };
let lastReceivedAt = null;

// Sự kiện cảnh báo đang mở trên máy chủ (CN05): luôn thấy ở đầu trang
function renderOpenAlerts(list) {
  const box = document.getElementById("open-alerts");
  const ul = box.querySelector("ul");
  ul.replaceChildren();
  for (const a of list || []) {
    const li = document.createElement("li");
    li.className = a.status === "unknown" ? "unknown" : "active";
    const unit = ALERT_UNIT[a.type] || "";
    const state = a.status === "unknown"
      ? "chưa xác định (cảm biến lỗi trong lúc cảnh báo)"
      : `đỉnh ${a.peak_value} ${unit}, ngưỡng ${a.threshold} ${unit}`;
    li.textContent = `${a.label} từ ${fmtTime(a.started_at)} – ${state}`;
    if (SOURCE_LABEL[a.source]) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = SOURCE_LABEL[a.source];
      li.prepend(tag);
    }
    ul.appendChild(li);
  }
  box.hidden = ul.children.length === 0;
}

function renderCard(param, value, flag, reason) {
  const card = document.querySelector(`.card[data-param="${param}"]`);
  // null = không có số đo: hiển thị "—", không bao giờ hiển thị 0
  card.querySelector(".value").textContent =
    value == null ? "—" : `${value.toFixed(1)} ${UNITS[param]}`;
  const bad = flag && flag !== "ok";
  card.querySelector(".flag").textContent = bad ? (FLAG_LABEL[flag] || flag) : "";
  card.title = bad && reason ? reason : "";
  card.classList.toggle("is-bad", bad);
}

function render(data) {
  const d = data.device, m = data.measurement;
  const status = document.getElementById("device-status");
  const seen = document.getElementById("device-seen");
  const dot = document.getElementById("device-dot");

  renderOpenAlerts(data.open_alerts);
  if (!d) {
    status.textContent = "Chưa có thiết bị nào gửi dữ liệu";
    return;
  }
  status.textContent = d.online ? "Thiết bị đang hoạt động" : "Thiết bị OFFLINE";
  dot.className = d.online ? "online" : "offline";
  seen.textContent = `Nhận lần cuối ${fmtTime(d.last_seen_at)} (thời điểm server nhận)`;
  document.getElementById("cards").classList.toggle("is-stale", !d.online);

  const badge = document.getElementById("source-badge");
  const label = m && SOURCE_LABEL[m.source];
  badge.hidden = !label;
  badge.textContent = label ? `Đang hiển thị số đo ${label} – không phải đo thật` : "";

  if (m) {
    for (const p of ["temperature", "humidity", "lux"]) {
      renderCard(p, m[p], m.flags[p], m.flag_reason);
    }
    if (m.received_at !== lastReceivedAt) {     // đo độ trễ hiển thị (Ngày 6)
      lastReceivedAt = m.received_at;
      console.log("Độ trễ hiển thị (ms):", Date.now() - Date.parse(m.received_at));
    }
  }
}

function setServerOk(ok) {
  document.getElementById("server-banner").hidden = ok;
}

async function poll() {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 2500);
  try {
    const res = await fetch(`${API_BASE}/api/latest`, { cache: "no-store", signal: ctrl.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    render(await res.json());
    setServerOk(true);
  } catch (err) {
    setServerOk(false);                      // giữ nguyên số cũ trên màn hình
  } finally {
    clearTimeout(timer);
    setTimeout(poll, POLL_MS);               // gọi lần sau khi lần này xong, không chồng lệnh
  }
}

poll();