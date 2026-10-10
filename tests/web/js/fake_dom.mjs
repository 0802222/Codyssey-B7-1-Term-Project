// 화면 JS(chat.js·history.js·api.js)를 브라우저 없이 Node 에서 돌리기 위한 흉내 (C 담당, EE-14·EE-17)
//
// 스크립트가 쓰는 만큼만 만든 작은 DOM, 그리고 fetch·sessionStorage·location·history(방문 기록)·
// IntersectionObserver·requestAnimationFrame 을 흉내 낸다. 스크립트는 불러오는 순간 document 에서 요소를 찾아
// 처리기를 달기 때문에, 테스트마다 install() 로 새 화면을 만든 뒤 loadChat()·loadHistory() 로 새로 불러온다.
import { copyFileSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

class FakeText {
  constructor(text) {
    this.textContent = String(text);
    this.parentNode = null;
  }

  remove() {
    this.parentNode?.removeChildNode(this);
  }
}

class FakeElement {
  constructor(doc, tag) {
    this.ownerDocument = doc;
    this.tagName = tag.toUpperCase();
    this.childNodes = [];
    this.parentNode = null;
    this.attributes = {};
    this.dataset = {};
    this.listeners = {};
    this.hidden = false;
    this.disabled = false;
    this.className = "";
    this.id = "";
  }

  get children() {
    return this.childNodes.filter((node) => node instanceof FakeElement);
  }

  get childElementCount() {
    return this.children.length;
  }

  get textContent() {
    return this.childNodes.map((node) => node.textContent).join("");
  }

  set textContent(text) {
    this.replaceChildren();
    if (text !== "") this.append(String(text));
  }

  adopt(node) {
    const child = typeof node === "string" ? new FakeText(node) : node;
    child.parentNode?.removeChildNode(child);
    child.parentNode = this;
    return child;
  }

  removeChildNode(node) {
    this.childNodes = this.childNodes.filter((child) => child !== node);
    node.parentNode = null;
  }

  append(...nodes) {
    for (const node of nodes) this.childNodes.push(this.adopt(node));
  }

  prepend(...nodes) {
    this.childNodes.unshift(...nodes.map((node) => this.adopt(node)));
  }

  replaceChildren(...nodes) {
    for (const child of [...this.childNodes]) this.removeChildNode(child);
    this.append(...nodes);
  }

  remove() {
    this.parentNode?.removeChildNode(this);
  }

  get isConnected() {
    let node = this;
    while (node.parentNode) node = node.parentNode;
    return node === this.ownerDocument.root;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  addEventListener(type, listener) {
    (this.listeners[type] ??= []).push(listener);
  }

  // 사용자의 동작을 흉내 낸다: 처리기를 부르고 이벤트(preventDefault 했는지)를 돌려준다
  dispatch(type, fields = {}) {
    const event = {
      type,
      defaultPrevented: false,
      preventDefault() {
        this.defaultPrevented = true;
      },
      ...fields,
    };
    for (const listener of this.listeners[type] ?? []) listener(event);
    return event;
  }

  // 마우스 왼쪽 버튼으로 누른 것과 같다 (보조 키 없이). 새 탭 열기 같은 누르기는 dispatch 로 흉내 낸다
  click() {
    if (!this.disabled && !this.hidden) {
      this.dispatch("click", { button: 0, ctrlKey: false, metaKey: false, shiftKey: false, altKey: false });
    }
  }

  requestSubmit() {
    this.dispatch("submit");
  }

  focus() {
    this.ownerDocument.activeElement = this;
  }

  scrollIntoView() {}

  get offsetHeight() {
    return 0;
  }

  // 숨긴(hidden) 요소 안에 있으면 상자가 없다 — chat.js 가 포커스를 돌려줄 곳을 고를 때 본다
  getClientRects() {
    for (let node = this; node; node = node.parentNode) {
      if (node.hidden) return [];
    }
    return this.isConnected ? [{}] : [];
  }

  descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants()]);
  }

  querySelectorAll(selector) {
    return this.descendants().filter((element) => matches(element, selector));
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] ?? null;
  }
}

