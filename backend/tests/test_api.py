from conftest import make_payload


# ------------------------------------------------------------- POST /api/measurements
def test_post_valid_returns_config(client):
    r = client.post("/api/measurements", json=make_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["duplicate"] is False
    assert body["config"]["version"] == 1
    assert body["config"]["temp_high"] == 30
    assert body["config"]["confirm_samples"] == 3


def test_duplicate_is_not_stored_twice(client):
    client.post("/api/measurements", json=make_payload(seq=7))
    r = client.post("/api/measurements", json=make_payload(seq=7))
    assert r.json()["duplicate"] is True
    assert client.get("/api/history").json()["count"] == 1


def test_same_seq_after_reboot_is_new_sample(client):
    client.post("/api/measurements", json=make_payload(seq=1))
    r = client.post("/api/measurements", json=make_payload(seq=1, boot_id="a1b2c3d4"))
    assert r.json()["duplicate"] is False
    assert client.get("/api/history").json()["count"] == 2


def test_sensor_error_keeps_null_and_other_sensor(client):
    p = make_payload(temperature=None, humidity=None,
                     sensor_status={"dht22": "read_error", "bh1750": "ok"})
    client.post("/api/measurements", json=p)
    m = client.get("/api/latest").json()["measurement"]
    assert m["temperature"] is None and m["humidity"] is None  # không đổi thành 0
    assert m["flags"] == {"temperature": "read_error", "humidity": "read_error", "lux": "ok"}
    assert m["lux"] == 412.5
    assert "lỗi đọc" in m["flag_reason"]


def test_missing_value_when_sensor_says_ok(client):
    client.post("/api/measurements", json=make_payload(lux=None))
    m = client.get("/api/latest").json()["measurement"]
    assert m["flags"]["lux"] == "missing"


def test_out_of_range_is_flagged_but_raw_value_kept(client):
    client.post("/api/measurements", json=make_payload(humidity=105.2, lux=-3))
    m = client.get("/api/latest").json()["measurement"]
    assert m["humidity"] == 105.2 and m["lux"] == -3
    assert m["flags"]["humidity"] == "out_of_range"
    assert m["flags"]["lux"] == "out_of_range"
    assert m["flags"]["temperature"] == "ok"


def test_hot_but_valid_is_not_flagged(client):
    client.post("/api/measurements", json=make_payload(temperature=38.0))
    assert client.get("/api/latest").json()["measurement"]["flags"]["temperature"] == "ok"


def test_nan_is_treated_as_missing(client):
    raw = ('{"device_id":"esp32-room-01","boot_id":"b1","seq":1,"uptime_ms":1,'
           '"temperature":NaN,"humidity":50,"lux":10,'
           '"sensor_status":{"dht22":"ok","bh1750":"ok"}}')
    r = client.post("/api/measurements", content=raw,
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    m = client.get("/api/latest").json()["measurement"]
    assert m["temperature"] is None and m["flags"]["temperature"] == "missing"


def test_invalid_payload_rejected(client):
    p = make_payload()
    del p["seq"]
    assert client.post("/api/measurements", json=p).status_code == 422
    bad_status = make_payload(sensor_status={"dht22": "broken", "bh1750": "ok"})
    assert client.post("/api/measurements", json=bad_status).status_code == 422


# ---------------------------------------------------------------------- GET /api/latest
def test_latest_empty_database(client):
    body = client.get("/api/latest").json()
    assert body["device"] is None and body["measurement"] is None
    assert body["config"]["version"] == 1


def test_online_then_offline_after_30s(client, clock):
    client.post("/api/measurements", json=make_payload())
    clock.advance(30)
    assert client.get("/api/latest").json()["device"]["online"] is True
    clock.advance(1)
    body = client.get("/api/latest").json()
    assert body["device"]["online"] is False
    assert body["device"]["seconds_since_last"] == 31.0
    assert body["measurement"]["temperature"] == 28.4  # vẫn giữ số cũ để hiển thị


def test_latest_returns_newest_sample(client, clock):
    for seq, t in [(1, 25.0), (2, 26.0), (3, 27.0)]:
        client.post("/api/measurements", json=make_payload(seq=seq, temperature=t))
        clock.advance(5)
    m = client.get("/api/latest").json()["measurement"]
    assert m["seq"] == 3 and m["temperature"] == 27.0


def test_device_reports_applied_config_version(client):
    client.post("/api/measurements", json=make_payload(config_version_applied=1))
    body = client.get("/api/latest").json()
    assert body["config"] == {"version": 1, "applied_version": 1}


# --------------------------------------------------------------------- GET /api/history
def _post_series(client, clock, n, step_s=5):
    for i in range(1, n + 1):
        client.post("/api/measurements", json=make_payload(seq=i))
        clock.advance(step_s)


def test_history_range_filters_old_rows(client, clock):
    _post_series(client, clock, 3)
    clock.advance(2 * 3600)  # 2 giờ sau
    client.post("/api/measurements", json=make_payload(seq=100))
    assert client.get("/api/history?range=1h").json()["count"] == 1
    assert client.get("/api/history?range=24h").json()["count"] == 4


def test_history_from_to_and_sorted(client, clock):
    # clock bắt đầu lúc 2026-10-26 03:00:00 UTC = 10:00:00 giờ Việt Nam
    _post_series(client, clock, 10)  # 10 mẫu cách nhau 5 s
    body = client.get("/api/history", params={
        "from": "2026-10-26T10:00:10+07:00",   # = start + 10 s
        "to": "2026-10-26T03:00:30Z",          # = start + 30 s
    }).json()
    seqs = [it["seq"] for it in body["items"]]
    assert seqs == [3, 4, 5, 6, 7]
    assert body["gap_threshold_s"] == 15


def test_history_bad_params(client):
    assert client.get("/api/history?range=abc").status_code == 400
    assert client.get("/api/history?from=hom-qua").status_code == 400
    r = client.get("/api/history", params={"from": "2026-10-26T12:00:00Z",
                                           "to": "2026-10-26T11:00:00Z"})
    assert r.status_code == 400


# ---------------------------------------------------------------------- GET /api/settings
def test_settings_defaults(client):
    s = client.get("/api/settings").json()
    assert s["version"] == 1
    assert (s["temp_high"], s["temp_recover"]) == (30, 29)
    assert (s["hum_high"], s["hum_recover"]) == (75, 72)
    assert (s["lux_low"], s["lux_recover"]) == (300, 350)
    assert s["light_alert_enabled"] is False
