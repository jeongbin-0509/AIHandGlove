const predictionText = document.querySelector("#prediction");
const confidenceText = document.querySelector("#confidence");
const confidenceBar = document.querySelector("#confidenceBar");
const receivedAt = document.querySelector("#receivedAt");
const connection = document.querySelector("#connection");
const history = document.querySelector("#history");
const ttsToggle = document.querySelector("#ttsToggle");
const pulse = document.querySelector("#pulse");

let ttsEnabled = true;
const items = [];

function showPrediction(result, speak = true) {
  const percent = Math.round(result.confidence * 100);
  predictionText.textContent = result.label;
  confidenceText.textContent = `${percent}%`;
  confidenceBar.style.width = `${percent}%`;
  receivedAt.textContent = `${new Date(result.timestamp).toLocaleTimeString("ko-KR")} · Jetson Nano에서 인식`;
  pulse.classList.remove("animate");
  requestAnimationFrame(() => pulse.classList.add("animate"));

  items.unshift(result);
  if (items.length > 8) items.pop();
  history.innerHTML = items.map(item =>
    `<li><strong>${escapeHtml(item.label)}</strong><span>${Math.round(item.confidence * 100)}% · ${new Date(item.timestamp).toLocaleTimeString("ko-KR")}</span></li>`
  ).join("");

  if (speak && ttsEnabled && "speechSynthesis" in window) {
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(result.label);
    utterance.lang = "ko-KR";
    utterance.rate = 0.95;
    speechSynthesis.speak(utterance);
  }
}

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = value;
  return element.innerHTML;
}

ttsToggle.addEventListener("click", () => {
  ttsEnabled = !ttsEnabled;
  ttsToggle.classList.toggle("active", ttsEnabled);
  ttsToggle.textContent = ttsEnabled ? "🔊 자동 음성 켜짐" : "🔇 자동 음성 꺼짐";
  if (!ttsEnabled && "speechSynthesis" in window) speechSynthesis.cancel();
});

const socket = io({ transports: ["websocket", "polling"] });
socket.on("connect", () => { connection.textContent = "실시간 연결됨"; connection.classList.add("online"); });
socket.on("disconnect", () => { connection.textContent = "재연결 중"; connection.classList.remove("online"); });
socket.on("prediction", result => showPrediction(result, true));

fetch("/api/predictions/latest")
  .then(response => response.json())
  .then(({ prediction }) => { if (prediction) showPrediction(prediction, false); })
  .catch(() => {});
