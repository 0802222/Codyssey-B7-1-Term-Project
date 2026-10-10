// 가입·로그인 폼(auth.js)을 Node 에서 그대로 실행해, 오류 안내 뒤 버튼이 다시 켜지는지 확인한다 (C 담당, EE-21)
//   node --test tests/web/js/   (pytest 는 tests/web/test_chat_js_behavior.py 에서 이 폴더를 부른다)
//
// auth.js 는 module 이 아닌 일반 스크립트라 node:vm 으로 실행하고, 쓰는 만큼만 흉내 낸 화면(오류 칸·폼·입력칸·버튼)과
// fetch·location·sessionStorage 를 넘긴다. 입력 규칙 값은 가입 화면(AUTH_INPUT_RULES)과 같게 적었다 — 값 자체는
// test_auth_pages.py·test_auth_rules_match_server.py 가 확인한다.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const SOURCE = readFileSync(new URL("../../../app/static/js/auth.js", import.meta.url), "utf8");
const EMAIL_PATTERN = String.raw`[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+`;

class FakeElement {
  constructor(props = {}) {
    this.hidden = false;
    this.disabled = false;
    this.textContent = "";
    this.dataset = {};
    this.attributes = new Set();
    this.listeners = {};
    Object.assign(this, props);
  }

  addEventListener(type, listener) {
    (this.listeners[type] ??= []).push(listener);
  }

  hasAttribute(name) {
    return this.attributes.has(name);
  }

  focus() {
    this.page.activeElement = this;
  }
}

// signup.html·login.html 에서 auth.js 가 찾는 요소만 같은 id·속성으로 만든다
function authPage(kind) {
  const page = { activeElement: null };
  const make = (props) => new FakeElement({ page, ...props });
  const errorBox = make({ id: "form-error", hidden: true });
  const errorText = make({ id: "form-error-text" });
  const email = make({ name: "email", value: "", maxLength: 100, pattern: EMAIL_PATTERN });
  const password = make({ name: "password", value: "", minLength: 8, maxLength: 64, attributes: new Set(["data-ascii-only"]) });
  const idleLabel = kind === "signup" ? "가입하기" : "로그인";
  const busyLabel = kind === "signup" ? "가입하는 중…" : "로그인하는 중…";
  const button = make({ type: "submit", textContent: idleLabel, dataset: { busyLabel } });
  const form = make({ id: `${kind}-form`, elements: { email, password } });
  form.querySelector = (selector) => (selector === 'button[type="submit"]' ? button : null);
  const byId = { "form-error": errorBox, "form-error-text": errorText, [`${kind}-form`]: form };
  page.document = { getElementById: (id) => byId[id] ?? null };
  return { page, errorBox, errorText, email, password, button, form, idleLabel, busyLabel };
}

// 화면을 만들고 auth.js 를 실행한다. reply(call) 는 서버 응답(또는 그 약속)을 돌려주거나 연결 끊김처럼 던진다
function load(kind, reply) {
  const screen = authPage(kind);
  const calls = [];
  const storage = new Map();
  const context = {
    document: screen.page.document,
    location: { replaced: null, replace(url) { this.replaced = url; } },
    sessionStorage: { setItem: (key, value) => storage.set(key, value), getItem: (key) => storage.get(key) ?? null },
    fetch: async (url, init) => {
      calls.push({ url, body: JSON.parse(init.body) });
      return reply({ url, body: JSON.parse(init.body) });
    },
  };
  vm.createContext(context);
  vm.runInContext(SOURCE, context);
  return { ...screen, calls, storage, location: context.location };
}

