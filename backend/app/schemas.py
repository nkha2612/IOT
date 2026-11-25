"""Mô hình dữ liệu vào/ra của API (khớp docs/api.md)."""

import math
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Trạng thái cảm biến do firmware báo
SensorState = Literal["ok", "read_error", "not_detected"]


class SensorStatus(BaseModel):
    dht22: SensorState
    bh1750: SensorState


# ----------------------------------------------------------------- chế độ demo (v1.1)
# Kịch bản firmware biết chạy (firmware/tv1_firmware/demo.cpp). "stop" = về đo thật.
DEMO_SCENARIOS = ("temp_high", "hum_high", "light_low", "dht_error",
                  "error_during_alert", "bh1750_lost", "out_of_range", "offline")
DemoName = Literal["temp_high", "hum_high", "light_low", "dht_error",
                   "error_during_alert", "bh1750_lost", "out_of_range", "offline"]

AlertStateName = Literal["normal", "active", "unknown", "off"]


class LocalAlertState(BaseModel):
    """Trạng thái cảnh báo tại thiết bị (LED/còi), firmware gửi kèm mỗi gói."""

    temperature: AlertStateName
    humidity: AlertStateName
    light: AlertStateName


class DemoProgress(BaseModel):
    """Firmware đang phát kịch bản demo: mẫu thứ sample / total."""

    scenario: str = Field(max_length=32)
    sample: int = Field(ge=0)
    total: int = Field(ge=0)


class DemoRequest(BaseModel):
    """Website bấm nút demo."""

    scenario: Literal[DemoName, "stop"]  # type: ignore[valid-type]


class DemoCommand(BaseModel):
    """Lệnh demo gửi xuống ESP32 trong phản hồi POST /api/measurements."""

    id: str
    scenario: str
    age_s: float


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
    # v1.1 – không bắt buộc, firmware cũ không gửi
    alert_state: Optional[LocalAlertState] = None
    demo: Optional[DemoProgress] = None
    # v1.2 – nguồn số đo. Bỏ trống: có "demo" thì là demo, không thì là đo thật.
    # Firmware gửi "sim" khi đang giả lập bằng lệnh Serial (sim lux …).
    source: Optional[Literal["real", "demo", "sim"]] = None

    def resolved_source(self) -> str:
        if self.source:
            return self.source
        return "demo" if self.demo else "real"

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
    demo: Optional[DemoCommand] = None  # v1.1: chỉ có trong DEMO_COMMAND_TTL_S sau khi bấm nút


class SettingsUpdate(BaseModel):
    """Website lưu ngưỡng mới (PUT /api/settings). Kiểm tra giống validateAlertConfig của firmware."""

    model_config = ConfigDict(extra="forbid")

    temp_high: float = Field(ge=-40, le=80)
    temp_recover: float = Field(ge=-40, le=80)
    hum_high: float = Field(ge=0, le=100)
    hum_recover: float = Field(ge=0, le=100)
    lux_low: float = Field(ge=0, le=65535)
    lux_recover: float = Field(ge=0, le=65535)
    light_alert_enabled: bool

    @field_validator("*", mode="before")
    @classmethod
    def finite_only(cls, v):
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError("phải là số hữu hạn")
        return v

    def problems(self) -> list[str]:
        out = []
        if self.temp_recover >= self.temp_high:
            out.append("Ngưỡng hồi phục nhiệt độ phải nhỏ hơn ngưỡng cảnh báo")
        if self.hum_recover >= self.hum_high:
            out.append("Ngưỡng hồi phục độ ẩm phải nhỏ hơn ngưỡng cảnh báo")
        if self.lux_recover <= self.lux_low:
            out.append("Ngưỡng hồi phục ánh sáng phải lớn hơn ngưỡng thiếu sáng")
        return out
