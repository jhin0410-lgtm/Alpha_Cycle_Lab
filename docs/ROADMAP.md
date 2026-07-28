# Roadmap

1. 거래소 캘린더와 시간대 인식 세션 모델
   - 완료: 명시적 캘린더 및 테스트/예제 지원
2. 기업행동·상장폐지·유니버스 편입 이력
   - 부분 완료: 가격 기준, split/reverse split 회계, 시점별 universe
   - 남음: 현금·주식배당, 상장폐지 실행 정책, 공식 데이터 공급자
3. 부분체결, 거래정지, 지정가 주문과 주문 수명
   - 완료: market/limit, DAY/GTC, 거래량 기반 부분체결, `is_halted`, 복수 Fill
   - 남음: 호가창·체결 우선순위·장중 주문 수정과 취소 이벤트
4. PIT 재무·거시 데이터 어댑터와 revision 정책
   - 완료: 재무·거시 스키마, first_release/latest_known, 로컬 CSV 어댑터, 동기화 snapshot
   - 남음: DART·ECOS·FRED 등 공식 공급자 어댑터와 장중 공개시각 정밀화
5. 벤치마크 정렬 및 팩터 귀속
   - 완료: strict/inner 날짜 정렬, 상대성과 지표, 다중팩터 OLS, 감사 출력
   - 남음: 통화·비동기 시장 정렬, 표준 팩터 공급자, rolling attribution
6. 시나리오·스트레스 테스트
   - 완료: 경로 수익률·변동성·비용·일회성 충격, 팩터 베타 충격, 브레이크이븐 분석
   - 남음: rolling beta, 비선형 옵션성, 상관관계 붕괴, 포지션별 재평가와 유동성 시장충격
7. 재현 가능한 Paper Trading 저장 계층
   - 완료: SQLite session journal, 원자적 commit, 멱등 retry, fill 중복 차단, hash chain, 상태 복구와 감사 export
   - 남음: heartbeat, multi-process leader election, 원격·암호화 저장소
8. 읽기 전용 broker reconciliation과 주문 승인 게이트
   - 완료: snapshot schema, freshness 검사, 현금·포지션·주문·체결 대조, fail-closed 보고서
   - 남음: 실제 broker snapshot adapter, 체결 정정·취소, 다중통화·결제일 현금, 응답 서명 검증
9. 실시간 시장 인텔리전스
   - 부분 완료: 토스증권 OAuth2 읽기 전용 현재가·1분/일봉, rate-limit 재시도, 원본·정규화 불변 snapshot
   - 부분 완료: 수익률·상대강도·변동성·거래량·낙폭·RSI·추세 효율성 feature
   - 남음: 장 캘린더·호가·체결·랭킹·시장 폭, 명시적 scheduler와 데이터 보존 정책
10. 기업·거시·산업 인텔리전스
   - 남음: OpenDART 공시·XBRL, ECOS 거시지표, 경쟁사·수주·CAPEX·점유율 evidence model
11. 투자 논리·촉매·학습 loop
   - 남음: 시점별 thesis와 Bull/Base/Bear 저장, 1·5·20·60일 성과 라벨, champion-challenger 검증
12. 독립 보안검토 후에만 제한적 모의주문 어댑터 검토
   - 남음: 자격증명 저장소, 최소 권한, idempotency key, rate limit, kill switch, 사용자 확인

실계좌 자동매매는 현재 로드맵 범위가 아닙니다. 주문 연동보다 분석 정확성, 시점 정합성,
재현 가능성, 사후 성과검증과 학습 loop를 우선합니다.
