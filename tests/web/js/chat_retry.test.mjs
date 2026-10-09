// 채팅 화면의 다시 보내기·요청 번호 규칙을 실제 chat.js·api.js 로 실행해 확인한다 (C 담당, EE-14)
//   node --test tests/web/js/   (pytest 는 tests/web/test_chat_js_behavior.py 에서 이 파일을 부른다)
//
// 서버는 fakeServer() 로 흉내 낸다: 같은 client_request_id 로 이미 완료된 질문이면 AI 를 다시 부르지 않고
// 저장한 답을 돌려준다 (API 명세 3장 "중복 요청"). 그래서 AI 호출 수로 중복 호출이 있었는지 알 수 있다.
import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import { brokenBody, error, install, json, loadChat, offline, settle } from "./fake_dom.mjs";

const CONVERSATION = "9b1c4da5-7a74-4f97-88cb-1b2790e510a9";
const realNow = Date.now;

afterEach(() => {
  Date.now = realNow;
});

function fakeServer() {
  const turns = new Map(); // client_request_id → { status: "pending" | "completed" | "interrupted", turn }
  let aiCalls = 0;
  const answer = (body) => {
    aiCalls += 1;
    return {
      request_id: `request-${aiCalls}`,
      turn_id: aiCalls,
      conversation_id: body.conversation_id,
      level: body.level,
      question: body.question,
      answer: `답변 ${aiCalls}`,
      status: "completed",
      created_at: "2026-10-09T01:00:00Z",
    };
  };
  return {
    get aiCalls() {
      return aiCalls;
    },
    // 질문을 받아 AI 를 부르기 시작했다(pending). finish 전까지 같은 키는 409 CHAT_BUSY
    start(body) {
      turns.set(body.client_request_id, { status: "pending", turn: answer(body) });
    },
    finish(key) {
      turns.get(key).status = "completed";
    },
    // 재시작 때 남은 pending 을 서버가 중단(interrupted)으로 정리했다 (#22) → 같은 키는 503 AI_UNAVAILABLE
    interrupt(key) {
      turns.get(key).status = "interrupted";
    },
    chat(body) {
      const saved = turns.get(body.client_request_id);
      if (saved?.status === "pending") {
        return error(409, "CHAT_BUSY", "이전 질문에 답하는 중이에요. 잠시 기다려 주세요.");
      }
      if (saved?.status === "interrupted") {
        return error(503, "AI_UNAVAILABLE", "지금은 AI를 이용할 수 없어요. 잠시 후 다시 시도해 주세요.");
      }
      if (saved) return json(200, saved.turn);
      const turn = answer(body);
      turns.set(body.client_request_id, { status: "completed", turn });
      return json(200, turn);
    },
  };
}

const $ = (id) => document.getElementById(id);
const chatCalls = (calls) => calls.filter((call) => call.url === "/api/chat");
const keys = (calls) => chatCalls(calls).map((call) => call.body.client_request_id);
const bubbles = () => $("thread").children.map((item) => item.querySelector(".bubble").textContent);

async function ask(question) {
  $("question").value = question;
  $("chat-form").dispatch("submit");
  await settle();
}

async function resend() {
  $("chat-retry").click();
  await settle();
}

// reply(call, n): n 번째 /api/chat 요청(1부터)에 대한 응답. 대화 만들기와 토큰 받기는 늘 성공
function serve(reply) {
  let chats = 0;
  return (call) => {
    if (call.url === "/api/conversations") return json(201, { id: CONVERSATION, title: "새 대화" });
    if (call.url === "/api/auth/me") return json(200, { user: { id: 1 }, csrf_token: "token-2" });
    chats += 1;
    return reply(call, chats);
  };
}

test("서버가 실패를 알려 오면(504) 다시 보내기는 새 요청 번호로 보낸다", async () => {
  const server = fakeServer();
  const { calls } = install(
    serve((call, n) => (n === 1 ? error(504, "AI_TIMEOUT", "응답이 지연되고 있어요.") : server.chat(call.body))),
  );
  await loadChat();

  await ask("API가 뭐야?");
  assert.equal($("chat-error-text").textContent, "응답이 지연되고 있어요.");
  assert.equal($("chat-retry").hidden, false);
  assert.deepEqual(bubbles(), ["API가 뭐야?"]); // 실패한 질문 말풍선은 남는다

  await resend();
  const [first, second] = keys(calls);
  assert.notEqual(second, first); // 같은 키면 서버가 저장한 실패를 그대로 돌려준다
  assert.deepEqual(bubbles(), ["API가 뭐야?", "답변 1"]); // 말풍선이 두 번 쌓이지 않는다
  assert.equal($("chat-error").hidden, true);
});

