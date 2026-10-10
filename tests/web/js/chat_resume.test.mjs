// 채팅 화면의 이어서 질문(/chat?conversation=<대화 id>)과 주소 맞추기를 실제 chat.js 로 실행해 확인한다 (C 담당, EE-17)
//   node --test tests/web/js/*.test.mjs   (pytest 는 tests/web/test_chat_js_behavior.py 에서 이 파일도 부른다)
import assert from "node:assert/strict";
import { test } from "node:test";

import { deferred, error, install, json, loadChat, offline, settle } from "./fake_dom.mjs";

const CONVERSATION = "9b1c4da5-7a74-4f97-88cb-1b2790e510a9";
const NEW_CONVERSATION = "1c0fd1a2-3b4c-4d5e-8f60-718293a4b5c6";
const $ = (id) => document.getElementById(id);
const bubbles = () => $("thread").children.map((item) => item.querySelector(".bubble").textContent);
const chatCalls = (calls) => calls.filter((call) => call.url === "/api/chat");
const createCalls = (calls) => calls.filter((call) => call.url === "/api/conversations");
const checkedLevel = () => document.querySelector('input[name="level"]:checked').value;

function turn(id, question, extra = {}) {
  return {
    id,
    conversation_id: CONVERSATION,
    level: "easy",
    question,
    answer: `답변 ${id}`,
    status: "completed",
    error_code: null,
    created_at: "2026-10-09T01:00:00Z",
    ...extra,
  };
}

const PAST = [
  turn(1, "API가 뭐야?", { level: "easy" }),
  turn(2, "더 쉽게", { status: "failed", error_code: "AI_TIMEOUT", answer: null }),
  turn(3, "예시 하나 더", { level: "advanced", created_at: "2026-10-09T15:30:00Z" }),
];

// 서버 흉내: 지난 대화 상세, 대화 만들기, 질문(늘 성공 — chat 으로 바꿀 수 있다)
function serve({ detail = () => json(200, { conversation: { id: CONVERSATION, title: "새 대화" }, turns: PAST }), chat } = {}) {
  let answers = 0;
  return (call) => {
    if (call.url.startsWith("/api/conversations/")) return detail(call);
    if (call.url === "/api/conversations") return json(201, { id: NEW_CONVERSATION, title: "새 대화" });
    if (call.url === "/api/auth/me") return json(200, { user: { id: 1 }, csrf_token: "token-2" });
    answers += 1;
    if (chat) return chat(call, answers);
    return json(200, {
      request_id: `r${answers}`,
      turn_id: 100 + answers,
      conversation_id: call.body.conversation_id,
      level: call.body.level,
      question: call.body.question,
      answer: `새 답변 ${answers}`,
      status: "completed",
      created_at: "2026-10-09T02:00:00Z",
    });
  };
}

async function ask(question) {
  $("question").value = question;
  $("chat-form").dispatch("submit");
  await settle();
}

async function openAt(url, reply = serve()) {
  const page = install(reply, { url });
  await loadChat();
  await settle();
  return page;
}

test("이어서 질문: 주소의 대화를 불러와 답을 받은 턴만 그리고, 다음 질문은 대화를 만들지 않고 같은 대화로 보낸다", async () => {
  const { calls } = install(serve(), { url: `/chat?conversation=${CONVERSATION}` });
  // 대화 칸의 aria-live 를 바꾸는 순서를 남긴다 (지난 대화를 그리는 동안 껐다가 다시 켠다)
  const live = [];
  const setAttribute = $("thread").setAttribute.bind($("thread"));
  $("thread").setAttribute = (name, value) => {
    if (name === "aria-live") live.push(value);
    setAttribute(name, value);
  };
  await loadChat();
  await settle();
  await new Promise((resolve) => setTimeout(resolve, 5)); // 화면을 두 번 그린 뒤(requestAnimationFrame 두 번)

  assert.deepEqual(calls.map((call) => `${call.method} ${call.url}`), [`GET /api/conversations/${CONVERSATION}`]);
  // 답을 못 받은 "더 쉽게" 는 그리지 않는다 — 화면의 대화 = 서버가 문맥으로 쓰는 완료된 턴
  assert.deepEqual(bubbles(), ["API가 뭐야?", "답변 1", "예시 하나 더", "답변 3"]);
  assert.equal($("thread").children[2].querySelector(".msg-meta").textContent, "전공자 · 2026. 10. 10. 오전 12:30:00");
  assert.equal(checkedLevel(), "advanced"); // 마지막으로 답을 받은 수준
  assert.equal($("follow-ups").hidden, false);
  assert.equal($("chat-empty").hidden, true);
  assert.equal($("chat-loading").childElementCount, 0);
  assert.deepEqual(live, ["off", "polite"]); // 지난 대화를 스크린리더가 한꺼번에 읽지 않게 껐다가 다시 켰다
  assert.deepEqual(history.urls, [`/chat?conversation=${CONVERSATION}`]); // 주소는 그대로

  await ask("스마트 계약은?");

  assert.equal(createCalls(calls).length, 0);
  const [sent] = chatCalls(calls);
  assert.equal(sent.body.conversation_id, CONVERSATION);
  assert.equal(sent.body.level, "advanced");
  assert.deepEqual(bubbles().slice(-2), ["스마트 계약은?", "새 답변 1"]);
});

