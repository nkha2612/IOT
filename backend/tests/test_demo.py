"""Chế độ demo (API v1.1): website bấm nút -> lệnh đi kèm phản hồi POST -> ESP32 phát kịch bản."""

from conftest import make_payload


def test_no_demo_by_default(client):
    body = client.post("/api/measurements", json=make_payload()).json()
    assert body["demo"] is None  # firmware cũ bỏ qua trường null
    state = client.get("/api/demo").json()
    assert state["request"] is None
    assert "temp_high" in state["scenarios"] and len(state["scenarios"]) == 8


def test_demo_request_is_sent_with_ack(client, clock):
    r = client.post("/api/demo", json={"scenario": "temp_high"})
    assert r.status_code == 200
    req = r.json()["request"]
    assert req["scenario"] == "temp_high"

    clock.advance(3)
    ack = client.post("/api/measurements", json=make_payload(seq=1)).json()
    assert ack["demo"] == {"id": req["id"], "scenario": "temp_high", "age_s": 3.0}
    assert ack["config"]["version"] == 1  # cấu hình vẫn gửi như cũ


def test_each_click_gets_new_id(client, clock):
    first = client.post("/api/demo", json={"scenario": "hum_high"}).json()["request"]["id"]
    clock.advance(1)
    second = client.post("/api/demo", json={"scenario": "hum_high"}).json()["request"]["id"]
    assert first != second  # bấm lại cùng nút vẫn chạy lại


def test_stop_and_unknown_scenario(client):
    assert client.post("/api/demo", json={"scenario": "stop"}).status_code == 200
    assert client.post("/api/demo", json={"scenario": "chay_lung_tung"}).status_code == 422


def test_demo_command_expires(client, clock):
    client.post("/api/demo", json={"scenario": "offline"})
    clock.advance(121)
    assert client.post("/api/measurements", json=make_payload(seq=1)).json()["demo"] is None


def test_device_reports_progress_and_local_alerts(client):
    p = make_payload(seq=3, temperature=32.5,
                     alert_state={"temperature": "active", "humidity": "normal", "light": "off"},
                     demo={"scenario": "temp_high", "sample": 3, "total": 7})
    assert client.post("/api/measurements", json=p).status_code == 200
    dev = client.get("/api/demo").json()["device"]
    assert dev["device_id"] == "esp32-room-01"
    assert dev["alert_state"]["temperature"] == "active"
    assert dev["demo"] == {"scenario": "temp_high", "sample": 3, "total": 7}

    # Mẫu thật kế tiếp: hết demo
    client.post("/api/measurements", json=make_payload(seq=4))
    dev = client.get("/api/demo").json()["device"]
    assert dev["demo"] is None and dev["alert_state"] is None


def test_old_firmware_payload_still_valid(client):
    # Gói đúng API v1 (không có alert_state/demo) vẫn được nhận như trước
    assert client.post("/api/measurements", json=make_payload(seq=9)).status_code == 200


def test_bad_alert_state_is_rejected(client):
    p = make_payload(alert_state={"temperature": "hot", "humidity": "normal", "light": "off"})
    assert client.post("/api/measurements", json=p).status_code == 422