// chat.js 와 테스트가 쓰는 선택자만 안다. 모르는 선택자면 바로 알 수 있게 오류를 낸다
function matches(element, selector) {
  if (selector.startsWith(".")) return element.className.split(/\s+/).includes(selector.slice(1));
  if (selector === 'button[type="submit"]') return element.tagName === "BUTTON" && element.type === "submit";
  if (selector === "button[data-question]") {
    return element.tagName === "BUTTON" && element.dataset.question !== undefined;
  }
  if (selector === 'input[name="level"]:checked') {
    return element.tagName === "INPUT" && element.name === "level" && element.checked === true;
  }
  if (selector === 'input[name="level"]') return element.tagName === "INPUT" && element.name === "level";
  if (selector === '[aria-hidden="true"]') return element.getAttribute("aria-hidden") === "true";
  if (/^[a-z]+$/.test(selector)) return element.tagName === selector.toUpperCase(); // 태그 이름 (li, details 등)
  throw new Error(`가짜 DOM 이 모르는 선택자: ${selector}`);
}

class FakeDocument {
  constructor(title = "") {
    this.root = new FakeElement(this, "html");
    this.body = new FakeElement(this, "body");
    this.root.append(this.body);
    this.activeElement = this.body;
    this.title = title;
  }

  createElement(tag) {
    return new FakeElement(this, tag);
  }

  getElementById(id) {
    return this.root.descendants().find((element) => element.id === id) ?? null;
  }

  querySelector(selector) {
    return this.root.querySelector(selector);
  }

  querySelectorAll(selector) {
    return this.root.querySelectorAll(selector);
  }
}

// 요소를 만드는 짧은 도우미: el("tag", { 속성 }, ...자식)
function builder(doc) {
  return (tag, props = {}, ...children) => {
    const element = doc.createElement(tag);
    Object.assign(element, props);
    element.append(...children);
    return element;
  };
}

// chat.html 에서 chat.js 가 찾는 요소만 같은 id·속성으로 만든다
function chatPage() {
  const doc = new FakeDocument("채팅 — EasyExplain");
  const el = builder(doc);
  doc.body.append(
    el("input", { type: "radio", name: "level", value: "easy", checked: true, dataset: { label: "아주 쉽게" } }),
    el("input", { type: "radio", name: "level", value: "beginner", checked: false, dataset: { label: "입문자" } }),
    el("input", { type: "radio", name: "level", value: "advanced", checked: false, dataset: { label: "전공자" } }),
    el("button", { id: "new-chat", type: "button" }, "새 대화"),
    el("div", { id: "chat-empty" }),
    el("ol", { id: "thread" }),
    el("div", { id: "chat-loading" }),
    el(
      "div",
      { id: "chat-error", hidden: true },
      el("span", { id: "chat-error-text" }),
      el("p", { id: "chat-error-note" }),
      el("button", { id: "chat-retry", type: "button", hidden: true }, "다시 보내기"),
    ),
    el(
      "div",
      { id: "follow-ups", hidden: true },
      ...["더 쉽게", "예시 하나 더", "핵심만"].map((question) =>
        el("button", { type: "button", dataset: { question } }, question),
      ),
    ),
    el(
      "form",
      { id: "chat-form" },
      el("textarea", { id: "question", value: "", maxLength: 2000, readOnly: false, selectionStart: 0, selectionEnd: 0 }),
      el("span", { id: "question-count" }, "0 / 2000"),
      el("button", { type: "submit", dataset: { busyLabel: "기다리는 중…" } }, "보내기"),
    ),
  );
  return doc;
}

