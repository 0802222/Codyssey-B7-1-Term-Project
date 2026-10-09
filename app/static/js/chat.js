/*
 * 채팅 화면 (EE-12, EE-14, EE-17) — /chat
 *
 * 1. 질문을 보내면, 첫 질문일 때 POST /api/conversations 로 대화를 만들고 그 id 를 이 화면이 들고 있다가
 *    이어지는 질문에 쓴다. 같은 대화로 보내야 서버가 앞의 질문·답변을 문맥으로 쓴다.
 * 2. POST /api/chat 에 { conversation_id, question, level, client_request_id } 를 보낸다 (API 명세 3장).
 *    client_request_id 는 질문마다 새로 만드는 UUID — 같은 요청이 두 번 가도 서버가 AI 를 두 번 부르지 않는다.
 * 3. 답을 기다리는 동안 보내기 버튼을 잠그고, 답변 자리에 "답변을 만드는 중" 을 보여 준다.
 * 4. 질문·답변은 textContent 로만 넣는다 — 답변에 <script> 가 섞여 와도 글자로만 보인다.
 * 5. 시각은 API 의 UTC(…Z)를 한국 시간(KST)으로 바꿔 보여 준다.
 * 6. 실패하면 서버가 보낸 error.message 를 오류 칸에 보여 주고, 입력한 질문은 지우지 않는다.
 *    질문 말풍선은 남겨 두고 오류 칸의 "다시 보내기" 로 같은 질문을 다시 보낼 수 있다.
 * 7. 이어서 질문(EE-17): 내 기록의 "이어서 질문" 은 /chat?conversation=<대화 id> 로 연다. 그 대화의 지난 질문·답변
 *    (GET /api/conversations/{id} 의 완료된 턴)을 그려 두고 이어지는 질문을 같은 대화로 보낸다. 없는 대화·남의 대화·
 *    모양이 틀린 id 는 "대화를 찾을 수 없어요." 를 보여 주고 새 대화로 시작한다.
 *
 * 수준 값(easy·beginner·advanced)과 이름은 이 파일에 적지 않고 HTML 의 라디오 버튼에서 읽는다 —
 * app/web/router.py 의 CHAT_INPUT_RULES 한곳에서 정한다.
 * CSRF 토큰을 붙여 POST 하는 apiPost 는 api.js (로그아웃 버튼과 같이 쓴다). 401 이면 api.js 가 로그인 화면으로 보낸다.
 */

import {
  CONVERSATION_NOT_FOUND_MESSAGE,
  apiGet,
  apiPost,
  failureMessage,
  isUuid,
  outcomeUnknown,
} from "/static/js/api.js";

// 질문 한도(429 RATE_LIMITED)에 걸린 뒤 보내기를 막는 시간(초). 서버가 언제 풀리는지 알려 주지 않아서 처음은 10초,
// 연달아 걸리면 두 배씩 늘려 최대 60초 — 사용자 한도는 최근 60초 동안의 질문을 세므로 60초를 기다리면 반드시 풀린다
const RATE_LIMIT_WAITS = [10, 20, 40, 60];
// 60초씩 기다려도 계속 걸리면 사용자 한도가 아니라 서비스 전체의 하루 한도다 (서버는 UTC 0시 = 한국 오전 9시에 초기화)
const DAILY_LIMIT_NOTE =
  "계속 이 안내가 나오면 오늘 서비스 전체의 질문 한도를 다 썼을 수 있어요. 한도는 매일 오전 9시에 다시 채워져요.";

