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
   - 남음: 실제 broker reconciliation, heartbeat, multi-process leader election, 원격·암호화 저장소
8. 독립 보안검토 후에만 KIS 모의투자 어댑터 검토

실계좌 자동매매는 현재 로드맵 범위가 아닙니다.
