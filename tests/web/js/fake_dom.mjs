// 채팅 화면 JS(chat.js·api.js)를 브라우저 없이 Node 에서 돌리기 위한 흉내 (C 담당, EE-14)
//
// chat.js 가 쓰는 만큼만 만든 작은 DOM, 그리고 fetch·sessionStorage·location 을 흉내 낸다.
// chat.js 는 불러오는 순간 document 에서 요소를 찾아 처리기를 달기 때문에, 테스트마다 install() 로
// 새 화면을 만든 뒤 loadChat() 으로 chat.js 를 새로 불러온다.
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

  click() {
    if (!this.disabled && !this.hidden) this.dispatch("click");
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
  throw new Error(`가짜 DOM 이 모르는 선택자: ${selector}`);
}

class FakeDocument {
  constructor() {
    this.root = new FakeElement(this, "html");
    this.body = new FakeElement(this, "body");
    this.root.append(this.body);
    this.activeElement = this.body;
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

// chat.html 에서 chat.js 가 찾는 요소만 같은 id·속성으로 만든다
function chatPage() {
  const doc = new FakeDocument();
  const el = (tag, props = {}, ...children) => {
    const element = doc.createElement(tag);
    Object.assign(element, props);
    element.append(...children);
    return element;
  };
  doc.body.append(
    el("input", { type: "radio", name: "level", value: "easy", checked: true, dataset: { label: "아주 쉽게" } }),
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

// 새 채팅 화면과 브라우저 전역(fetch·sessionStorage·location·history)을 흉내 내 설치한다.
// reply(call, calls) 는 요청 하나에 대한 응답을 돌려주거나 offline() 처럼 던진다. url: 화면을 연 주소
export function install(reply, { token = "token-1", url = "/chat" } = {}) {
  const doc = chatPage();
  const storage = new Map(token ? [["csrf_token", token]] : []);
  const calls = [];
  globalThis.document = doc;
  globalThis.window = { innerHeight: 800 };
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
  // 화면이 주소를 바꾸면(replaceState·pushState) 그 주소를 순서대로 남긴다
  globalThis.history = {
    urls: [],
    replaceState(_state, _title, next) {
      address.url = next;
      this.urls.push(next);
    },
    pushState(_state, _title, next) {
      address.url = next;
      this.urls.push(next);
    },
  };
  globalThis.fetch = async (url, init = {}) => {
    const call = {
      url,
      method: init.method ?? "GET",
      headers: init.headers ?? {},
      body: init.body ? JSON.parse(init.body) : null,
    };
    calls.push(call);
    return reply(call, calls);
  };
  return { doc, storage, calls };
}

// chat.js 는 /static/js/api.js 를 주소로 불러온다. 같은 폴더의 api.js 로 바꾼 사본을 임시 폴더에 두고
// 테스트마다 새로 불러온다 (주소 뒤의 ?n= 이 다르면 Node 가 새 모듈로 실행한다)
const JS_DIR = new URL("../../../app/static/js/", import.meta.url);
const copies = mkdtempSync(join(tmpdir(), "easyexplain-chat-js-"));
const chatSource = readFileSync(new URL("chat.js", JS_DIR), "utf8");
const IMPORT = 'from "/static/js/api.js"';
if (!chatSource.includes(IMPORT)) throw new Error(`chat.js 에 ${IMPORT} 가 없다`);
writeFileSync(join(copies, "chat.js"), chatSource.replace(IMPORT, 'from "./api.js"'));
copyFileSync(new URL("api.js", JS_DIR), join(copies, "api.js"));
let loaded = 0;

export async function loadChat() {
  loaded += 1;
  await import(`${pathToFileURL(join(copies, "chat.js")).href}?n=${loaded}`);
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
