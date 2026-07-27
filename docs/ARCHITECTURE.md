# Architecture

처리 순서는 다음과 같습니다.

```text
TradingCalendar
→ MarketDataFeed / PriceBasis
→ CorporateActionStore
→ UniverseMembershipStore
→ Strategy
→ RebalanceSchedule
→ TargetPosition
→ RiskManager
→ SimulatedBroker
→ Portfolio
→ Reporting
```

전략 인터페이스에는 브로커가 전달되지 않으므로 직접 주문할 수 없습니다.
`MarketDataFeed.history_through(date)`는 현재 이벤트 날짜 이후 행을 반환하지 않습니다.
시점별 유니버스가 주입되면 전략이 받는 history는 해당 세션에 알려진 active ticker로만
제한됩니다. 미래 편입 이력은 `available_date` 조건 때문에 과거 전략 입력에 노출되지
않습니다.

기업행동은 각 세션의 주문 처리 전에 적용됩니다. 현재 `split`과 `reverse_split`만
포트폴리오 수량·평균원가·마지막 평가가격에 반영합니다. cash dividend, stock dividend,
delisting은 안전한 회계 정책이 구현될 때까지 실행을 중단합니다.

`next_open` 목표는 큐에 보관되었다가 다음 실제 거래 세션의 장 시작 시가로 주문화됩니다.
마지막 거래일 목표는 실행 가격이 없으므로 체결되지 않습니다. `same_close`는 전략이 당일
종가를 본 뒤 그 종가로 체결한다는 강한 가정이므로 사용자가 명시해야 합니다.

포트폴리오는 `Decimal` 현금·원가·비용과 정수 수량을 사용합니다. 분할은 총 원가와 현금,
실현손익을 바꾸지 않습니다. fractional share가 생기는 병합은 임의 반올림하지 않고
중단합니다. 성과 비율은 pandas 입출력 경계 뒤에서 float로 계산합니다. 주문 ID, 정렬,
전략 동률 처리와 감사 출력은 모두 결정론적입니다.

`BrokerAdapter`는 향후 확장 경계입니다. 현재 실행 가능한 구현은 네트워크를 쓰지 않는
`SimulatedBroker`뿐입니다. `KISBrokerAdapter`는 문서화된 안전 스텁이고 언제나 예외를
발생시킵니다.
