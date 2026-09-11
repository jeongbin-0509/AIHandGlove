const promptText = document.querySelector("#prompt");
const feedback = document.querySelector("#feedback");
const recognition = document.querySelector("#recognition");
const confidenceBar = document.querySelector("#confidenceBar");
const scoreText = document.querySelector("#score");
const comboText = document.querySelector("#combo");
const timeText = document.querySelector("#time");
const startButton = document.querySelector("#startButton");
const connection = document.querySelector("#connection");
const gloveButton = document.querySelector("#gloveButton");
const adminButton = document.querySelector("#adminButton");
const adminDialog = document.querySelector("#adminDialog");
const adminForm = document.querySelector("#adminForm");
const adminCode = document.querySelector("#adminCode");
const adminMessage = document.querySelector("#adminMessage");
const closeAdmin = document.querySelector("#closeAdmin");

let labels = [];
let target = "";
let score = 0;
let combo = 0;
let seconds = 45;
let playing = false;
let accepting = false;
let timer;
let serialPort;
let serialReader;
let gloveConnected = false;
let sensorWindow = [];
let framesSinceInference = 0;
let inferencePending = false;

adminButton.addEventListener("click", async () => {
  const response = await fetch("/api/admin/status", { cache: "no-store" });
  const result = await response.json();
  if (result.authenticated) {
    location.href = "/collect";
    return;
  }
  adminMessage.textContent = "";
  adminDialog.showModal();
  adminCode.focus();
});

closeAdmin.addEventListener("click", () => adminDialog.close());
adminDialog.addEventListener("click", event => {
  if (event.target === adminDialog) adminDialog.close();
});

adminForm.addEventListener("submit", async event => {
  event.preventDefault();
  adminMessage.textContent = "확인 중…";
  const response = await fetch("/api/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: adminCode.value })
  });
  const result = await response.json();
  if (!response.ok) {
    adminMessage.textContent = result.error || "권한 확인에 실패했습니다.";
    adminCode.select();
    return;
  }
  location.href = result.redirect;
});

function parseSensorLine(line) {
  try {
    if (line.startsWith("{")) {
      const value = JSON.parse(line);
      const frame = [...value.flex, ...value.acc, ...value.gyro].map(Number);
      return frame.length === 11 && frame.every(Number.isFinite) ? frame : null;
    }
    const entries = Object.fromEntries(line.split(/\s+/).map(item => item.split(":")));
    const keys = ["thumb", "index", "middle", "ring", "little", "accX", "accY", "accZ", "gyroX", "gyroY", "gyroZ"];
    const frame = keys.map(key => Number(entries[key]));
    return frame.every(Number.isFinite) ? frame : null;
  } catch {
    return null;
  }
}

async function readGlove() {
  const decoder = new TextDecoderStream();
  serialPort.readable.pipeTo(decoder.writable).catch(() => {});
  serialReader = decoder.readable.getReader();
  let buffer = "";
  try {
    while (gloveConnected) {
      const { value, done } = await serialReader.read();
      if (done) break;
      buffer += value;
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        const frame = parseSensorLine(line.trim());
        if (!frame) continue;
        sensorWindow.push(frame);
        if (sensorWindow.length > 40) sensorWindow.shift();
        framesSinceInference += 1;
        if (sensorWindow.length === 40 && framesSinceInference >= 4 && !inferencePending) {
          framesSinceInference = 0;
          sendForInference([...sensorWindow]);
        }
      }
    }
  } finally {
    serialReader?.releaseLock();
  }
}

async function sendForInference(sequence) {
  inferencePending = true;
  try {
    const response = await fetch("/api/local-inference", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sequence })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
  } catch (error) {
    recognition.textContent = error.message || "로컬 추론 연결 실패";
  } finally {
    inferencePending = false;
  }
}

gloveButton.addEventListener("click", async () => {
  if (!("serial" in navigator)) {
    feedback.textContent = "Chrome 또는 Edge에서 로컬 주소를 열어주세요.";
    return;
  }
  try {
    serialPort = await navigator.serial.requestPort();
    await serialPort.open({ baudRate: 115200 });
    gloveConnected = true;
    gloveButton.textContent = "장갑 연결됨";
    gloveButton.disabled = true;
    startButton.disabled = false;
    feedback.textContent = "장갑 연결 완료 · 게임을 시작하세요.";
    readGlove();
  } catch (error) {
    feedback.textContent = `장갑 연결 실패: ${error.message}`;
  }
});

function chooseNext() {
  const choices = labels.filter(label => label !== target);
  target = choices[Math.floor(Math.random() * choices.length)];
  promptText.textContent = target;
  feedback.textContent = "수어를 보여주세요!";
  feedback.className = "feedback";
  recognition.textContent = "Jetson 인식 대기 중";
  confidenceBar.style.width = "0%";
  accepting = true;
}

function startGame() {
  if (labels.length < 2) {
    feedback.textContent = "게임용 수어 목록을 불러오지 못했습니다.";
    return;
  }
  clearInterval(timer);
  score = 0;
  combo = 0;
  seconds = 45;
  playing = true;
  scoreText.textContent = score;
  comboText.textContent = combo;
  timeText.textContent = seconds;
  startButton.textContent = "다시 시작";
  chooseNext();
  timer = setInterval(() => {
    seconds -= 1;
    timeText.textContent = seconds;
    if (seconds <= 0) finishGame();
  }, 1000);
}

function finishGame() {
  clearInterval(timer);
  playing = false;
  accepting = false;
  promptText.textContent = `${score}점`;
  feedback.textContent = `게임 종료 · 최고 콤보 ${combo}회`;
  feedback.className = "feedback correct";
  recognition.textContent = "다시 시작해서 기록에 도전하세요.";
  startButton.textContent = "한 번 더 하기";
}

function handlePrediction(result) {
  const percent = Math.round(result.confidence * 100);
  recognition.textContent = `인식: ${result.label} · ${percent}%`;
  confidenceBar.style.width = `${percent}%`;
  if (!playing || !accepting || result.confidence < 0.7) return;

  if (result.label === target) {
    accepting = false;
    combo += 1;
    score += 100 + Math.min(combo - 1, 10) * 10;
    scoreText.textContent = score;
    comboText.textContent = combo;
    feedback.textContent = `정답! +${100 + Math.min(combo - 1, 10) * 10}점`;
    feedback.className = "feedback correct";
    setTimeout(() => { if (playing) chooseNext(); }, 750);
  } else {
    combo = 0;
    comboText.textContent = combo;
    feedback.textContent = `${result.label}(으)로 인식했어요. 다시 해보세요.`;
    feedback.className = "feedback wrong";
  }
}

startButton.addEventListener("click", startGame);

fetch("/api/sample-counts", { cache: "no-store" })
  .then(response => response.json())
  .then(result => {
    labels = Object.entries(result.counts)
      .filter(([label, count]) => label !== "none" && count >= 20)
      .map(([label]) => label);
  })
  .catch(() => { feedback.textContent = "수어 목록을 불러오지 못했습니다."; });

const socket = io({ transports: ["websocket", "polling"] });
socket.on("connect", () => {
  connection.textContent = location.hostname === "127.0.0.1" || location.hostname === "localhost" ? "로컬 AI 준비" : "게임 서버 연결됨";
  connection.classList.add("online");
});
socket.on("disconnect", () => {
  connection.textContent = "서버 재연결 중";
  connection.classList.remove("online");
});
socket.on("prediction", handlePrediction);
