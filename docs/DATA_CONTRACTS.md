# Data Contracts

## OHLCV

필수 열은 `date,ticker,open,high,low,close,volume,trading_value`입니다.
`adjusted_close,market,sector,theme`은 선택입니다. 날짜-종목 중복, 결측, 음수,
0 이하 가격, 비정상 high/low를 거부합니다. 검증 결과에는 전체 기간, 종목별 시작·종료
날짜와 행 수, 요청 시 최신성 차이가 포함됩니다. 데이터는 날짜·종목 순으로 안정 정렬됩니다.

날짜는 캘린더가 제공된 경우 반드시 실제 거래 세션이어야 합니다. 거래일은 ISO 날짜 형식으로
저장하고, 체결/주문 timestamp는 ISO 8601 with timezone offset 형식으로 저장합니다.
예: `2024-01-03T09:00:00+09:00`.

## Price Basis

- `raw`: 실제 체결과 시가평가에 사용하는 원시 OHLCV
- `split_adjusted`: 분할 효과를 소급 조정한 분석용 가격
- `total_return_adjusted`: 배당까지 소급 조정한 총수익 분석용 가격

`adjusted_close`가 있어도 `close`를 자동 대체하지 않습니다. 백테스트 엔진은 실행과
포트폴리오 평가에 `raw`만 허용합니다. 조정 가격과 기업행동 이벤트를 동시에 적용해
이중 조정하지 않습니다.

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

## Point-in-Time

필수 열은 `observation_date,available_date,retrieved_at,source,revision_id`입니다.
`available_date`는 관측일보다 빠를 수 없습니다. `PointInTimeStore.as_of(D)`는
`available_date <= D`인 행만 복사해 반환하므로 미래 공개 데이터를 차단합니다.
실제 공개 시각과 개정 이력의 품질은 공급자가 보증해야 합니다.

## Audit Outputs

기존 출력에 `corporate_actions.csv`가 추가됩니다. 기업행동이 없어도 다음 헤더를 가진
빈 파일을 생성합니다.

```text
effective_date,ticker,action_type,ratio,quantity_before,quantity_after,
average_cost_before,average_cost_after,cash_effect,status,reason
```