test("응답을 못 받았으면(연결 끊김) 같은 요청 번호로 다시 보내 저장된 답을 받는다", async () => {
  const server = fakeServer();
  const { calls } = install(
    serve((call, n) => {
      const reply = server.chat(call.body); // 서버는 처리했다
      return n === 1 ? offline() : reply; // 첫 응답은 화면에 오지 못했다
    }),
  );
  await loadChat();

  await ask("API가 뭐야?");
  assert.match($("chat-error-text").textContent, /^서버에 연결하지 못했어요/);
  await resend();

  const [first, second] = keys(calls);
  assert.equal(second, first);
  assert.equal(server.aiCalls, 1); // AI 를 다시 부르지 않았다
  assert.deepEqual(bubbles(), ["API가 뭐야?", "답변 1"]);
});

test("처리 중(409 CHAT_BUSY)이면 시간이 지나도 같은 번호로 다시 묻고, 서버가 중단을 확정하면(503) 그때 새 번호", async () => {
  const server = fakeServer();
  let now = realNow();
  Date.now = () => now;
  const { calls } = install(
    serve((call, n) => {
      if (n === 1) {
        server.start(call.body); // 서버는 처리를 시작했는데
        return offline(); // 응답은 오지 못했다
      }
      return server.chat(call.body);
    }),
  );
  await loadChat();

  await ask("API가 뭐야?");
  for (const later of [61_000, 10 * 60_000]) {
    now += later; // 1분, 10분이 지나도
    await resend();
    assert.equal($("chat-error-text").textContent, "이전 질문에 답하는 중이에요. 잠시 기다려 주세요.");
  }
  assert.equal(new Set(keys(calls)).size, 1); // 화면은 시간만으로 실패라고 단정하지 않는다

  server.interrupt(keys(calls)[0]); // 서버가 남은 pending 을 중단으로 정리 (#22)
  await resend(); // 같은 번호 → 503 (서버가 실패를 확정)
  assert.equal($("chat-error-text").textContent, "지금은 AI를 이용할 수 없어요. 잠시 후 다시 시도해 주세요.");
  await resend(); // 이제 새 번호
  const all = keys(calls);
  assert.equal(all.length, 5);
  assert.equal(new Set(all.slice(0, 4)).size, 1);
  assert.notEqual(all[4], all[0]);
  assert.deepEqual(bubbles(), ["API가 뭐야?", "답변 2"]);
});

test("대화 만들기·통신이 늦어 처음 보낸 지 60초가 넘어도 처리 중이면 같은 번호 — AI 를 두 번 부르지 않는다 (PR #47 리뷰)", async () => {
  // 리뷰의 시간 순서: 대화 만들기 응답 50초 지연 → 질문은 50초에 서버 도착 → 51초에 연결 유실 →
  // 61초에 같은 번호로 다시 → CHAT_BUSY → 원래 질문은 75초에 완료(AI 25초) → 76초에 다시 보내기
  const server = fakeServer();
  const start = realNow();
  let now = start;
  Date.now = () => now;
  const { calls } = install((call, all) => {
    if (call.url === "/api/conversations") {
      now = start + 50_000;
      return json(201, { id: CONVERSATION, title: "새 대화" });
    }
    if (chatCalls(all).length === 1) {
      server.start(call.body);
      now = start + 51_000;
      return offline();
    }
    return server.chat(call.body);
  });
  await loadChat();

  await ask("API가 뭐야?");
  now = start + 61_000;
  await resend();
  assert.equal($("chat-error-text").textContent, "이전 질문에 답하는 중이에요. 잠시 기다려 주세요.");
  server.finish(keys(calls)[0]);
  now = start + 76_000;
  await resend();

  assert.equal(new Set(keys(calls)).size, 1);
  assert.equal(server.aiCalls, 1); // 새 번호였다면 AI 호출·완료 턴이 2개
  assert.deepEqual(bubbles(), ["API가 뭐야?", "답변 1"]);
});

