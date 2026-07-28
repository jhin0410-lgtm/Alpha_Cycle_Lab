# Reproducible Paper Trading State

## Purpose

이 계층은 네트워크 주문을 실행하지 않습니다. 로컬 paper-trading 연구 프로세스가 세션 종료 시점의 주문 상태, 체결, 현금, 포지션, 평가가격과 누적 비용을 SQLite에 원자적으로 기록하고 재시작 후 동일 상태를 복구하기 위한 저장 경계입니다.

## Run Identity

데이터베이스 하나는 하나의 run만 보존합니다. 초기화 시 다음 값이 고정됩니다.

```text
run_id
strategy_name
initial_cash
config_digest
created_at
schema_version
```

같은 데이터베이스를 다른 run ID, 전략, 초기 현금 또는 설정 digest로 다시 초기화하면 실행을 중단합니다. 비밀키, 계좌번호와 인증정보는 저장 대상이 아닙니다.

## Session Commit

`PaperTradingStore.commit_session()`은 다음 데이터를 하나의 SQLite 트랜잭션으로 기록합니다.

- 거래 세션 날짜
- 정확한 시장 스냅샷 또는 입력 파일의 SHA-256 fingerprint
- 해당 세션에서 변경된 최신 주문 상태
- 고유 `fill_id`를 가진 체결
- 현금, 포지션, 평균원가, 실현손익, 마지막 평가가격
- 수수료, 세금, 슬리피지와 거래대금 누계

세션 날짜는 엄격하게 증가해야 합니다. 동일 세션과 동일 payload를 다시 기록하면 멱등적으로 기존 checkpoint를 반환합니다. 동일 세션에 다른 상태가 들어오거나 이미 사용된 fill ID가 다시 나타나면 전체 트랜잭션을 취소합니다.

## Integrity Chain

각 session payload는 key 정렬과 compact separator를 사용하는 canonical JSON으로 직렬화합니다.

```text
payload_hash = SHA256(canonical_payload)
state_hash = SHA256(previous_state_hash + payload_hash)
```

첫 세션의 previous hash는 64자리 0 문자열입니다. `verify_integrity()`는 다음을 다시 계산합니다.

- 연속적인 session sequence
- 엄격히 증가하는 session date
- previous hash 연결
- payload hash
- state hash
- payload 안의 fill ID와 별도 unique fill index 일치

검증 실패 상태는 정상으로 복구하거나 export하지 않습니다. 이 해시 체인은 우발적 변경과 불일치를 찾기 위한 감사 장치이며 전자서명이나 외부 공증을 대신하지 않습니다.

## Restore

- `latest_checkpoint()`는 최신 session checkpoint를 반환합니다.
- `restore_portfolio()`는 cash, position, average cost, realized P&L, last price와 비용 누계를 복구합니다.
- `restore_open_orders()`는 주문별 가장 최근 상태를 선택하고 아직 terminal 상태가 아닌 DAY/GTC 주문만 반환합니다.

복구된 상태는 다음 세션을 이어가기 위한 입력입니다. 실제 broker의 주문·잔고와 자동 대조하거나 주문을 전송하지 않습니다.

## CLI

```bash
python -m alpha_cycle.cli paper-state init --database data/private/paper.sqlite --run-id research-001 --strategy momentum --initial-cash 80000000 --config-digest CONFIG_SHA256
python -m alpha_cycle.cli paper-state verify --database data/private/paper.sqlite
python -m alpha_cycle.cli paper-state export --database data/private/paper.sqlite --output outputs/paper-audit
```

SQLite, DB journal, 주문·체결 로그는 `.gitignore` 대상입니다. 감사 export에는 다음 파일이 생성됩니다.

```text
paper_sessions.csv
paper_orders.csv
paper_fills.csv
paper_checkpoints.csv
paper_positions.csv
paper_metadata.json
```

## Boundaries

- 실시간 데이터 수집 없음
- 주문 전송 없음
- KIS 또는 다른 broker 동기화 없음
- multi-process leader election 없음
- 외부 object storage 또는 원격 DB 없음
- DB 암호화와 전자서명 없음
- 전략 프로세스 heartbeat와 자동 재시작 없음
- 실제 체결 정정·취소·broker reconciliation 없음

실전 모의투자 어댑터는 별도의 보안검토와 broker reconciliation 정책이 구현된 이후에만 이 저장 경계 위에 연결해야 합니다.
