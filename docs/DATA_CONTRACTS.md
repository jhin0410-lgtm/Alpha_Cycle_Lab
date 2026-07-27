# Data Contracts

## OHLCV

필수 열은 `date,ticker,open,high,low,close,volume,trading_value`입니다.
`adjusted_close,market,sector,theme`은 선택입니다. 날짜-종목 중복, 결측, 음수,
0 이하 가격, 비정상 high/low를 거부합니다. 검증 결과에는 전체 기간, 종목별 시작·종료
날짜와 행 수, 요청 시 최신성 차이가 포함됩니다. 데이터는 날짜·종목 순으로 안정 정렬됩니다.

## Point-in-Time

필수 열은 `observation_date,available_date,retrieved_at,source,revision_id`입니다.
`available_date`는 관측일보다 빠를 수 없습니다. `PointInTimeStore.as_of(D)`는
`available_date <= D`인 행만 복사해 반환하므로 미래 공개 데이터를 차단합니다.
실제 공개 시각과 개정 이력의 품질은 공급자가 보증해야 합니다.

