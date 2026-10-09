/*
 * 내 기록 화면 (EE-17) — /history
 *
 * 1. 대화 목록: GET /api/me/conversations?limit=20&offset=0 으로 내 대화를 불러와 서버가 정렬해 준 순서(최근에
 *    질문한 대화가 위)대로 붙인다. 더 있으면(has_more) "더 보기" 가 다음 20개를 이어 붙인다.
 * 2. 서버 글(제목 등)은 textContent 로만 넣는다 — <script> 가 섞여 와도 글자로만 보인다.
 * 3. 시각은 API 의 UTC 를 한국 시간(KST)으로 바꿔 보여 준다.
 *
 * 한 번에 불러오는 수는 이 파일에 적지 않고 HTML 의 data- 속성에서 읽는다 — app/web/router.py 의 HISTORY_RULES.
 * 401 이면 api.js 의 apiGet 이 로그인 화면으로 보낸다.
 */

import { apiGet, failureMessage } from "/static/js/api.js";

const page = document.getElementById("history");
const PAGE_SIZE = Number(page.dataset.pageSize); // 목록을 한 번에 불러오는 대화 수

const list = document.getElementById("conversation-list");
const emptyState = document.getElementById("list-empty");
const moreButton = document.getElementById("list-more");
const moreLabel = moreButton.textContent;

/* ── 상태 줄·오류 칸 ── */

// 칸(목록·상세)마다 있는 상태 줄(role="status")과 오류 칸(role="alert" + 다시 시도 버튼)을 다룬다.
// 상태 줄은 늘 두고 글만 바꾼다 — 숨겼다 보이는 상태 칸은 스크린리더가 바뀐 글을 못 읽을 수 있다
function panel(name) {
  const status = document.getElementById(`${name}-status`);
  const box = document.getElementById(`${name}-error`);
  const text = document.getElementById(`${name}-error-text`);
  const note = document.getElementById(`${name}-error-note`);
  const retryButton = document.getElementById(`${name}-retry`);
  let retry = null; // 다시 시도 버튼이 부를 함수
  retryButton.addEventListener("click", () => retry?.());
  return {
    box,
    say(message) {
      status.textContent = message; // "" 이면 비운다 (빈 칸은 자리를 차지하지 않는다 — style.css)
    },
    // 오류 칸에 안내를 글자로 넣어 보여 준다. hint: 아래 줄에 화면이 덧붙이는 안내 ("~해요"),
    // onRetry: "다시 시도" 버튼이 부를 함수 (없으면 버튼을 숨긴다)
    fail(message, { hint = "", onRetry = null } = {}) {
      text.textContent = message;
      note.textContent = hint;
      retry = onRetry;
      retryButton.hidden = onRetry === null;
      box.hidden = false;
    },
    clear() {
      box.hidden = true;
      text.textContent = ""; // 지난 오류를 스크린리더가 다시 읽지 않게 비운다
      note.textContent = "";
      retry = null;
      retryButton.hidden = true;
    },
  };
}

const listPanel = panel("list");

/* ── 시각 ── */

// API 시각은 UTC(예: 2026-10-02T07:00:00Z). 화면에는 한국 시간으로 바꿔 보여 준다 (DB·API 는 UTC 그대로).
// 채팅 화면(chat.js)과 같은 변환 — 이슈 #24 에 적힌 식 그대로
function formatKst(t) {
  return new Date(t).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
}

// <time datetime="원래 UTC">한국 시간</time>. 시각이 없거나 읽을 수 없으면 null
function timeElement(t) {
  if (!t || Number.isNaN(Date.parse(t))) return null;
  const time = document.createElement("time");
  time.dateTime = t;
  time.textContent = formatKst(t);
  return time;
}

/* ── 대화 목록 ── */

let nextOffset = 0; // 다음에 불러올 위치 = 지금까지 받은 대화 수
let listLoaded = false; // 첫 쪽을 받았는지
let listLoading = false; // 목록을 받는 중인지 (더 보기 연타를 막는다)
const shown = new Map(); // 대화 id → 목록 항목의 링크. 같은 대화를 두 번 붙이지 않는다

// 목록 응답(명세 2장): { items: [{ id, title, created_at, updated_at }], limit, offset, has_more }
function isConversationPage(result) {
  return result.ok && Array.isArray(result.data?.items) && typeof result.data.has_more === "boolean";
}

// 목록 항목 하나: 대화 상세로 가는 링크 (제목 + 최근에 질문한 시각 = 목록을 정렬한 기준 updated_at)
function addConversation(conversation) {
  const title = document.createElement("span");
  title.className = "history-item-title";
  title.textContent = conversation.title;
  const body = document.createElement("span");
  body.className = "history-item-body";
  body.append(title);
  const time = timeElement(conversation.updated_at);
  if (time) {
    time.className = "history-item-time";
    body.append(time);
  }
  const link = document.createElement("a");
  link.className = "history-item";
  link.href = `/history?conversation=${encodeURIComponent(conversation.id)}`;
  link.append(body);
  const item = document.createElement("li");
  item.append(link);
  list.append(item);
  shown.set(conversation.id, link);
  return link;
}

// "더 보기" 를 누를 수 없게 하고 "불러오는 중…" 으로 바꾸거나 되돌린다
function setMoreBusy(on) {
  moreButton.disabled = on;
  moreButton.textContent = on ? moreButton.dataset.busyLabel : moreLabel;
}

// 다음 쪽(처음이면 첫 쪽)을 불러와 목록 끝에 붙인다
async function loadConversations() {
  if (listLoading) return;
  listLoading = true;
  const first = !listLoaded;
  listPanel.clear();
  if (first) {
    listPanel.say("기록을 불러오는 중이에요.");
  } else {
    setMoreBusy(true);
  }
  const result = await apiGet(`/api/me/conversations?limit=${PAGE_SIZE}&offset=${nextOffset}`);
  listLoading = false;
  listPanel.say("");
  setMoreBusy(false);
  if (!isConversationPage(result)) {
    // 첫 쪽이면 오류 칸의 "다시 시도" 로, 더 보기였으면 그 버튼을 다시 누르면 같은 쪽을 다시 받는다
    listPanel.fail(failureMessage(result), { onRetry: first ? loadConversations : null });
    return;
  }
  const added = [];
  for (const conversation of result.data.items) {
    // 그사이 다른 탭에서 질문하면 순서가 바뀌어 이미 붙인 대화가 다음 쪽에 또 올 수 있다
    if (!shown.has(conversation.id)) added.push(addConversation(conversation));
  }
  nextOffset += result.data.items.length;
  listLoaded = true;
  moreButton.hidden = !result.data.has_more;
  list.hidden = shown.size === 0;
  emptyState.hidden = shown.size > 0; // 대화가 하나도 없으면 "아직 대화가 없어요"
  if (!first) {
    // 더 보기: 새로 붙은 첫 대화로 포커스 — 키보드로 이어서 내려가게. 새 대화 없이 버튼만 사라졌으면 마지막 대화로
    // (누른 버튼이 숨으면 포커스를 잃는다)
    const target = added[0] ?? (moreButton.hidden ? [...shown.values()].pop() : null);
    target?.focus();
  }
}

moreButton.addEventListener("click", loadConversations);

/* ── 시작 ── */

loadConversations();
