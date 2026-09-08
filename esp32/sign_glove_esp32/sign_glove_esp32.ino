#include <Arduino.h>
#include <Wire.h>
#include <ICM_20948.h>

// AIHandGlove - ESP32 + Flex Sensor x5 + ICM-20948 V2
constexpr uint8_t FLEX_COUNT = 5;
constexpr uint8_t FLEX_PINS[FLEX_COUNT] = {25, 34, 35, 32, 33}; // 엄지부터 소지
constexpr uint8_t IMU_SDA_PIN = 21;
constexpr uint8_t IMU_SCL_PIN = 22;
constexpr uint32_t SERIAL_BAUD_RATE = 115200;
constexpr uint32_t SAMPLE_INTERVAL_MS = 50; // 20 Hz
constexpr uint8_t FLEX_AVERAGE_SAMPLES = 8;

enum OutputMode {
  PLOT_ALL,
  PLOT_FLEX,
  PLOT_IMU,
  JSON_DATA
};

// Serial Plotter에서 모든 센서를 표시한다.
constexpr OutputMode OUTPUT_MODE = PLOT_ALL;

struct SensorData {
  uint16_t flex[FLEX_COUNT];
  float acc[3];
  float gyro[3];
};

ICM_20948_I2C imu;
bool imuReady = false;
uint32_t previousSampleTime = 0;
float lastAcc[3] = {0.0f, 0.0f, 0.0f};
float lastGyro[3] = {0.0f, 0.0f, 0.0f};

bool beginImu() {
  Wire.begin(IMU_SDA_PIN, IMU_SCL_PIN);
  Wire.setClock(400000);

  imu.begin(Wire, 1); // 0x69
  if (imu.status == ICM_20948_Stat_Ok) return true;

  imu.begin(Wire, 0); // 0x68
  return imu.status == ICM_20948_Stat_Ok;
}

uint16_t readFlexAverage(uint8_t pin) {
  uint32_t sum = 0;
  for (uint8_t sample = 0; sample < FLEX_AVERAGE_SAMPLES; sample++) {
    sum += analogRead(pin);
    delayMicroseconds(200);
  }
  return static_cast<uint16_t>(sum / FLEX_AVERAGE_SAMPLES);
}

void readImu(SensorData &data) {
  // 새 프레임이 없는 순간에는 0 대신 직전 정상값을 유지한다.
  if (imuReady && imu.dataReady()) {
    imu.getAGMT();
    lastAcc[0] = imu.accX(); // mg
    lastAcc[1] = imu.accY();
    lastAcc[2] = imu.accZ();
    lastGyro[0] = imu.gyrX(); // dps
    lastGyro[1] = imu.gyrY();
    lastGyro[2] = imu.gyrZ();
  }

  for (uint8_t axis = 0; axis < 3; axis++) {
    data.acc[axis] = lastAcc[axis];
    data.gyro[axis] = lastGyro[axis];
  }
}

void readSensors(SensorData &data) {
  for (uint8_t finger = 0; finger < FLEX_COUNT; finger++) {
    data.flex[finger] = readFlexAverage(FLEX_PINS[finger]);
  }
  readImu(data);
}

void printFlexPlot(const SensorData &data, bool finishLine) {
  Serial.print("thumb:"); Serial.print(data.flex[0]);
  Serial.print("\tindex:"); Serial.print(data.flex[1]);
  Serial.print("\tmiddle:"); Serial.print(data.flex[2]);
  Serial.print("\tring:"); Serial.print(data.flex[3]);
  Serial.print("\tlittle:"); Serial.print(data.flex[4]);
  if (finishLine) Serial.println();
  else Serial.print('\t');
}

void printImuPlot(const SensorData &data) {
  Serial.print("accX:"); Serial.print(data.acc[0], 2);
  Serial.print("\taccY:"); Serial.print(data.acc[1], 2);
  Serial.print("\taccZ:"); Serial.print(data.acc[2], 2);
  Serial.print("\tgyroX:"); Serial.print(data.gyro[0], 2);
  Serial.print("\tgyroY:"); Serial.print(data.gyro[1], 2);
  Serial.print("\tgyroZ:"); Serial.println(data.gyro[2], 2);
}

void printJsonArray(const uint16_t *values, uint8_t count) {
  for (uint8_t index = 0; index < count; index++) {
    Serial.print(values[index]);
    if (index + 1 < count) Serial.print(',');
  }
}

void printJsonArray(const float *values, uint8_t count) {
  for (uint8_t index = 0; index < count; index++) {
    Serial.print(values[index], 4);
    if (index + 1 < count) Serial.print(',');
  }
}

void printJson(const SensorData &data) {
  Serial.print("{\"flex\":["); printJsonArray(data.flex, FLEX_COUNT);
  Serial.print("],\"acc\":["); printJsonArray(data.acc, 3);
  Serial.print("],\"gyro\":["); printJsonArray(data.gyro, 3);
  Serial.println("]}");
}

void sendSensorData(const SensorData &data) {
  switch (OUTPUT_MODE) {
    case PLOT_FLEX: printFlexPlot(data, true); break;
    case PLOT_IMU: printImuPlot(data); break;
    case JSON_DATA: printJson(data); break;
    case PLOT_ALL:
    default:
      printFlexPlot(data, false);
      printImuPlot(data);
      break;
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  delay(1000);

  analogReadResolution(12); // 0 ~ 4095
  for (uint8_t finger = 0; finger < FLEX_COUNT; finger++) {
    pinMode(FLEX_PINS[finger], INPUT);
    analogSetPinAttenuation(FLEX_PINS[finger], ADC_11db);
  }

  imuReady = beginImu();
  if (OUTPUT_MODE == JSON_DATA) {
    Serial.println(imuReady ? "# ICM20948_READY" : "# ICM20948_NOT_FOUND");
    Serial.println("# SIGN_GLOVE_READY");
  }
}

void loop() {
  const uint32_t now = millis();
  if (now - previousSampleTime < SAMPLE_INTERVAL_MS) return;
  previousSampleTime = now;

  SensorData data{};
  readSensors(data);
  sendSensorData(data);
}
