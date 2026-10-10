/*
 * 본문으로 건너뛰기 (EE-21) — 모든 페이지 맨 앞의 링크 (base.html)
 *
 * 링크의 기본 동작은 주소 끝에 #main 을 붙여 방문 기록을 하나 늘린다. 그러면 뒤로 가기가 같은 페이지 안에서 한 번
 * 멈추고, 채팅은 뒤로 가기 뒤에 주소(/chat)와 화면의 대화가 어긋나며(chat.js 의 syncAddress 는 지금 칸만 고친다),
 * 내 기록은 상세에서 돌아온 목록의 포커스가 방금 본 대화가 아니라 본문으로 간다.
 * 그래서 주소와 방문 기록은 그대로 두고 포커스만 본문(main, tabindex="-1")으로 옮긴다.
 * 스크립트가 뜨지 않은 브라우저에서는 링크 기본 동작으로 똑같이 본문에 간다.
 */

const link = document.querySelector(".skip-link");
const main = document.getElementById("main");

link?.addEventListener("click", (event) => {
  if (!main) return;
  event.preventDefault(); // 주소에 #main 을 붙이지 않는다
  main.focus(); // 본문으로 포커스 — 화면도 본문으로 스크롤되고 다음 Tab 은 본문의 첫 컨트롤
});
