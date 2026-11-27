"""Tách dữ liệu demo/giả lập, nâng cấp database cũ, đột biến (MAD), nghi kẹt, xuất CSV."""

import csv
import io
import sqlite3

from conftest import make_payload

from app import db


def post(client, clock, seq, step=5, **kw):
    r = client.post("/api/measurements", json=make_payload(seq=seq, **kw))
    assert r.status_code == 200, r.text
    clock.advance(step)
    return r.json()


def latest(client):
    return client.get("/api/latest").json()["measurement"]


def baseline(client, clock, n=30, start_seq=1):
    """n mẫu thật ổn định có nhiễu nhỏ: 27.0/27.1/27.2 °C, 64.5–65.5 %RH, 400–420 lux."""
    for i in range(n):
        post(client, clock, start_seq + i, temperature=27.0 + 0.1 * (i % 3),
             humidity=65.0 + 0.5 * ((i % 3) - 1), lux=410.0 + 10 * ((i % 3) - 1))
    return start_seq + n


# ------------------------------------------------------------------ nguồn dữ liệu
def test_source_is_resolved_and_filtered(client, clock):
    post(client, clock, 1)
    post(client, clock, 2, demo={"scenario": "temp_high", "sample": 1, "total": 7})
    post(client, clock, 3, source="sim", lux=120)
    assert latest(client)["source"] == "sim"  # thẻ trên website vẫn thấy mẫu mới nhất
    h = lambda s=None: client.get("/api/history", params={"source": s} if s else {}).json()
    assert [i["source"] for i in h()["items"]] == ["real"]  # mặc định: chỉ dữ liệu thật
    assert [i["source"] for i in h("all")["items"]] == ["real", "demo", "sim"]
    assert h("demo")["count"] == 1
    assert client.get("/api/history", params={"source": "fake"}).status_code == 400


def test_old_database_is_upgraded_without_losing_data(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)  # lược đồ bản v1 (26/10), chưa có cột source
    con.executescript("""
        CREATE TABLE measurements (id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT NOT NULL,
          boot_id TEXT NOT NULL, seq INTEGER NOT NULL, uptime_ms INTEGER NOT NULL,
          received_at TEXT NOT NULL, temperature REAL, humidity REAL, lux REAL,
          dht22_status TEXT NOT NULL, bh1750_status TEXT NOT NULL, temp_flag TEXT NOT NULL,
          hum_flag TEXT NOT NULL, lux_flag TEXT NOT NULL, flag_reason TEXT,
          UNIQUE (device_id, boot_id, seq));
        CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT NOT NULL,
          type TEXT NOT NULL, threshold REAL NOT NULL, start_value REAL, peak_value REAL,
          started_at TEXT NOT NULL, ended_at TEXT, status TEXT NOT NULL);
        INSERT INTO measurements VALUES (1,'esp32-phong01','b1',1,5,'2026-11-20T01:00:00.000Z',
          28.1,60.2,350,'ok','ok','ok','ok','ok',NULL);
    """)
    con.commit()
    con.close()
    db.init_db(path)
    con = sqlite3.connect(path)
    assert con.execute("SELECT source, temperature FROM measurements").fetchone() == ("real", 28.1)
    cols = {r[1] for r in con.execute("PRAGMA table_info(alerts)")}
    assert {"source", "end_reason", "end_value", "updated_at"} <= cols
    db.init_db(path)  # chạy lại lần nữa không lỗi


# ---------------------------------------------------------------------- đột biến
def test_isolated_spike_is_flagged_with_reason(client, clock):
    seq = baseline(client, clock)
    post(client, clock, seq, temperature=35.0)
    m = latest(client)
    assert m["flags"]["temperature"] == "spike"
    assert m["flags"]["humidity"] == "ok"
    assert "đột biến 35" in m["flag_reason"] and "trung vị 27.1" in m["flag_reason"]
    post(client, clock, seq + 1, temperature=27.1)
    assert latest(client)["flags"]["temperature"] == "ok"
    items = client.get("/api/history").json()["items"]
    assert [i["flags"]["temperature"] for i in items].count("spike") == 1  # cờ cũ vẫn giữ


