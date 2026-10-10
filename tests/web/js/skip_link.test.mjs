// 본문으로 건너뛰기(skip-link.js)를 Node 에서 그대로 실행해 확인한다 (C 담당, EE-21)
//   node --test tests/web/js/   (pytest 는 tests/web/test_chat_js_behavior.py 에서 이 폴더를 부른다)
//
// 링크를 누르면(키보드 Enter 도 click) 기본 동작(주소에 #main, 방문 기록 +1)을 막고 본문(main)으로 포커스만 옮겨야 한다.
import assert from "node:assert/strict";
import { test } from "node:test";

let loaded = 0;

// base.html 에서 skip-link.js 가 찾는 두 요소만 흉내 낸다. main 이 없는 화면도 만들 수 있다
async function load({ withMain = true } = {}) {
  const listeners = {};
  const page = { focused: null };
  const link = { addEventListener: (type, listener) => (listeners[type] ??= []).push(listener) };
  const main = { focus: () => { page.focused = "main"; } };
  globalThis.document = {
    querySelector: (selector) => (selector === ".skip-link" ? link : null),
    getElementById: (id) => (id === "main" && withMain ? main : null),
  };
  loaded += 1;
  await import(`${new URL("../../../app/static/js/skip-link.js", import.meta.url).href}?n=${loaded}`);
  page.click = () => {
    const event = { defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
    for (const listener of listeners.click ?? []) listener(event);
    return event;
  };
  return page;
}

test("누르면 주소를 바꾸지 않고(기본 동작을 막고) 본문으로 포커스를 옮긴다", async () => {
  const page = await load();
  const event = page.click();
  assert.equal(event.defaultPrevented, true, "주소에 #main 이 붙으면 방문 기록이 늘어 뒤로 가기·채팅 주소가 어긋난다");
  assert.equal(page.focused, "main");
});

test("본문이 없는 화면이면 막지 않고 링크 기본 동작에 맡긴다", async () => {
  const page = await load({ withMain: false });
  const event = page.click();
  assert.equal(event.defaultPrevented, false);
  assert.equal(page.focused, null);
});
