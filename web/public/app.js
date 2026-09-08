const FEATURES = ["flex_thumb", "flex_index", "flex_middle", "flex_ring", "flex_little", "acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z"];
const connectButton = document.querySelector("#connectButton");
const recordButton = document.querySelector("#recordButton");
const form = document.querySelector("#captureForm");
const labelSelect = document.querySelector("#labelSelect");
const participantId = document.querySelector("#participantId");
const message = document.querySelector("#message");
const countdown = document.querySelector("#countdown");
const sampleCount = document.querySelector("#sampleCount");
const badge = document.querySelector("#deviceBadge");
const frameRate = document.querySelector("#frameRate");
const canvas = document.querySelector("#signalCanvas");
const ctx = canvas.getContext("2d");

let port;
let reader;
let connected = false;
let recording = false;
let capture = [];
let saved = 0;
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
  if (!connected || recording) return;
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
  countdown.textContent = "저장 중";

  try {
    const response = await fetch("/api/samples", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        participantId: participantId.value,
        sessionId,
        label: labelSelect.value,
        featureNames: FEATURES,
        sequence: capture,
        firmwareVersion: "0.1.0"
      })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    saved += 1;
    sampleCount.textContent = saved;
    countdown.textContent = "완료";
    message.textContent = `${labelSelect.value} 샘플이 저장됐습니다. 잠시 쉬고 다시 반복하세요.`;
  } catch (error) {
    countdown.textContent = "실패";
    message.textContent = error.message;
  } finally { recordButton.disabled = !connected; }
});

function addGraphPoint(frame) {
  const flex = frame.slice(0, 5).reduce((a, b) => a + b, 0) / 5 / 4095;
  const motion = Math.min(1, Math.hypot(...frame.slice(8, 11)) / 300);
  graph.push([flex, motion]);
  if (graph.length > 120) graph.shift();
  drawGraph();
}

function drawGraph() {
  const dpr = devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (canvas.width !== width * dpr) { canvas.width = width * dpr; canvas.height = height * dpr; }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  [[0, "#5bd7ff"], [1, "#ffad66"]].forEach(([channel, color]) => {
    ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 2;
    graph.forEach((point, index) => {
      const x = index / 119 * width;
      const y = height - point[channel] * (height - 24) - 12;
      index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.stroke();
  });
}

setInterval(() => { frameRate.textContent = `${framesThisSecond} Hz`; framesThisSecond = 0; }, 1000);
document.querySelector("#supportNotice").textContent = "serial" in navigator ? "Chrome · Edge · 115200 baud" : "Chrome 또는 Edge가 필요합니다.";
loadLabels().catch(() => { message.textContent = "서버에서 수어 목록을 가져오지 못했습니다."; });

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
