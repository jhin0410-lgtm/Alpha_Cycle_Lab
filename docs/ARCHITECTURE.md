# Architecture

라이브 시장 인텔리전스 처리 순서는 다음과 같습니다.

```text
TossInvestReadOnlyClient
→ OAuth2 token cache / rate-limit retry
→ current prices + 1m or 1d candles
→ response schema and OHLC validation
→ MarketIntelligenceCollector
→ explainable technical features
→ content-addressed immutable snapshot
→ future outcome labels / thesis / learning loop
```

백테스트와 paper-state 처리 순서는 다음과 같습니다.

```text
TradingCalendar
→ MarketDataFeed / PriceBasis / is_halted
→ CorporateActionStore
→ UniverseMembershipStore
→ ResearchDataPortal
   ├─ FinancialStatementStore
   └─ MacroSeriesStore
→ Strategy
→ RebalanceSchedule
→ TargetPosition
→ Order lifecycle queue
→ RiskManager
→ SimulatedBroker
→ Fill(s)
→ Portfolio
→ PaperTradingStore (optional session checkpoint)
→ ReadOnlyBrokerSnapshot
→ ReconciliationGate
   ├─ ready: comparison passed
   ├─ review_required: warning, submission disabled
   └─ blocked: mismatch, submission disabled
→ Reporting
   ├─ benchmark alignment / factor attribution
   └─ scenario path stress / factor stress / breakeven
```

`TossInvestReadOnlyClient`는 외부 네트워크를 사용하는 유일한 현재 구현이지만 공식 호스트와
읽기 전용 시장 데이터 경로만 허용합니다. 현재가를 최대 200종목까지 묶음 조회하고 캔들은
종목별로 수집합니다. 토큰은 만료 직전까지 메모리에만 캐시하며 429와 일시적 5xx는 제한된
횟수만 재시도합니다. 계좌·자산·주문 API는 이 어댑터에 존재하지 않습니다.

`MarketIntelligenceCollector`는 provider 응답을 곧바로 전략 또는 주문으로 전달하지 않습니다.
원본 payload, 정규화된 현재가와 캔들, 계산된 feature를 하나의 snapshot으로 묶고 canonical
JSON SHA-256으로 식별합니다. snapshot에는 adjusted 여부와 수집 시각이 포함되며 access token과
자격증명은 포함되지 않습니다. 이 경계 뒤에서만 사후 수익률 라벨과 모델 검증을 수행합니다.

전략 인터페이스에는 브로커가 전달되지 않으므로 직접 주문할 수 없습니다.
`MarketDataFeed.history_through(date)`는 현재 이벤트 날짜 이후 행을 반환하지 않습니다.
시점별 유니버스가 주입되면 전략이 받는 history는 해당 세션에 알려진 active ticker로만
제한됩니다. 미래 편입 이력은 `available_date` 조건 때문에 과거 전략 입력에 노출되지
않습니다.

`ResearchDataPortal`은 가격 피드와 독립적인 연구 데이터 경계입니다. 재무·거시 저장소는
자연키별 초도치와 수정치를 모두 보존하고, 평가일의 `available_date` 이전에 공개된 행만
선택합니다. `first_release`는 최초 공개값을 고정하고 `latest_known`은 평가일 당시까지 알려진
최신 수정치를 사용합니다. 두 저장소의 결과는 하나의 `ResearchSnapshot`으로 복사되어
전략 또는 연구 코드에 전달될 수 있습니다. 외부 API 호출은 어댑터 경계 밖에 있으며 현재
구현은 로컬 CSV/DataFrame만 읽습니다.

기업행동은 각 세션의 주문 처리 전에 적용됩니다. 현재 `split`과 `reverse_split`만
포트폴리오 수량·평균원가·마지막 평가가격에 반영합니다. cash dividend, stock dividend,
delisting은 안전한 회계 정책이 구현될 때까지 실행을 중단합니다.

`next_open` 목표는 큐에 보관되었다가 다음 실제 거래 세션에 주문으로 생성됩니다.
`same_close`는 전략이 당일 종가를 본 뒤 주문을 생성한다는 강한 가정이므로 사용자가
명시해야 합니다. 이미 열린 GTC 주문은 신규 목표 주문보다 먼저 다음 세션에서 체결을
시도하며, 신규 목표 수량 계산은 열린 주문의 잔량을 예상 보유수량에 포함해 중복 주문을
방지합니다.