// history.html 에서 history.js 가 찾는 요소만 같은 id·속성으로 만든다. 값은 HISTORY_RULES·CHAT_INPUT_RULES 와 같다.
// detail: 주소에 conversation 이 있으면 서버가 처음부터 상세 칸을 보이게 그린다 (app/web/router.py)
function historyPage({ detail }) {
  const doc = new FakeDocument("내 기록 — EasyExplain");
  const el = builder(doc);
  const errorBox = (name) =>
    el(
      "div",
      { id: `${name}-error`, hidden: true },
      el("span", { id: `${name}-error-text` }),
      el("p", { id: `${name}-error-note` }),
      el("button", { id: `${name}-retry`, type: "button", hidden: true }, "다시 시도"),
    );
  doc.body.append(
    el(
      "div",
      { id: "history", dataset: { pageSize: "20", untitled: "새 대화", titleMaxLength: "30" } },
      el("h1", { id: "history-heading" }, "내 기록"),
      el(
        "ul",
        { id: "level-names", hidden: true },
        el("li", { dataset: { level: "easy" } }, "아주 쉽게"),
        el("li", { dataset: { level: "beginner" } }, "입문자"),
        el("li", { dataset: { level: "advanced" } }, "전공자"),
      ),
      el(
        "div",
        { id: "list-view", hidden: detail },
        el("p", { id: "list-status" }, detail ? "" : "기록을 불러오는 중이에요."),
        errorBox("list"),
        el("div", { id: "list-empty", hidden: true }),
        el("ul", { id: "conversation-list", hidden: true }),
        el("button", { id: "list-more", type: "button", hidden: true, dataset: { busyLabel: "불러오는 중…" } }, "더 보기"),
      ),
      el(
        "div",
        { id: "detail-view", hidden: !detail },
        el("a", { id: "back-to-list", href: "/history" }, "목록으로"),
        el("a", { id: "continue-top", href: "/chat", hidden: true }, "이어서 질문"),
        el("h2", { id: "detail-title" }),
        el("p", { id: "detail-meta" }),
        el("p", { id: "detail-status" }, detail ? "대화를 불러오는 중이에요." : ""),
        errorBox("detail"),
        el("ol", { id: "detail-thread" }),
        el("a", { id: "continue-bottom", href: "/chat", hidden: true }, "이어서 질문"),
      ),
    ),
  );
  return doc;
}

// IntersectionObserver 흉내: history.js 가 지켜보는 항목을 테스트가 "화면에 보였다" 로 알린다 (showOnScreen)
const observers = [];
class FakeIntersectionObserver {
  constructor(callback, options) {
    this.callback = callback;
    this.options = options;
    this.watched = new Set();
    observers.push(this);
  }

  observe(element) {
    this.watched.add(element);
  }

  unobserve(element) {
    this.watched.delete(element);
  }

  disconnect() {
    this.watched.clear();
  }
}

// 이 요소들이 화면에 들어왔다고 알린다 (스크롤해서 보이게 된 것과 같다)
export function showOnScreen(elements) {
  for (const observer of observers) {
    const entries = elements
      .filter((element) => observer.watched.has(element))
      .map((target) => ({ target, isIntersecting: true }));
    if (entries.length > 0) observer.callback(entries, observer);
  }
}

// 지금 지켜보는(아직 첫 질문을 묻지 않은) 항목 수
export function watchedCount() {
  return observers.reduce((sum, observer) => sum + observer.watched.size, 0);
}

// 응답을 테스트가 원하는 때에 보내려고 쓰는 약속: const later = deferred(); … later.resolve(json(200, …))
export function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

// 서버 응답 흉내
export const json = (status, data) => ({ ok: status >= 200 && status < 300, status, json: async () => data });
export const error = (status, code, message) => json(status, { error: { code, message, request_id: "r" } });
// 성공 헤더(200)는 받았는데 본문을 받는 중에 연결이 끊긴 경우 — response.json() 이 실패한다
export const brokenBody = (status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => {
    throw new TypeError("본문을 받는 중에 연결이 끊김");
  },
});
// 서버에 닿지 못함, 또는 응답을 받지 못함(fetch 가 실패)
export const offline = () => {
  throw new TypeError("Failed to fetch");
};

