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
let lastReceivedAt = null;

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

  if (!d) {
    status.textContent = "Chưa có thiết bị nào gửi dữ liệu";
    return;
  }
  status.textContent = d.online ? "Thiết bị đang hoạt động" : "Thiết bị OFFLINE";
  dot.className = d.online ? "online" : "offline";
  seen.textContent = `Nhận lần cuối ${fmtTime(d.last_seen_at)} (thời điểm server nhận)`;
  document.getElementById("cards").classList.toggle("is-stale", !d.online);

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