function submit(screen) {
  let prevented = false;
  const done = screen.form.listeners.submit[0]({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true, "브라우저 기본 전송(페이지 이동)을 막는다");
  return done;
}

function fill(screen, email, password) {
  screen.email.value = email;
  screen.password.value = password;
}

const json = (status, data) => ({ ok: status >= 200 && status < 300, status, json: async () => data });
const failure = (status, code, message) => json(status, { error: { code, message, request_id: "r" } });
function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

// 오류 안내가 뜬 뒤의 공통 모습: 버튼 잠금 해제·글자 되돌림, 오류 칸에 문구, 포커스는 오류 칸, 입력은 그대로
function assertUnlockedWithError(screen, message, email, password) {
  assert.equal(screen.button.disabled, false, "오류 안내 뒤 버튼이 다시 켜진다");
  assert.equal(screen.button.textContent, screen.idleLabel, "버튼 글자가 되돌아온다");
  assert.equal(screen.errorBox.hidden, false);
  assert.equal(screen.errorText.textContent, message);
  assert.equal(screen.page.activeElement, screen.errorBox, "포커스는 오류 칸 (다음 Tab 이 이메일 칸)");
  assert.equal(screen.email.value, email, "입력한 이메일은 지우지 않는다");
  assert.equal(screen.password.value, password, "입력한 비밀번호는 지우지 않는다");
}

for (const [kind, status, code, message] of [
  ["signup", 409, "EMAIL_ALREADY_EXISTS", "이미 가입된 이메일이에요."],
  ["login", 401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다."],
]) {
  test(`${kind}: 서버 오류(${status}) 안내 뒤 버튼 잠금이 풀린다 — 보내는 동안은 잠김`, async () => {
    const answer = deferred();
    const screen = load(kind, () => answer.promise);
    fill(screen, "guide@example.com", "guide-pass-1");
    const done = submit(screen);
    await Promise.resolve();
    assert.equal(screen.button.disabled, true, "보내는 동안 잠근다 (같은 요청이 두 번 가지 않게)");
    assert.equal(screen.button.textContent, screen.busyLabel);
    answer.resolve(failure(status, code, message));
    await done;
    assertUnlockedWithError(screen, message, "guide@example.com", "guide-pass-1");
    assert.equal(screen.location.replaced, null, "실패하면 이동하지 않는다");
  });

  test(`${kind}: 서버에 닿지 못하면 안내 후 버튼 잠금이 풀린다`, async () => {
    const screen = load(kind, () => {
      throw new TypeError("Failed to fetch");
    });
    fill(screen, "guide@example.com", "guide-pass-1");
    await submit(screen);
    assertUnlockedWithError(screen, "서버에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.", "guide@example.com", "guide-pass-1");
  });

  test(`${kind}: JSON 이 아닌 오류 응답(프록시 오류 페이지 등)도 안내 후 버튼 잠금이 풀린다`, async () => {
    const screen = load(kind, () => ({ ok: false, status: 502, json: async () => { throw new SyntaxError("HTML"); } }));
    fill(screen, "guide@example.com", "guide-pass-1");
    await submit(screen);
    assertUnlockedWithError(screen, "일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", "guide@example.com", "guide-pass-1");
  });

  test(`${kind}: 오류 뒤 다시 누르면 다시 보낸다 (풀린 버튼이 실제로 동작)`, async () => {
    let attempt = 0;
    const screen = load(kind, () => {
      attempt += 1;
      return attempt === 1 ? failure(status, code, message) : json(kind === "signup" ? 201 : 200, { csrf_token: "token-1" });
    });
    fill(screen, "guide@example.com", "guide-pass-1");
    await submit(screen);
    await submit(screen);
    assert.equal(screen.calls.length, 2);
    assert.equal(screen.location.replaced, kind === "signup" ? "/login?joined=1" : "/chat");
  });
}

test("보내는 중에 다시 눌러도(Enter 연타) 요청은 한 번만 간다", async () => {
  const answer = deferred();
  const screen = load("signup", () => answer.promise);
  fill(screen, "guide@example.com", "guide-pass-1");
  const first = submit(screen);
  await Promise.resolve();
  await submit(screen);
  answer.resolve(failure(409, "EMAIL_ALREADY_EXISTS", "이미 가입된 이메일이에요."));
  await first;
  assert.equal(screen.calls.length, 1);
});

test("보내기 전 검사에서 걸리면 서버에 보내지 않고, 버튼은 잠그지 않고, 포커스는 오류 칸", async () => {
  const screen = load("signup", () => assert.fail("서버에 보내면 안 된다"));
  fill(screen, "guide@example.com", "short");
  await submit(screen);
  assert.equal(screen.calls.length, 0);
  assertUnlockedWithError(screen, "비밀번호는 8~64자로 입력해 주세요.", "guide@example.com", "short");
});

test("성공하면 이동이 끝날 때까지 버튼은 잠근 채로 둔다 (두 번 가입되지 않게)", async () => {
  const screen = load("login", () => json(200, { csrf_token: "token-1" }));
  fill(screen, "guide@example.com", "guide-pass-1");
  await submit(screen);
  assert.equal(screen.button.disabled, true);
  assert.equal(screen.location.replaced, "/chat");
  assert.equal(screen.storage.get("csrf_token"), "token-1");
});
