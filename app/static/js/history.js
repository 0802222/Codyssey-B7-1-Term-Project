/*
 * 내 기록 화면 (EE-17) — /history (대화 목록), /history?conversation=<대화 id> (대화 상세)
 *
 * 1. 대화 목록: GET /api/me/conversations?limit=20&offset=0 으로 내 대화를 불러와 서버가 정렬해 준 순서(최근에
 *    질문한 대화가 위)대로 붙인다. 더 있으면(has_more) "더 보기" 가 다음 20개를 이어 붙인다.
 * 2. 제목: 서버가 대화를 만들 때 붙인 제목("새 대화")이 그대로면 그 대화의 첫 질문 앞부분을 대신 보여 준다.
 *    첫 질문은 상세(GET /api/conversations/{id})에만 있어서, 화면에 보이는 항목만 한 번에 3개씩 불러온다.
 *    서버가 제목을 채우면(첫 질문 일부 등 — DB 명세) 그 제목을 그대로 쓰고 상세를 묻지 않는다.
 * 3. 대화 상세: 목록에서 대화를 누르면 페이지를 새로 받지 않고 주소만 /history?conversation=<id> 로 바꾼 뒤
 *    (history.pushState) GET /api/conversations/{id} 의 턴을 서버가 정렬해 준 순서(오래된 것이 위)대로 채팅 화면과
 *    같은 말풍선으로 그린다. 주소에 대화 id 가 있어서 새로고침·뒤로 가기·주소 공유가 그대로 되고, 뒤로 가기로
 *    목록에 돌아오면 더 보기로 불러온 목록이 그대로 남아 있다. 주소의 id 는 UUID 모양인지 먼저 본다.
 *    답을 받지 못한 턴(실패·중단·답을 만드는 중)은 질문 아래에 답이 없다는 안내를 "~해요" 로 보여 주고(원인 코드는
 *    그대로 보여 주지 않는다), 질문 한도에 걸려 쌓인 실패처럼 연달아 2개 이상이면 하나로 접는다.
 * 4. 서버 글(제목·질문·답변)은 textContent 로만 넣는다 — <script> 가 섞여 와도 글자로만 보인다.
 * 5. 시각은 API 의 UTC 를 한국 시간(KST)으로 바꿔 보여 준다.
 *
 * 한 번에 불러오는 수·제목 기준은 이 파일에 적지 않고 HTML 의 data- 속성에서 읽는다 — app/web/router.py 의 HISTORY_RULES.
 * 수준 이름(아주 쉽게 등)도 HTML 의 수준 이름표(#level-names)에서 읽는다 — CHAT_INPUT_RULES.
 * 401 이면 api.js 의 apiGet 이 로그인 화면으로 보낸다.
 */

import { CONVERSATION_NOT_FOUND_MESSAGE, apiGet, failureMessage, isUuid } from "/static/js/api.js";

const page = document.getElementById("history");
const PAGE_SIZE = Number(page.dataset.pageSize); // 목록을 한 번에 불러오는 대화 수
const UNTITLED = page.dataset.untitled; // 서버가 대화를 만들 때 붙이는 제목 ("새 대화")
const TITLE_MAX_LENGTH = Number(page.dataset.titleMaxLength); // 첫 질문으로 만든 제목의 최대 글자 수
// 첫 질문을 알려고 상세를 동시에 몇 개까지 부를지 — 목록 한 쪽(20개)을 한꺼번에 묻지 않게 조금씩
const TITLE_REQUESTS_AT_ONCE = 3;

const heading = document.getElementById("history-heading");
const listView = document.getElementById("list-view");
const list = document.getElementById("conversation-list");
const emptyState = document.getElementById("list-empty");
const moreButton = document.getElementById("list-more");
const moreLabel = moreButton.textContent;
const detailView = document.getElementById("detail-view");
const backLink = document.getElementById("back-to-list");
const detailTitle = document.getElementById("detail-title");
const detailMeta = document.getElementById("detail-meta");
const thread = document.getElementById("detail-thread");
// 수준 값(easy 등) → 화면 이름(아주 쉽게 등)
const levelNames = new Map(
  Array.from(document.getElementById("level-names").children, (item) => [item.dataset.level, item.textContent.trim()]),
);
const LIST_TITLE = document.title; // "내 기록 — EasyExplain". 상세에서는 앞에 대화 제목을 붙인다

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
const detailPanel = panel("detail");

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

