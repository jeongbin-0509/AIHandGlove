import os
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO
from supabase import Client, create_client


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__, static_folder="public", static_url_path="")
socketio = SocketIO(app, cors_allowed_origins=[], async_mode="threading")

LABELS = ["안녕하세요", "감사합니다", "사랑해요", "미안합니다", "괜찮아요", "none"]
PARTICIPANT_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{2,40}$")
recent_predictions: deque[dict] = deque(maxlen=20)

supabase: Client | None = None
if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


@app.get("/api/health")
def health():
    return jsonify(ok=True, databaseConfigured=supabase is not None)


@app.get("/api/labels")
def get_labels():
    return jsonify(labels=LABELS)


@app.get("/api/sample-counts")
def sample_counts():
    if supabase is None:
        return jsonify(error="Supabase 환경 변수가 설정되지 않았습니다."), 503
    try:
        counts = {}
        for label in LABELS:
            result = (
                supabase.table("glove_samples")
                .select("id", count="exact")
                .eq("label", label)
                .limit(1)
                .execute()
            )
            counts[label] = result.count or 0
        return jsonify(counts=counts, total=sum(counts.values()))
    except Exception:
        app.logger.exception("Supabase sample count query failed")
        return jsonify(error="수어별 수집량을 가져오지 못했습니다."), 500


@app.get("/api/predictions/latest")
def latest_prediction():
    return jsonify(prediction=recent_predictions[-1] if recent_predictions else None)


@app.post("/api/predictions")
def publish_prediction():
    expected_token = os.environ.get("JETSON_API_TOKEN", "")
    supplied_token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not expected_token or supplied_token != expected_token:
        return jsonify(error="인증에 실패했습니다."), 401

    body = request.get_json(silent=True) or {}
    label = body.get("label")
    confidence = body.get("confidence")
    if not isinstance(label, str) or not label.strip() or not isinstance(confidence, (int, float)):
        return jsonify(error="추론 결과 형식이 올바르지 않습니다."), 400

    prediction = {
        "label": label.strip()[:80],
        "confidence": max(0.0, min(1.0, float(confidence))),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    recent_predictions.append(prediction)
    socketio.emit("prediction", prediction)
    return jsonify(ok=True), 202


@app.post("/api/samples")
def save_sample():
    if supabase is None:
        return jsonify(error="Supabase 환경 변수가 설정되지 않았습니다."), 503

    body = request.get_json(silent=True) or {}
    sequence = body.get("sequence")
    participant_id = body.get("participantId", "")

    valid_sequence = (
        isinstance(sequence, list)
        and len(sequence) == 40
        and all(
            isinstance(frame, list)
            and len(frame) == 11
            and all(isinstance(value, (int, float)) for value in frame)
            for frame in sequence
        )
    )

    if body.get("label") not in LABELS or not valid_sequence:
        return jsonify(error="라벨 또는 센서 시퀀스 형식이 올바르지 않습니다."), 400
    if not PARTICIPANT_PATTERN.fullmatch(participant_id):
        return jsonify(error="참가자 ID 형식이 올바르지 않습니다."), 400

    record = {
        "participant_id": participant_id,
        "session_id": str(body.get("sessionId", ""))[:80],
        "label": body["label"],
        "sample_rate_hz": 20,
        "sequence_length": 40,
        "feature_names": body.get("featureNames", []),
        "sequence": sequence,
        "firmware_version": str(body.get("firmwareVersion", "unknown"))[:40],
        "status": "pending",
    }

    try:
        result = supabase.table("glove_samples").insert(record).execute()
        return jsonify(id=result.data[0]["id"]), 201
    except Exception:
        app.logger.exception("Supabase sample insert failed")
        return jsonify(error="샘플 저장에 실패했습니다."), 500


@app.get("/api/training-data")
def training_data():
    if supabase is None:
        return jsonify(error="Supabase 환경 변수가 설정되지 않았습니다."), 503
    expected_token = os.environ.get("JETSON_API_TOKEN", "")
    supplied_token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not expected_token or supplied_token != expected_token:
        return jsonify(error="인증에 실패했습니다."), 401

    try:
        result = (
            supabase.table("glove_samples")
            .select("id,participant_id,session_id,label,feature_names,sequence,created_at")
            .eq("status", "approved")
            .order("created_at")
            .limit(5000)
            .execute()
        )
        return jsonify(samples=result.data)
    except Exception:
        app.logger.exception("Supabase training data query failed")
        return jsonify(error="학습 데이터 조회에 실패했습니다."), 500


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/demo")
def demo():
    return send_from_directory(app.static_folder, "demo.html")


@app.get("/<path:path>")
def static_or_index(path: str):
    requested = BASE_DIR / "public" / path
    if requested.is_file():
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")), debug=True)
