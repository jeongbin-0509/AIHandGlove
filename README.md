# AIHandGlove

ESP32 장갑의 플렉스 센서 5개와 IMU(가속도 3축, 자이로 3축) 시계열을 Jetson Nano에서 Transformer로 분류하는 프로젝트입니다.

## 현재 회로

| 센서 | ESP32 핀 |
|---|---:|
| 엄지 플렉스 | D25 |
| 검지 플렉스 | D34 |
| 중지 플렉스 | D35 |
| 약지 플렉스 | D32 |
| 소지 플렉스 | D33 |
| ICM-20948 V2 SDA | D21 |
| ICM-20948 V2 SCL | D22 |

ICM-20948은 ESP32의 `3.3V`와 `GND`에 연결해야 합니다. 사용 중인 V2 모듈에 전압 레귤레이터와 레벨 시프터가 있는지 확인하기 전에는 ESP32 I/O에 5V 신호를 넣지 마세요. Arduino Library Manager에서 `SparkFun 9DoF IMU Breakout - ICM 20948` 라이브러리가 필요합니다. 코드는 AD0 상태에 따라 I2C 주소 `0x69`, `0x68`을 차례로 탐색합니다.

## 구조

- `esp32/sign_glove_esp32.ino`: 센서 값을 20 Hz JSON Lines 형식으로 전송
- `jetson/collect_data.py`: 실제 장갑에서 라벨이 붙은 2초 시퀀스 수집
- `jetson/train.py`: Transformer 학습 및 최적 체크포인트 저장
- `jetson/main.py`: 슬라이딩 윈도 기반 실시간 추론
- `data/<label>/*.npz`: 수집된 원본 샘플(자동 생성)
- `models/sign_transformer.pt`: 학습 결과(자동 생성)

## 데이터 수집 권장안

한 샘플은 기본적으로 20 Hz × 2초 = 40 프레임이며, 각 프레임은 11개 특징을 가집니다. ICM-20948 가속도는 `mg`, 자이로는 `dps` 단위로 저장되며 학습 데이터의 통계로 채널별 정규화됩니다.

1. 우선 10~20개 단어와 `none`(수어가 아닌 평상시 움직임) 클래스로 작은 어휘를 정합니다.
2. 사람마다 장갑을 낀 뒤 손을 편 상태와 주먹 상태로 플렉스 센서 범위를 확인합니다. 센서 위치는 세션마다 동일하게 고정합니다.
3. 한 사람·한 날짜를 하나의 세션으로 잡고, 각 단어를 세션당 30~50회 수집합니다.
4. 동작 시작 전 중립 자세와 동작 종료 후 중립 자세가 2초 창 안에 들어가도록 수행합니다.
5. 빠르기, 손목 각도, 팔 방향을 조금씩 바꾸되 잘못 수행한 샘플은 즉시 삭제하고 다시 받습니다.
6. 최소 5명, 가능하면 10명 이상에게 받고 마지막 1~2명은 학습에 전혀 쓰지 않는 사용자 독립 테스트셋으로 둡니다.
7. 각 클래스의 샘플 수를 비슷하게 맞추고 `none`은 다른 클래스 합계에 가까울 만큼 다양하게 수집합니다.

수집 명령 예시:

```bash
cd jetson
python3 collect_data.py --label hello --person p01 --session p01_day1 --count 50 --port /dev/ttyUSB0
```

같은 사람이라도 날짜나 장갑을 다시 착용했다면 새 `session` 값을 사용합니다. 저장 파일에는 익명 참가자 ID, 세션, UTC 시각, 특징 이름이 함께 기록됩니다. 얼굴·이름 같은 개인정보는 저장하지 않는 것을 권장합니다. 각 동작 직후 `n`을 입력하면 잘못 수행한 샘플을 저장하지 않고 다시 수집합니다.

## 학습과 추론

데이터가 준비된 뒤 사용할 명령입니다. 현재 요청 범위에서는 실행하지 않았습니다.

```bash
cd jetson
python3 train.py --epochs 60 --device auto
python3 main.py --model ../models/sign_transformer.pt --port /dev/ttyUSB0
```

## 웹 데이터 수집기

`web/`은 Flask 기반 Web Serial 수집 사이트이며 Render에서 실행할 수 있습니다. Supabase SQL Editor에서 `supabase/schema.sql`을 먼저 실행하고, Render 환경 변수 `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `JETSON_API_TOKEN`을 설정합니다. 웹에서 장갑을 사용할 때 ESP32의 출력 모드는 `OUTPUT_JSON`이어야 합니다.

Jetson은 승인된 샘플만 다음과 같이 동기화합니다.

```bash
export GLOVE_API_URL=https://YOUR_RENDER_SERVICE.onrender.com
export JETSON_API_TOKEN=YOUR_RENDER_TOKEN
python3 sync_data.py
```

학습은 같은 세션의 샘플이 학습/검증 양쪽에 섞이지 않도록 세션 단위로 분리합니다. 체크포인트에는 라벨 순서와 학습 데이터의 정규화 통계도 함께 저장되어 추론 때 동일하게 적용됩니다.

## 중요한 한계와 다음 단계

- 한 손 장갑만으로는 양손 수어나 얼굴 표정·몸 방향이 의미를 바꾸는 수어를 완전히 인식할 수 없습니다. 첫 어휘는 한 손과 손목 움직임만으로 구별되는 표현으로 제한하세요.
- 연속 문장 인식은 단어별로 잘라 수집한 분류 문제와 다릅니다. 먼저 고립 수어 분류를 안정화한 뒤, 연속 스트림의 시작/끝 라벨링과 CTC 또는 구간 검출 모델을 추가하는 편이 안전합니다.
- Jetson Nano에서는 이 작은 모델로 시작하고, 정확도를 확인한 다음 ONNX/TensorRT 변환을 별도 단계로 진행하세요.
