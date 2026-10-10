// 내 기록 화면(history.js)을 실제로 실행해 확인한다 (C 담당, EE-17)
//   node --test tests/web/js/*.test.mjs   (pytest 는 tests/web/test_chat_js_behavior.py 에서 이 파일도 부른다)
//
// 서버는 historyServer() 로 흉내 낸다: 대화 목록은 limit·offset 대로 잘라 최근 것부터, 상세는 대화마다 정한 턴을
// 돌려준다 (API 명세 2장). 화면에 보였다는 신호(IntersectionObserver)는 showOnScreen() 으로 보낸다.
import assert from "node:assert/strict";
import { test } from "node:test";

import { deferred, error, idle, install, json, loadHistory, offline, showOnScreen, watchedCount } from "./fake_dom.mjs";

const $ = (id) => document.getElementById(id);
const uuid = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const items = () => $("conversation-list").children; // 목록 항목(<li>)
const links = () => document.querySelectorAll(".history-item");
const titlesShown = () => document.querySelectorAll(".history-item-title").map((title) => title.textContent);
const listCalls = (calls) => calls.filter((call) => call.url.startsWith("/api/me/conversations"));
const detailCalls = (calls) => calls.filter((call) => call.url.startsWith("/api/conversations/"));

// 턴 하나 (명세 2장의 턴 항목). n: 대화 번호
function turn(n, id, question, extra = {}) {
  return {
    id,
    conversation_id: uuid(n),
    level: "easy",
    question,
    answer: `답변 ${id}`,
    status: "completed",
    error_code: null,
    created_at: "2026-10-09T01:00:00Z",
    ...extra,
  };
}

// 서버 흉내: 대화 count 개 (1 이 가장 최근에 질문한 대화). titles·turns 로 대화별 제목·턴을 정한다
function historyServer(count, { titles = {}, turns = {} } = {}) {
  const conversations = Array.from({ length: count }, (_, i) => ({
    id: uuid(i + 1),
    title: titles[i + 1] ?? "새 대화",
    created_at: "2026-10-09T00:00:00Z",
    updated_at: new Date(Date.UTC(2026, 9, 9, 12) - i * 60_000).toISOString(),
  }));
  return {
    conversations,
    list(call) {
      const query = new URL(call.url, "http://localhost").searchParams;
      const limit = Number(query.get("limit"));
      const offset = Number(query.get("offset"));
      const items = conversations.slice(offset, offset + limit);
      return json(200, { items, limit, offset, has_more: offset + limit < conversations.length });
    },
    detail(call) {
      const id = call.url.slice("/api/conversations/".length);
      const n = conversations.findIndex((conversation) => conversation.id === id) + 1;
      if (n === 0) return error(404, "CONVERSATION_NOT_FOUND", "대화를 찾을 수 없어요.");
      return json(200, { conversation: conversations[n - 1], turns: turns[n] ?? [turn(n, n * 10, `질문 ${n}`)] });
    },
    reply(call) {
      return call.url.startsWith("/api/me/conversations") ? this.list(call) : this.detail(call);
    },
  };
}

// 내 기록 화면(/history)을 연다. 주소를 바꾸려면 options.url
function installHistory(reply, options = {}) {
  return install(reply, { url: "/history", ...options });
}

async function openHistory(server, options = {}) {
  const page = installHistory((call) => server.reply(call), options);
  await loadHistory();
  await idle(page);
  return page;
}

// ── 대화 목록 ──

