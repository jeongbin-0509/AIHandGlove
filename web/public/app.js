const FEATURES = ["flex_thumb", "flex_index", "flex_middle", "flex_ring", "flex_little", "acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z"];
const connectButton = document.querySelector("#connectButton");
const recordButton = document.querySelector("#recordButton");
const form = document.querySelector("#captureForm");
const labelSelect = document.querySelector("#labelSelect");
const participantId = document.querySelector("#participantId");
const message = document.querySelector("#message");
const countdown = document.querySelector("#countdown");
const sampleCount = document.querySelector("#sampleCount");
const uploadCount = document.querySelector("#uploadCount");
const uploadStatus = document.querySelector("#uploadStatus");
const badge = document.querySelector("#deviceBadge");
const frameRate = document.querySelector("#frameRate");
const reviewActions = document.querySelector("#reviewActions");
const saveButton = document.querySelector("#saveButton");
const discardButton = document.querySelector("#discardButton");
const chartGroups = [
  { canvas: document.querySelector("#flexCanvas"), legend: document.querySelector("#flexLegend"), indexes: [0, 1, 2, 3, 4], labels: ["엄지", "검지", "중지", "약지", "소지"], colors: ["#69f5bd", "#5bd7ff", "#a98bff", "#ff7eb6", "#ffd166"], fixedRange: [0, 4095], digits: 0 },
  { canvas: document.querySelector("#accCanvas"), legend: document.querySelector("#accLegend"), indexes: [5, 6, 7], labels: ["X", "Y", "Z"], colors: ["#5bd7ff", "#ffad66", "#ff6b6b"], digits: 1 },
  { canvas: document.querySelector("#gyroCanvas"), legend: document.querySelector("#gyroLegend"), indexes: [8, 9, 10], labels: ["X", "Y", "Z"], colors: ["#5bd7ff", "#ffad66", "#ff6b6b"], digits: 1 }
];

let port;
let reader;
let connected = false;
let recording = false;
let capture = [];
let pendingSample = null;
let saved = 0;
let uploading = false;
const UPLOAD_QUEUE_KEY = "aihandglove_upload_queue_v1";
let uploadQueue = loadUploadQueue();
let framesThisSecond = 0;
const graph = [];
const sessionId = `web_${new Date().toISOString().replace(/[:.]/g, "-")}`;

async function loadLabels() {
  const response = await fetch("/api/labels");
  const { labels } = await response.json();
  labelSelect.innerHTML = labels.map(label => `<option value="${label}">${label}</option>`).join("");
}

function parseSensorLine(line) {
  if (line.startsWith("{")) {
    try {
      const value = JSON.parse(line);
      const frame = [...value.flex, ...value.acc, ...value.gyro].map(Number);
      return frame.length === 11 && frame.every(Number.isFinite) ? frame : null;
    } catch { return null; }
  }

  const entries = Object.fromEntries(
    line.split(/\s+/).map(item => item.split(":"))
  );
  const plotterKeys = ["thumb", "index", "middle", "ring", "little", "accX", "accY", "accZ", "gyroX", "gyroY", "gyroZ"];
  const frame = plotterKeys.map(key => Number(entries[key]));
  return frame.length === 11 && frame.every(Number.isFinite) ? frame : null;
}

async function readSerial() {
  const decoder = new TextDecoderStream();
  port.readable.pipeTo(decoder.writable).catch(() => {});
  reader = decoder.readable.getReader();
  let buffer = "";
  try {
    while (connected) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        const frame = parseSensorLine(line.trim());
        if (!frame) continue;
        framesThisSecond += 1;
        addGraphPoint(frame);
        if (recording && capture.length < 40) capture.push(frame);
      }
    }
  } finally { reader?.releaseLock(); }
}

