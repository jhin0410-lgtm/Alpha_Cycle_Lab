# Broker Reconciliation Safety Contract

## 목적

이 계층은 주문을 전송하지 않습니다. 브로커에서 읽어온 것으로 가정한 하나의 불변 JSON
스냅샷을 로컬 `PaperTradingStore`의 검증된 감사 상태와 비교하고, 새로운 주문을 제출해도 되는지
판정하는 fail-closed 안전 게이트입니다.

`KISBrokerAdapter`는 계속 비활성 상태이며 네트워크, 토큰 발급, 계좌 조회와 주문 API 호출은
이번 범위에 포함되지 않습니다.

## 브로커 스냅샷 계약

```json
{
  "schema_version": 1,
  "broker": "synthetic-read-only",
  "account_ref_hash": "64-character sha256 hex",
  "snapshot_id": "immutable-provider-snapshot-id",
  "captured_at": "2026-07-28T09:00:00+09:00",
  "cash": "80000000",
  "fill_history_complete": false,
  "positions": [
    {
      "ticker": "005930",
      "quantity": 10,
      "average_cost": "70000"
    }
  ],
  "open_orders": [
    {
      "client_order_id": "O00000001",
      "broker_order_id": "provider-order-id",
      "ticker": "005930",
      "side": "buy",
      "quantity": 5,
      "filled_quantity": 2,
      "status": "partially_filled"
    }
  ],
  "fills": [
    {
      "fill_id": "provider-fill-id",
      "client_order_id": "O00000001",
      "ticker": "005930",
      "side": "buy",
      "quantity": 2,
      "price": "71000",
      "timestamp": "2026-07-28T09:01:00+09:00"
    }
  ]
}
```

`account_ref_hash`는 SHA-256 16진수 digest만 허용합니다. 실제 계좌번호, 토큰, 앱 키, 비밀번호와
사용자 식별자를 JSON, 로그 또는 Git 저장소에 넣지 않습니다.

`captured_at`과 체결 timestamp는 timezone-aware ISO-8601이어야 합니다. 동일 ticker, 주문 ID,
브로커 주문 ID와 fill ID의 중복은 거부합니다. 금액과 단가는 finite decimal이어야 하며 수량은
음수가 아닌 정수여야 합니다.

## 로컬 상태 구성

`local_state_from_store()`는 다음 절차를 사용합니다.

1. SQLite hash chain과 fill index를 검증합니다.
2. 임시 디렉터리에 normalized paper audit를 export합니다.
3. 최신 현금, 포지션과 주문 상태를 선택합니다.
4. 전체 committed fill ID 집합을 구성합니다.
5. 임시 파일을 제거합니다.

손상된 PaperTradingStore는 reconciliation 입력으로 사용하지 않습니다.

## 비교 항목

### 시간

- 미래 timestamp가 허용 오차를 넘으면 차단
- 기본 300초보다 오래된 스냅샷 차단
- 브로커 스냅샷 날짜가 최신 로컬 세션보다 이전이면 차단

### 현금

현금 차이가 설정된 tolerance를 넘으면 차단합니다. tolerance 기본값은 0입니다.

### 포지션

- 브로커에만 존재하는 포지션 차단
- 로컬에만 존재하는 포지션 차단
- 수량 불일치 차단
- 평균원가 차이는 warning으로 기록하지만 warning 상태도 자동 주문 제출을 허용하지 않음

평균원가는 브로커별 수수료·세금 반영 방식이 다를 수 있으므로 수량과 별도로 취급합니다.

### 미체결 주문

로컬 `pending`은 브로커 `open`, 로컬 `partially_filled`는 브로커
`partially_filled`에 대응합니다. 다음 불일치는 모두 차단합니다.

- 한쪽에만 존재하는 활성 주문
- ticker 또는 side 차이
- 원수량 차이
- 누적 체결수량 차이
- 상태 차이

브로커 `client_order_id`는 로컬 `order_id`와 정확히 일치해야 합니다.

### 체결

브로커 snapshot의 fill ID가 로컬 journal에 없으면 차단합니다. 브로커 체결이 알 수 없는 로컬
주문을 참조해도 차단합니다.

`fill_history_complete=true`는 스냅샷이 해당 run의 전체 체결 이력을 포함한다는 강한 계약입니다.
이 경우 로컬에만 존재하는 fill도 차단합니다. 일부 기간 체결만 제공하는 공급자는 반드시 false를
사용해야 합니다.

## 상태와 주문 게이트

```text
ready
  이슈 없음
  can_submit_orders = true

review_required
  warning만 존재
  can_submit_orders = false

blocked
  blocking 이슈 하나 이상
  can_submit_orders = false
```

warning은 자동으로 무시하지 않습니다. 사용자가 원인을 확인하고 로컬 또는 브로커 상태를 수정한
뒤 새 스냅샷으로 다시 실행해야 합니다.

## CLI

```bash
python -m alpha_cycle.cli broker-reconcile \
  --database data/private/paper.sqlite \
  --snapshot data/private/broker_snapshot.json \
  --output outputs/reconciliation \
  --max-snapshot-age-seconds 300 \
  --future-tolerance-seconds 5 \
  --cash-tolerance 0 \
  --average-cost-tolerance 0.01
```

생성 파일:

```text
reconciliation_report.json
reconciliation_issues.csv
```

`ready`가 아니면 파일을 먼저 생성한 뒤 CLI 종료코드 2를 반환합니다.

## 보안 및 모델 한계

- 읽기 전용 JSON 입력이며 API 연결 없음
- 주문 제출 기능 없음
- broker snapshot의 진위나 서명을 검증하지 않음
- 외부 timestamp authority 없음
- 계좌번호 대신 hash만 허용하지만 hash도 공개 저장소에 커밋하지 않는 것을 권장
- broker의 체결 정정, 취소, 수수료 사후 조정과 결제일 현금은 아직 모델링하지 않음
- 다중 계좌, 다중 통화, 예수금 D+1/D+2, 대차와 미수금 미지원
- 평균원가 tolerance는 수량 불일치를 정당화하지 않음

실제 KIS 모의투자 어댑터는 이 gate와 별도로 자격증명 저장소, 요청 서명, rate limit,
idempotency key, kill switch, 주문 한도, 사용자 확인, broker 응답 원문 보존과 독립 보안검토가
완료된 이후에만 검토합니다.
