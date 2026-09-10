const promptText = document.querySelector("#prompt");
const feedback = document.querySelector("#feedback");
const recognition = document.querySelector("#recognition");
const confidenceBar = document.querySelector("#confidenceBar");
const scoreText = document.querySelector("#score");
const comboText = document.querySelector("#combo");
const timeText = document.querySelector("#time");
const startButton = document.querySelector("#startButton");
const connection = document.querySelector("#connection");

let labels = [];
let target = "";
let score = 0;
let combo = 0;
let seconds = 45;
let playing = false;
let accepting = false;
let timer;

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
  connection.textContent = "게임 서버 연결됨";
  connection.classList.add("online");
});
socket.on("disconnect", () => {
  connection.textContent = "서버 재연결 중";
  connection.classList.remove("online");
});
socket.on("prediction", handlePrediction);
