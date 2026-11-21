// js/demo.js – Mục "Kiểm tra tình huống" để trình bày (API v1.1: POST/GET /api/demo).
// Bấm nút -> backend giữ lệnh -> ESP32 nhận trong phản hồi POST kế tiếp (≤ 5 s) và tự phát số đo
// của tình huống qua đúng đường thật: cảnh báo tại thiết bị, LED, còi, backend, các thẻ phía trên.
// Về đo thật: nút "Về đo thật" hoặc nút EN trên ESP32.
(() => {
  const DEMO_API = (typeof API_BASE === "string" ? API_BASE : "") + "/api/demo";
  const POLL_MS = 2000;

  // Khớp bảng kịch bản trong firmware/tv1_firmware/demo.cpp (số mẫu mỗi bước, 5 s một mẫu).
  const SCENARIOS = {
    temp_high: {
      title: "Nhiệt độ cao",
      steps: [
        [4, "32,5 °C > ngưỡng 30 °C: đếm đủ 3 mẫu liên tiếp thì cảnh báo, LED đỏ sáng liền, còi kêu"],
        [3, "27,5 °C < 29 °C: đủ 3 mẫu thì hồi phục, LED đỏ tắt, còi im"],
      ],
    },
    hum_high: {
      title: "Độ ẩm cao",
      steps: [
        [4, "82 % > ngưỡng 75 %: 3 mẫu thì cảnh báo"],
        [3, "65 % < 72 %: 3 mẫu thì hồi phục"],
      ],
    },
    light_low: {
      title: "Thiếu sáng",
      steps: [
        [1, "Tạm bật “phòng đang sử dụng”; 620 lux: bình thường"],
        [4, "90 lux < ngưỡng 300 lux: 3 mẫu thì cảnh báo thiếu sáng"],
        [3, "620 lux > 350 lux: 3 mẫu thì hồi phục"],
      ],
    },
    dht_error: {
      title: "Lỗi cảm biến DHT22",
      steps: [[3, "Nhiệt độ, độ ẩm gửi null (không phải 0): thẻ hiện “—” và “Lỗi đọc cảm biến”, LED đỏ nháy, còi im"]],
    },
    error_during_alert: {
      title: "Lỗi khi đang cảnh báo",
      steps: [
        [3, "32,5 °C: 3 mẫu thì cảnh báo nhiệt độ"],
        [2, "DHT22 lỗi khi đang cảnh báo: “chưa xác định”, còi tắt, không tự coi là đã hồi phục"],
        [1, "Đọc lại được 32,5 °C: quay lại cảnh báo (vẫn là sự kiện cũ)"],
        [3, "27,5 °C: 3 mẫu thì hồi phục"],
      ],
    },
    bh1750_lost: {
      title: "Mất cảm biến ánh sáng",
      steps: [[3, "BH1750 không phát hiện: thẻ Ánh sáng “—”, nhiệt độ và độ ẩm vẫn có số"]],
    },
    out_of_range: {
      title: "Ngoài miền đo",
      steps: [[3, "85 °C ngoài miền đo DHT22 (−40…80 °C): vẫn lưu số gốc, gắn cờ “Ngoài miền đo”, không dùng để cảnh báo"]],
    },
    offline: {
      title: "Mất kết nối",
      steps: [[8, "ESP32 ngừng gửi 40 s: sau 30 s thẻ trạng thái chuyển OFFLINE, vẫn giữ số cũ; hết 40 s tự gửi lại"]],
    },
  };
  const totalOf = (key) => SCENARIOS[key].steps.reduce((n, [k]) => n + k, 0);

  const ALERT_TEXT = {
    normal: ["Bình thường", "ok"],
    active: ["ĐANG CẢNH BÁO", "active"],
    unknown: ["Chưa xác định", "unknown"],
    off: ["Không xét", "off"],
  };

  const $ = (id) => document.getElementById(id);
  const buttons = $("demo-buttons");
  const statusEl = $("demo-status");
  const stepEl = $("demo-step");
  const bar = $("demo-progress");
  const stopBtn = $("demo-stop");
  let clicked = null;      // { id, scenario, at } lần bấm gần nhất trên trang này
  let sawRunning = false;  // đã thấy ESP32 chạy kịch bản vừa bấm

  for (const [key, s] of Object.entries(SCENARIOS)) {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.scenario = key;
    b.innerHTML = `<strong>${s.title}</strong><small>~${totalOf(key) * 5} s</small>`;
    b.addEventListener("click", () => send(key));
    buttons.appendChild(b);
  }
  stopBtn.addEventListener("click", () => send("stop"));

  async function send(scenario) {
    try {
      const res = await fetch(DEMO_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const st = await res.json();
      clicked = { id: st.request.id, scenario, at: Date.now() };
      sawRunning = false;
      render(st);
    } catch (err) {
      statusEl.textContent = `Không gửi được lệnh tới máy chủ (${err.message})`;
    }
  }

  function stepText(key, sample) {
    let n = 0;
    for (const [k, text] of SCENARIOS[key].steps) {
      n += k;
      if (sample <= n) return text;
    }
    return "";
  }

  function renderAlerts(al) {
    for (const p of ["temperature", "humidity", "light"]) {
      const chip = document.querySelector(`#demo-alerts [data-param="${p}"] .state`);
      const [text, cls] = al ? ALERT_TEXT[al[p]] || [al[p], ""] : ["—", ""];
      chip.textContent = text;
      chip.className = `state ${cls}`;
    }
  }

  function render(st) {
    const dev = st.device;
    renderAlerts(dev && dev.seconds_since < 30 ? dev.alert_state : null);

    const running = dev && dev.demo && dev.seconds_since < 15 ? dev.demo : null;
    const sinceClick = clicked ? (Date.now() - clicked.at) / 1000 : Infinity;
    document.querySelectorAll("#demo-buttons button").forEach((b) => {
      b.classList.toggle("is-running", !!running && b.dataset.scenario === running.scenario);
    });

    if (running && SCENARIOS[running.scenario]) {
      if (clicked && running.scenario === clicked.scenario) sawRunning = true;
      const s = SCENARIOS[running.scenario];
      statusEl.textContent = `Đang chạy: ${s.title} – mẫu ${running.sample}/${running.total}`;
      stepEl.textContent = stepText(running.scenario, running.sample);
      bar.hidden = false;
      bar.max = running.total;
      bar.value = running.sample;
      stopBtn.disabled = false;
      return;
    }

    bar.hidden = true;
    stopBtn.disabled = !clicked || clicked.scenario === "stop" || sinceClick > 60;
    if (clicked && clicked.scenario === "offline" && sinceClick < 50) {
      statusEl.textContent = `Đang chạy: Mất kết nối – ESP32 ngừng gửi (${Math.round(sinceClick)} s / 40 s)`;
      stepEl.textContent = SCENARIOS.offline.steps[0][1];
    } else if (clicked && clicked.scenario !== "stop" && !sawRunning && sinceClick < 20) {
      statusEl.textContent = `Đã gửi lệnh “${SCENARIOS[clicked.scenario].title}”, chờ ESP32 nhận (tối đa khoảng 5 s)…`;
      stepEl.textContent = "";
    } else if (clicked && clicked.scenario !== "stop" && !sawRunning && sinceClick < 120) {
      statusEl.textContent = "ESP32 chưa nhận lệnh: kiểm tra thiết bị có đang gửi dữ liệu (thẻ trạng thái phía trên).";
      stepEl.textContent = "";
    } else if (clicked && sinceClick < 120) {
      statusEl.textContent = "Xong – thiết bị đã về đo thật.";
      stepEl.textContent = "";
    } else {
      statusEl.textContent = "Đang đo thật. Bấm một tình huống để trình bày.";
      stepEl.textContent = "";
    }
  }

  async function poll() {
    try {
      const res = await fetch(DEMO_API, { cache: "no-store" });
      if (res.ok) render(await res.json());
    } catch (err) {
      /* app.js đã hiện băng "mất kết nối máy chủ" */
    } finally {
      setTimeout(poll, POLL_MS);
    }
  }
  poll();
})();
