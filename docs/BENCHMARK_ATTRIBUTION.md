# Benchmark Alignment and Factor Attribution

## Purpose

이 계층은 전략의 절대수익을 벤치마크 상대성과와 팩터 노출로 분해합니다. 분석은 백테스트
종료 후 수행되는 사후 통계이며 투자성과의 원인이나 미래 반복 가능성을 증명하지 않습니다.

## Input Contracts

### Benchmark returns

```text
date,benchmark,return
```

- `date`: ISO 거래일
- `benchmark`: 시리즈 식별자
- `return`: 해당 날짜의 단순수익률
- 같은 `date,benchmark` 중복 금지
- 결측·무한대·`-1` 미만 수익률 금지

### Factor returns

```text
date,factor,return
```

- `factor`: 시장, 규모, 가치, 모멘텀 등 사용자가 정의한 식별자
- 같은 `date,factor` 중복 금지
- 결측·무한대 금지
- 팩터가 long-short 수익률일 수 있으므로 benchmark와 달리 `-1` 하한을 강제하지 않음

## Alignment

전략수익률은 `equity_curve.csv`의 연속 두 시점 equity로 계산합니다. 첫 equity 행에는 이전
관측치가 없으므로 수익률 행을 만들지 않습니다.

- `strict`: 모든 전략수익률 날짜에 선택한 benchmark와 모든 factor가 있어야 함
- `inner`: 공통 날짜만 남김

어느 정책도 결측 수익률을 0, 직전 값, 다음 값으로 채우지 않습니다. 비동기 국가 시장,
휴장일, 환율 변환이 필요한 경우 사용자가 비교 가능한 일별 수익률을 먼저 구성해야 합니다.

## Benchmark Metrics

- benchmark cumulative return
- benchmark annualized return
- strategy cumulative return과 benchmark cumulative return의 차이
- tracking error: active return 표준편차의 연환산
- information ratio: active return 평균 / active return 표준편차의 연환산
- beta: strategy와 benchmark의 표본 공분산 / benchmark 표본 분산
- correlation

benchmark 분산이나 active return 분산이 0이면 관련 비율은 0으로 안전하게 반환합니다.

## Factor Model

모형은 다음의 ordinary least squares입니다.

```text
strategy_return_t = alpha + beta_1 factor_1,t + ... + beta_k factor_k,t + residual_t
```

출력:

- periodic alpha
- arithmetic annualized alpha
- factor beta
- R-squared
- annualized residual volatility
- beta × factor mean × periods_per_year 방식의 평균 연환산 factor contribution
- modeled return과 residual return 시계열

필요 관측치는 `max(minimum_factor_observations, factor_count + 2)`입니다. 설계행렬의 rank가
부족하면 다중공선성을 임의로 해결하지 않고 오류를 발생시킵니다.

## Audit Outputs

벤치마크가 제공되면 기본 8개 산출물에 다음이 추가됩니다.

- `benchmark_alignment.csv`: 정렬된 strategy, benchmark, factor, modeled, residual 수익률
- `attribution_summary.json`: benchmark 지표, factor alpha/beta/R², 정렬 정책

## Modeling Boundaries

- 팩터 정의와 원천 데이터 품질을 검증하지 않음
- 통화, 세금, 거래시간, 비동기 시장을 자동 보정하지 않음
- 일별 선형모형이며 비선형 노출과 regime 변화는 포착하지 못할 수 있음
- full-sample 계수는 기간 중 노출 변화를 숨길 수 있음
- 높은 R²는 좋은 전략을 의미하지 않고 낮은 R²는 나쁜 전략을 의미하지 않음
- 양의 alpha는 표본오차, 누락변수, 데이터마이닝의 결과일 수 있음
- 표준오차, t-statistic, Newey-West 보정, rolling attribution은 아직 지원하지 않음