const form = document.getElementById("chat-form");
const questionInput = document.getElementById("question");
const sendButton = form.querySelector('button[type="submit"]');
const sendLabel = sendButton.textContent;
const countText = document.getElementById("question-count");
const thread = document.getElementById("thread");
const loading = document.getElementById("chat-loading");
const emptyState = document.getElementById("chat-empty");
const errorBox = document.getElementById("chat-error");
const errorText = document.getElementById("chat-error-text");
const errorNote = document.getElementById("chat-error-note");
const retryButton = document.getElementById("chat-retry");
const followUps = document.getElementById("follow-ups");
const followUpButtons = followUps.querySelectorAll("button[data-question]");
const newChatButton = document.getElementById("new-chat");
const levelRadios = document.querySelectorAll('input[name="level"]');

let conversationId = null; // 첫 질문 때 POST /api/conversations 로 받는다. 새로고침하면 새 대화로 시작한다
let waiting = false; // 답을 기다리는 중인지
// 답을 받지 못해 "다시 보내기" 를 기다리는 질문 요청 (없으면 null). 모양은 아래 sendQuestion 의 request
let failed = null;
let rateLimitStreak = 0; // 연달아 받은 429 수 — 429 가 아닌 결과를 받으면 0
let cooldownTimer = null; // 429 뒤 기다리는 동안 남은 시간을 고치는 타이머 (기다리는 중이 아니면 null)
let opening = false; // 이어서 질문: 지난 대화를 불러오는 중인지 (그동안은 보내지 않는다)

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

// 첫 질문이면 대화를 먼저 만들고, 질문 요청을 보낸다. 결과는 apiPost 의 { ok, status, offline, data } 그대로
async function askServer(request) {
  if (conversationId === null) {
    const created = await apiPost("/api/conversations", {});
    if (!created.ok || !created.data?.id) {
      return created; // 대화를 만들지 못했다 — 질문은 아직 보내지 않았다
    }
    conversationId = created.data.id;
  }
  return apiPost("/api/chat", {
    conversation_id: conversationId,
    question: request.question,
    level: request.level.value,
    client_request_id: request.requestId,
  });
}

// 성공 응답(명세 3장): { request_id, turn_id, conversation_id, level, question, answer, status, created_at }
function isAnswer(result) {
  return result.ok && result.data?.status === "completed" && typeof result.data.answer === "string";
}

/* ── 화면에 그리기 ── */

// 오류 칸에 안내 문구를 글자로 넣어 보여 준다. role="alert" 라서 나타나는 순간 스크린리더가 읽는다.
// retry: 오류 칸 오른쪽에 "다시 보내기" 버튼을 보일지 (요청이 실패했을 때만. 입력 안내에는 없다)
// note: 서버 문구 아래에 화면이 덧붙이는 안내 ("~해요")
function showError(message, { retry = false, note = "" } = {}) {
  errorText.textContent = message;
  errorNote.textContent = note;
  retryButton.hidden = !retry;
  errorBox.hidden = false;
}