test("이어서 질문: 지난 대화를 불러오는 동안은 보내지 않고 안내를 보여 준다", async () => {
  const later = deferred();
  const { calls } = install(serve({ detail: () => later.promise }), { url: `/chat?conversation=${CONVERSATION}` });
  await loadChat();
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal($("chat-loading").textContent, "지난 대화를 불러오는 중이에요.");
  assert.equal($("chat-empty").hidden, true); // 새 대화 안내가 잠깐 보이지 않는다
  assert.equal(document.querySelector('button[type="submit"]').disabled, true);
  $("question").value = "기다리는 동안 보낸 질문";
  $("chat-form").dispatch("submit");
  $("new-chat").click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(chatCalls(calls), []);
  assert.deepEqual(createCalls(calls), []); // 새 대화로 새지 않는다

  later.resolve(json(200, { conversation: { id: CONVERSATION, title: "새 대화" }, turns: PAST }));
  await settle();
  await ask("기다리는 동안 보낸 질문");
  assert.equal(chatCalls(calls)[0].body.conversation_id, CONVERSATION);
});

test("이어서 질문: 없는 대화·남의 대화(404)면 안내하고 새 대화로 — 주소는 /chat, 다음 질문은 대화부터 만든다", async () => {
  const reply = serve({ detail: () => error(404, "CONVERSATION_NOT_FOUND", "대화를 찾을 수 없어요.") });
  const { calls } = await openAt(`/chat?conversation=${CONVERSATION}`, reply);

  assert.equal($("chat-error").hidden, false);
  assert.equal($("chat-error-text").textContent, "대화를 찾을 수 없어요.");
  assert.equal($("chat-error-note").textContent, "새 대화로 시작해요.");
  assert.equal($("chat-retry").hidden, true); // 다시 보낼 질문이 없다
  assert.equal($("chat-empty").hidden, false);
  assert.equal(location.search, "");
  assert.deepEqual(history.urls, ["/chat"]);

  await ask("새로 묻기");
  assert.equal(createCalls(calls).length, 1);
  assert.equal(chatCalls(calls)[0].body.conversation_id, NEW_CONVERSATION);
});

test("이어서 질문: 주소의 id 모양이 틀리면 서버에 묻지 않고 같은 안내", async () => {
  for (const id of ["../me/chats", "not-a-uuid", "", `${CONVERSATION}0`]) {
    const { calls } = await openAt(`/chat?conversation=${encodeURIComponent(id)}`);

    assert.deepEqual(calls, [], id);
    assert.equal($("chat-error-text").textContent, "대화를 찾을 수 없어요.", id);
    assert.equal($("chat-error-note").textContent, "새 대화로 시작해요.", id);
    assert.equal(location.search, "", id);
  }
});

test("이어서 질문: 서버 오류·연결 끊김이면 그 문구와 함께 새 대화로 시작하고 내 기록에서 다시 열 수 있다고 알린다", async () => {
  for (const detail of [() => error(503, "DB_ERROR", "데이터베이스 오류가 발생했어요. 잠시 후 다시 시도해 주세요."), () => offline()]) {
    await openAt(`/chat?conversation=${CONVERSATION}`, serve({ detail }));

    assert.notEqual($("chat-error-text").textContent, "");
    assert.equal(
      $("chat-error-note").textContent,
      "지난 대화를 불러오지 못해 새 대화로 시작해요. 내 기록에서 다시 열 수 있어요.",
    );
    assert.equal(location.search, "");
    assert.equal(document.querySelector('button[type="submit"]').disabled, false);
  }
});