test("목록: 서버가 정렬한 순서대로 20개를 붙이고, 더 보기로 다음 20개(offset=20)를 이어 붙인다", async () => {
  const server = historyServer(25);
  const page = await openHistory(server);

  assert.deepEqual(listCalls(page.calls).map((call) => call.url), ["/api/me/conversations?limit=20&offset=0"]);
  assert.equal(listCalls(page.calls)[0].cache, "no-store"); // 새로고침하면 늘 지금 기록을 받는다
  assert.deepEqual(
    links().map((link) => link.href),
    server.conversations.slice(0, 20).map((conversation) => `/history?conversation=${conversation.id}`),
  );
  assert.equal($("conversation-list").hidden, false);
  assert.equal($("list-status").textContent, ""); // "기록을 불러오는 중이에요." 를 비웠다
  assert.equal($("list-more").hidden, false);

  $("list-more").click();
  await idle(page);

  assert.equal(listCalls(page.calls)[1].url, "/api/me/conversations?limit=20&offset=20");
  assert.equal(links().length, 25);
  assert.equal(links()[20].href, `/history?conversation=${uuid(21)}`);
  assert.equal($("list-more").hidden, true); // 더 없으면 숨긴다
  assert.equal(document.activeElement, links()[20]); // 새로 붙은 첫 대화로 포커스 (버튼이 사라져도 이어서 내려간다)
});

test("목록: 더 보기는 받는 동안 잠기고, 순서가 바뀌어 같은 대화가 다음 쪽에 또 와도 한 번만 붙인다", async () => {
  const server = historyServer(40);
  const later = deferred();
  let lists = 0;
  const page = installHistory((call) => {
    if (!call.url.startsWith("/api/me/conversations")) return server.detail(call);
    lists += 1;
    if (lists === 1) return server.list(call);
    // 그사이 다른 탭에서 질문해 맨 위에 새 대화가 생기면, 다음 쪽은 한 칸씩 밀려 20번째 대화가 또 온다
    return later.promise;
  });
  await loadHistory();
  await idle(page);

  $("list-more").click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal($("list-more").disabled, true);
  assert.equal($("list-more").textContent, "불러오는 중…");
  $("list-more").click(); // 잠겨 있어 요청이 또 가지 않는다
  assert.equal(lists, 2);

  const shifted = server.conversations.slice(19, 39);
  later.resolve(json(200, { items: shifted, limit: 20, offset: 20, has_more: true }));
  await idle(page);

  assert.equal($("list-more").disabled, false);
  assert.equal($("list-more").textContent, "더 보기");
  assert.equal(links().length, 39); // 20번째는 한 번만
  assert.equal(new Set(links().map((link) => link.href)).size, 39);
});

test("목록: 대화가 없으면 빈 목록 안내만 보이고 목록·더 보기는 숨긴다", async () => {
  await openHistory(historyServer(0));

  assert.equal($("list-empty").hidden, false);
  assert.equal($("conversation-list").hidden, true);
  assert.equal($("list-more").hidden, true);
  assert.equal($("list-status").textContent, "");
});

test("목록: 못 불러오면 서버 문구와 다시 시도 — 누르면 다시 불러온다", async () => {
  const server = historyServer(3);
  let lists = 0;
  const page = installHistory((call) => {
    lists += 1;
    if (lists === 1) return error(503, "DB_ERROR", "데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요.");
    return server.reply(call);
  });
  await loadHistory();
  await idle(page);

  assert.equal($("list-error").hidden, false);
  assert.equal($("list-error-text").textContent, "데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요.");
  assert.equal($("list-retry").hidden, false);
  assert.equal($("list-empty").hidden, true); // 실패를 "대화 없음" 으로 보이지 않는다

  $("list-retry").click();
  await idle(page);

  assert.equal($("list-error").hidden, true);
  assert.equal($("list-error-text").textContent, "");
  assert.equal(links().length, 3);
});

test("목록: 서버에 닿지 못하면 연결 안내 문구", async () => {
  const page = installHistory(() => offline());
  await loadHistory();
  await idle(page);

  assert.equal($("list-error-text").textContent, "서버에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.");
});

test("목록: 로그인이 풀렸으면(401) 로그인 화면으로", async () => {
  const page = installHistory(() => error(401, "AUTH_REQUIRED", "로그인이 필요해요."));
  await loadHistory();
  await new Promise((resolve) => setTimeout(resolve, 10));

  assert.equal(location.replaced, "/login?expired=1");
  assert.equal($("list-error").hidden, true); // 오류 칸을 띄우지 않고 넘어간다
  assert.equal(page.storage.has("csrf_token"), false);
});

