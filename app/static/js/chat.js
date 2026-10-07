/*
 * 채팅 화면 (EE-12) — /chat
 *
 * 1. 질문을 보내면, 첫 질문일 때 POST /api/conversations 로 대화를 만들고 그 id 를 이 화면이 들고 있다가
 *    이어지는 질문에 쓴다. 같은 대화로 보내야 서버가 앞의 질문·답변을 문맥으로 쓴다.
 * 2. POST /api/chat 에 { conversation_id, question, level, client_request_id } 를 보낸다 (API 명세 3장).
 *    client_request_id 는 요청마다 새로 만드는 UUID — 같은 요청이 두 번 가도 서버가 AI 를 두 번 부르지 않는다.
 * 3. 답을 기다리는 동안 보내기 버튼을 잠근다 (중복 전송 방지).
 * 4. 질문·답변은 textContent 로만 넣는다 — 답변에 <script> 가 섞여 와도 글자로만 보인다.
 * 5. 시각은 API 의 UTC(…Z)를 한국 시간(KST)으로 바꿔 보여 준다.
 * 6. 실패하면 서버가 보낸 error.message 를 오류 칸에 보여 주고, 입력한 질문은 지우지 않는다.
 *
 * 수준 값(easy·beginner·advanced)과 이름은 이 파일에 적지 않고 HTML 의 라디오 버튼에서 읽는다 —
 * app/web/router.py 의 CHAT_INPUT_RULES 한곳에서 정한다.
 * CSRF 토큰을 붙여 POST 하는 apiPost 는 api.js (로그아웃 버튼과 같이 쓴다).
 */

import { UNKNOWN_ERROR_MESSAGE, apiPost, failureMessage } from "/static/js/api.js";

const form = document.getElementById("chat-form");
const questionInput = document.getElementById("question");
const sendButton = form.querySelector('button[type="submit"]');
const sendLabel = sendButton.textContent;
const countText = document.getElementById("question-count");
const thread = document.getElementById("thread");
const emptyState = document.getElementById("chat-empty");
const errorBox = document.getElementById("chat-error");
const errorText = document.getElementById("chat-error-text");
const followUps = document.getElementById("follow-ups");
const followUpButtons = followUps.querySelectorAll("button[data-question]");

let conversationId = null; // 첫 질문 때 POST /api/conversations 로 받는다. 새로고침하면 새 대화로 시작한다
let waiting = false; // 답을 기다리는 중인지

/* ── 서버에 보내기 ── */

