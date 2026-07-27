# Security

실제 키, 계좌번호, 원시·개인 데이터, 주문/체결 로그를 커밋하지 마십시오. `.env.example`
에는 placeholder만 있으며 `.env*`는 예외 파일을 제외하고 무시됩니다. `secrets/`,
`credentials/`, `data/raw/`, `data/private/`, `outputs/`, 로컬 DB도 무시됩니다.

현재 코드는 외부 API에 연결하지 않습니다. `BrokerAdapter.live_trading_enabled` 기본값은
`False`이고 KIS 스텁은 모든 실행에서 예외를 발생시킵니다. 실전 어댑터를 추가하려면 별도
위협 모델, 키 저장소, 사용자 확인, 주문 한도, kill switch, 감사 로그, 모의투자 검증이
필수입니다. 취약점은 공개 이슈보다 저장소 소유자에게 비공개로 보고하십시오.