test("목록: 시각은 정렬 기준(updated_at)을 한국 시간으로, <time> 에는 원래 UTC", async () => {
  const server = historyServer(1);
  server.conversations[0].updated_at = "2026-10-09T15:30:00Z";
  await openHistory(server);

  const time = links()[0].querySelector(".history-item-time");
  assert.equal(time.textContent, "2026. 10. 10. 오전 12:30:00");
  assert.equal(time.dateTime, "2026-10-09T15:30:00Z");
});

// ── 제목 대체 ──

test("제목: 서버 제목이 있으면 그대로, \"새 대화\" 면 화면에 보인 항목만 첫 질문 앞부분으로 바꾼다", async () => {
  const server = historyServer(25, {
    titles: { 1: "서버가 정한 제목" },
    turns: {
      2: [turn(2, 20, "  API가\n\n뭐야?  ")],
      3: [turn(3, 30, "가".repeat(29) + "🙂끝")],
      4: [turn(4, 40, "🙂".repeat(45))],
    },
  });
  const page = await openHistory(server);

  assert.equal(detailCalls(page.calls).length, 0); // 보이기 전에는 묻지 않는다
  assert.equal(titlesShown()[0], "서버가 정한 제목");
  assert.equal(titlesShown()[1], "새 대화"); // 우선 서버 제목

  showOnScreen(items().slice(0, 4));
  await idle(page);

  // 1번은 서버 제목이 있어서 묻지 않는다
  assert.deepEqual(detailCalls(page.calls).map((call) => call.url), [2, 3, 4].map((n) => `/api/conversations/${uuid(n)}`));
  assert.equal(titlesShown()[1], "API가 뭐야?"); // 줄바꿈·연이은 공백은 한 칸
  assert.equal(titlesShown()[2], `${"가".repeat(29)}🙂…`); // 30자 + …
  assert.equal(titlesShown()[3], `${"🙂".repeat(30)}…`); // 이모지를 반으로 자르지 않는다
  assert.equal(titlesShown()[4], "새 대화"); // 아직 안 보인 항목은 그대로
  // 첫 쪽 20개 중 서버 제목이 있는 1번은 처음부터 지켜보지 않고, 보인 3개는 지켜보기를 그만뒀다
  assert.equal(watchedCount(), 20 - 1 - 3);
});

test("제목: 상세는 동시에 3개까지만 묻고, 하나가 끝나면 다음 것을 묻는다", async () => {
  const server = historyServer(10);
  const waiting = [];
  const page = installHistory((call) => {
    if (call.url.startsWith("/api/me/conversations")) return server.list(call);
    const later = deferred();
    waiting.push({ call, later });
    return later.promise;
  });
  await loadHistory();
  await idle(page);

  showOnScreen(items());
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(page.inFlight, 3);

  waiting[0].later.resolve(server.detail(waiting[0].call));
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(detailCalls(page.calls).length, 4);
  assert.equal(page.inFlight, 3);

  for (let i = 1; i < 10; i += 1) {
    while (waiting.length <= i) await new Promise((resolve) => setTimeout(resolve, 0));
    waiting[i].later.resolve(server.detail(waiting[i].call));
  }
  await idle(page);
  assert.deepEqual(titlesShown(), Array.from({ length: 10 }, (_, i) => `질문 ${i + 1}`));
});

test("제목: IntersectionObserver 가 없는 브라우저는 바로 묻되 동시에 3개씩", async () => {
  const server = historyServer(8);
  let most = 0;
  const page = installHistory(async (call) => {
    most = Math.max(most, page.inFlight);
    await new Promise((resolve) => setTimeout(resolve, 1));
    return server.reply(call);
  }, { intersection: false });
  await loadHistory();
  await idle(page);

  assert.equal(detailCalls(page.calls).length, 8);
  assert.ok(most <= 3, `동시에 ${most}개`);
  assert.deepEqual(titlesShown(), Array.from({ length: 8 }, (_, i) => `질문 ${i + 1}`));
});

