/*
 * 로그인 뒤 서버 API 를 부를 때 같이 쓰는 함수 — 채팅(chat.js)과 로그아웃(logout.js)이 import 한다.
 *
 * 상태를 바꾸는 요청(POST)에는 X-CSRF-Token 헤더가 필요하다 (API 명세 공통 규칙).
 * 로그인 화면(auth.js)이 로그인 응답의 csrf_token 을 이 탭의 sessionStorage 에 넣어 두고, 여기서 꺼낸다.
 * 없으면(새 탭, 저장소를 못 쓰는 브라우저) GET /api/auth/me 로 다시 받는다.
 *
 * type="module" 로 불러서 이 파일의 이름은 다른 스크립트(auth.js 등)와 겹치지 않는다.
 */

// auth.js 가 csrf_token 을 보관하는 이름과 같아야 한다
export const CSRF_TOKEN_KEY = "csrf_token";

// 응답 본문을 JSON 으로 읽는다. JSON 이 아니면(프록시의 HTML 오류 페이지 등) null
export async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

// X-CSRF-Token 헤더에 넣을 값. 받지 못하면 null — 그때는 보낸 요청이 401·403 으로 돌아온다
export async function getCsrfToken() {
  try {
    const saved = sessionStorage.getItem(CSRF_TOKEN_KEY);
    if (saved) return saved;
  } catch {
    // 저장소를 쓸 수 없는 브라우저 — 서버에서 받는다
  }
  try {
    const response = await fetch("/api/auth/me", { credentials: "same-origin" });
    const data = await readJson(response);
    if (!response.ok || !data?.csrf_token) return null;
    try {
      sessionStorage.setItem(CSRF_TOKEN_KEY, data.csrf_token);
    } catch {
      // 보관하지 못해도 이번 요청에는 쓸 수 있다
    }
    return data.csrf_token;
  } catch {
    return null; // 서버에 닿지 못했다 — 이어서 보낼 요청도 실패한다
  }
}

// 보관한 토큰을 지운다. 로그아웃할 때, 그리고 토큰이 틀렸다는 답(403 CSRF_REJECTED)을 받았을 때 —
// 다른 탭에서 다시 로그인하면 세션과 함께 토큰이 바뀌는데 이 탭에는 예전 토큰이 남아 있어서다
export function forgetCsrfToken() {
  try {
    sessionStorage.removeItem(CSRF_TOKEN_KEY);
  } catch {
    // 저장소를 쓸 수 없으면 지울 것도 없다
  }
}

// 로그인 뒤의 POST 요청: X-CSRF-Token 헤더 + 같은 출처의 세션 쿠키, body 가 있으면 JSON 으로 보낸다.
// 결과는 { ok, status, offline, data } — 서버에 닿지 못했으면 offline 이 true, status 는 0
export async function apiPost(url, body) {
  const headers = {};
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const csrfToken = await getCsrfToken();
  if (csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }
  let response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    return { ok: false, status: 0, offline: true, data: null }; // 인터넷 끊김, 서버 꺼짐
  }
  const data = response.status === 204 ? null : await readJson(response);
  if (data?.error?.code === "CSRF_REJECTED") {
    forgetCsrfToken(); // 다음 요청은 /api/auth/me 에서 새 토큰을 받는다
  }
  return { ok: response.ok, status: response.status, offline: false, data };
}
