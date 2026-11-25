"""Sự kiện cảnh báo (CN05). Các chuỗi số giống hệt firmware/test_host/test_alerts.cpp,
để thiết bị (LED/còi) và máy chủ (sự kiện trên website) cùng kết luận một trạng thái."""

import sqlite3

import pytest
from conftest import make_payload

E = None  # mẫu lỗi
N, A, U = "normal", "active", "unknown"


class Feeder:
    """Gửi lần lượt từng mẫu cách nhau 5 s, đọc trạng thái bộ máy cảnh báo trong DB."""

    def __init__(self, client, clock, param="temperature", source=None):
        self.client, self.clock, self.param, self.source = client, clock, param, source
        self.seq = 0
        self.db = client.app.state.db_path

    def send(self, value, **extra):
        self.seq += 1
        p = make_payload(seq=self.seq, **extra)
        if self.source:
            p["source"] = self.source
        if value is None:
            p[self.param] = None
            sensor = "bh1750" if self.param == "lux" else "dht22"
            p["sensor_status"][sensor] = "read_error"
            if sensor == "dht22":
                other = "humidity" if self.param == "temperature" else "temperature"
                p[other] = None
        else:
            p[self.param] = value
        r = self.client.post("/api/measurements", json=p)
        assert r.status_code == 200, r.text
        self.clock.advance(5)

    def state(self, kind, source="real"):
        con = sqlite3.connect(self.db)
        row = con.execute("SELECT state FROM alert_channels WHERE kind = ? AND source = ?",
                          (kind, source)).fetchone()
        con.close()
        return row[0] if row else N

    def run(self, kind, steps):
        for value, expect in steps:
            self.send(value)
            assert self.state(kind) == expect, f"sau mẫu {value}: mong {expect}"


def alerts(client, **params):
    params.setdefault("range", "24h")
    return client.get("/api/alerts", params=params).json()["items"]


def enable_light(client, on=True):
    s = client.get("/api/settings").json()
    body = {k: s[k] for k in ("temp_high", "temp_recover", "hum_high", "hum_recover",
                              "lux_low", "lux_recover")}
    body["light_alert_enabled"] = on
    assert client.put("/api/settings", json=body).status_code == 200


def test_1_2_temperature_needs_3_samples_and_hysteresis(client, clock):
    f = Feeder(client, clock)
    f.run("temp_high", [(30.0, N), (30.5, N), (29.9, N), (30.5, N), (30.6, N), (30.7, A)])
    f.run("temp_high", [(29.5, A), (29.0, A), (28.9, A), (28.8, A), (28.7, N)])
    items = alerts(client)
    assert len(items) == 1
    a = items[0]
    assert (a["type"], a["status"], a["threshold"]) == ("temp_high", "closed", 30.0)
    assert (a["start_value"], a["peak_value"], a["end_value"]) == (30.7, 30.7, 28.7)
    assert a["end_reason"] == "recovered" and a["label"] == "Nhiệt độ cao"
    assert a["duration_s"] == 25.0  # mở ở mẫu 30.7, đóng ở mẫu 28.7 (5 mẫu × 5 s sau)


def test_3_4_error_breaks_chain_and_unknown_during_alert(client, clock):
    f = Feeder(client, clock)
    f.run("temp_high", [(31, N), (31, N), (E, N), (31, N), (31, N), (31, A)])
    f.run("temp_high", [(E, U), (E, U)])
    assert alerts(client)[0]["status"] == "unknown"
    assert len(client.get("/api/latest").json()["open_alerts"]) == 1
    f.run("temp_high", [(28, A), (E, U), (28, A), (28, A), (28, N)])
    items = alerts(client)
    assert len(items) == 1 and items[0]["status"] == "closed"  # vẫn là một sự kiện


def test_5_humidity_single_event(client, clock):
    f = Feeder(client, clock, param="humidity")
    f.run("hum_high", [(76, N), (77, N), (78, A), (74, A), (73, A), (71, A), (71, A),
                       (74, A), (71, A), (70, A), (70, N)])
    items = alerts(client)
    assert len(items) == 1 and items[0]["peak_value"] == 78