connectButton.addEventListener("click", async () => {
  if (!("serial" in navigator)) {
    message.textContent = "이 브라우저는 Web Serial을 지원하지 않습니다. Chrome 또는 Edge를 사용해 주세요.";
    return;
  }
  try {
    port = await navigator.serial.requestPort();
    await port.open({ baudRate: 115200 });
    connected = true;
    badge.textContent = "장갑 연결됨";
    badge.classList.add("connected");
    connectButton.textContent = "장갑 연결 완료";
    connectButton.disabled = true;
    recordButton.disabled = false;
    message.textContent = "수어를 선택하고 동작 기록을 시작하세요.";
    readSerial();
    setTimeout(() => {
      if (connected && graph.length === 0) {
        message.textContent = "센서값이 없습니다. ESP32 연결과 115200 baud 출력을 확인해 주세요.";
      }
    }, 3000);
  } catch (error) {
    message.textContent = `연결하지 못했습니다: ${error.message}`;
  }
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (!connected || recording || pendingSample) return;
  recordButton.disabled = true;
  for (let number = 3; number > 0; number -= 1) {
    countdown.textContent = number;
    await new Promise(resolve => setTimeout(resolve, 700));
  }
  countdown.textContent = "동작!";
  capture = [];
  recording = true;
  while (capture.length < 40 && connected) await new Promise(resolve => setTimeout(resolve, 20));
  recording = false;
  if (capture.length !== 40) {
    countdown.textContent = "중단됨";
    recordButton.disabled = !connected;
    message.textContent = "40프레임을 채우지 못했습니다. 연결을 확인하고 다시 기록해 주세요.";
    return;
  }

  pendingSample = {
    participantId: participantId.value,
    sessionId,
    label: labelSelect.value,
    featureNames: FEATURES,
    sequence: capture.map(frame => [...frame]),
    firmwareVersion: "0.1.0"
  };
  countdown.textContent = "확인";
  reviewActions.hidden = false;
  message.textContent = `${pendingSample.label} 데이터 40프레임을 수집했습니다. 저장하거나 버리기를 선택하세요.`;
});

saveButton.addEventListener("click", () => {
  if (!pendingSample) return;
  const queuedLabel = pendingSample.label;
  uploadQueue.push(pendingSample);
  persistUploadQueue();
  clearPendingSample();
  countdown.textContent = "준비";
  message.textContent = `${queuedLabel} 데이터를 전송 대기열에 넣었습니다. 바로 다음 동작을 기록할 수 있습니다.`;
  updateUploadStatus();
  flushUploadQueue();
});

