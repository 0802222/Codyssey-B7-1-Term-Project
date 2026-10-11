-- 사용자별 최근 대화 20건을 조회합니다.
-- 대화 원문이 포함될 수 있어 운영 DB에서 자동 실행하지 않습니다.
SELECT
    users.email,
    conversations.title AS conversation_title,
    chat_turns.created_at,
    chat_turns.level,
    chat_turns.status,
    chat_turns.question,
    chat_turns.answer
FROM chat_turns
-- JOIN: 대화 제목 연결
JOIN conversations ON conversations.id = chat_turns.conversation_id
-- JOIN: 사용자 이메일 연결
JOIN users ON users.id = chat_turns.user_id
-- WHERE: 지정한 이메일의 사용자만 조회
WHERE users.email = :email
-- ORDER BY: 최신 턴 우선, 같은 시각이면 큰 ID 우선
ORDER BY chat_turns.created_at DESC, chat_turns.id DESC
-- LIMIT: 최대 20건
LIMIT 20;
