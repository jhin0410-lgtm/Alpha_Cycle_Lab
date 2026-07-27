# Data Contracts

## OHLCV

필수 열은 `date,ticker,open,high,low,close,volume,trading_value`입니다.
`adjusted_close,market,sector,theme,is_halted`는 선택입니다. 날짜-종목 중복, 결측, 음수,
0 이하 가격, 비정상 high/low를 거부합니다. `is_halted`는 boolean, 0/1 또는 명확한
true/false 문자열만 허용합니다. 검증 결과에는 전체 기간, 종목별 시작·종료 날짜와 행 수,
요청 시 최신성 차이가 포함됩니다. 데이터는 날짜·종목 순으로 안정 정렬됩니다.

날짜는 캘린더가 제공된 경우 반드시 실제 거래 세션이어야 합니다. 거래일은 ISO 날짜 형식으로
저장하고, 체결 timestamp는 ISO 8601 with timezone offset 형식으로 저장합니다.
예: `2024-01-03T09:00:00+09:00`.

## Price Basis

- `raw`: 실제 체결과 시가평가에 사용하는 원시 OHLCV
- `split_adjusted`: 분할 효과를 소급 조정한 분석용 가격
- `total_return_adjusted`: 배당까지 소급 조정한 총수익 분석용 가격

`adjusted_close`가 있어도 `close`를 자동 대체하지 않습니다. 백테스트 엔진은 실행과
포트폴리오 평가에 `raw`만 허용합니다. 조정 가격과 기업행동 이벤트를 동시에 적용해
이중 조정하지 않습니다.

## Financial Statements

필수 열은 다음과 같습니다.

```text
ticker,metric,period_end,fiscal_period,value,unit,
available_date,retrieved_at,source,revision_id,revision_sequence
```

선택 열은 `period_start,currency`입니다. 자연키는
`ticker,metric,period_end,fiscal_period`입니다.

- `available_date >= period_end`
- `retrieved_at >= available_date`
- `revision_sequence`는 0 이상의 정수
- 같은 자연키에서 revision_sequence와 revision_id는 각각 고유
- revision_sequence가 증가할수록 available_date가 과거로 역행할 수 없음
- period_start가 있으면 `period_start <= period_end`

`FinancialStatementStore.as_of(D, policy=...)`는 D까지 공개된 revision만 사용합니다.
`ticker`와 `metric` 필터를 선택적으로 적용할 수 있습니다.

## Macro Series

필수 열은 다음과 같습니다.

```text
series_id,observation_date,frequency,value,unit,
available_date,retrieved_at,source,revision_id,revision_sequence
```

자연키는 `series_id,observation_date`입니다.

- `available_date >= observation_date`
- `retrieved_at >= available_date`
- revision_sequence와 revision_id는 자연키 안에서 각각 고유
- 수정 순서가 증가할 때 공개일이 과거로 역행할 수 없음

`MacroSeriesStore.as_of(D, policy=...)`는 D까지 공개된 revision만 반환하며 series_id로
필터링할 수 있습니다.

## Revision Policy

- `first_release`: 평가일까지 공개된 값 중 자연키별 최초 공개 revision을 고정
- `latest_known`: 평가일까지 공개된 값 중 자연키별 최신 revision을 선택

어느 정책도 평가일 이후 공개되는 수정치를 과거에 소급 노출하지 않습니다.
`ResearchDataPortal.snapshot(D)`는 재무와 거시 저장소에 동일한 정책을 적용하고 방어적
복사본을 반환합니다. 현재 `CsvFinancialDataAdapter`와 `CsvMacroDataAdapter`는 로컬 파일만
읽으며 네트워크를 사용하지 않습니다.

## Orders

`orders.csv`는 주문당 한 행을 사용합니다.

```text
order_id,created_at,ticker,side,quantity,reference_price,status,rejection_reason,
order_type,time_in_force,limit_price,filled_quantity,remaining_quantity,
last_attempt_at,last_attempt_reason
```

- `order_type`: `market` 또는 `limit`
- `time_in_force`: `day` 또는 `gtc`
- `status`: `pending`, `partially_filled`, `filled`, `rejected`, `cancelled`, `expired`
- `quantity`: 주문 원수량이며 변경되지 않음
- `filled_quantity`: 모든 Fill의 누적 수량
- `remaining_quantity = quantity - filled_quantity`
- limit 주문은 양수 `limit_price`가 필수이고 market 주문은 limit_price를 가질 수 없음
- DAY 주문은 해당 일봉의 한 번의 시도 후 잔량이 expired가 됨
- GTC 주문은 잔량이 있으면 다음 데이터 세션으로 이월됨