function loadUploadQueue() {
  try {
    const value = JSON.parse(localStorage.getItem(UPLOAD_QUEUE_KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function persistUploadQueue() {
  localStorage.setItem(UPLOAD_QUEUE_KEY, JSON.stringify(uploadQueue));
}

function updateUploadStatus(failed = false) {
  uploadCount.textContent = uploadQueue.length;
  uploadStatus.textContent = failed ? "연결 복구 후 재시도" : uploadQueue.length ? "백그라운드 전송 중" : "전송 완료";
}

async function flushUploadQueue() {
  if (uploading || uploadQueue.length === 0) return;
  uploading = true;
  let retryDelay = 100;

  try {
    while (uploadQueue.length > 0) {
      const response = await fetch("/api/samples", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(uploadQueue[0])
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "서버 전송 실패");
      uploadQueue.shift();
      persistUploadQueue();
      saved += 1;
      sampleCount.textContent = saved;
      updateUploadStatus();
    }
  } catch (error) {
    updateUploadStatus(true);
    if (!recording && !pendingSample) message.textContent = `전송이 지연되고 있습니다: ${error.message}`;
    retryDelay = 5000;
  } finally {
    uploading = false;
    if (uploadQueue.length > 0) setTimeout(flushUploadQueue, retryDelay);
  }
}

discardButton.addEventListener("click", () => {
  if (!pendingSample) return;
  clearPendingSample();
  countdown.textContent = "준비";
  message.textContent = "방금 수집한 데이터는 DB에 저장하지 않고 버렸습니다. 다시 기록할 수 있습니다.";
});

function clearPendingSample() {
  pendingSample = null;
  capture = [];
  reviewActions.hidden = true;
  saveButton.disabled = false;
  discardButton.disabled = false;
  recordButton.disabled = !connected;
}

function addGraphPoint(frame) {
  graph.push(frame);
  if (graph.length > 120) graph.shift();
  updateLegends(frame);
  drawGraph();
}

function updateLegends(frame) {
  chartGroups.forEach(group => {
    group.legend.innerHTML = group.indexes.map((frameIndex, index) =>
      `<span><i style="background:${group.colors[index]}"></i>${group.labels[index]} <b>${frame[frameIndex].toFixed(group.digits)}</b></span>`
    ).join("");
  });
}

function drawGraph() {
  chartGroups.forEach(group => {
    const { canvas } = group;
    const ctx = canvas.getContext("2d");
    const dpr = devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = width * dpr;
      canvas.height = height * dpr;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const values = graph.flatMap(point => group.indexes.map(index => point[index]));
    let min = group.fixedRange?.[0] ?? Math.min(...values, 0);
    let max = group.fixedRange?.[1] ?? Math.max(...values, 1);
    if (!group.fixedRange) {
      const padding = Math.max((max - min) * 0.12, 1);
      min -= padding;
      max += padding;
    }

    group.indexes.forEach((frameIndex, channelIndex) => {
      ctx.beginPath();
      ctx.strokeStyle = group.colors[channelIndex];
      ctx.lineWidth = 1.8;
      graph.forEach((point, index) => {
        const x = graph.length < 2 ? 0 : index / (graph.length - 1) * width;
        const ratio = (point[frameIndex] - min) / Math.max(max - min, 1);
        const y = height - Math.max(0, Math.min(1, ratio)) * (height - 20) - 10;
        index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      });
      ctx.stroke();
    });
  });
}

function initializeLegends() {
  chartGroups.forEach(group => {
    group.legend.innerHTML = group.labels.map((label, index) =>
      `<span><i style="background:${group.colors[index]}"></i>${label} <b>--</b></span>`
    ).join("");
  });
}

setInterval(() => { frameRate.textContent = `${framesThisSecond} Hz`; framesThisSecond = 0; }, 1000);
document.querySelector("#supportNotice").textContent = "serial" in navigator ? "Chrome · Edge · 115200 baud" : "Chrome 또는 Edge가 필요합니다.";
loadLabels().catch(() => { message.textContent = "서버에서 수어 목록을 가져오지 못했습니다."; });
initializeLegends();
updateUploadStatus();
flushUploadQueue();

if (document.modelContext?.registerTool) {
  document.modelContext.registerTool({
    name: "configure_glove_collection",
    title: "수어 수집 설정",
    description: "화면에서 수집할 수어와 익명 참가자 ID를 설정합니다.",
    inputSchema: {
      type: "object",
      properties: {
        label: { type: "string" },
        participantId: { type: "string", pattern: "^[a-zA-Z0-9_-]{2,40}$" }
      },
      required: ["label", "participantId"],
      additionalProperties: false
    },
    annotations: { readOnlyHint: false, untrustedContentHint: false },
    execute({ label, participantId: requestedParticipantId }) {
      const option = [...labelSelect.options].find(item => item.value === label);
      if (!option) throw new Error("지원하지 않는 수어 라벨입니다.");
      if (!/^[a-zA-Z0-9_-]{2,40}$/.test(requestedParticipantId)) {
        throw new Error("참가자 ID 형식이 올바르지 않습니다.");
      }
      labelSelect.value = label;
      participantId.value = requestedParticipantId;
      message.textContent = `${label} 수집 준비가 완료됐습니다.`;
      return { label, participantId: requestedParticipantId, status: "configured" };
    }
  });
}