def test_6_light_ignored_when_room_not_in_use(client, clock):
    f = Feeder(client, clock, param="lux")
    f.run("lux_low", [(100, N)] * 4)
    assert alerts(client) == []


def test_7_8_light_when_in_use_then_disabled(client, clock):
    enable_light(client, True)
    f = Feeder(client, clock, param="lux")
    f.run("lux_low", [(290, N), (280, N), (270, A), (320, A), (360, A), (360, A), (360, N)])
    f.run("lux_low", [(100, N), (100, N), (100, A)])
    enable_light(client, False)
    f.run("lux_low", [(100, N)])
    items = alerts(client)
    assert [a["end_reason"] for a in items] == ["light_disabled", "recovered"]
    assert items[1]["peak_value"] == 270  # thiếu sáng: lưu giá trị thấp nhất


def test_9_settings_validation(client):
    s = client.get("/api/settings").json()
    good = {k: s[k] for k in ("temp_high", "temp_recover", "hum_high", "hum_recover",
                              "lux_low", "lux_recover", "light_alert_enabled")}
    assert client.put("/api/settings", json={**good, "temp_recover": 30}).status_code == 422
    assert client.put("/api/settings", json={**good, "hum_high": 120}).status_code == 422
    assert client.put("/api/settings", json={**good, "lux_recover": 300}).status_code == 422
    assert client.put("/api/settings", json={**good, "confirm_samples": 5}).status_code == 422
    r = client.put("/api/settings", json=good).json()
    assert r["changed"] is False and r["version"] == 1  # không đổi gì thì không tăng version
    r = client.put("/api/settings", json={**good, "temp_high": 31, "temp_recover": 30}).json()
    assert r["changed"] is True and r["version"] == 2 and r["temp_high"] == 31
    ack = client.post("/api/measurements", json=make_payload(seq=1)).json()
    assert ack["config"]["version"] == 2 and ack["config"]["temp_high"] == 31


def test_new_threshold_applies_and_resets_counters(client, clock):
    f = Feeder(client, clock)
    f.run("temp_high", [(30.5, N), (30.5, N)])
    client.put("/api/settings", json={"temp_high": 30.2, "temp_recover": 29, "hum_high": 75,
                                      "hum_recover": 72, "lux_low": 300, "lux_recover": 350,
                                      "light_alert_enabled": False})
    f.run("temp_high", [(30.5, N), (30.5, N), (30.5, A)])  # đếm lại từ đầu như firmware
    assert alerts(client)[0]["threshold"] == 30.2


def test_demo_alerts_are_separate_and_closed_when_real_data_returns(client, clock):
    real = Feeder(client, clock)
    real.run("temp_high", [(27, N)] * 3)
    demo = Feeder(client, clock, source="demo")
    demo.seq = 1000
    for _ in range(4):
        demo.send(32.5)
    assert real.state("temp_high", "demo") == A
    assert real.state("temp_high") == N  # dữ liệu thật không bị ảnh hưởng
    assert alerts(client) == []  # mặc định chỉ xem dữ liệu thật
    demo_items = alerts(client, source="demo")
    assert len(demo_items) == 1 and demo_items[0]["status"] == "open"
    assert client.get("/api/latest").json()["open_alerts"][0]["source"] == "demo"

    real.seq = 2000
    real.send(27)
    demo_items = alerts(client, source="demo")
    assert demo_items[0]["status"] == "closed" and demo_items[0]["end_reason"] == "source_changed"
    assert client.get("/api/latest").json()["open_alerts"] == []


def test_duplicate_does_not_count_twice(client, clock):
    for seq in (1, 2, 2, 2):  # gửi lại gói 2 hai lần
        client.post("/api/measurements", json=make_payload(seq=seq, temperature=31))
        clock.advance(5)
    con = sqlite3.connect(client.app.state.db_path)
    on = con.execute("SELECT on_count FROM alert_channels WHERE kind='temp_high'").fetchone()[0]
    assert on == 2


@pytest.mark.parametrize("bad", ["hot", "x"])
def test_alerts_bad_params(client, bad):
    assert client.get("/api/alerts", params={"status": bad}).status_code == 400
    assert client.get("/api/alerts", params={"source": bad}).status_code == 400
