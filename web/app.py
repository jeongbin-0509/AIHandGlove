import os
import re
import hashlib
import secrets
import sys
from threading import Lock
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, send_from_directory, session, url_for
from flask_socketio import SocketIO
from supabase import Client, create_client


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__, static_folder="public", static_url_path="")
app.secret_key = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RENDER") == "true",
)
socketio = SocketIO(app, cors_allowed_origins=[], async_mode="threading")

LABELS = ["안녕하세요", "감사합니다", "사랑해요", "미안합니다", "괜찮아요", "none"]
PARTICIPANT_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{2,40}$")
recent_predictions: deque[dict] = deque(maxlen=20)
JETSON_TOKEN_SHA256 = "3aec97c7a25acaceefb3f9b5d7a6c1f75259a32cecc187a37cba77aaf45f619b"
local_predictor = None
local_predictor_lock = Lock()

supabase: Client | None = None
if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def jetson_is_authorized() -> bool:
    supplied_token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    expected_token = os.environ.get("JETSON_API_TOKEN", "")
    plain_match = bool(expected_token) and secrets.compare_digest(supplied_token, expected_token)
    supplied_hash = hashlib.sha256(supplied_token.encode()).hexdigest()
    hash_match = bool(supplied_token) and secrets.compare_digest(supplied_hash, JETSON_TOKEN_SHA256)
    return plain_match or hash_match


def admin_is_authorized() -> bool:
    return session.get("admin") is True


def get_local_predictor():
    global local_predictor
    if local_predictor is not None:
        return local_predictor
    model_path = BASE_DIR.parent / "models" / "sign_transformer.pt"
    if not model_path.exists():
        raise RuntimeError("로컬 학습 모델을 찾지 못했습니다.")
    jetson_dir = BASE_DIR.parent / "jetson"
    if str(jetson_dir) not in sys.path:
        sys.path.insert(0, str(jetson_dir))
    from inference import SignPredictor
    local_predictor = SignPredictor(model_path, "auto")
    return local_predictor


@app.get("/api/health")
def health():
    return jsonify(ok=True, databaseConfigured=supabase is not None)


@app.get("/api/admin/status")
def admin_status():
    return jsonify(authenticated=admin_is_authorized())


@app.post("/api/admin/login")
def admin_login():
    expected_code = os.environ.get("ADMIN_CODE", "")
    supplied_code = str((request.get_json(silent=True) or {}).get("code", ""))
    if not expected_code:
        return jsonify(error="서버에 ADMIN_CODE가 설정되지 않았습니다."), 503
    if not secrets.compare_digest(supplied_code, expected_code):
        return jsonify(error="관리자 코드가 올바르지 않습니다."), 401
    session.clear()
    session["admin"] = True
    return jsonify(ok=True, redirect=url_for("collect"))


@app.post("/api/admin/logout")
def admin_logout():
    session.clear()
    return jsonify(ok=True)


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
    if not jetson_is_authorized():
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


@app.post("/api/local-inference")
def local_inference():
    if request.remote_addr not in {"127.0.0.1", "::1"}:
        return jsonify(error="로컬 컴퓨터에서만 사용할 수 있습니다."), 403
    body = request.get_json(silent=True) or {}
    sequence = body.get("sequence")
    if not (
        isinstance(sequence, list)
        and len(sequence) == 40
        and all(isinstance(frame, list) and len(frame) == 11 for frame in sequence)
    ):
        return jsonify(error="40×11 센서 데이터가 필요합니다."), 400
    try:
        import numpy as np
        with local_predictor_lock:
            label, confidence, _ = get_local_predictor().predict(np.asarray(sequence, dtype=np.float32))
        prediction = {
            "label": label,
            "confidence": confidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        recent_predictions.append(prediction)
        socketio.emit("prediction", prediction)
        return jsonify(prediction=prediction)
    except Exception:
        app.logger.exception("Local inference failed")
        return jsonify(error="로컬 AI 추론에 실패했습니다."), 500


@app.post("/api/samples")
def save_sample():
    if not admin_is_authorized():
        return jsonify(error="관리자 로그인이 필요합니다."), 401
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
    if not jetson_is_authorized():
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
    return send_from_directory(app.static_folder, "game.html")


@app.get("/collect")
def collect():
    if not admin_is_authorized():
        return redirect(url_for("index"))
    return send_from_directory(app.static_folder, "index.html")


@app.get("/index.html")
def protected_index_file():
    return redirect(url_for("collect"))


@app.get("/demo")
def demo():
    return send_from_directory(app.static_folder, "demo.html")


@app.get("/game")
def game():
    return send_from_directory(app.static_folder, "game.html")


@app.get("/<path:path>")
def static_or_index(path: str):
    requested = BASE_DIR / "public" / path
    if requested.is_file():
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "game.html")


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "3000")), debug=True)