def test_not_enough_history_no_spike_check(client, clock):
    seq = baseline(client, clock, n=10)
    post(client, clock, seq, temperature=35.0)
    assert latest(client)["flags"]["temperature"] == "ok"


def test_level_shift_is_not_a_spike(client, clock):
    """Bật đèn: lux nhảy từ ~410 lên ~800 và giữ nguyên – thay đổi thật, không phải đột biến."""
    seq = baseline(client, clock)
    for i in range(5):
        post(client, clock, seq + i, lux=800.0 + i)
    items = client.get("/api/history").json()["items"][-5:]
    assert [i["flags"]["lux"] for i in items] == ["ok"] * 5
    assert all(i["flag_reason"] is None for i in items)


def test_two_sample_spike_kept(client, clock):
    seq = baseline(client, clock)
    post(client, clock, seq, humidity=90.0)
    post(client, clock, seq + 1, humidity=90.0)
    post(client, clock, seq + 2, humidity=65.0)
    flags = [i["flags"]["humidity"] for i in client.get("/api/history").json()["items"][-3:]]
    assert flags == ["spike", "spike", "ok"]


def test_demo_values_never_become_baseline_or_spike(client, clock):
    seq = baseline(client, clock)
    for i in range(30):
        post(client, clock, 500 + i, temperature=32.5,
             demo={"scenario": "temp_high", "sample": i, "total": 30})
    assert latest(client)["flags"]["temperature"] == "ok"  # demo không bị so với dữ liệu thật
    post(client, clock, seq, temperature=27.1)  # mẫu thật kế tiếp so với mốc thật, không phải 32.5
    assert latest(client)["flags"]["temperature"] == "ok"


def test_spike_still_counts_for_alerts_like_firmware(client, clock):
    seq = baseline(client, clock)
    for i in range(3):
        post(client, clock, seq + i, temperature=35.0)
    a = client.get("/api/alerts").json()["items"]
    assert len(a) == 1 and a[0]["start_value"] == 35.0


# ---------------------------------------------------------------------- nghi kẹt
def test_dht22_stuck_after_20_minutes(client, clock):
    seq = 1
    for i in range(20 * 12):  # 240 mẫu × 5 s = 20 phút, nhiệt/ẩm giữ nguyên
        post(client, clock, seq + i, temperature=27.3, humidity=64.0, lux=400.0 + (i % 5))
    m = latest(client)
    assert m["flags"]["temperature"] == "ok"  # mẫu cuối mới bắt đầu sau 19 phút 55 giây
    post(client, clock, 1000, temperature=27.3, humidity=64.0, lux=401.0)
    m = latest(client)
    assert m["flags"] == {"temperature": "stuck", "humidity": "stuck", "lux": "ok"}
    assert "nghi kẹt – DHT22 lặp nguyên 27.3 °C / 64 %RH suốt 20 phút" in m["flag_reason"]


def test_dark_room_is_not_stuck(client, clock):
    for i in range(20 * 12 + 2):
        post(client, clock, i + 1, temperature=27.0 + 0.1 * (i % 2), humidity=65 + (i % 2), lux=0.0)
    assert latest(client)["flags"]["lux"] == "ok"


def test_stuck_run_broken_by_change(client, clock):
    for i in range(200):
        post(client, clock, i + 1, temperature=27.3, humidity=64.0)
    post(client, clock, 300, temperature=27.4, humidity=64.0)
    for i in range(50):
        post(client, clock, 400 + i, temperature=27.3, humidity=64.0)
    assert latest(client)["flags"]["temperature"] == "ok"  # chuỗi mới chỉ ~4 phút


