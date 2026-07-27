# Alpha Cycle Lab

개인 투자 연구를 위한 결정론적 이벤트 기반 백테스트 코어입니다. Python 3.12와
`src` 레이아웃을 사용하며, 전략·주문·위험관리·체결·포트폴리오 회계를 분리합니다.

> 이 프로젝트는 교육 및 연구 목적이며 투자 추천 프로그램이 아닙니다. 실전 주문 기능은
> 없고 의도적으로 비활성화되어 있습니다. 포함된 예제 전략과 fixture의 결과는 실제 성과
> 주장이 아니며 미래 수익을 보장하지 않습니다.

## 현재 구현 범위

- 일봉 OHLCV 계약, 정합성·기간·최신성 검사와 시간순 피드
- `available_date`로 공개 시점을 강제하는 Point-in-Time 계약
- RAW, SPLIT_ADJUSTED, TOTAL_RETURN_ADJUSTED 가격 기준 구분
- 시점별 투자 유니버스와 미래 구성종목 비노출
- split/reverse split의 수량·평균원가 회계 및 감사 출력
- 목표 비중 기반 장기 전용 다종목 포트폴리오와 정수 주식 주문
- 다음 거래일 시가(기본) 또는 명시적 당일 종가 체결
- 매수/매도 수수료, 매도세, 고정/비율 슬리피지
- 단일종목, 총익스포저, 회전율, 유동성, 일손실, 낙폭 제한과 구조화된 거절
- 연구 검증용 Buy-and-Hold 및 횡단면 모멘텀 예제
- 성과지표와 8개 감사 출력 파일, YAML 설정, CLI
- 추상 `BrokerAdapter`, 로컬 `SimulatedBroker`, 항상 비활성인 KIS 안전 스텁
- 명시적 거래 캘린더와 `Asia/Seoul` 세션 기반 체결/리밸런싱 지원

공매도, 레버리지, 실시간 데이터, 실전 증권사 주문, 자동매매는 지원하지 않습니다.

## 가격·기업행동 안전 정책

`MarketDataFeed`의 기본 가격 기준은 `raw`입니다. `adjusted_close`가 존재해도 `close`를
자동 대체하지 않습니다. split-adjusted 및 total-return-adjusted 데이터는 분석용으로만
구분하며 주문 체결과 포트폴리오 시가평가에는 사용할 수 없습니다.

현재 회계에 반영하는 기업행동은 `split`과 `reverse_split`뿐입니다. 현금배당,
주식배당, 상장폐지는 임의로 추정하거나 조용히 무시하지 않고 백테스트를 중단합니다.
분할 결과가 정수 수량이 아니면 fractional share 현금 정산을 추정하지 않고 오류를 냅니다.

## 설치와 실행

```bash
python -m pip install -e ".[dev]"
python -m alpha_cycle.cli backtest --input data/sample/prices.csv --strategy momentum --initial-cash 80000000 --config config/example.yaml --output outputs/momentum_test
```

Windows PowerShell과 POSIX 셸 모두에서 위 한 줄 명령을 사용할 수 있습니다. 예제 CSV는
프로그램 검증용 합성 데이터일 뿐입니다. 실행 후 `equity_curve.csv`, `positions.csv`,
`orders.csv`, `fills.csv`, `trades.csv`, `corporate_actions.csv`, `metrics.json`,
`backtest_report.md`가 생성됩니다.

```bash
python -m pytest
python -m ruff check .
python -m mypy
```

## 주요 한계

시점별 유니버스가 제공되지 않으면 데이터에 존재하는 종목만 보므로 survivorship bias가
남을 수 있습니다. Point-in-Time 계약과 다음 날 체결은 look-ahead bias를 줄이지만 원천
데이터의 실제 공개 시각까지 보증하지 않습니다. total-return-adjusted 가격은 미래 배당
정보가 과거 가격에 소급 반영될 수 있으므로 전략 실행 입력으로 안전하다고 가정하지 않습니다.

체결은 일봉 기반 단순 모델이고 시장 충격, 호가, 거래정지, 부분체결을 재현하지 않습니다.
거래비용 설정은 예시이며 특정 시장이나 증권사의 현재 요율이 아닙니다. 기본 시장 시간대는
`Asia/Seoul`입니다. 공식 KRX 휴장일·기업행동·구성종목 자동 다운로드는 지원하지 않으며,
테스트와 예제는 명시적 합성 데이터 계약을 사용합니다.

## 구조

```text
src/alpha_cycle/
  data/ domain/ strategies/ portfolio/ risk/
  backtest/ brokers/ reporting/ calendar/ cli.py config.py
tests/
  unit/ integration/
config/  data/sample/  docs/  .github/workflows/
```

설계 상세는 [ARCHITECTURE](docs/ARCHITECTURE.md), 가정은
[BACKTEST_ASSUMPTIONS](docs/BACKTEST_ASSUMPTIONS.md), 데이터 계약은
[DATA_CONTRACTS](docs/DATA_CONTRACTS.md), 공개 저장소 지침은
[SECURITY](docs/SECURITY.md)를 참고하십시오. 향후 계획은 [ROADMAP](docs/ROADMAP.md)에
정리되어 있습니다.
