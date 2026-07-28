# Security

실제 키, 계좌번호, 원시·개인 데이터, 주문/체결 로그를 커밋하지 마십시오. `.env.example`
에는 placeholder만 있으며 `.env*`는 예외 파일을 제외하고 무시됩니다. `secrets/`,
`credentials/`, `data/raw/`, `data/private/`, `outputs/`, 로컬 DB도 무시됩니다.

토스증권 연동은 현재 OAuth2 client credentials와 계좌 비의존 시장 데이터에만 한정됩니다.
`TOSSINVEST_CLIENT_ID`와 `TOSSINVEST_CLIENT_SECRET`은 로컬 환경변수로만 읽으며, 어댑터는
공식 `https://openapi.tossinvest.com` 호스트만 허용합니다. access token과 client secret은
예외 메시지, snapshot, CSV, 테스트 fixture 또는 로그에 기록하지 않습니다.

토스증권 어댑터의 경로 allow-list에는 현재가·캔들 등 읽기 전용 시장 데이터만 존재합니다.
계좌 조회와 주문 생성·정정·취소·조건주문 경로는 구현하지 않았고, allow-list 밖의 요청은
실행 전에 거부합니다. `BrokerAdapter.live_trading_enabled` 기본값은 `False`이고 KIS 스텁도
모든 실행에서 예외를 발생시킵니다.

브로커 reconciliation 입력은 읽기 전용 JSON 파일이며 `account_ref_hash`에는 64자리 SHA-256
16진수만 허용합니다. 실제 계좌번호, 앱 키, 시크릿, access token, refresh token, 주민번호,
전화번호와 이메일을 snapshot, 감사 출력 또는 테스트 fixture에 넣지 않습니다. 계좌 hash도
공개 저장소가 아니라 `data/private/`에서 관리하는 것을 기본 정책으로 합니다.

reconciliation 결과가 `ready`가 아니면 주문 제출을 허용하지 않습니다. 오래된 snapshot,
미래 timestamp, 현금·수량·주문·체결 불일치, 알 수 없는 broker 주문과 미기록 fill은
fail-closed합니다. 평균원가 warning도 자동 주문을 허용하지 않습니다.

실전 또는 모의투자 어댑터를 추가하려면 별도 위협 모델, OS 또는 클라우드 키 저장소, 최소 권한,
사용자 확인, 주문 한도, idempotency key, rate limit, kill switch, 감사 로그, 응답 원문 보존,
broker reconciliation, 체결 정정 정책과 독립 보안검토가 필수입니다. 취약점은 공개 이슈보다
저장소 소유자에게 비공개로 보고하십시오.
