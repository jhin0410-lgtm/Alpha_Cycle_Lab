# Scenario and Stress Testing

## Purpose

이 계층은 완료된 백테스트의 일별 전략 수익률을 명시적인 가정 아래 변형해 민감도와 손실
흡수 여력을 확인합니다. 미래 가격을 예측하거나 실제 위기 확률을 산정하지 않습니다.

## YAML Contract

최상위 키는 `path_scenarios`와 `factor_scenarios`입니다. 둘 중 하나 이상이 있어야 하며 모든
시나리오 이름은 대소문자를 무시하고 고유해야 합니다. `base`는 자동 생성되는 기준 경로이므로
사용자 시나리오 이름으로 사용할 수 없습니다.

### Path scenario

```yaml
path_scenarios:
  - name: liquidity_shock
    recurring_shift_bps: -10
    volatility_multiplier: 1.75
    cost_drag_bps: 5
    one_time_shock: -0.12
    shock_date: 2024-03-15
```

- `recurring_shift_bps`: 모든 기간 수익률에 더하는 basis-point 이동
- `volatility_multiplier`: 원본 평균을 중심으로 편차에 적용하는 0 이상의 배수
- `cost_drag_bps`: 모든 기간 수익률에서 차감하는 0 이상의 basis-point 비용
- `one_time_shock`: 특정 날짜의 변형된 수익률에 곱셈 방식으로 적용하는 단순수익률
- `shock_date`: 일회성 충격이 0이 아닐 때 필수이며 전략 수익률 경로에 존재해야 함

기간별 변형식은 다음과 같습니다.

```text
stressed_return_t = mean_return
                    + volatility_multiplier × (base_return_t - mean_return)
                    + recurring_shift_bps / 10000
                    - cost_drag_bps / 10000
```

일회성 충격 날짜에는 다음을 추가 적용합니다.

```text
stressed_return = (1 + stressed_return) × (1 + one_time_shock) - 1
```

변형 결과가 결측·무한대 또는 -100% 이하이면 실행을 중단합니다.

### Factor scenario

```yaml
factor_scenarios:
  - name: risk_off
    shocks:
      market: -0.08
      value: 0.01
      momentum: -0.03
```

팩터 시나리오는 벤치마크와 팩터 CSV를 이용해 먼저 계산된 OLS 결과가 필요합니다. 설정의 factor
이름은 attribution 결과의 beta 이름과 정확히 일치해야 합니다.

```text
estimated_period_return = alpha_periodic + Σ(beta_i × factor_shock_i)
```

설정에 없는 팩터는 충격 0으로 간주합니다. 설정에 있지만 회귀 결과에 없는 팩터는 오류입니다.
위기 시 beta, alpha, 상관관계가 변하지 않는다는 강한 가정이므로 결과를 예측치로 해석하면 안
됩니다.

## Breakeven

`stress_summary.json`은 다음 값을 제공합니다.

- `base_terminal_growth`: 원본 수익률 경로의 누적 성장배수
- `one_time_return_to_breakeven`: 누적 성장배수를 1로 만드는 단일 곱셈 수익률
- `recurring_cost_drag_bps_to_breakeven`: 모든 기간에 같은 비용을 차감해 terminal growth가
  1이 되는 basis-point 값

원본 경로가 이미 손실이면 반복 비용 여력은 0으로 반환합니다. 브레이크이븐 값은 최대 허용
거래비용이나 안전마진을 보증하지 않습니다.

## Audit Outputs

`--stress-config`를 제공하면 다음 파일이 추가됩니다.

### `stress_scenarios.csv`

```text
scenario,observations,cumulative_return,annualized_return,annualized_volatility,
maximum_drawdown,worst_period_return,terminal_growth,terminal_loss_vs_base
```

`base`가 첫 행이고 사용자 path scenario가 설정 순서대로 이어집니다.

### `stress_paths.csv`

```text
date,scenario,base_return,stressed_return,growth
```

각 시나리오의 전체 날짜별 계산 경로를 보존합니다.

### `factor_stress.csv`

```text
scenario,alpha_component,factor_component,estimated_period_return,
estimated_annualized_return,shocks,contributions
```

팩터 시나리오가 없어도 안정적인 헤더를 가진 빈 CSV를 생성합니다.

### `stress_summary.json`

브레이크이븐 결과와 path/factor scenario 개수를 기록합니다.

## Boundaries

- 일별 단순수익률 경로만 지원
- 충격 확률과 발생 시점을 추정하지 않음
- 거시변수 변화가 기업 매출·마진·밸류에이션에 연결되는 구조모형이 아님
- 포지션별 금리 듀레이션, 신용스프레드, 환율, 델타·감마 재평가 없음
- 위기 중 거래정지, 상관관계 붕괴, 시장충격, 강제청산을 자동 모사하지 않음
- full-sample factor beta를 고정 사용
- VaR, Expected Shortfall, 확률적 Monte Carlo, regime transition은 아직 지원하지 않음