# ---------------------------------------------------------------------- CSV
def test_export_csv(client, clock):
    post(client, clock, 1)
    post(client, clock, 2, humidity=None, temperature=None,
         sensor_status={"dht22": "read_error", "bh1750": "ok"})
    post(client, clock, 3, demo={"scenario": "temp_high", "sample": 1, "total": 7})
    r = client.get("/api/export.csv", params={"range": "1h"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    text = r.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert [x["seq"] for x in rows] == ["1", "2"]  # mặc định chỉ dữ liệu thật
    assert rows[0]["received_at_vn"] == "2026-10-26 10:00:00"
    assert rows[1]["temperature"] == "" and rows[1]["temp_flag"] == "read_error"
    assert "lỗi đọc" in rows[1]["flag_reason"]
    all_rows = list(csv.DictReader(io.StringIO(
        client.get("/api/export.csv", params={"source": "all"}).content.decode("utf-8-sig"))))
    assert [x["source"] for x in all_rows] == ["real", "real", "demo"]


def test_slow_drift_is_not_a_spike(client, clock):
    """Dữ liệu thật 26/11 06:05: nhiệt độ hạ dần 30,0 -> 29,9 (0,1 mỗi mẫu) lệch 0,6 so với
    trung vị 5 phút trước và từng bị gắn nhầm "đột biến"."""
    seq = baseline(client, clock)
    t = 27.1
    for i in range(30):  # tăng dần 0,1 °C mỗi mẫu tới 30 °C
        t = round(t + 0.1, 1)
        post(client, clock, seq + i, temperature=t)
    flags = [i["flags"]["temperature"] for i in client.get("/api/history").json()["items"]]
    assert "spike" not in flags
    post(client, clock, seq + 100, temperature=36.0)  # nhảy thật vẫn bị bắt
    assert latest(client)["flags"]["temperature"] == "spike"


def test_step_at_threshold_edge_is_cleared_when_level_stays(client, clock):
    """Dữ liệu thật 26/11 01:53: mẫu đầu của bước nhảy lệch sát ngưỡng bị gắn cờ, các mẫu sau
    (cùng mức mới) không còn vượt ngưỡng nên trước đây cờ ở lại mãi."""
    seq = baseline(client, clock)
    for i, t in enumerate([28.0, 27.9, 27.9]):  # trung vị 27,9–28,0; MAD nhỏ -> ngưỡng δ = 0,5
        post(client, clock, seq + i, temperature=t)
    post(client, clock, seq + 10, temperature=28.6)  # lệch sát ngưỡng
    for i in range(4):
        post(client, clock, seq + 11 + i, temperature=28.5)  # ở lại mức mới
    flags = [i["flags"]["temperature"] for i in client.get("/api/history").json()["items"]]
    assert "spike" not in flags


def test_no_spike_right_after_connection_gap(client, clock):
    """Dữ liệu thật 26/11 07:09: sau 7,8 phút mất Wi-Fi, độ ẩm khác hẳn trước lúc mất – thay đổi
    thật trong lúc không có số liệu, không phải đột biến."""
    seq = baseline(client, clock)
    clock.advance(7.8 * 60)
    for i, h in enumerate([58.5, 56.8, 54.6, 53.8, 53.0]):
        post(client, clock, seq + i, humidity=h)
    flags = [i["flags"]["humidity"] for i in client.get("/api/history").json()["items"]]
    assert "spike" not in flags


def test_spike_during_slow_drift_is_kept(client, clock):
    """Đột biến chen giữa lúc nhiệt độ đang trôi (trung vị đã lệch khỏi mức hiện tại) vẫn phải
    giữ cờ khi các mẫu sau quay về đúng mức ngay trước nó."""
    seq = baseline(client, clock)
    t = 27.1
    for i in range(20):
        t = round(t - 0.05, 2)
        post(client, clock, seq + i, temperature=t)
    post(client, clock, seq + 30, temperature=21.0)
    for i in range(4):
        post(client, clock, seq + 31 + i, temperature=t)
    flags = [i["flags"]["temperature"] for i in client.get("/api/history").json()["items"]]
    assert flags.count("spike") == 1
