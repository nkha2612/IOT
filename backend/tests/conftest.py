import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # để import được "app"

from app.main import create_app  # noqa: E402


class FakeClock:
    """Đồng hồ giả để kiểm tra online/offline và lọc lịch sử mà không phải chờ thật."""

    def __init__(self):
        self.now = datetime(2026, 10, 26, 3, 0, 0, tzinfo=timezone.utc)  # 10:00 giờ VN

    def __call__(self):
        return self.now

    def advance(self, seconds: float):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def client(tmp_path, clock):
    app = create_app(db_path=tmp_path / "test.db", frontend_dir=tmp_path / "no-frontend",
                     clock=clock)
    with TestClient(app) as c:
        yield c


def make_payload(seq=1, **overrides):
    payload = {
        "device_id": "esp32-room-01",
        "boot_id": "7f3a91c2",
        "seq": seq,
        "uptime_ms": 5000 * seq,
        "temperature": 28.4,
        "humidity": 65.2,
        "lux": 412.5,
        "sensor_status": {"dht22": "ok", "bh1750": "ok"},
        "config_version_applied": 1,
    }
    payload.update(overrides)
    return payload
