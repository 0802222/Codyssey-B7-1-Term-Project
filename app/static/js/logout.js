/*
 * 로그아웃 버튼 (EE-12) — 로그인했을 때 모든 페이지 헤더에 있다 (base.html)
 *
 * POST /api/auth/logout 을 X-CSRF-Token 헤더와 함께 보낸다 (토큰은 api.js 가 sessionStorage 에서 꺼내거나,
 * 없으면 GET /api/auth/me 로 다시 받는다). 성공(204)이면 서버가 세션과 쿠키를 지운 것이고, 401 이면 세션이
 * 이미 끝난 것(만료 등)이라 어느 쪽이든 로그아웃된 상태다 → 보관한 csrf_token 을 지우고 첫 화면(/)으로 간다.
 * 그래서 다른 요청과 달리 401 에도 로그인 화면으로 보내지 않는다 (redirectOn401: false).
 */

import { apiPost, failureMessage, forgetCsrfToken } from "/static/js/api.js";

const logoutButton = document.getElementById("logout-button");
const LOGOUT_OPTIONS = { redirectOn401: false }; // 401 = 이미 로그아웃된 상태 → 아래에서 / 로 보낸다

logoutButton.addEventListener("click", async () => {
  logoutButton.disabled = true; // 보내는 동안 다시 누르지 못하게
  // 토큰이 낡았으면(403 CSRF_REJECTED — 다른 탭에서 다시 로그인) apiPost 가 새 토큰으로 한 번 더 보낸다
  const result = await apiPost("/api/auth/logout", undefined, LOGOUT_OPTIONS);
  if (result.status === 204 || result.status === 401) {
    forgetCsrfToken();
    location.replace("/"); // 방금 페이지를 방문 기록에서 빼서 뒤로 가기로 돌아오지 않게
    return;
  }
  // 서버에 닿지 못했거나 서버 오류 — 아직 로그인된 상태라 버튼을 다시 켜고 알린다
  logoutButton.disabled = false;
  window.alert(failureMessage(result));
});