// 요청마다 새 UUID(v4). crypto.randomUUID 는 HTTPS·localhost 에서만 있어서, 없으면 같은 형식을 직접 만든다
function newRequestId() {
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // 버전 4 (무작위로 만든 UUID)
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // 변형 10xx (RFC 9562 형식)
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

// 서버가 실패를 알려 왔거나 서버에 닿지 못했을 때 던진다. message 는 화면에 보여 줄 문구
class RequestFailed extends Error {}

// 첫 질문이면 대화를 먼저 만들고, 질문을 보내 완료된 턴(명세 3장의 성공 응답)을 돌려준다
async function askServer(question, level) {
  if (conversationId === null) {
    const created = await apiPost("/api/conversations", {});
    if (!created.ok || !created.data?.id) {
      throw new RequestFailed(failureMessage(created));
    }
    conversationId = created.data.id;
  }
  const result = await apiPost("/api/chat", {
    conversation_id: conversationId,
    question,
    level,
    client_request_id: newRequestId(), // 요청마다 새로 만든다. 실패한 질문을 다시 보낼 때도 새 값
  });
  // 성공 응답: { request_id, turn_id, conversation_id, level, question, answer, status, created_at }
  if (!result.ok || result.data?.status !== "completed" || typeof result.data.answer !== "string") {
    throw new RequestFailed(failureMessage(result));
  }
  return result.data;
}

/* ── 화면에 그리기 ── */

// 오류 칸에 안내 문구를 글자로 넣어 보여 준다. role="alert" 라서 나타나는 순간 스크린리더가 읽는다
function showError(message) {
  errorText.textContent = message;
  errorBox.hidden = false;
}

function clearError() {
  errorBox.hidden = true;
  errorText.textContent = ""; // 입력칸의 aria-describedby 가 지난 오류를 읽지 않게 비운다
}

// 글자 수 안내 "0 / 2000". 최대 글자 수는 입력칸의 maxlength 에서 읽는다
function updateCount() {
  countText.textContent = `${questionInput.value.length} / ${questionInput.maxLength}`;
}

// 스크린리더에만 읽히는 말머리 ("내 질문", "답변")
function speaker(text) {
  const label = document.createElement("span");
  label.className = "visually-hidden";
  label.textContent = text;
  return label;
}

// 말풍선. 글은 textContent 로만 넣는다 — innerHTML 이면 글 속의 <script>·<img onerror> 가 실행될 수 있다
function createBubble(text) {
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  return bubble;
}

// 내 질문: 오른쪽 말풍선 + 아래 줄에 고른 수준
function addQuestion(text, levelLabel) {
  const meta = document.createElement("p");
  meta.className = "msg-meta";
  meta.textContent = levelLabel;
  const item = document.createElement("li");
  item.className = "msg msg-me";
  item.append(speaker("내 질문"), createBubble(text), meta);
  thread.append(item);
  emptyState.hidden = true;
  form.scrollIntoView({ block: "nearest" }); // 방금 보낸 질문과 입력 상자가 보이게
  return item;
}

// 답변: 전구 캐릭터 + 왼쪽 말풍선
function addAnswer(text) {
  const mascot = document.createElement("img");
  mascot.className = "msg-mascot";
  mascot.src = "/static/img/mascot.svg";
  mascot.alt = ""; // 꾸밈 그림이라 스크린리더가 읽지 않는다
  mascot.width = 38;
  mascot.height = 38;
  const item = document.createElement("li");
  item.className = "msg msg-ai";
  item.append(speaker("답변"), mascot, createBubble(text));
  thread.append(item);
  // 답이 화면보다 길면 답의 첫 줄부터, 짧으면 아래 입력 상자까지 보이게 스크롤한다
  if (item.offsetHeight > window.innerHeight * 0.6) {
    item.scrollIntoView({ block: "start" });
  } else {
    form.scrollIntoView({ block: "nearest" });
  }
  return item;
}

// API 시각은 UTC(예: 2026-10-02T07:00:00Z). 화면에는 한국 시간으로 바꿔 보여 준다 (DB·API 는 UTC 그대로)
function formatKst(t) {
  return new Date(t).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
}

// 질문 말풍선 아래, 수준 옆에 턴 시각을 붙인다: <time datetime="원래 UTC">한국 시간</time>
// 응답에는 턴 시각(created_at — 서버가 질문을 받은 때) 하나뿐이라 질문 쪽에 한 번 보여 준다
function addTurnTime(questionItem, createdAt) {
  if (!createdAt || Number.isNaN(Date.parse(createdAt))) return; // 시각이 없거나 읽을 수 없으면 수준만 둔다
  const time = document.createElement("time");
  time.dateTime = createdAt;
  time.textContent = formatKst(createdAt);
  questionItem.querySelector(".msg-meta").append(" · ", time);
}

// 지금 고른 수준. value 는 API 로 보내는 값, label 은 말풍선 아래에 쓰는 이름 (라디오 버튼의 data-label)
function selectedLevel() {
  const radio = document.querySelector('input[name="level"]:checked');
  return { value: radio.value, label: radio.dataset.label };
}

// 답을 기다리는 동안 보내기·후속 버튼을 잠그고 보내기 버튼은 "기다리는 중…" 으로 바꾼다. 입력칸은 읽기
// 전용으로 두어서, 보낸 질문이 그대로 남아 있다가 답을 받으면 비운다 (실패하면 그대로 남아 다시 보낼 수 있다)
function setWaiting(on) {
  waiting = on;
  sendButton.disabled = on;
  sendButton.textContent = on ? sendButton.dataset.busyLabel : sendLabel;
  questionInput.readOnly = on;
  for (const button of followUpButtons) {
    button.disabled = on;
  }
}

/* ── 질문 보내기 ── */

// 질문 하나를 보내고 답을 받아 붙인다. fromInput: 입력칸의 질문이면 답을 받은 뒤 입력칸을 비운다
async function sendQuestion(question, { fromInput }) {
  if (waiting) return; // 이미 기다리는 중이면 무시한다 (Enter·클릭 연타)
  clearError();
  const level = selectedLevel();
  // 잠그는 버튼에 포커스가 있었으면 브라우저가 포커스를 뺀다. 잠금을 푼 뒤 그 자리로 돌려준다
  const focusedBefore = document.activeElement;
  setWaiting(true);
  const questionItem = addQuestion(question, level.label);
  try {
    const turn = await askServer(question, level.value);
    addTurnTime(questionItem, turn.created_at);
    addAnswer(turn.answer);
    followUps.hidden = false; // 답이 있어야 "더 쉽게" 같은 후속 질문이 뜻이 있다
    if (fromInput) {
      questionInput.value = "";
      updateCount();
    }
  } catch (error) {
    // 답을 받지 못한 질문은 대화에서 뺀다 — 화면의 대화를 서버가 문맥으로 쓰는 완료된 턴과 맞춘다.
    // 입력칸의 질문은 지우지 않았으니 그대로 다시 보낼 수 있다 (보낼 때마다 새 client_request_id)
    questionItem.remove();
    emptyState.hidden = thread.children.length > 0;
    showError(error instanceof RequestFailed ? error.message : UNKNOWN_ERROR_MESSAGE);
  } finally {
    setWaiting(false);
    if (document.activeElement === document.body && focusedBefore?.isConnected) {
      focusedBefore.focus({ preventScroll: true });
    }
  }
}

// 보내기 전 검사: 앞뒤 공백을 뺀 질문이 1~최대 글자인지. 문제가 있으면 안내 문구, 없으면 ""
function findQuestionProblem(question) {
  if (question === "") return "질문을 입력해 주세요.";
  if (question.length > questionInput.maxLength) {
    return `질문은 ${questionInput.maxLength}자 이하로 입력해 주세요.`;
  }
  return "";
}

form.addEventListener("submit", (event) => {
  event.preventDefault(); // 브라우저 기본 전송(페이지 이동)을 막는다 → 입력한 글이 그대로 남는다
  if (waiting) return;
  clearError();
  const question = questionInput.value.trim(); // 앞뒤 공백은 빼고 보낸다 (서버도 같은 기준으로 다시 본다)
  const problem = findQuestionProblem(question);
  if (problem) {
    showError(problem); // 서버에 보내지 않는다. 입력한 글은 그대로 둔다
    questionInput.focus(); // 고칠 곳으로 포커스 (Enter 로 보냈으면 이미 여기)
    return;
  }
  sendQuestion(question, { fromInput: true });
});

// Enter 는 보내기, Shift+Enter 는 줄바꿈. 한글을 조합하는 중의 Enter 는 글자를 확정하는 것이라 보내지 않는다
// (Safari 는 조합을 끝내는 Enter 에 isComposing 대신 keyCode 229 를 준다)
questionInput.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  form.requestSubmit();
});

