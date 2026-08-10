#include <Arduino.h>
#include <math.h>

// ========================================
// AI 수어 인식 장갑 - ESP32
// ========================================

// 센서 데이터 구조체
struct SensorData {
  int flex[5];      // 손가락 굽힘 센서 5개
  float acc[3];     // 가속도 x, y, z
  float gyro[3];    // 자이로 x, y, z
};

// 데이터 전송 주기
// 50ms = 초당 20번
const unsigned long SEND_INTERVAL = 50;

unsigned long lastSendTime = 0;


// ========================================
// 센서 데이터 읽기
// ========================================
void readSensors(SensorData &data) {

  /*
    지금은 센서가 없기 때문에
    가짜 센서 데이터를 생성한다.

    나중에 실제 센서를 연결하면
    이 함수 내부만 수정하면 된다.
  */

  static float t = 0;

  t += 0.1;


  // ----------------------------------------
  // Flex sensor 가상 데이터
  // ----------------------------------------

  data.flex[0] = 1800 + 200 * sin(t);
  data.flex[1] = 1900 + 200 * sin(t + 0.3);
  data.flex[2] = 2000 + 200 * sin(t + 0.6);
  data.flex[3] = 1900 + 200 * sin(t + 0.9);
  data.flex[4] = 1800 + 200 * sin(t + 1.2);


  // ----------------------------------------
  // 가속도 센서 가상 데이터
  // ----------------------------------------

  data.acc[0] = 0.1 * sin(t);
  data.acc[1] = 0.1 * cos(t);
  data.acc[2] = 1.0;


  // ----------------------------------------
  // 자이로 센서 가상 데이터
  // ----------------------------------------

  data.gyro[0] = 5.0 * sin(t);
  data.gyro[1] = 5.0 * cos(t);
  data.gyro[2] = 2.0 * sin(t);
}


// ========================================
// JSON 형태로 Jetson에 전송
// ========================================
void sendSensorData(SensorData &data) {

  Serial.print("{");

  // Flex
  Serial.print("\"flex\":[");

  for (int i = 0; i < 5; i++) {

    Serial.print(data.flex[i]);

    if (i < 4) {
      Serial.print(",");
    }

  }

  Serial.print("],");


  // Accelerometer
  Serial.print("\"acc\":[");

  for (int i = 0; i < 3; i++) {

    Serial.print(data.acc[i], 4);

    if (i < 2) {
      Serial.print(",");
    }

  }

  Serial.print("],");


  // Gyroscope
  Serial.print("\"gyro\":[");

  for (int i = 0; i < 3; i++) {

    Serial.print(data.gyro[i], 4);

    if (i < 2) {
      Serial.print(",");
    }

  }

  Serial.print("]");

  Serial.println("}");
}


// ========================================
// Arduino 시작
// ========================================
void setup() {

  Serial.begin(115200);

  delay(1000);

  Serial.println("# SIGN_GLOVE_READY");

}


// ========================================
// 반복 실행
// ========================================
void loop() {

  unsigned long currentTime = millis();


  if (currentTime - lastSendTime >= SEND_INTERVAL) {

    lastSendTime = currentTime;


    SensorData sensorData;


    // 센서값 읽기
    readSensors(sensorData);


    // Jetson으로 전송
    sendSensorData(sensorData);

  }

}