function clearError() {
  errorBox.hidden = true;
  errorText.textContent = ""; // 입력칸의 aria-describedby 가 지난 오류를 읽지 않게 비운다
  errorNote.textContent = "";
  retryButton.hidden = true;
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

// 답변 말풍선 왼쪽의 전구 캐릭터
function mascotImage() {
  const mascot = document.createElement("img");
  mascot.className = "msg-mascot";
  mascot.src = "/static/img/mascot.svg";
  mascot.alt = ""; // 꾸밈 그림이라 스크린리더가 읽지 않는다
  mascot.width = 38;
  mascot.height = 38;
  return mascot;
}

// 답변: 전구 캐릭터 + 왼쪽 말풍선
function addAnswer(text) {
  const item = document.createElement("li");
  item.className = "msg msg-ai";
  item.append(speaker("답변"), mascotImage(), createBubble(text));
  thread.append(item);
  // 답이 화면보다 길면 답의 첫 줄부터, 짧으면 아래 입력 상자까지 보이게 스크롤한다
  if (item.offsetHeight > window.innerHeight * 0.6) {
    item.scrollIntoView({ block: "start" });
  } else {
    form.scrollIntoView({ block: "nearest" });
  }
  return item;
}

// 답을 기다리는 동안 답변 자리에 "답변을 만드는 중" + 점 세 개(시안). role="status" 칸(chat-loading)에 넣으면
// 스크린리더가 한 번 읽는다. 점은 꾸밈이라 aria-hidden, 깜빡임은 CSS 가 한다(움직임 줄이기 설정이면 멈춘다)
function showLoading(on) {
  if (!on) {
    loading.replaceChildren(); // 비우면 자리도 차지하지 않는다 (.chat-loading:empty)
    return;
  }
  const dots = document.createElement("span");
  dots.className = "loading-dots";
  dots.setAttribute("aria-hidden", "true");
  dots.append(document.createElement("i"), document.createElement("i"), document.createElement("i"));
  const bubble = createBubble("답변을 만드는 중");
  bubble.prepend(dots);
  const item = document.createElement("div");
  item.className = "msg msg-ai msg-loading";
  item.append(mascotImage(), bubble);
  loading.replaceChildren(item);
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

// 보내는 길을 잠그거나 푼다 — 답을 기다릴 때와 질문 한도(429) 뒤 기다릴 때 같이 쓴다.
// 보내기·다시 보내기·후속·새 대화 버튼을 잠그고, 입력칸은 읽기 전용으로 둔다 (보낸 질문은 지우지 않는다)
function setLocked(on) {
  sendButton.disabled = on;
  retryButton.disabled = on;
  questionInput.readOnly = on;
  newChatButton.disabled = on; // 기다리는 중에 대화를 바꾸면 답이 어느 대화 것인지 꼬인다
  for (const button of followUpButtons) {
    button.disabled = on;
  }
}

// 지금 보낼 수 없는지 (답을 기다리는 중, 지난 대화를 불러오는 중, 429 뒤 기다리는 중) — Enter·클릭 연타도 여기서 막는다
function isLocked() {
  return waiting || opening || cooldownTimer !== null;
}

// 답을 기다리는 동안: 잠그고 보내기 버튼은 "기다리는 중…", 답변 자리에는 "답변을 만드는 중".
// 입력칸의 질문은 남아 있다가 답을 받으면 비운다 (실패하면 남아 다시 보낼 수 있다)
function setWaiting(on) {
  waiting = on;
  setLocked(on);
  sendButton.textContent = on ? sendButton.dataset.busyLabel : sendLabel;
  showLoading(on);
}

// 질문 한도(429): 한도가 풀릴 시간을 주려고 정한 시간 동안 잠그고 오류 칸 아래 줄에 남은 시간을 보여 준다.
// 1초마다 바뀌는 숫자는 스크린리더가 매번 읽지 않게 aria-hidden 으로 두고, 읽어 줄 문장은 처음에 한 번만 넣는다.
// 다 기다리면 "이제 다시 보낼 수 있어요." 로 바꾼다 (오류 칸이 바뀌어 스크린리더가 한 번 더 읽는다)
function startCooldown() {
  rateLimitStreak += 1;
  const seconds = RATE_LIMIT_WAITS[Math.min(rateLimitStreak, RATE_LIMIT_WAITS.length) - 1];
  const until = Date.now() + seconds * 1000;
  const spoken = document.createElement("span");
  spoken.className = "visually-hidden";
  spoken.textContent = `${seconds}초 뒤에 다시 보낼 수 있어요.`;
  const shown = document.createElement("span");
  shown.setAttribute("aria-hidden", "true");
  const countdown = document.createElement("span");
  countdown.append(spoken, shown);
  errorNote.replaceChildren(countdown);
  if (rateLimitStreak >= RATE_LIMIT_WAITS.length) {
    errorNote.append(document.createElement("br"), DAILY_LIMIT_NOTE);
  }
  setLocked(true);
  const tick = () => {
    const left = Math.ceil((until - Date.now()) / 1000);
    if (left > 0) {
      shown.textContent = `${left}초 뒤에 다시 보낼 수 있어요.`;
      return;
    }
    clearInterval(cooldownTimer);
    cooldownTimer = null;
    setLocked(false);
    countdown.replaceChildren("이제 다시 보낼 수 있어요.");
  };
  cooldownTimer = setInterval(tick, 250);
  tick();
}

/* ── 질문 보내기 ── */

// 새 질문 하나를 보낸다. fromInput: 입력칸의 질문이면 답을 받은 뒤 입력칸을 비운다.
// 질문 요청 = { question, level: { value, label }, fromInput, item: 내 질문 말풍선,
//              requestId: client_request_id, sameIdNext: 다시 보낼 때 같은 번호를 쓸지 }
function sendQuestion(question, { fromInput }) {
  if (isLocked()) return; // 기다리는 중이면 무시한다 (Enter·클릭 연타, 429 뒤 기다리는 동안)
  const level = selectedLevel();
  // 답을 못 받은 질문과 같은 질문(같은 글·같은 수준)을 다시 보내면 "다시 보내기" 와 같게 한다 — 말풍선을 또 붙이지 않는다
  if (failed && failed.question === question && failed.level.value === level.value) {
    failed.fromInput ||= fromInput;
    resendFailed();
    return;
  }
  dropFailed(); // 다른 질문을 보내면 답을 못 받은 앞 질문은 다시 보내지 않는 것으로 본다
  const request = {
    question,
    level,
    fromInput,
    item: null,
    requestId: newRequestId(),
    sameIdNext: false,
  };
  clearError();
  request.item = addQuestion(question, level.label);
  send(request);
}

// 답을 못 받은 질문을 다시 보낸다 (오류 칸의 "다시 보내기"). 같은 말풍선·질문·수준 그대로, 입력칸의 글도 그대로.
// 요청 번호(client_request_id)는 앞의 실패가 어떤 것이었는지에 따라 정한다 (showFailure 의 sameIdNext):
// - 응답을 못 받아 서버가 처리했는지 모름(연결 끊김, JSON 이 아닌 응답, 200 인데 본문을 못 읽음) → 같은 번호.
//   서버가 이미 답을 만들었으면 AI 를 다시 부르지 않고 저장한 답을 돌려주고, 아직 만드는 중이면 409 CHAT_BUSY
// - 처리 중(409 CHAT_BUSY) → 같은 번호로 다시 묻는다. 시간이 얼마나 지나도 바꾸지 않는다 — 화면은 서버가 언제
//   처리를 시작했는지 모르므로, 시간만으로 실패라고 단정하면 아직 처리 중인 질문을 새 번호로 한 번 더 보낼 수 있다.
//   재시작 때 남은 처리 중 표시는 서버가 중단으로 정리하면(#22) 같은 번호에 503 이 와서 그때 새 번호가 된다
// - 서버가 실패를 알려 옴(AI 시간 초과·오류, 한도 초과, 중단 등) → 새 번호. 같은 번호면 서버가 저장한 실패를 그대로
//   돌려준다 (API 명세 3장 "다시 시도는 클라이언트가 새 키로")
function resendFailed() {
  if (isLocked() || !failed) return;
  if (!failed.sameIdNext) {
    failed.requestId = newRequestId();
  }
  send(failed);
}

// 질문 요청을 보내고 결과를 화면에 붙인다
async function send(request) {
  clearError();
  // 잠그는 버튼에 포커스가 있었으면 브라우저가 포커스를 뺀다. 잠금을 푼 뒤 그 자리로 돌려준다
  const focusedBefore = document.activeElement;
  setWaiting(true);
  let result;
  try {
    result = await askServer(request);
  } catch {
    result = { ok: false, status: 0, offline: false, data: null }; // 예상하지 못한 오류 → 대체 문구
  }
  setWaiting(false);
  if (result.data?.error?.code !== "RATE_LIMITED") {
    rateLimitStreak = 0; // 연달아 받은 429 만 센다 — 다른 결과가 오면 다음 429 는 다시 10초부터
  }
  if (isAnswer(result)) {
    showAnswer(request, result.data);
    restoreFocus(focusedBefore);
  } else {
    showFailure(request, result);
  }
}

// 답을 받았다: 질문 아래 시각, 답변 말풍선, 후속 버튼. 입력칸에서 보낸 질문이 그대로 남아 있으면 비운다
// (실패한 뒤 입력칸의 글을 고쳐 두었으면 그 글은 둔다)
function showAnswer(request, turn) {
  failed = null;
  addTurnTime(request.item, turn.created_at);
  addAnswer(turn.answer);
  followUps.hidden = false; // 답이 있어야 "더 쉽게" 같은 후속 질문이 뜻이 있다
  if (request.fromInput && questionInput.value.trim() === request.question) {
    questionInput.value = "";
    updateCount();
  }
}

// 답을 못 받았다: 질문 말풍선은 남기고(시안) 오류 칸에 서버 문구와 "다시 보내기" 를 보여 준다. 입력칸의 글은 그대로
function showFailure(request, result) {
  const code = result.data?.error?.code;
  if (code === "VALIDATION_ERROR") {
    // 422: 같은 질문은 다시 보내도 같은 결과라 다시 보내기 없이 고칠 곳(입력칸)으로 보낸다. 말풍선은 뺀다
    failed = null;
    request.item.remove();
    emptyState.hidden = thread.children.length > 0;
    showError(failureMessage(result), { note: "질문을 고쳐서 다시 보내 주세요." });
    questionInput.focus();
    return;
  }
  failed = request;
  // 다시 보낼 때 같은 요청 번호를 쓸지 (규칙은 resendFailed 위)
  request.sameIdNext = outcomeUnknown(result) || code === "CHAT_BUSY";
  let note = "";
  if (code === "CONVERSATION_NOT_FOUND") {
    // 404: 대화가 서버에 없다(지워졌거나, 다른 탭에서 다른 계정으로 로그인함). 다시 보내면 새 대화를 만들게 하고,
    // 화면에서도 지난 대화를 빼고 이 질문만 남긴다 — 화면의 대화 = 서버가 문맥으로 쓰는 대화
    conversationId = null;
    for (const item of [...thread.children]) {
      if (item !== request.item) item.remove();
    }
    followUps.hidden = true;
    note = "다시 보내면 새 대화로 시작해요.";
  }
  showError(failureMessage(result), { retry: true, note });
  if (code === "RATE_LIMITED") {
    startCooldown(); // 한도가 풀릴 시간을 준다 — 그동안 보내기·다시 보내기가 잠긴다
    errorBox.focus(); // 잠긴 버튼에는 포커스를 둘 수 없어서 오류 칸에 둔다. 다음 Tab 이 다시 보내기
    return;
  }
  retryButton.focus(); // Enter 한 번이면 다시 보낸다. 오류 칸은 role="alert" 라 스크린리더가 읽는다
}

// 다시 보내지 않기로 한 질문(다른 질문을 실제로 보냄, 새 대화)은 말풍선을 대화에서 뺀다 —
// 화면의 대화를 서버가 문맥으로 쓰는 완료된 턴과 맞춘다. 입력 안내(빈 질문·넘치는 붙여 넣기)는 아무것도
// 보내지 않은 것이라 빼지 않는다 — 요청 번호를 잃으면 같은 질문이 새 번호로 가서 중복 처리될 수 있다
function dropFailed() {
  if (!failed) return;
  failed.item.remove();
  failed = null;
  emptyState.hidden = thread.children.length > 0;
}

// 잠금이 풀리면 포커스를 원래 자리로. 그 자리가 없거나 숨었으면(다시 보내기 버튼) 입력칸으로
function restoreFocus(before) {
  if (document.activeElement !== document.body) return;
  const visible = before && before !== document.body && before.isConnected && before.getClientRects().length > 0;
  (visible ? before : questionInput).focus({ preventScroll: true });
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
  if (isLocked()) return;
  const question = questionInput.value.trim(); // 앞뒤 공백은 빼고 보낸다 (서버도 같은 기준으로 다시 본다)
  const problem = findQuestionProblem(question);
  if (problem) {
    // 서버에 보내지 않는다. 입력한 글도, 답을 못 받은 앞 질문(failed)과 그 요청 번호도 그대로 둔다 —
    // 지우면 같은 질문을 다시 보낼 때 새 번호가 되어, 서버가 이미 답한 질문을 한 번 더 처리할 수 있다
    showError(problem, { retry: failed !== null });
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

// 새 대화: 화면의 대화와 conversation_id 를 비운다. 다음 질문 때 POST /api/conversations 로 새 대화를
// 만든다 — 누르기만 하고 묻지 않으면 빈 대화가 생기지 않는다. 지난 대화는 서버에 저장돼 있고, 입력칸의 글은 둔다
newChatButton.addEventListener("click", () => {
  if (isLocked()) return;
  failed = null; // 답을 못 받은 질문도 지난 대화와 함께 화면에서 빠진다
  conversationId = null;
  thread.replaceChildren();
  emptyState.hidden = false;
  followUps.hidden = true;
  clearError();
  questionInput.focus();
});

// 후속 버튼: 같은 대화에 버튼 문구("더 쉽게" 등)를 그대로 질문으로 보낸다. 수준은 지금 고른 것,
// client_request_id 는 새로. 입력칸에 쓰던 글은 건드리지 않는다
for (const button of followUpButtons) {
  button.addEventListener("click", () => {
    sendQuestion(button.dataset.question, { fromInput: false });
  });
}

// 오류 칸의 "다시 보내기": 답을 못 받은 질문을 같은 말풍선 그대로 다시 보낸다
retryButton.addEventListener("click", resendFailed);

/* ── 이어서 질문 (EE-17) ── */

// 수준 값(easy 등)의 화면 이름 — 라디오 버튼의 data-label (값과 이름은 CHAT_INPUT_RULES 한곳). 없는 값이면 값 그대로
function levelName(value) {
  for (const radio of levelRadios) {
    if (radio.value === value) return radio.dataset.label;
  }
  return value;
}

// 지난 대화를 불러오는 동안 상태 칸(role="status")에 안내를 넣는다 — 스크린리더가 한 번 읽는다
function showOpening(on) {
  if (!on) {
    loading.replaceChildren();
    return;
  }
  const line = document.createElement("p");
  line.className = "chat-opening";
  line.textContent = "지난 대화를 불러오는 중이에요.";
  loading.replaceChildren(line);
}

// 불러온 지난 대화를 그린다. 답을 받은 턴(completed)만 그린다 — 화면의 대화를 서버가 문맥으로 쓰는 완료된 턴과
// 맞춘다 (답을 못 받은 턴은 내 기록에서 볼 수 있다). 대화 칸은 aria-live 라서 지난 대화를 스크린리더가 한꺼번에
// 읽지 않도록 그리는 동안 끄고, 브라우저가 화면에 반영한 뒤(두 번 그린 뒤) 다시 켠다 — 새 답변은 전처럼 읽는다
function drawPastTurns(turns) {
  const answered = turns.filter((turn) => turn.status === "completed" && typeof turn.answer === "string");
  thread.setAttribute("aria-live", "off");
  for (const turn of answered) {
    const item = addQuestion(turn.question, levelName(turn.level));
    addTurnTime(item, turn.created_at);
    addAnswer(turn.answer);
  }
  requestAnimationFrame(() => requestAnimationFrame(() => thread.setAttribute("aria-live", "polite")));
  emptyState.hidden = thread.children.length > 0;
  if (answered.length === 0) return;
  followUps.hidden = false; // 답이 있어야 "더 쉽게" 같은 후속 질문이 뜻이 있다
  // 마지막으로 답을 받은 질문의 수준을 골라 둔다 — 이어서 물을 때 같은 눈높이로
  const lastLevel = answered[answered.length - 1].level;
  if ([...levelRadios].some((radio) => radio.value === lastLevel)) {
    for (const radio of levelRadios) radio.checked = radio.value === lastLevel;
  }
}

// 지난 대화를 열지 못했다: 안내하고 새 대화로 시작한다. 주소도 /chat 으로 바꿔 새로고침해도 같은 안내가 나오지 않게 한다
function startOver(message, note) {
  conversationId = null;
  history.replaceState(null, "", "/chat");
  emptyState.hidden = false;
  showError(message, { note });
}

// 주소의 대화를 불러와 이어서 묻게 한다. 서버는 같은 대화의 완료된 최근 턴을 문맥으로 쓰므로 화면은 conversation_id 만
// 이어 쓰면 된다. id 는 UUID 모양인지 먼저 본다 — 틀린 값은 요청 주소에 넣지 않는다 (다른 API 를 부를 수 있다)
async function openConversation(id) {
  if (!isUuid(id)) {
    startOver(CONVERSATION_NOT_FOUND_MESSAGE, "새 대화로 시작해요.");
    return;
  }
  opening = true;
  setLocked(true);
  emptyState.hidden = true;
  showOpening(true);
  let result;
  try {
    result = await apiGet(`/api/conversations/${id}`);
  } catch {
    result = { ok: false, status: 0, offline: false, data: null }; // 예상하지 못한 오류 → 대체 문구
  }
  opening = false;
  showOpening(false);
  setLocked(false);
  if (result.ok && Array.isArray(result.data?.turns)) {
    conversationId = id;
    drawPastTurns(result.data.turns);
    return;
  }
  // 없는 대화·남의 대화(서버가 똑같이 404)는 서버 문구 그대로. 그 밖의 실패(연결 끊김·서버 오류)도 새 대화로
  // 시작하되, 내 기록에서 다시 열 수 있다고 알린다
  const notFound = result.data?.error?.code === "CONVERSATION_NOT_FOUND";
  startOver(
    failureMessage(result),
    notFound ? "새 대화로 시작해요." : "지난 대화를 불러오지 못해 새 대화로 시작해요. 내 기록에서 다시 열 수 있어요.",
  );
}

// 이어서 질문으로 열었으면(주소에 conversation 이 있으면) 그 대화부터 불러온다
const requestedConversation = new URLSearchParams(location.search).get("conversation");
if (requestedConversation !== null) {
  openConversation(requestedConversation);
}

// 붙여 넣기: 브라우저는 maxlength 를 넘는 뒷부분을 말없이 잘라 넣는다. 질문이 잘린 채 보내지지 않게,
// 붙여 넣은 뒤의 길이가 최대를 넘으면 넣지 않고 안내한다 (가입·로그인 칸과 같은 방식)
questionInput.addEventListener("paste", (event) => {
  if (isLocked()) return; // 읽기 전용이라 어차피 들어가지 않는다
  const pasted = (event.clipboardData?.getData("text") ?? "").replace(/\r\n?/g, "\n"); // 줄바꿈은 한 글자
  const replaced = questionInput.selectionEnd - questionInput.selectionStart; // 고른 글은 붙여 넣는 글로 바뀐다
  if (questionInput.value.length - replaced + pasted.length > questionInput.maxLength) {
    event.preventDefault();
    // 넣지 않았으니 입력칸의 질문은 그대로다 — 답을 못 받은 앞 질문과 그 요청 번호도 그대로 둔다 (보내기 전 안내와 같다)
    showError(`질문은 ${questionInput.maxLength}자까지 입력할 수 있어요.`, { retry: failed !== null });
  }
});