test("401 이면 보관한 토큰을 지우고 /login?expired=1 로 간다", async () => {
  const { storage } = install(serve(() => error(401, "AUTH_REQUIRED", "로그인이 필요합니다.")));
  await loadChat();

  $("question").value = "API가 뭐야?";
  $("chat-form").dispatch("submit");
  for (let i = 0; i < 50 && !location.replaced; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(location.replaced, "/login?expired=1");
  assert.equal(storage.has("csrf_token"), false);
  assert.equal($("chat-error").hidden, true); // 이동하는 동안 오류 칸을 띄우지 않는다
});

test("CSRF 토큰이 낡았으면(403) 새 토큰을 받아 같은 요청을 한 번만 다시 보낸다", async () => {
  const server = fakeServer();
  const { calls, storage } = install(
    serve((call, n) => (n === 1 ? error(403, "CSRF_REJECTED", "CSRF 토큰이 유효하지 않습니다.") : server.chat(call.body))),
  );
  await loadChat();

  await ask("API가 뭐야?");
  const chats = chatCalls(calls);
  assert.equal(chats.length, 2);
  assert.equal(chats[0].headers["X-CSRF-Token"], "token-1");
  assert.equal(chats[1].headers["X-CSRF-Token"], "token-2"); // GET /api/auth/me 로 받은 새 토큰
  assert.equal(chats[1].body.client_request_id, chats[0].body.client_request_id); // 서버는 처리하지 않았다
  assert.equal(storage.get("csrf_token"), "token-2");
  assert.deepEqual(bubbles(), ["API가 뭐야?", "답변 1"]);
});

test("질문 한도(429)면 정한 시간 동안 보내기를 잠그고 남은 초를 보여 준 뒤 새 번호로 다시 보낸다", async () => {
  const server = fakeServer();
  const limited = () => error(429, "RATE_LIMITED", "질문 요청 한도를 초과했어요. 잠시 후 다시 시도해 주세요.");
  const { calls } = install(serve((call, n) => (n === 1 ? limited() : server.chat(call.body))));
  await loadChat();

  $("question").value = "API가 뭐야?";
  $("chat-form").dispatch("submit");
  for (let i = 0; i < 50 && $("chat-error").hidden; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));

  const send = document.querySelector('button[type="submit"]');
  assert.equal($("chat-retry").disabled, true);
  assert.equal(send.disabled, true);
  assert.equal($("question").readOnly, true);
  assert.equal($("chat-error-note").querySelector('[aria-hidden="true"]').textContent, "10초 뒤에 다시 보낼 수 있어요.");
  $("chat-form").dispatch("submit"); // 잠긴 동안에는 보내지 않는다
  assert.equal(chatCalls(calls).length, 1);

  Date.now = () => realNow() + 10_500;
  await new Promise((resolve) => setTimeout(resolve, 300)); // 남은 시간을 고치는 타이머가 한 번 돈다
  assert.equal($("chat-error-note").textContent, "이제 다시 보낼 수 있어요.");
  assert.equal($("chat-retry").disabled, false);

  await resend();
  const [first, second] = keys(calls);
  assert.notEqual(second, first);
});

// ── PR #47 리뷰(vivleon)에서 찾은 두 경로 ──

test("성공(200) 헤더를 받았는데 본문을 못 읽으면 같은 요청 번호로 다시 보낸다", async () => {
  const server = fakeServer();
  const { calls } = install(
    serve((call, n) => {
      const reply = server.chat(call.body); // 서버는 답을 저장했다
      return n === 1 ? brokenBody(200) : reply; // 본문을 받는 중에 연결이 끊겼다
    }),
  );
  await loadChat();

  await ask("API가 뭐야?");
  assert.equal($("chat-error-text").textContent, "일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요.");
  await resend();

  const [first, second] = keys(calls);
  assert.equal(second, first);
  assert.equal(server.aiCalls, 1); // 새 번호였다면 AI 를 두 번 부르고 완료 턴이 2개 생긴다
  assert.deepEqual(bubbles(), ["API가 뭐야?", "답변 1"]);
});

test("응답을 못 받은 뒤 넘치는 붙여 넣기를 막아도 요청 번호를 지켜, 그대로 보내면 같은 번호", async () => {
  const server = fakeServer();
  const { calls } = install(
    serve((call, n) => {
      const reply = server.chat(call.body);
      return n === 1 ? offline() : reply;
    }),
  );
  await loadChat();

  await ask("API가 뭐야?");
  const paste = $("question").dispatch("paste", { clipboardData: { getData: () => "가".repeat(2000) } });
  assert.equal(paste.defaultPrevented, true); // 넣지 않는다 → 입력칸의 질문은 그대로
  assert.equal($("question").value, "API가 뭐야?");
  assert.equal($("chat-error-text").textContent, "질문은 2000자까지 입력할 수 있어요.");
  assert.equal($("chat-retry").hidden, false); // 다시 보내기는 남는다
  assert.deepEqual(bubbles(), ["API가 뭐야?"]); // 답을 못 받은 말풍선도 남는다

  $("chat-form").dispatch("submit"); // 입력칸에 그대로 남은 같은 질문을 보낸다
  await settle();
  const [first, second] = keys(calls);
  assert.equal(second, first);
  assert.equal(server.aiCalls, 1);
  assert.deepEqual(bubbles(), ["API가 뭐야?", "답변 1"]);
});

test("응답을 못 받은 뒤 빈 질문 안내가 떠도 요청 번호를 지켜, 질문을 되돌려 보내면 같은 번호", async () => {
  const server = fakeServer();
  const { calls } = install(
    serve((call, n) => {
      const reply = server.chat(call.body);
      return n === 1 ? offline() : reply;
    }),
  );
  await loadChat();

  await ask("API가 뭐야?");
  $("question").value = "   ";
  $("chat-form").dispatch("submit"); // 보내지 않고 안내만
  assert.equal($("chat-error-text").textContent, "질문을 입력해 주세요.");
  assert.equal($("chat-retry").hidden, false);
  assert.equal(chatCalls(calls).length, 1);

  await ask("API가 뭐야?");
  const [first, second] = keys(calls);
  assert.equal(second, first);
  assert.equal(server.aiCalls, 1);
});