test("제목: 상세를 못 불러오거나 질문이 없는 대화면 \"새 대화\" 그대로", async () => {
  const server = historyServer(2, { turns: { 2: [] } });
  const page = installHistory((call) => {
    if (call.url === `/api/conversations/${uuid(1)}`) return error(500, "INTERNAL_ERROR", "일시적인 오류가 발생했어요.");
    return server.reply(call);
  });
  await loadHistory();
  await idle(page);
  showOnScreen(items());
  await idle(page);

  assert.deepEqual(titlesShown(), ["새 대화", "새 대화"]);
  assert.equal($("list-error").hidden, true); // 제목을 못 불러온 것은 오류 칸에 띄우지 않는다
});

// ── 대화 상세 ──

const MIXED_TURNS = [
  turn(1, 1, "첫 질문", { level: "easy" }),
  turn(1, 2, "두 번째 질문", { level: "beginner", created_at: "2026-10-09T15:30:00Z" }),
];

test("상세: 누르면 주소만 바꿔(pushState) 턴을 서버 순서(오래된 것이 위)대로 그리고 제목으로 포커스", async () => {
  const server = historyServer(3, { turns: { 1: MIXED_TURNS } });
  const page = await openHistory(server);
  const before = history.length;

  const event = links()[0].dispatch("click", { button: 0 });
  await idle(page);

  assert.equal(event.defaultPrevented, true); // 페이지를 새로 받지 않는다
  assert.equal(history.length, before + 1); // 뒤로 가기로 목록에 돌아올 수 있다
  assert.equal(location.search, `?conversation=${uuid(1)}`);
  assert.equal($("list-view").hidden, true);
  assert.equal($("detail-view").hidden, false);
  assert.equal(document.activeElement, $("detail-title"));
  assert.equal($("detail-title").textContent, "첫 질문");
  assert.equal(document.title, "첫 질문 — 내 기록 — EasyExplain");

  const bubbles = $("detail-thread").querySelectorAll(".bubble").map((bubble) => bubble.textContent);
  assert.deepEqual(bubbles, ["첫 질문", "답변 1", "두 번째 질문", "답변 2"]);
  const metas = $("detail-thread").querySelectorAll(".msg-meta").map((meta) => meta.textContent);
  assert.deepEqual(metas, [
    `아주 쉽게 · ${new Date("2026-10-09T01:00:00Z").toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })}`,
    "입문자 · 2026. 10. 10. 오전 12:30:00",
  ]);
  assert.equal($("detail-meta").textContent, "질문 2개 · 시작 2026. 10. 9. 오전 9:00:00");
});

test("상세: 가운데 버튼·Ctrl 과 함께 누르면 막지 않는다 (새 탭으로 열기)", async () => {
  const page = await openHistory(historyServer(2));

  for (const fields of [{ button: 1 }, { button: 0, ctrlKey: true }, { button: 0, metaKey: true }, { button: 0, shiftKey: true }]) {
    const event = links()[0].dispatch("click", fields);
    assert.equal(event.defaultPrevented, false);
  }
  await idle(page);
  assert.deepEqual(history.urls, []);
  assert.equal($("detail-view").hidden, true);
});

test("상세: 뒤로 가기로 목록에 돌아오면 다시 받지 않고(더 보기 그대로) 방금 본 대화로 포커스, 앞으로 가기는 다시 상세", async () => {
  const server = historyServer(25);
  const page = await openHistory(server);
  $("list-more").click();
  await idle(page);
  links()[22].click();
  await idle(page);

  history.back();
  await idle(page);

  assert.equal($("detail-view").hidden, true);
  assert.equal($("list-view").hidden, false);
  assert.equal(links().length, 25);
  assert.equal(listCalls(page.calls).length, 2); // 목록은 다시 받지 않는다
  assert.equal(document.activeElement, links()[22]);
  assert.equal(document.title, "내 기록 — EasyExplain");

  history.forward();
  await idle(page);
  assert.equal($("detail-view").hidden, false);
  assert.equal($("detail-title").textContent, "질문 23");
  assert.equal(document.activeElement, $("detail-title"));
});

