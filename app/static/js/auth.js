/*
 * 회원가입·로그인 폼 (EE-09) — /signup, /login 이 함께 쓴다.
 *
 * 1. 보내기 전에 입력 규칙을 화면에서 먼저 확인하고, 어긋나면 무엇을 고칠지 오류 칸에 알려 준다.
 * 2. 규칙에 맞으면 페이지를 새로 불러오지 않고 fetch 로 JSON API 를 부른다.
 * 3. 보내는 동안 버튼을 잠가 같은 요청이 두 번 가지 않게 한다.
 * 4. 실패하면 서버가 보낸 error.message 를 오류 칸에 보여 주고, 입력값은 지우지 않는다.
 * 5. 성공하면 가입은 로그인 화면으로, 로그인은 채팅 화면으로 이동한다.
 *
 * 규칙의 값(글자 수, 비밀번호에 영어만 받는지)은 이 파일에 적지 않고 HTML 에서 읽는다 —
 * 입력칸의 minlength·maxlength 와 비밀번호 칸의 data-ascii-only. 그 값은 app/web/router.py 의
 * AUTH_INPUT_RULES 한곳에서 정한다. 화면 검사는 빨리 알려 주기 위한 것이고, 최종 검사는 서버가 한다.
 * 이메일 형식은 서버만 검사한다 (서버의 "올바른 이메일 형식을 입력해 주세요." 가 그대로 나온다).
 */

// 서버의 오류 문구를 받지 못했을 때 보여 줄 문구
const NETWORK_ERROR_MESSAGE = "서버에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.";
const UNKNOWN_ERROR_MESSAGE = "일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요.";

// 영어만 받는 비밀번호에 쓸 수 있는 글자: 영문·숫자·기호와 공백 (ASCII 32~126). 한글·이모지는 안 된다
const ENGLISH_ONLY = /^[\x20-\x7E]*$/;
const NOT_ENGLISH_MESSAGE = "비밀번호는 영어(영문·숫자·기호)로만 입력해 주세요.";

// 로그인 응답의 csrf_token 을 보관하는 이름. 채팅 화면(EE-12·EE-14)이 같은 이름으로 꺼내
// 로그인 뒤 POST 요청의 X-CSRF-Token 헤더에 붙인다.
const CSRF_TOKEN_KEY = "csrf_token";

const errorBox = document.getElementById("form-error");
const errorText = document.getElementById("form-error-text");

// moveFocus: 제출할 때는 오류 칸으로 포커스를 옮긴다. 입력하는 도중(붙여 넣기)에는 칸에 그대로 둔다
function showError(message, { moveFocus = true } = {}) {
  errorText.textContent = message; // HTML 이 아니라 글자로만 넣는다
  errorBox.hidden = false; // role="alert" 라서 나타나는 순간 스크린리더가 읽는다
  if (moveFocus) {
    errorBox.focus(); // 포커스를 오류 칸으로 옮긴다. 여기서 Tab 을 누르면 이메일 칸이다
  }
}

function clearError() {
  errorBox.hidden = true;
  errorText.textContent = ""; // 입력칸의 aria-describedby 가 지난 오류를 읽지 않게 비운다
}

// 이 탭의 sessionStorage 에 보관한다. 페이지를 옮겨도 남고, 탭을 닫으면 지워진다.
// 브라우저 설정으로 저장소를 쓸 수 없으면 건너뛴다 — 그때는 다음 화면이 GET /api/auth/me 로 다시 받는다.
function saveCsrfToken(token) {
  try {
    sessionStorage.setItem(CSRF_TOKEN_KEY, token);
  } catch {
    // 로그인 자체는 끝났으므로 이동은 그대로 한다
  }
}

// 응답 본문을 JSON 으로 읽는다. JSON 이 아니면(프록시의 HTML 오류 페이지 등) null
async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

// 보내기 전 검사: 규칙에 어긋나면 안내 문구를, 맞으면 "" 를 돌려준다. 위의 칸부터 하나씩 본다
function findInputProblem(form) {
  const { email, password } = form.elements;

  if (email.value.trim() === "") return "이메일을 입력해 주세요.";
  if (email.value.length > email.maxLength) {
    return `이메일은 ${email.maxLength}자 이하로 입력해 주세요.`;
  }
  if (password.value === "") return "비밀번호를 입력해 주세요.";
  if (password.hasAttribute("data-ascii-only") && !ENGLISH_ONLY.test(password.value)) {
    return NOT_ENGLISH_MESSAGE;
  }
  if (password.value.length < password.minLength || password.value.length > password.maxLength) {
    return `비밀번호는 ${password.minLength}~${password.maxLength}자로 입력해 주세요.`;
  }
  return "";
}

