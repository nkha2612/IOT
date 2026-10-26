"""Mô hình dữ liệu vào/ra của API (khớp docs/api.md)."""

import math
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Trạng thái cảm biến do firmware báo
SensorState = Literal["ok", "read_error", "not_detected"]


class SensorStatus(BaseModel):
    dht22: SensorState
    bh1750: SensorState


class MeasurementIn(BaseModel):
    """Gói đo ESP32 gửi lên mỗi 5 giây."""

    model_config = ConfigDict(extra="ignore")

    device_id: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    boot_id: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9]+$")
    seq: int = Field(ge=0)
    uptime_ms: int = Field(ge=0)
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    lux: Optional[float] = None
    sensor_status: SensorStatus
    config_version_applied: Optional[int] = Field(default=None, ge=0)

    @field_validator("temperature", "humidity", "lux", mode="before")
    @classmethod
    def nan_to_none(cls, v):
        # Một số thư viện in NaN/Infinity thay cho null; coi như không có giá trị
        if isinstance(v, float) and not math.isfinite(v):
            return None
        return v


class DeviceConfig(BaseModel):
    version: int
    temp_high: float
    temp_recover: float
    hum_high: float
    hum_recover: float
    lux_low: float
    lux_recover: float
    light_alert_enabled: bool
    confirm_samples: int


class MeasurementAck(BaseModel):
    ok: bool
    duplicate: bool
    config: DeviceConfig