test("상세: 목록으로 링크도 주소만 바꾸고, 처음부터 상세로 열었으면 그때 목록을 받는다", async () => {
  const server = historyServer(3);
  const page = installHistory((call) => server.reply(call), { url: `/history?conversation=${uuid(2)}` });
  await loadHistory();
  await idle(page);
  assert.equal(listCalls(page.calls).length, 0); // 상세만 열었을 때는 목록을 받지 않는다
  assert.equal(document.activeElement, document.body); // 처음 열 때는 포커스를 옮기지 않는다

  const event = $("back-to-list").dispatch("click", { button: 0 });
  await idle(page);

  assert.equal(event.defaultPrevented, true);
  assert.equal(location.search, "");
  assert.equal(listCalls(page.calls).length, 1);
  assert.equal(links().length, 3);
  assert.equal(document.activeElement, $("history-heading")); // 본 대화가 목록에 없을 때는 제목으로
});

test("상세: <script>·<img onerror> 가 섞인 질문·답변·제목은 글자로만 보인다", async () => {
  const attack = "<script>alert('xss')</script><img src=x onerror=alert(1)>";
  const server = historyServer(1, { turns: { 1: [turn(1, 1, attack, { answer: `답: ${attack}` })] } });
  const page = installHistory((call) => server.reply(call), { url: `/history?conversation=${uuid(1)}` });
  await loadHistory();
  await idle(page);

  const bubbles = $("detail-thread").querySelectorAll(".bubble").map((bubble) => bubble.textContent);
  assert.deepEqual(bubbles, [attack, `답: ${attack}`]);
  assert.equal($("detail-title").textContent, `${attack.slice(0, 30)}…`);
  const tags = document.root.descendants().map((element) => element.tagName);
  assert.equal(tags.includes("SCRIPT"), false);
  assert.equal(document.querySelectorAll("img").every((img) => img.className === "msg-mascot"), true);
});

test("상세: 답이 없는 턴은 원인 코드 대신 \"~해요\" 안내, 연달아 2개 이상이면 \"답을 받지 못한 질문 N개\" 로 접는다", async () => {
  const turns = [
    turn(1, 1, "질문 A"),
    turn(1, 2, "질문 B", { status: "failed", error_code: "AI_TIMEOUT", answer: null }),
    turn(1, 3, "질문 B"),
    turn(1, 4, "질문 C", { status: "failed", error_code: "RATE_LIMITED", answer: null }),
    turn(1, 5, "질문 C", { status: "failed", error_code: "RATE_LIMITED", answer: null }),
    turn(1, 6, "질문 C", { status: "failed", error_code: "AI_UPSTREAM_ERROR", answer: null }),
    turn(1, 7, "질문 C", { status: "interrupted", answer: null }),
    turn(1, 8, "질문 D"),
    turn(1, 9, "질문 E", { status: "pending", answer: null }),
  ];
  const page = installHistory((call) => historyServer(1, { turns: { 1: turns } }).reply(call), {
    url: `/history?conversation=${uuid(1)}`,
  });
  await loadHistory();
  await idle(page);

  const top = $("detail-thread").children;
  // A·답 / B·시간 초과 안내(하나뿐이라 접지 않음) / B·답 / 접힌 4개 / D·답 / E·처리 중 안내
  assert.equal(top.length, 2 + 2 + 2 + 1 + 2 + 2);
  assert.equal(top[3].className, "msg msg-ai msg-missing");
  assert.equal(top[3].querySelector(".bubble").textContent, "응답이 늦어져 답을 받지 못했어요.");
  const group = top[6];
  assert.equal(group.className, "missing-group");
  const details = group.querySelector("details");
  assert.equal(details.querySelector("summary").textContent, "답을 받지 못한 질문 4개");
  const notes = details.querySelectorAll(".msg-missing").map((item) => item.querySelector(".bubble").textContent);
  assert.deepEqual(notes, [
    "질문 한도에 걸려 답을 받지 못했어요.",
    "질문 한도에 걸려 답을 받지 못했어요.",
    "오류가 나서 답을 받지 못했어요.",
    "답을 만드는 중에 멈춰서 답이 없어요.",
  ]);
  assert.equal(top[10].querySelector(".bubble").textContent, "아직 답을 만드는 중이에요. 잠시 뒤 다시 열어 보세요.");
  const text = $("detail-thread").textContent;
  for (const code of ["AI_TIMEOUT", "RATE_LIMITED", "AI_UPSTREAM_ERROR", "interrupted", "pending", "null"]) {
    assert.equal(text.includes(code), false, code);
  }
});