/* ── 제목 ── */

const titles = new Map(); // 대화 id → 첫 질문으로 정한 제목 (한 번 정하면 다시 묻지 않는다)
const titleElements = new Map(); // 대화 id → 목록 항목의 제목 칸

// 서버가 제목을 채우지 않은 대화인지 — 대화를 만들 때 붙인 "새 대화" 그대로이거나 비어 있음
function isUntitled(serverTitle) {
  const title = (serverTitle ?? "").trim();
  return title === "" || title === UNTITLED;
}

// 보여 줄 제목: 서버 제목이 있으면 그것, 없으면 첫 질문 앞부분, 질문도 없는 대화면 "새 대화"
function displayTitle(serverTitle, firstQuestion) {
  if (!isUntitled(serverTitle)) return serverTitle.trim();
  if (typeof firstQuestion === "string" && firstQuestion.trim() !== "") return excerpt(firstQuestion);
  return UNTITLED;
}

// 질문 앞부분: 줄바꿈·연이은 공백은 한 칸으로 줄이고, 최대 글자 수를 넘으면 자르고 … 를 붙인다.
// 글자는 Array.from 으로 센다 — 이모지처럼 두 칸(UTF-16)짜리 글자를 반으로 자르지 않는다 (서버의 글자 수와 같은 기준)
function excerpt(text) {
  const oneLine = text.replace(/\s+/g, " ").trim();
  const chars = Array.from(oneLine);
  return chars.length > TITLE_MAX_LENGTH ? `${chars.slice(0, TITLE_MAX_LENGTH).join("")}…` : oneLine;
}

// 정한 제목을 기억하고 목록 항목에 넣는다
function setTitle(id, title) {
  titles.set(id, title);
  const element = titleElements.get(id);
  if (element) element.textContent = title;
}

// 상세 응답(명세 2장): { conversation: { id, title, created_at, updated_at }, turns: [턴, …] } — 턴은 오래된 순
function isConversationDetail(result) {
  return result.ok && Boolean(result.data?.conversation) && Array.isArray(result.data.turns);
}

const titleQueue = []; // 첫 질문을 불러올 대화 id (화면에 보인 순서)
let titleRequests = 0; // 지금 보내 둔 상세 요청 수

// 첫 턴의 질문으로 제목을 정한다. 못 불러오면(서버 오류·연결 끊김) 서버 제목("새 대화")을 그대로 둔다
async function loadTitle(id) {
  if (titles.has(id) || !isUuid(id)) return;
  const result = await apiGet(`/api/conversations/${id}`);
  if (isConversationDetail(result)) {
    setTitle(id, displayTitle(result.data.conversation.title, result.data.turns[0]?.question));
  }
}

// 줄 선 순서대로, 동시에 TITLE_REQUESTS_AT_ONCE 개까지만 보낸다. 하나가 끝나면 다음 것을 보낸다
function pumpTitles() {
  while (titleRequests < TITLE_REQUESTS_AT_ONCE && titleQueue.length > 0) {
    const id = titleQueue.shift();
    titleRequests += 1;
    loadTitle(id).finally(() => {
      titleRequests -= 1;
      pumpTitles();
    });
  }
}

function queueTitle(id) {
  titleQueue.push(id);
  pumpTitles();
}