// 붙여 넣기 검사: 브라우저는 maxlength 를 넘는 뒷부분을 말없이 잘라 넣는다. 잘린 값으로 가입되지 않게,
// 붙여 넣을 글이 칸의 최대 길이보다 길거나 영어만 받는 칸에 다른 글자가 섞여 있으면 안내 문구를 돌려준다
function findPasteProblem(input, clipboardText) {
  const text = clipboardText.replace(/[\r\n]/g, ""); // 한 줄 입력칸에는 줄바꿈이 들어가지 않는다
  if (input.hasAttribute("data-ascii-only") && !ENGLISH_ONLY.test(text)) {
    return NOT_ENGLISH_MESSAGE;
  }
  if (text.length > input.maxLength) {
    const field = input.name === "email" ? "이메일은" : "비밀번호는";
    return `${field} ${input.maxLength}자까지 입력할 수 있어요.`;
  }
  return "";
}

// form 을 보내면 apiUrl 로 이메일·비밀번호를 POST 하고, 성공하면 onSuccess(응답 JSON) 를 부른다
function connectAuthForm(form, apiUrl, onSuccess) {
  const button = form.querySelector('button[type="submit"]');
  const idleLabel = button.textContent;

  function setSending(sending) {
    button.disabled = sending;
    button.textContent = sending ? button.dataset.busyLabel || idleLabel : idleLabel;
  }

  for (const input of [form.elements.email, form.elements.password]) {
    input.addEventListener("paste", (event) => {
      const problem = findPasteProblem(input, event.clipboardData?.getData("text") ?? "");
      if (problem) {
        event.preventDefault(); // 넣지 않는다 → 입력칸은 붙여 넣기 전 그대로
        showError(problem, { moveFocus: false });
      }
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault(); // 브라우저 기본 전송(페이지 이동)을 막는다 → 입력값이 그대로 남는다
    if (button.disabled) return; // 이미 보내는 중이면 무시한다

    clearError();
    const problem = findInputProblem(form);
    if (problem) {
      showError(problem); // 서버에 보내지 않는다. 입력값은 그대로 둔다
      return;
    }
    setSending(true);

    let response;
    try {
      response = await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // 비밀번호는 앞뒤 공백까지 그대로 보낸다 (명세: 공백을 지우지 않는다)
        body: JSON.stringify({
          email: form.elements.email.value,
          password: form.elements.password.value,
        }),
        credentials: "same-origin", // 같은 출처의 쿠키만 주고받는다 (로그인 응답의 세션 쿠키)
      });
    } catch {
      // 서버에 닿지 못했다 (인터넷 끊김, 서버 꺼짐)
      setSending(false);
      showError(NETWORK_ERROR_MESSAGE);
      return;
    }

    const data = await readJson(response);
    if (response.ok) {
      onSuccess(data); // 이동하는 동안 다시 누르지 못하게 버튼은 잠근 채로 둔다
      return;
    }
    setSending(false);
    showError(data?.error?.message || UNKNOWN_ERROR_MESSAGE);
  });
}

// 이동할 때 replace 를 쓰면 방금 페이지가 방문 기록에서 빠져서,
// 뒤로 가기로 입력이 채워진 폼에 다시 돌아오지 않는다.

const signupForm = document.getElementById("signup-form");
if (signupForm) {
  connectAuthForm(signupForm, "/api/auth/signup", () => {
    // 가입 API 는 계정만 만들고 로그인 상태(세션)는 만들지 않는다 → 로그인 화면으로.
    // joined=1 이면 로그인 화면이 "가입이 끝났어요" 안내를 띄운다 (이메일은 주소에 넣지 않는다)
    location.replace("/login?joined=1");
  });
}

const loginForm = document.getElementById("login-form");
if (loginForm) {
  connectAuthForm(loginForm, "/api/auth/login", (data) => {
    // 세션 쿠키는 브라우저가 알아서 저장한다(HttpOnly 라 JS 는 못 읽는다). csrf_token 만 직접 보관한다
    if (data?.csrf_token) {
      saveCsrfToken(data.csrf_token);
    }
    location.replace("/chat");
  });
}