test("상세: 없는 대화·남의 대화(404)는 \"대화를 찾을 수 없어요.\" + 목록 안내 (다시 시도·이어서 질문 없음)", async () => {
  const page = installHistory((call) => historyServer(1).reply(call), { url: `/history?conversation=${uuid(99)}` });
  await loadHistory();
  await idle(page);

  assert.equal($("detail-error").hidden, false);
  assert.equal($("detail-error-text").textContent, "대화를 찾을 수 없어요.");
  assert.equal($("detail-error-note").textContent, "목록에서 다시 골라 주세요.");
  assert.equal($("detail-retry").hidden, true);
  assert.equal($("continue-top").hidden, true);
  assert.equal($("continue-bottom").hidden, true);
  assert.equal($("detail-title").textContent, "");
});

test("상세: 주소의 id 모양이 틀리면 서버에 묻지 않고 같은 안내", async () => {
  for (const id of ["../me/chats", "not-a-uuid", "", `${uuid(1)}x`]) {
    const page = installHistory((call) => historyServer(1).reply(call), { url: `/history?conversation=${encodeURIComponent(id)}` });
    await loadHistory();
    await idle(page);

    assert.deepEqual(page.calls, [], id);
    assert.equal($("detail-error-text").textContent, "대화를 찾을 수 없어요.", id);
  }
});

test("상세: 서버 오류면 서버 문구와 다시 시도 — 누르면 다시 불러온다", async () => {
  const server = historyServer(1, { turns: { 1: MIXED_TURNS } });
  let details = 0;
  const page = installHistory((call) => {
    details += 1;
    if (details === 1) return error(503, "DB_ERROR", "데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요.");
    return server.reply(call);
  }, { url: `/history?conversation=${uuid(1)}` });
  await loadHistory();
  await idle(page);

  assert.equal($("detail-error-text").textContent, "데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요.");
  assert.equal($("detail-retry").hidden, false);

  $("detail-retry").click();
  await idle(page);

  assert.equal($("detail-error").hidden, true);
  assert.equal($("detail-thread").querySelectorAll(".bubble").length, 4);
});

test("상세: 이어서 질문 링크는 그 대화로 채팅 화면을 연다 (/chat?conversation=<id>)", async () => {
  const page = installHistory((call) => historyServer(2).reply(call), { url: `/history?conversation=${uuid(2)}` });
  await loadHistory();
  await idle(page);

  for (const link of [$("continue-top"), $("continue-bottom")]) {
    assert.equal(link.hidden, false);
    assert.equal(link.href, `/chat?conversation=${uuid(2)}`);
  }
});

test("상세: 질문이 없는 대화는 안내하고, 이어서 질문(첫 질문부터)은 열어 둔다", async () => {
  const page = installHistory((call) => historyServer(1, { turns: { 1: [] } }).reply(call), {
    url: `/history?conversation=${uuid(1)}`,
  });
  await loadHistory();
  await idle(page);

  assert.equal($("detail-status").textContent, "이 대화에는 아직 질문이 없어요.");
  assert.equal($("detail-title").textContent, "새 대화");
  assert.equal($("detail-meta").textContent, "질문 0개 · 시작 2026. 10. 9. 오전 9:00:00");
  assert.equal($("continue-bottom").hidden, false);
});

test("상세: 늦게 온 응답은 그사이 목록으로 돌아갔으면 그리지 않는다", async () => {
  const server = historyServer(2);
  const later = deferred();
  const page = installHistory((call) => (call.url.startsWith("/api/me/") ? server.list(call) : later.promise));
  await loadHistory();
  await idle(page);
  links()[0].click();
  history.back();
  await new Promise((resolve) => setTimeout(resolve, 0));

  later.resolve(server.detail({ url: `/api/conversations/${uuid(1)}` }));
  await idle(page);

  assert.equal($("detail-view").hidden, true);
  assert.equal($("detail-thread").children.length, 0);
  assert.equal(document.title, "내 기록 — EasyExplain");
});