// 화면에 보이는(또는 곧 보일 — 위아래 200px) 항목만 첫 질문을 묻는다. 목록을 끝까지 내려 보지 않으면 아래 대화는
// 묻지 않는다. IntersectionObserver 가 없는 브라우저에서는 바로 줄을 세운다 (그래도 동시에 3개씩)
const waitingForTitle = new Map(); // 지켜보는 목록 항목 → 대화 id
const titleObserver =
  typeof IntersectionObserver === "function"
    ? new IntersectionObserver(onItemsVisible, { rootMargin: "200px 0px" })
    : null;

function onItemsVisible(entries) {
  for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    titleObserver.unobserve(entry.target);
    queueTitle(waitingForTitle.get(entry.target));
    waitingForTitle.delete(entry.target);
  }
}

function watchForTitle(item, id) {
  if (titleObserver === null) {
    queueTitle(id);
    return;
  }
  waitingForTitle.set(item, id);
  titleObserver.observe(item);
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

// 목록 항목 하나: 대화 상세로 가는 링크 (제목 + 최근에 질문한 시각 = 목록을 정렬한 기준 updated_at).
// 서버 제목이 "새 대화" 면 우선 그대로 보여 주고, 항목이 화면에 보이면 첫 질문을 불러와 바꾼다
function addConversation(conversation) {
  const title = document.createElement("span");
  title.className = "history-item-title";
  title.textContent = titles.get(conversation.id) ?? displayTitle(conversation.title, null);
  titleElements.set(conversation.id, title);
  const body = document.createElement("span");
  body.className = "history-item-body";
  body.append(title);
  const time = timeElement(conversation.updated_at);
  if (time) {
    time.className = "history-item-time";
    body.append(time);
  }
  const url = `/history?conversation=${encodeURIComponent(conversation.id)}`;
  const link = document.createElement("a");
  link.className = "history-item";
  link.href = url;
  link.append(body);
  link.addEventListener("click", (event) => followInPage(event, url));
  const item = document.createElement("li");
  item.append(link);
  list.append(item);
  shown.set(conversation.id, link);
  if (isUntitled(conversation.title) && !titles.has(conversation.id)) {
    watchForTitle(item, conversation.id);
  }
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

/* ── 말풍선 (채팅 화면과 같은 모양 — style.css 의 .msg·.bubble 를 같이 쓴다) ── */

// 스크린리더에만 읽히는 말머리 ("내 질문", "답변")
function speaker(text) {
  const label = document.createElement("span");
  label.className = "visually-hidden";
  label.textContent = text;
  return label;
}

// 말풍선. 글은 textContent 로만 넣는다 — innerHTML 이면 글 속의 <script>·<img onerror> 가 실행될 수 있다
function bubble(text) {
  const element = document.createElement("div");
  element.className = "bubble";
  element.textContent = text;
  return element;
}

// 답변 말풍선 왼쪽의 전구 캐릭터 (꾸밈 그림이라 스크린리더가 읽지 않는다)
function mascotImage() {
  const mascot = document.createElement("img");
  mascot.className = "msg-mascot";
  mascot.src = "/static/img/mascot.svg";
  mascot.alt = "";
  mascot.width = 38;
  mascot.height = 38;
  return mascot;
}

// 수준 값의 화면 이름. 이름표에 없는 값이면 값 그대로
function levelName(value) {
  return levelNames.get(value) ?? value;
}

// 답을 받은 턴인지 (완료되지 않은 턴의 answer 는 null — 명세 2장)
function hasAnswer(turn) {
  return turn.status === "completed" && typeof turn.answer === "string";
}

// 답이 없는 턴의 안내. 서버의 원인 코드(error_code)는 그대로 보여 주지 않고 사용자 말("~해요")로 바꾼다
function missingNote(turn) {
  if (turn.status === "pending") return "아직 답을 만드는 중이에요. 잠시 뒤 다시 열어 보세요.";
  if (turn.status === "interrupted") return "답을 만드는 중에 멈춰서 답이 없어요.";
  if (turn.error_code === "AI_TIMEOUT") return "응답이 늦어져 답을 받지 못했어요.";
  if (turn.error_code === "RATE_LIMITED") return "질문 한도에 걸려 답을 받지 못했어요.";
  return "오류가 나서 답을 받지 못했어요.";
}

// 턴 하나 → 내 질문 말풍선(아래 줄에 수준 · 한국 시간) + 답변 말풍선(답이 없으면 그 안내를 흐린 점선 말풍선으로)
function turnItems(turn) {
  const meta = document.createElement("p");
  meta.className = "msg-meta";
  meta.append(levelName(turn.level));
  const time = timeElement(turn.created_at);
  if (time) meta.append(" · ", time);
  const question = document.createElement("li");
  question.className = "msg msg-me";
  question.append(speaker("내 질문"), bubble(turn.question), meta);
  const answer = document.createElement("li");
  if (hasAnswer(turn)) {
    answer.className = "msg msg-ai";
    answer.append(speaker("답변"), mascotImage(), bubble(turn.answer));
  } else {
    answer.className = "msg msg-ai msg-missing";
    answer.append(speaker("답변 없음"), mascotImage(), bubble(missingNote(turn)));
  }
  return [question, answer];
}

// 답이 없는 턴이 이만큼 이어지면 하나로 접는다 — 질문 한도에 걸려 연달아 실패한 턴이 쌓인 경우 등.
// 하나뿐인 실패(실패 뒤 다시 보내 성공 등)는 접지 않고 그대로 보여 준다
const FOLD_FROM = 2;

// 접힌 묶음: "답을 받지 못한 질문 N개". <details> 라 누르거나 키보드(Enter·Space)로 펼친다. 처음에는 접혀 있다
function foldedTurns(turns) {
  const summary = document.createElement("summary");
  summary.textContent = `답을 받지 못한 질문 ${turns.length}개`;
  const inner = document.createElement("ol");
  inner.className = "thread";
  inner.append(...turns.flatMap(turnItems));
  const details = document.createElement("details");
  details.append(summary, inner);
  const item = document.createElement("li");
  item.className = "missing-group";
  item.append(details);
  return item;
}

// 턴들(오래된 순) → 대화 칸에 넣을 항목들. 답이 없는 턴이 FOLD_FROM 개 이상 이어진 곳만 접는다
function threadItems(turns) {
  const items = [];
  let missing = []; // 지금까지 이어진, 답이 없는 턴
  const flush = () => {
    if (missing.length >= FOLD_FROM) {
      items.push(foldedTurns(missing));
    } else {
      items.push(...missing.flatMap(turnItems));
    }
    missing = [];
  };
  for (const turn of turns) {
    if (hasAnswer(turn)) {
      flush();
      items.push(...turnItems(turn));
    } else {
      missing.push(turn);
    }
  }
  flush();
  return items;
}

/* ── 대화 상세 ── */

let openedId = null; // 마지막으로 연 대화 — 목록으로 돌아오면 그 항목으로 포커스를 돌려준다
let detailTicket = 0; // 상세를 열 때마다 1씩 — 그사이 다른 화면으로 바뀌었으면 늦게 온 응답은 버린다

// 불러온 대화를 그린다: 제목(목록 항목도 같이), "질문 N개 · 시작 <시각>", 턴들(오래된 순 = 서버 순서 그대로)
function drawDetail(id, { conversation, turns }) {
  const title = displayTitle(conversation.title, turns[0]?.question);
  setTitle(id, title);
  detailTitle.textContent = title;
  document.title = `${title} — ${LIST_TITLE}`;
  detailMeta.replaceChildren(`질문 ${turns.length}개`);
  const started = timeElement(conversation.created_at);
  if (started) detailMeta.append(" · 시작 ", started);
  if (turns.length === 0) detailPanel.say("이 대화에는 아직 질문이 없어요.");
  thread.replaceChildren(...threadItems(turns));
}

// 대화 하나를 불러와 보여 준다. moveFocus: 화면 안에서 넘어왔으면 제목으로 포커스를 옮긴다
async function showDetail(id, { moveFocus }) {
  openedId = id;
  const ticket = ++detailTicket;
  listView.hidden = true;
  detailView.hidden = false;
  detailPanel.clear();
  detailPanel.say("");
  detailMeta.replaceChildren();
  thread.replaceChildren();
  // 목록에서 왔으면 그 항목의 제목을 바로 보여 주고 포커스를 옮긴다. 제목을 모르면 불러온 뒤에 옮긴다
  const known = titles.get(id) ?? titleElements.get(id)?.textContent ?? "";
  detailTitle.textContent = known;
  document.title = known ? `${known} — ${LIST_TITLE}` : LIST_TITLE;
  if (moveFocus && known) detailTitle.focus();
  const focusLater = moveFocus && !known;
  let result;
  if (isUuid(id)) {
    detailPanel.say("대화를 불러오는 중이에요.");
    result = await apiGet(`/api/conversations/${id}`);
    if (ticket !== detailTicket) return; // 그사이 목록이나 다른 대화로 바뀌었다
    detailPanel.say("");
  } else {
    // 주소의 id 모양이 틀렸다(잘린 주소, 손으로 고친 주소) — 서버에 묻지 않고 없는 대화와 같게 안내한다
    result = { ok: false, status: 0, offline: false, data: null };
  }
  if (isConversationDetail(result)) {
    drawDetail(id, result.data);
    if (focusLater) detailTitle.focus();
    return;
  }
  // 없는 대화·남의 대화(서버가 똑같이 404 로 답한다)·모양이 틀린 id 는 목록으로 안내하고, 그 밖의 실패는 다시 시도
  const notFound = !isUuid(id) || result.data?.error?.code === "CONVERSATION_NOT_FOUND";
  if (notFound) {
    detailTitle.textContent = "";
    document.title = LIST_TITLE;
  }
  detailPanel.fail(
    notFound ? CONVERSATION_NOT_FOUND_MESSAGE : failureMessage(result),
    notFound ? { hint: "목록에서 다시 골라 주세요." } : { onRetry: () => showDetail(id, { moveFocus: true }) },
  );
  if (focusLater) detailPanel.box.focus();
}

/* ── 주소에 따라 목록·상세 ── */

// 목록을 보여 준다. 처음이면 첫 쪽을 불러오고, 이미 불러왔으면 그대로(더 보기로 불러온 것까지) 둔다
function showList({ moveFocus }) {
  detailTicket += 1; // 기다리던 상세 응답이 늦게 와도 그리지 않는다
  detailView.hidden = true;
  listView.hidden = false;
  document.title = LIST_TITLE;
  if (!listLoaded) loadConversations();
  // 상세에서 돌아왔으면 방금 본 대화로 포커스(그 자리로 스크롤도 된다), 없으면 제목 "내 기록" 으로
  if (moveFocus) (shown.get(openedId) ?? heading).focus();
}

// 주소의 conversation 값(볼 대화 id). 없으면 null — 목록
function conversationInAddress() {
  return new URLSearchParams(location.search).get("conversation");
}

// 지금 주소에 맞는 칸을 보여 준다. moveFocus: 화면 안에서 바뀔 때만 포커스를 옮긴다 (처음 열 때는 브라우저 기본 그대로)
function route({ moveFocus }) {
  const id = conversationInAddress();
  if (id === null) {
    showList({ moveFocus });
  } else {
    showDetail(id, { moveFocus });
  }
}

// 링크를 누르면 페이지를 새로 받지 않고 주소만 바꿔(history.pushState) 그 칸을 보여 준다.
// 새 탭으로 열기(가운데 버튼, Ctrl·Cmd·Shift·Alt 와 함께 누르기)는 막지 않고 브라우저에 맡긴다
function followInPage(event, url) {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  history.pushState(null, "", url);
  route({ moveFocus: true });
}

backLink.addEventListener("click", (event) => followInPage(event, "/history"));
window.addEventListener("popstate", () => route({ moveFocus: true })); // 뒤로·앞으로 가기

/* ── 시작 ── */

route({ moveFocus: false });