주문은 원수량과 `filled_quantity`, `remaining_quantity`를 분리합니다. DAY 주문은 해당
일봉의 한 번의 체결 시도 후 잔량이 만료되고, GTC 주문은 `pending` 또는
`partially_filled` 상태로 다음 세션에 이월됩니다. 여러 주문은 종목별 일일 거래량 참여
한도를 공유합니다. 한 주문은 여러 `Fill`을 만들 수 있으며 각 체결에는 고유 `fill_id`가
부여됩니다.

시장가 주문은 선택한 open/close 기준가격에 슬리피지를 적용합니다. 지정가 주문은 일봉의
high/low로 지정가 도달 여부만 판정합니다. 정확한 장중 체결 순서는 알 수 없으므로 지정가
체결의 감사 timestamp는 해당 세션 close를 사용합니다. `is_halted=true`인 세션은 체결을
만들지 않으며 DAY 잔량은 만료되고 GTC 잔량은 유지됩니다.

`PaperTradingStore`는 선택적 로컬 지속성 경계입니다. 한 SQLite 파일은 하나의 run identity를
보존하며 세션 날짜, 시장 입력 fingerprint, 최신 주문 상태, 체결, 현금, 포지션, 평가가격과
비용 누계를 하나의 트랜잭션으로 기록합니다. 동일 세션과 동일 payload 재처리는 멱등적이고,
다른 payload 또는 중복 fill ID는 전체 commit을 취소합니다.

각 paper session은 canonical JSON payload hash와 이전 session hash를 연결한 state hash를
가집니다. 재시작 시 최신 portfolio와 open order를 복구할 수 있으며, hash chain 또는 fill
index가 일치하지 않으면 fail-closed합니다.

`ReadOnlyBrokerSnapshot`은 네트워크 어댑터가 아니라 검증된 JSON 입력 계약입니다. 실제
계좌번호 대신 SHA-256 account reference만 허용하고, snapshot ID와 timezone-aware 수집시각,
현금, 포지션, 활성 주문과 체결을 보존합니다. 중복 ID와 비정상 수치, 오래된 스냅샷은
reconciliation 전에 거부합니다.

`ReconciliationGate`는 검증된 PaperTradingStore를 임시 normalized audit view로 변환한 뒤
브로커 snapshot과 비교합니다. 현금·포지션 수량·활성 주문·누적 체결 불일치는 blocking이고,
평균원가 차이는 warning입니다. warning도 자동 주문 제출을 허용하지 않습니다. 현재는 결과만
계산하고 `KISBrokerAdapter`의 주문 실행 경로는 계속 비활성입니다.

백테스트 종료 후 `strategy_returns_from_result()`가 equity audit trail을 일별 단순수익률로
변환합니다. 벤치마크·팩터 계층은 이 경로를 외부 수익률과 정렬하며 결측값을 forward-fill하지
않습니다. 스트레스 계층은 같은 전략 수익률 경로를 입력으로 받아 명시적 수익률 이동,
변동성 배수, 반복 비용 및 특정 날짜 일회성 충격을 적용합니다. 원본 equity curve나 포트폴리오
회계를 수정하지 않고 별도 감사 산출물을 생성합니다.

팩터 스트레스는 `calculate_factor_attribution()`이 추정한 고정 OLS alpha와 beta를 입력으로
사용합니다. 사용자가 지정한 factor shock과 beta의 곱을 합산해 1기간 추정 수익률을 만들며,
포지션별 재평가나 위기 시 beta 변화를 추정하지 않습니다. 브레이크이븐 계산은 원본 수익률
경로의 terminal growth를 1로 만드는 일회성 수익률과 기간별 비용 드래그를 수치적으로 계산합니다.

포트폴리오는 `Decimal` 현금·원가·비용과 정수 수량을 사용합니다. 분할은 총 원가와 현금,
실현손익을 바꾸지 않습니다. fractional share가 생기는 병합은 임의 반올림하지 않고
중단합니다. 성과 비율과 스트레스 계산은 pandas 입출력 경계 뒤에서 float로 계산합니다.
주문 ID, fill ID, 정렬, 전략 동률 처리와 감사 출력은 모두 결정론적입니다.

`BrokerAdapter`는 향후 확장 경계입니다. 현재 실행 가능한 구현은 네트워크를 쓰지 않는
`SimulatedBroker`뿐입니다. `KISBrokerAdapter`는 문서화된 안전 스텁이고 언제나 예외를
발생시킵니다. broker reconciliation 성공은 주문 기능 활성화를 의미하지 않습니다.