// 새 화면과 브라우저 전역(fetch·sessionStorage·location·history·window)을 흉내 내 설치한다.
// reply(call, calls) 는 요청 하나에 대한 응답(또는 그 약속)을 돌려주거나 offline() 처럼 던진다.
// url: 화면을 연 주소 — /history 로 시작하면 내 기록 화면, 아니면 채팅 화면.
// intersection: false 면 IntersectionObserver 가 없는 브라우저
export function install(reply, { token = "token-1", url = "/chat", intersection = true } = {}) {
  const onHistory = url.startsWith("/history");
  const doc = onHistory ? historyPage({ detail: url.includes("conversation=") }) : chatPage();
  const storage = new Map(token ? [["csrf_token", token]] : []);
  const calls = [];
  let inFlight = 0; // 응답을 아직 받지 못한 요청 수
  globalThis.document = doc;
  const windowListeners = {};
  globalThis.window = {
    innerHeight: 800,
    addEventListener(type, listener) {
      (windowListeners[type] ??= []).push(listener);
    },
    fire(type) {
      for (const listener of windowListeners[type] ?? []) listener({ type });
    },
  };
  globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0);
  observers.length = 0;
  if (intersection) {
    globalThis.IntersectionObserver = FakeIntersectionObserver;
  } else {
    delete globalThis.IntersectionObserver;
  }
  globalThis.sessionStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key),
  };
  const address = { url };
  globalThis.location = {
    replaced: null,
    replace(next) {
      this.replaced = next;
    },
    get pathname() {
      return new URL(address.url, "http://localhost").pathname;
    },
    get search() {
      return new URL(address.url, "http://localhost").search;
    },
  };
  // 방문 기록: pushState 는 새 칸을 쌓고 replaceState 는 지금 칸을 바꾼다. back()·forward() 는 칸을 옮긴 뒤
  // 브라우저처럼 popstate 를 알린다. urls 에는 화면이 바꾼 주소를 순서대로 남긴다
  const entries = [url];
  let index = 0;
  globalThis.history = {
    urls: [],
    get length() {
      return entries.length;
    },
    replaceState(_state, _title, next) {
      entries[index] = next;
      address.url = next;
      this.urls.push(next);
    },
    pushState(_state, _title, next) {
      entries.splice(index + 1, entries.length, next);
      index += 1;
      address.url = next;
      this.urls.push(next);
    },
    back() {
      if (index === 0) return;
      index -= 1;
      address.url = entries[index];
      window.fire("popstate");
    },
    forward() {
      if (index === entries.length - 1) return;
      index += 1;
      address.url = entries[index];
      window.fire("popstate");
    },
  };
  globalThis.fetch = async (url, init = {}) => {
    const call = {
      url,
      method: init.method ?? "GET",
      headers: init.headers ?? {},
      body: init.body ? JSON.parse(init.body) : null,
      cache: init.cache,
    };
    calls.push(call);
    inFlight += 1;
    try {
      return await reply(call, calls);
    } finally {
      inFlight -= 1;
    }
  };
  return {
    doc,
    storage,
    calls,
    get inFlight() {
      return inFlight;
    },
  };
}

// chat.js·history.js 는 /static/js/api.js 를 주소로 불러온다. 같은 폴더의 api.js 로 바꾼 사본을 임시 폴더에 두고
// 테스트마다 새로 불러온다 (주소 뒤의 ?n= 이 다르면 Node 가 새 모듈로 실행한다)
const JS_DIR = new URL("../../../app/static/js/", import.meta.url);
const copies = mkdtempSync(join(tmpdir(), "easyexplain-js-"));
const IMPORT = 'from "/static/js/api.js"';
for (const name of ["chat.js", "history.js"]) {
  const source = readFileSync(new URL(name, JS_DIR), "utf8");
  if (!source.includes(IMPORT)) throw new Error(`${name} 에 ${IMPORT} 가 없다`);
  writeFileSync(join(copies, name), source.replace(IMPORT, 'from "./api.js"'));
}
copyFileSync(new URL("api.js", JS_DIR), join(copies, "api.js"));
let loaded = 0;

export async function loadChat() {
  loaded += 1;
  await import(`${pathToFileURL(join(copies, "chat.js")).href}?n=${loaded}`);
}

export async function loadHistory() {
  loaded += 1;
  await import(`${pathToFileURL(join(copies, "history.js")).href}?n=${loaded}`);
}

// 내 기록 화면이 보낸 요청이 모두 끝나고 화면이 그려질 때까지 기다린다 (응답을 붙잡아 둔 요청이 있으면 쓰지 않는다)
export async function idle(page) {
  let quiet = 0;
  for (let i = 0; i < 400; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
    quiet = page.inFlight === 0 ? quiet + 1 : 0;
    if (quiet >= 3) return;
  }
  throw new Error("요청이 끝나지 않았다");
}

// chat.js 가 비동기로 보내고 받는 동안 기다린다 (보내기 버튼이 풀리고 "답변을 만드는 중" 이 빌 때까지)
export async function settle() {
  for (let i = 0; i < 200; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
    const send = document.querySelector('button[type="submit"]');
    if (!send.disabled && document.getElementById("chat-loading").childElementCount === 0) return;
  }
  throw new Error("보내기가 끝나지 않았다");
}
