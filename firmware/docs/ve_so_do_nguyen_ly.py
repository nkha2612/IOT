#!/usr/bin/env python3
"""Vẽ sơ đồ nguyên lý (schematic) của mạch TV1 ra so_do_nguyen_ly.svg (+ .png nếu có cairosvg).

    python3 firmware/docs/ve_so_do_nguyen_ly.py

Khớp firmware/tv1_firmware/config.h và so_do_breadboard.svg. Sửa mạch thì sửa file này rồi chạy lại.
"""

from pathlib import Path

W, H = 1040, 900
INK, MUTED, ACC = "#1b1f24", "#5b6470", "#b3261e"
out: list[str] = []


def add(s: str) -> None:
    out.append(s)


def line(x1, y1, x2, y2, w=2, dash=None, color=INK):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{w}"{d}/>')


def text(x, y, s, size=15, anchor="start", weight="400", color=INK):
    add(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" fill="{color}">{s}</text>')


def dot(x, y):
    add(f'<circle cx="{x}" cy="{y}" r="4" fill="{INK}"/>')


def resistor_h(x1, x2, y, name, value, dash=None):
    """Điện trở nằm ngang (ký hiệu IEC: hình chữ nhật)."""
    mid = (x1 + x2) / 2
    line(x1, y, mid - 28, y, dash=dash)
    line(mid + 28, y, x2, y, dash=dash)
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<rect x="{mid - 28}" y="{y - 9}" width="56" height="18" fill="white" stroke="{INK}" stroke-width="2"{d}/>')
    text(mid, y - 16, name, 13, "middle", "600")
    text(mid, y + 30, value, 13, "middle", color=MUTED)


def resistor_v(x, y1, y2, name, value, dash=None):
    mid = (y1 + y2) / 2
    line(x, y1, x, mid - 28, dash=dash)
    line(x, mid + 28, x, y2, dash=dash)
    d = f' stroke-dasharray="{dash}"' if dash else ""
    add(f'<rect x="{x - 9}" y="{mid - 28}" width="18" height="56" fill="white" stroke="{INK}" stroke-width="2"{d}/>')
    text(x + 16, mid - 4, name, 13, weight="600")
    text(x + 16, mid + 13, value, 13, color=MUTED)


def ground(x, y):
    line(x, y, x, y + 10)
    line(x - 12, y + 10, x + 12, y + 10)
    line(x - 7, y + 15, x + 7, y + 15)
    line(x - 3, y + 20, x + 3, y + 20)


def net(x, y, name, up=True):
    """Nhãn nguồn (3V3, 5V): mũi tên lên."""
    y2 = y - 14 if up else y + 14
    line(x, y, x, y2)
    add(f'<path d="M{x - 9} {y2} L{x + 9} {y2} L{x} {y2 - 10 if up else y2 + 10} Z" fill="{INK}"/>')
    text(x, y2 - 14 if up else y2 + 26, name, 13, "middle", "700")


def led_h(x, y, name, color_name):
    """LED nằm ngang, anode bên trái."""
    add(f'<path d="M{x} {y - 12} L{x} {y + 12} L{x + 22} {y} Z" fill="white" stroke="{INK}" stroke-width="2"/>')
    line(x + 22, y - 12, x + 22, y + 12)
    for dx in (6, 14):  # hai mũi tên phát sáng
        line(x + dx, y - 16, x + dx + 9, y - 27, 1.5)
        add(f'<path d="M{x + dx + 9} {y - 27} l-5 1 l3 3 Z" fill="{INK}"/>')
    text(x + 98, y + 5, name, 13, weight="600")
    text(x + 124, y + 5, f"– {color_name}", 13, color=MUTED)


def box(x, y, w, h, title, sub):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="white" stroke="{INK}" stroke-width="2"/>')
    text(x + w / 2, y - 22, title, 15, "middle", "700")
    text(x + w / 2, y - 6, sub, 12, "middle", color=MUTED)


def pin_left(x, y, label):
    text(x + 10, y + 5, label, 13)


def pin_right(x, y, label):
    text(x - 10, y + 5, label, 13, "end")


# ------------------------------------------------------------------ khung
add(f'<rect width="{W}" height="{H}" fill="white"/>')
text(30, 38, "Sơ đồ nguyên lý – Giám sát môi trường phòng học (TV1)", 20, weight="700")
text(30, 60, "Khớp firmware/tv1_firmware/config.h. Cấp nguồn ESP32 qua cổng USB (5V). Nét đứt = chỉ lắp khi module chưa có sẵn.", 13, color=MUTED)

# ------------------------------------------------------------------ ESP32
EX, EY, EW, EH = 60, 120, 190, 640
box(EX, EY, EW, EH, "U1 – ESP32 DevKit", "ESP32-WROOM-32, nguồn từ USB")
ER = EX + EW
P = {"3V3": 150, "GND": 200, "5V": 250, "GPIO4": 330, "GPIO21": 440, "GPIO22": 490,
     "GPIO25": 570, "GPIO26": 640, "GPIO27": 720}
labels = {"3V3": "3V3", "GND": "GND", "5V": "5V (VIN)", "GPIO4": "GPIO4", "GPIO21": "GPIO21 (SDA)",
          "GPIO22": "GPIO22 (SCL)", "GPIO25": "GPIO25", "GPIO26": "GPIO26", "GPIO27": "GPIO27"}
for k, y in P.items():
    line(ER, y, ER + 20, y)
    pin_right(ER, y, labels[k])
net(ER + 20, P["3V3"], "3V3")
line(ER + 20, P["GND"], ER + 40, P["GND"]); ground(ER + 40, P["GND"])
net(ER + 20, P["5V"], "5V")

# ------------------------------------------------------------------ DHT22 (GPIO4)
DX, DY = 720, 290
box(DX, DY, 170, 85, "U2 – DHT22", "nhiệt độ, độ ẩm (module)")
line(ER + 20, P["GPIO4"], DX, P["GPIO4"])
pin_left(DX, P["GPIO4"], "DATA")
dot(600, P["GPIO4"])
resistor_v(600, 230, P["GPIO4"], "R5", "10 kΩ*", dash="6 4")
net(600, 230, "3V3")
line(DX + 170, 308, DX + 190, 308); pin_right(DX + 170, 308, "VCC"); net(DX + 190, 308, "3V3")
line(DX + 170, 355, DX + 190, 355); pin_right(DX + 170, 355, "GND"); ground(DX + 190, 355)

# ------------------------------------------------------------------ BH1750 (I2C)
BX, BY = 720, 415
box(BX, BY, 170, 100, "U3 – BH1750 (GY-302)", "độ rọi, I²C địa chỉ 0x23")
line(ER + 20, P["GPIO21"], BX, P["GPIO21"]); pin_left(BX, P["GPIO21"], "SDA")
line(ER + 20, P["GPIO22"], BX, P["GPIO22"]); pin_left(BX, P["GPIO22"], "SCL")
line(BX + 170, 428, BX + 190, 428); pin_right(BX + 170, 428, "VCC"); net(BX + 190, 428, "3V3")
line(BX + 170, 460, BX + 210, 460); pin_right(BX + 170, 460, "GND")
line(BX + 170, 490, BX + 210, 490); pin_right(BX + 170, 490, "ADDR")
line(BX + 210, 460, BX + 210, 500); ground(BX + 210, 500)

# ------------------------------------------------------------------ LED đỏ, LED xanh
for key, rname, dname, cname in (("GPIO25", "R1", "D2", "LED đỏ"), ("GPIO26", "R2", "D3", "LED xanh")):
    y = P[key]
    line(ER + 20, y, 340, y)
    resistor_h(340, 470, y, rname, "330 Ω")
    line(470, y, 500, y)
    led_h(500, y, dname, cname)
    line(522, y, 570, y)
    ground(570, y)

# ------------------------------------------------------------------ còi qua 2N2222 (GPIO27)
y = P["GPIO27"]
line(ER + 20, y, 340, y)
resistor_h(340, 470, y, "R3", "1 kΩ")
BASE = 790
line(470, y, BASE, y)
dot(720, y)
resistor_v(720, y, 790, "R4", "10 kΩ")
ground(720, 790)
# transistor NPN Q1, base tại (BASE, y)
QX = BASE + 26
add(f'<circle cx="{QX + 8}" cy="{y}" r="30" fill="white" stroke="{INK}" stroke-width="2"/>')
line(BASE, y, QX - 2, y)
line(QX - 2, y - 18, QX - 2, y + 18, 3)
line(QX - 2, y - 8, QX + 22, y - 26)   # collector
line(QX - 2, y + 8, QX + 22, y + 26)   # emitter
add(f'<path d="M{QX + 22} {y + 26} l-11 -2 l5 -8 Z" fill="{INK}"/>')
text(QX + 48, y + 2, "Q1", 13, weight="600")
text(QX + 48, y + 18, "2N2222", 13, color=MUTED)
text(QX + 26, y - 30, "C", 12, color=MUTED)
text(QX + 26, y + 40, "E", 12, color=MUTED)
text(BASE - 6, y - 6, "B", 12, "end", color=MUTED)
CX = QX + 22
line(CX, y + 26, CX, 780); ground(CX, 780)
# còi giữa 5V và collector
YT = 600  # đỉnh còi
line(CX, y - 26, CX, YT + 60)
add(f'<rect x="{CX - 22}" y="{YT}" width="44" height="60" rx="4" fill="white" stroke="{INK}" stroke-width="2"/>')
text(CX, YT + 36, "BZ", 13, "middle", "700")
text(CX - 30, YT + 20, "BZ1", 13, "end", "600")
text(CX - 30, YT + 36, "còi chủ động 5V", 13, "end", color=MUTED)
text(CX + 6, YT - 5, "+", 14, weight="700")
line(CX, YT, CX, YT - 32)
net(CX, YT - 32, "5V")
dot(CX, YT - 20); dot(CX, YT + 72)
# diode bảo vệ song song còi, cathode về 5V
DXD = CX + 70
line(CX, YT - 20, DXD, YT - 20); line(CX, YT + 72, DXD, YT + 72)
line(DXD, YT - 20, DXD, YT + 14); line(DXD, YT + 40, DXD, YT + 72)
add(f'<path d="M{DXD - 12} {YT + 40} L{DXD + 12} {YT + 40} L{DXD} {YT + 16} Z" fill="white" stroke="{INK}" stroke-width="2"/>')
line(DXD - 12, YT + 14, DXD + 12, YT + 14, 3)
text(DXD + 18, YT + 24, "D1", 13, weight="600")
text(DXD + 18, YT + 40, "1N4148", 13, color=MUTED)

# ------------------------------------------------------------------ ghi chú
notes = [
    "Ghi chú",
    "• GPIO27 = HIGH: Q1 dẫn, còi kêu. R4 giữ Q1 tắt khi ESP32 khởi động.",
    "• D1 hấp thụ điện áp ngược của còi khi tắt.",
    "• R5 chỉ lắp khi module DHT22 chưa có trở kéo lên.",
    "• ADDR nối GND (hoặc để trống) → địa chỉ 0x23.",
    "• LED: chân dài (anode) về phía điện trở.",
]
for i, n in enumerate(notes):
    text(60 + (i > 3) * 470 if i else 60, 820 + (i if i <= 3 else i - 3) * 19 if i else 820, n, 13,
         weight="700" if i == 0 else "400", color=INK if i == 0 else MUTED)

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
       f'font-family="DejaVu Sans, Arial, sans-serif">' + "".join(out) + "</svg>")
here = Path(__file__).resolve().parent
(here / "so_do_nguyen_ly.svg").write_text(svg, encoding="utf-8")
print("Đã ghi", here / "so_do_nguyen_ly.svg")
try:
    import cairosvg
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(here / "so_do_nguyen_ly.png"), output_width=W * 2)
    print("Đã ghi", here / "so_do_nguyen_ly.png")
except ImportError:
    print("Chưa có cairosvg (pip install cairosvg): chỉ có file SVG")
