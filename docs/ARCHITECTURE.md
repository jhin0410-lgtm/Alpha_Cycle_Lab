# Architecture

처리 순서는 `TradingCalendar → MarketDataFeed → Strategy → RebalanceSchedule →
TargetPosition → RiskManager → SimulatedBroker → Fill → Portfolio → Reporting`입니다.
전략 인터페이스에는 브로커가 전달되지 않으므로 직접 주문할 수 없습니다.

`MarketDataFeed.history_through(date)`는 현재 이벤트 날짜 이후 행을 반환하지 않습니다.
`next_open` 모드의 목표는 큐에 보관되었다가 다음 실제 거래 세션의 장 시작 시가로
주문화됩니다. 마지막 거래일 목표는 실행 가격이 없으므로 체결되지 않습니다.
`same_close`는 전략이 당일 종가를 본 뒤 그 종가로 체결한다는 강한 가정이므로
사용자가 명시해야 합니다.

포트폴리오는 `Decimal` 현금·원가·비용과 정수 수량을 사용합니다. 성과 비율은 pandas
입출력 경계 뒤에서 float로 계산합니다. 주문 ID, 정렬, 전략 동률 처리는 모두
결정론적입니다.

`BrokerAdapter`는 향후 확장 경계입니다. 현재 실행 가능한 구현은 네트워크를 쓰지 않는
`SimulatedBroker`뿐입니다. `KISBrokerAdapter`는 문서화된 안전 스텁이고 언제나 예외를
발생시킵니다.

