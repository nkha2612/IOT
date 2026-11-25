"""tools/tinh_lai.py và tools/danh_gia.py dựa trên app.replay: chạy lại phải cho đúng kết quả cũ."""

import sqlite3

from conftest import make_payload

from app.replay import read_rows, read_settings, replay


def test_replay_reproduces_flags_and_alerts(client, clock, tmp_path):
    seq = 0
    for i in range(40):  # mốc ổn định, một đột biến, một cảnh báo nhiệt độ, một đoạn demo
        seq += 1
        t = 27.0 + 0.1 * (i % 3)
        if i == 30:
            t = 35.0
        client.post("/api/measurements", json=make_payload(seq=seq, temperature=t))
        clock.advance(5)
    client.put("/api/settings", json={"temp_high": 28, "temp_recover": 27.5, "hum_high": 75,
                                      "hum_recover": 72, "lux_low": 300, "lux_recover": 350,
                                      "light_alert_enabled": False})
    for i in range(5):
        seq += 1
        client.post("/api/measurements", json=make_payload(seq=seq, temperature=29.0))
        clock.advance(5)
    for i in range(4):
        seq += 1
        client.post("/api/measurements", json=make_payload(
            seq=seq, temperature=32.5, demo={"scenario": "temp_high", "sample": i, "total": 4}))
        clock.advance(5)

    src = client.app.state.db_path
    dst = tmp_path / "lai.db"
    replay(read_rows(src), dst, read_settings(src))

    q = ("SELECT seq, source, temp_flag, hum_flag, lux_flag, flag_reason FROM measurements "
         "ORDER BY received_at")
    qa = "SELECT type, source, status, threshold, start_value, started_at FROM alerts ORDER BY id"
    a, b = sqlite3.connect(src), sqlite3.connect(dst)
    assert a.execute(q).fetchall() == b.execute(q).fetchall()
    assert a.execute(qa).fetchall() == b.execute(qa).fetchall()
    assert [r[0] for r in b.execute("SELECT version FROM settings")] == [1, 2]
    assert ("spike",) in b.execute("SELECT temp_flag FROM measurements").fetchall()
    assert len(b.execute(qa).fetchall()) == 2  # một thật (ngưỡng 28), một demo