## Fills

`fills.csv`는 개별 부분체결당 한 행을 사용합니다.

```text
fill_id,order_id,timestamp,ticker,side,quantity,price,commission,tax,slippage
```

`fill_id`는 전체 백테스트에서 고유하고 `order_id`는 여러 행에 반복될 수 있습니다. 각 Fill의
수수료·세금·슬리피지는 해당 부분체결 수량에 대해서만 계산합니다. 일봉 지정가 체결은 실제
장중 시각을 알 수 없으므로 세션 close timestamp를 사용합니다.

## Execution Capacity and Halts

종목별 세션 체결 한도는 다음과 같습니다.

```text
floor(volume * max_volume_participation)
```

같은 종목의 여러 주문은 이 수량을 공유합니다. `is_halted=true`인 행은 체결 가능 수량을
사용하지 않고 모든 주문 시도를 차단합니다. 거래정지 여부를 가격 변화나 거래량 0만으로
추정하지 않습니다.

## Corporate Actions

필수 열은 다음과 같습니다.

```text
ticker,action_type,effective_date,available_date,source,revision_id
```

선택 열은 다음과 같습니다.

```text
ratio,cash_amount,currency,record_date,pay_date
```

지원 유형은 `split`, `reverse_split`, `cash_dividend`, `stock_dividend`, `delisting`입니다.
데이터 계약은 모든 유형을 검증하지만 엔진 회계는 현재 `split`과 `reverse_split`만
지원합니다.

- split/reverse_split: `ratio > 0`, `ratio != 1`, `cash_amount` 금지
- cash_dividend: non-negative `cash_amount`와 `currency` 필수, `ratio` 금지
- stock_dividend: positive `ratio` 필수
- delisting: 강제청산 가격을 추정하지 않음

strict 모드에서는 `available_date <= effective_date`를 요구합니다. 동일 ticker,
action_type, effective_date 중복은 거부합니다. 캘린더가 주입되면 effective_date는
거래 세션이어야 합니다. 분할 결과가 정수 수량이 아니면 fractional share 현금 정산을
추정하지 않습니다.

`CorporateActionStore.as_of(D)`는 `available_date <= D`인 이벤트만 반환합니다.
`actions_effective_on(session, information_date=D)`는 해당 시점에 알려진 이벤트만
결정론적으로 반환합니다.

## Universe Membership

필수 열은 다음과 같습니다.

```text
universe,ticker,member_from,member_to,available_date,source,revision_id
```

활성 조건은 다음과 같습니다.

```text
member_from <= session < member_to
```

`member_to`가 비어 있으면 아직 편출되지 않은 것으로 간주합니다. `member_to`는 exclusive
경계입니다. 동일 universe와 ticker의 기간 중복, 잘못된 날짜 범위, 빈 식별자를 거부합니다.
strict 모드에서는 `available_date <= member_from`을 요구합니다.

`UniverseMembershipStore.members_as_of()`는 요청한 session에 활성 상태이며
information_date까지 공개된 ticker만 정렬된 tuple로 반환합니다. 현재 구성종목을 과거
전체 기간에 소급 적용하지 않습니다.

## Generic Point-in-Time

필수 열은 `observation_date,available_date,retrieved_at,source,revision_id`입니다.
`available_date`는 관측일보다 빠를 수 없습니다. `PointInTimeStore.as_of(D)`는
`available_date <= D`인 행만 복사해 반환하므로 미래 공개 데이터를 차단합니다.
수정치 선택이 필요한 재무·거시 데이터는 위 전용 저장소와 revision_sequence 계약을
사용합니다. 실제 공개 시각과 개정 이력의 품질은 공급자가 보증해야 합니다.

## Audit Outputs

기업행동이 없어도 `corporate_actions.csv`는 다음 헤더를 가진 빈 파일을 생성합니다.

```text
effective_date,ticker,action_type,ratio,quantity_before,quantity_after,
average_cost_before,average_cost_after,cash_effect,status,reason
```

주문이나 체결이 없어도 `orders.csv`, `fills.csv`, `trades.csv`는 위 계약의 헤더를
유지합니다.