questionInput.addEventListener("input", updateCount);

// 후속 버튼: 같은 대화에 버튼 문구("더 쉽게" 등)를 그대로 질문으로 보낸다. 수준은 지금 고른 것,
// client_request_id 는 새로. 입력칸에 쓰던 글은 건드리지 않는다
for (const button of followUpButtons) {
  button.addEventListener("click", () => {
    sendQuestion(button.dataset.question, { fromInput: false });
  });
}

// 붙여 넣기: 브라우저는 maxlength 를 넘는 뒷부분을 말없이 잘라 넣는다. 질문이 잘린 채 보내지지 않게,
// 붙여 넣은 뒤의 길이가 최대를 넘으면 넣지 않고 안내한다 (가입·로그인 칸과 같은 방식)
questionInput.addEventListener("paste", (event) => {
  if (waiting) return; // 읽기 전용이라 어차피 들어가지 않는다
  const pasted = (event.clipboardData?.getData("text") ?? "").replace(/\r\n?/g, "\n"); // 줄바꿈은 한 글자
  const replaced = questionInput.selectionEnd - questionInput.selectionStart; // 고른 글은 붙여 넣는 글로 바뀐다
  if (questionInput.value.length - replaced + pasted.length > questionInput.maxLength) {
    event.preventDefault();
    showError(`질문은 ${questionInput.maxLength}자까지 입력할 수 있어요.`);
  }
});
