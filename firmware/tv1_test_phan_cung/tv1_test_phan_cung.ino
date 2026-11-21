/*
 * tv1_test_phan_cung.ino – Kiểm tra từng khối phần cứng ngay sau khi lắp (TV1, tuần 1).
 * Nạp sketch này TRƯỚC firmware chính. Serial Monitor: 115200 baud, chọn "New Line".
 * Gõ một số rồi Enter:
 *   1 = LED đỏ   2 = LED xanh   3 = còi   4 = DHT22   5 = quét I2C + BH1750   0 = chạy tất cả
 * Tọa độ trong thông báo lỗi khớp bảng cắm breadboard của tài liệu hướng dẫn tuần 1.
 */
#include <Wire.h>
#include <DHT.h>
#include <BH1750.h>

const uint8_t PIN_DHT = 4, PIN_SDA = 21, PIN_SCL = 22;
const uint8_t PIN_LED_RED = 25, PIN_LED_GREEN = 26, PIN_BUZZER = 27;

DHT dht(PIN_DHT, DHT22);
BH1750 lightMeter;

void blinkPin(uint8_t pin, int times, int onMs, int offMs) {
  for (int i = 0; i < times; i++) {
    digitalWrite(pin, HIGH);
    delay(onMs);
    digitalWrite(pin, LOW);
    delay(offMs);
  }
}

void testRed() {
  Serial.println(F("[1] LED do nhay 3 lan..."));
  blinkPin(PIN_LED_RED, 3, 300, 300);
  Serial.println(F("    Khong sang? Kiem tra: day GPIO25 o j4, tro 330 ohm f4-f8,"));
  Serial.println(F("    LED chan dai h8 / chan ngan h9, day noi j9 -> dai J- (GND)."));
}

void testGreen() {
  Serial.println(F("[2] LED xanh nhay 3 lan..."));
  blinkPin(PIN_LED_GREEN, 3, 300, 300);
  Serial.println(F("    Khong sang? Kiem tra: day GPIO26 o j12, tro 330 ohm f12-f16,"));
  Serial.println(F("    LED chan dai h16 / chan ngan h17, day noi j17 -> dai J- (GND)."));
}

void testBuzzer() {
  Serial.println(F("[3] Coi keu 3 tieng ngan..."));
  blinkPin(PIN_BUZZER, 3, 150, 350);
  Serial.println(F("    Im lang? Kiem tra: day 5V/VIN o g20, coi (+) j20 / (-) j23, transistor C g23 B g24 E g25,"));
  Serial.println(F("    tro 1k d24-f24, day GPIO27 o b24, tro 10k j24 -> J-, day noi j25 -> J-, diode vach o f20."));
}

void testDht() {
  Serial.println(F("[4] Doc DHT22 (cho 2,5 s)..."));
  delay(2500);  // DHT22 doc toi da 1 lan moi 2 giay
  const float h = dht.readHumidity(true);
  const float t = dht.readTemperature(false, false);
  if (isnan(h) || isnan(t)) {
    Serial.println(F("    LOI: khong doc duoc DHT22."));
    Serial.println(F("    Kiem tra: DHT22 OUT o e4, day GPIO4 o c4, DHT22 + vao dai A+ (3V3), - vao dai A- (GND);"));
    Serial.println(F("    module chua co tro keo len thi them tro 10k tu a4 len dai A+."));
  } else {
    Serial.printf("    OK: %.1f C, %.1f %%RH\n", t, h);
  }
}

void testI2c() {
  Serial.println(F("[5] Quet bus I2C (SDA=GPIO21, SCL=GPIO22)..."));
  int found = 0;
  uint8_t bhAddr = 0;
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.printf("    Thay thiet bi o 0x%02X\n", a);
      found++;
      if (a == 0x23 || a == 0x5C) bhAddr = a;
    }
  }
  if (found == 0) {
    Serial.println(F("    LOI: khong thay thiet bi nao."));
    Serial.println(F("    Kiem tra: BH1750 SDA o e9 + GPIO21 o c9; SCL o e11 + GPIO22 o c11;"));
    Serial.println(F("    VCC vao dai A+ (3V3), GND vao dai A-; khong dao SDA/SCL."));
    return;
  }
  if (!bhAddr) {
    Serial.println(F("    Co thiet bi I2C nhung khong phai BH1750 (0x23 hoac 0x5C)."));
    return;
  }
  if (!lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, bhAddr, &Wire)) {
    Serial.println(F("    LOI: BH1750 khong nhan lenh cau hinh."));
    return;
  }
  delay(200);  // lan do dau tien can khoang 180 ms
  for (int i = 0; i < 3; i++) {
    const float lx = lightMeter.readLightLevel();
    if (lx < 0) Serial.println(F("    LOI doc BH1750"));
    else Serial.printf("    OK: %.1f lux (che tay len cam bien thi so phai giam)\n", lx);
    delay(1000);
  }
}

void printMenu() {
  Serial.println();
  Serial.println(F("== Kiem tra phan cung TV1 =="));
  Serial.println(F("1 LED do | 2 LED xanh | 3 coi | 4 DHT22 | 5 I2C + BH1750 | 0 tat ca"));
}

void setup() {
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  pinMode(PIN_LED_RED, OUTPUT);
  digitalWrite(PIN_LED_RED, LOW);
  pinMode(PIN_LED_GREEN, OUTPUT);
  digitalWrite(PIN_LED_GREEN, LOW);
  Serial.begin(115200);
  delay(300);
  dht.begin();
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(100000);
  printMenu();
}

void loop() {
  if (!Serial.available()) return;
  const char c = (char)Serial.read();
  switch (c) {
    case '1': testRed(); break;
    case '2': testGreen(); break;
    case '3': testBuzzer(); break;
    case '4': testDht(); break;
    case '5': testI2c(); break;
    case '0': testRed(); testGreen(); testBuzzer(); testDht(); testI2c(); break;
    default: return;  // bo qua Enter va ky tu khac
  }
  printMenu();
}