test("이어서 질문: 로그인이 풀렸으면(401) 로그인 화면으로", async () => {
  install(serve({ detail: () => error(401, "AUTH_REQUIRED", "로그인이 필요해요.") }), {
    url: `/chat?conversation=${CONVERSATION}`,
  });
  await loadChat();
  await new Promise((resolve) => setTimeout(resolve, 10));

  assert.equal(location.replaced, "/login?expired=1");
});

test("이어서 질문: 답을 받은 턴이 없는 대화면 새 대화 안내를 보여 주되 같은 대화로 묻는다", async () => {
  const failedOnly = [turn(1, "[500] 질문", { status: "failed", error_code: "AI_UPSTREAM_ERROR", answer: null })];
  const reply = serve({ detail: () => json(200, { conversation: { id: CONVERSATION }, turns: failedOnly }) });
  const { calls } = await openAt(`/chat?conversation=${CONVERSATION}`, reply);

  assert.deepEqual(bubbles(), []);
  assert.equal($("chat-empty").hidden, false);
  assert.equal($("follow-ups").hidden, true);
  assert.equal(checkedLevel(), "easy");

  await ask("다시 묻기");
  assert.equal(createCalls(calls).length, 0);
  assert.equal(chatCalls(calls)[0].body.conversation_id, CONVERSATION);
});

test("이어서 연 대화에서 실패하면 다시 보내기는 EE-14 규칙 그대로 (같은 대화, 서버가 실패를 알려 오면 새 요청 번호)", async () => {
  const reply = serve({
    chat: (call, n) =>
      n === 1
        ? error(504, "AI_TIMEOUT", "응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요.")
        : json(200, { ...call.body, turn_id: 9, answer: "답", status: "completed", created_at: "2026-10-09T02:00:00Z" }),
  });
  const { calls } = await openAt(`/chat?conversation=${CONVERSATION}`, reply);

  await ask("실패할 질문");
  assert.equal($("chat-retry").hidden, false);
  $("chat-retry").click();
  await settle();

  const [first, second] = chatCalls(calls);
  assert.equal(first.body.conversation_id, CONVERSATION);
  assert.equal(second.body.conversation_id, CONVERSATION);
  assert.notEqual(second.body.client_request_id, first.body.client_request_id);
  assert.deepEqual(bubbles().slice(-2), ["실패할 질문", "답"]);
});

// ── 주소 맞추기 ──

test("주소: 첫 질문으로 대화를 만들면 /chat?conversation=<새 대화 id> 로 바꾼다 (방문 기록은 늘리지 않는다)", async () => {
  await openAt("/chat");
  const before = history.length;

  await ask("첫 질문");

  assert.deepEqual(history.urls, [`/chat?conversation=${NEW_CONVERSATION}`]);
  assert.equal(history.length, before); // replaceState
});

test("주소: 새 대화를 누르면 /chat 으로 — 새로고침해도 지난 대화가 다시 열리지 않는다", async () => {
  await openAt(`/chat?conversation=${CONVERSATION}`);

  $("new-chat").click();

  assert.equal(location.search, "");
  assert.deepEqual(bubbles(), []);
  assert.equal($("follow-ups").hidden, true);
});

test("주소: 질문 중에 대화가 없어지면(404) 새 대화로 다시 보내게 하고 주소도 /chat", async () => {
  const reply = serve({ chat: () => error(404, "CONVERSATION_NOT_FOUND", "대화를 찾을 수 없어요.") });
  await openAt(`/chat?conversation=${CONVERSATION}`, reply);

  await ask("없어진 대화에 질문");

  assert.equal($("chat-error-note").textContent, "다시 보내면 새 대화로 시작해요.");
  assert.equal(location.search, "");
  assert.deepEqual(bubbles(), ["없어진 대화에 질문"]); // 지난 대화는 빼고 이 질문만 남긴다 (EE-14)
});
