/*
 * 로그인 뒤 서버 API 를 부를 때 같이 쓰는 함수 — 채팅(chat.js)과 로그아웃(logout.js)이 import 한다.
 *
 * 상태를 바꾸는 요청(POST)에는 X-CSRF-Token 헤더가 필요하다 (API 명세 공통 규칙).
 * 로그인 화면(auth.js)이 로그인 응답의 csrf_token 을 이 탭의 sessionStorage 에 넣어 두고, 여기서 꺼낸다.
 * 없으면(새 탭, 저장소를 못 쓰는 브라우저) GET /api/auth/me 로 다시 받는다.
 * 응답이 401(로그인이 끝남)이면 로그인 화면으로 보낸다 (EE-14).
 *
 * type="module" 로 불러서 이 파일의 이름은 다른 스크립트(auth.js 등)와 겹치지 않는다.
 */

// auth.js 가 csrf_token 을 보관하는 이름과 같아야 한다
export const CSRF_TOKEN_KEY = "csrf_token";

// 401 일 때 가는 곳. expired=1 이면 로그인 화면이 "로그인이 풀렸어요" 안내를 띄운다 (app/web/router.py 의 login_page)
export const LOGIN_AGAIN_URL = "/login?expired=1";

// 서버의 오류 문구를 받지 못했을 때 보여 줄 문구 (auth.js 와 같은 문구)
export const NETWORK_ERROR_MESSAGE = "서버에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.";
export const UNKNOWN_ERROR_MESSAGE = "일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요.";

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

// 보관한 토큰을 지운다. 로그아웃할 때, 로그인이 풀렸을 때, 그리고 토큰이 틀렸다는 답(403 CSRF_REJECTED)을
// 받았을 때 — 다른 탭에서 다시 로그인하면 세션과 함께 토큰이 바뀌는데 이 탭에는 예전 토큰이 남아 있어서다
export function forgetCsrfToken() {
  try {
    sessionStorage.removeItem(CSRF_TOKEN_KEY);
  } catch {
    // 저장소를 쓸 수 없으면 지울 것도 없다
  }
}

// 로그인이 끝났을 때(만료, 다른 탭에서 로그아웃): 보관한 토큰을 지우고 로그인 화면으로 간다.
// replace — 지금 페이지를 방문 기록에서 빼서, 뒤로 가기로 로그인이 풀린 화면에 돌아오지 않게
export function goToLogin() {
  forgetCsrfToken();
  location.replace(LOGIN_AGAIN_URL);
}

// 로그인 뒤의 POST 요청: X-CSRF-Token 헤더 + 같은 출처의 세션 쿠키, body 가 있으면 JSON 으로 보낸다.
// 결과는 { ok, status, offline, data } — 서버에 닿지 못했으면 offline 이 true, status 는 0.
// 401 이면 로그인 화면으로 이동하고 결과를 돌려주지 않는다. 401 을 직접 다루는 곳(로그아웃)은 { redirectOn401: false }
export async function apiPost(url, body, { redirectOn401 = true } = {}) {
  let result = await sendPost(url, body);
  if (result.data?.error?.code === "CSRF_REJECTED") {
    // 토큰이 낡았다(다른 탭에서 다시 로그인해 바뀜). 서버는 이 검사에서 거절하고 요청을 처리하지 않았으니(질문 저장·
    // AI 호출 없음), sendPost 가 예전 토큰을 지운 뒤 새 토큰(GET /api/auth/me)으로 같은 요청을 한 번만 다시 보낸다
    result = await sendPost(url, body);
  }
  if (result.status === 401 && redirectOn401) {
    goToLogin();
    // 끝나지 않는 Promise: 다음 페이지를 불러오는 동안 화면이 오류를 띄우지 않고 기다리는 모습 그대로 넘어간다
    return new Promise(() => {});
  }
  return result;
}

// POST 를 한 번 보내고 결과를 { ok, status, offline, data } 로 돌려준다 (apiPost 가 부른다)
async function sendPost(url, body) {
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
    forgetCsrfToken(); // 다음에 보낼 때는 /api/auth/me 에서 새 토큰을 받는다
  }
  return { ok: response.ok, status: response.status, offline: false, data };
}

// 서버가 요청을 처리했는지 알 수 없는 실패인지: 서버에 닿지 못했거나(연결 끊김) 우리 서버의 오류 JSON 이 아닌
// 응답을 받았을 때(중간 프록시의 오류 페이지 등). 요청은 서버에 닿아 처리됐을 수도 있다.
// 우리 서버가 오류 JSON({"error": {"code", …}}) 으로 답했으면 무엇이 실패했는지 서버가 알려 준 것이다
export function outcomeUnknown(result) {
  return result.offline || (!result.ok && !result.data?.error?.code);
}

// 실패한 apiPost 결과를 화면에 보여 줄 문구로: 서버가 보낸 error.message, 못 받았으면 대체 문구
export function failureMessage(result) {
  if (result.offline) return NETWORK_ERROR_MESSAGE;
  return result.data?.error?.message || UNKNOWN_ERROR_MESSAGE;
}
