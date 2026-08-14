"""Registry of industry-specific deep-research contracts.

The registry intentionally does not force every industry through one universal set
of factors.  Each sector declares the operating variables that actually transmit
macro/industry conditions into company earnings, valuation, and catalysts.
"""

from __future__ import annotations

from alpha_cycle.intelligence.sector_vertical import (
    SectorEvidenceRequirement,
    SectorVerticalDefinition,
)


def _r(
    key: str,
    label: str,
    domain: str,
    priority: str,
    rationale: str,
    *sources: str,
) -> SectorEvidenceRequirement:
    return SectorEvidenceRequirement(
        key=key,
        label=label,
        domain=domain,
        priority=priority,
        rationale=rationale,
        preferred_sources=tuple(sources),
    )


SEMICONDUCTOR = SectorVerticalDefinition(
    sector_id="semiconductor",
    display_name="반도체",
    thesis_question=(
        "메모리/AI 수요와 공급 제약이 가격·믹스·가동률을 통해 어느 기업의 "
        "이익 추정치를 가장 크게 상향시키며, 그 기대가 현재 가격에 얼마나 반영됐는가?"
    ),
    requirements=(
        _r("macro_liquidity", "글로벌 유동성·금리·달러", "macro", "important", "AI/성장주 멀티플과 한국 외국인 수급에 직접 영향", "Fed", "FRED", "BOK ECOS"),
        _r("end_demand", "서버·AI·PC·모바일 최종수요", "demand", "required", "bit demand와 제품 믹스의 출발점", "company IR", "industry shipment data"),
        _r("memory_pricing", "DRAM·NAND 가격", "pricing", "required", "메모리 영업레버리지의 핵심 ASP 변수", "official/company disclosures", "licensed price data"),
        _r("hbm_demand_mix", "HBM 수요·믹스·세대", "demand", "required", "AI 메모리의 구조적 성장과 업체별 ASP 차별화", "company IR", "customer disclosures"),
        _r("inventory_cycle", "산업·업체·고객 재고", "supply_demand", "required", "메모리 가격 전환점과 주문 정상화 판단", "KOSIS", "company filings"),
        _r("capacity_utilization", "생산능력·가동률", "supply", "required", "공급 탄력성과 가격 지속성 판단", "KOSIS", "company IR"),
        _r("supplier_capex", "공급사 CAPEX·웨이퍼 투입", "supply", "important", "향후 공급 증가와 사이클 후반 리스크 판단", "company filings", "company IR"),
        _r("hbm_capacity_yield", "HBM 캐파·수율·패키징 병목", "competition", "required", "HBM 매출 실현 속도와 업체별 점유율 차별화", "company IR", "customer qualification disclosures"),
        _r("competitive_position", "기술·점유율·고객 qualification", "competition", "required", "산업 호황이 기업별 이익으로 다르게 전달되는 이유", "company IR", "customer disclosures"),
        _r("business_mix_drag", "파운드리·NAND·모바일 등 혼합사업 영향", "company", "important", "동일 반도체 신호가 삼성전자와 하이닉스에 다르게 전달됨", "OpenDART", "company IR"),
        _r("earnings_transmission", "매출→마진→영업이익 전달", "earnings", "required", "산업 신호를 실제 기업 손익으로 연결", "OpenDART"),
        _r("expectation_revision", "컨센서스·실적추정치 revision", "expectations", "required", "펀더멘털 변화가 시장 기대를 앞서는지 확인", "certified consensus source"),
        _r("catalyst_calendar", "1·3·6·12개월 촉매", "catalyst", "important", "qualification·가격협상·실적발표 등 재평가 시점 식별", "OpenDART", "company IR"),
        _r("valuation_regime", "사이클 조정 밸류에이션", "valuation", "required", "좋은 산업과 좋은 주식을 현재 가격에서 구분", "OpenDART", "KRX/Kiwoom price history"),
        _r("flow_price_confirmation", "외국인·기관 수급과 상대강도", "market", "important", "펀더멘털 thesis의 시장 확인과 진입 타이밍", "Kiwoom", "KRX"),
        _r("export_control_geopolitics", "수출규제·미중정책·AI 규제", "policy", "important", "장비·고객·지역별 수요와 valuation risk에 영향", "government primary sources"),
    ),
)

DEFENSE = SectorVerticalDefinition(
    sector_id="defense",
    display_name="방산",
    thesis_question="국방예산·지정학 수요가 수주·생산능력·마진으로 얼마나 빠르게 전환되며 현재 수주 기대를 넘어서는가?",
    requirements=(
        _r("defense_budget", "국가별 국방예산·조달계획", "macro_policy", "required", "최종 수요의 원천", "defense ministries", "NATO"),
        _r("geopolitical_demand", "분쟁·재무장·재고보충 수요", "demand", "required", "예산 외 긴급조달과 주문 가속 판단", "government releases"),
        _r("export_pipeline", "수출 파이프라인·입찰", "orders", "required", "다음 수주 모멘텀의 구체성 판단", "DAPA", "company IR"),
        _r("backlog", "수주잔고·매출인식 일정", "earnings", "required", "장기 기대를 실제 매출 시점으로 변환", "OpenDART", "company IR"),
        _r("production_capacity", "생산능력·증설·병목", "supply", "required", "수주가 매출로 전환되는 속도의 상한", "company IR"),
        _r("margin_mix", "수출/내수·제품 믹스 마진", "earnings", "required", "수주 증가와 이익 증가의 차이를 설명", "OpenDART", "company IR"),
        _r("working_capital", "선수금·운전자본·현금흐름", "financial", "important", "대형 수주 성장의 현금흐름 품질 확인", "OpenDART"),
        _r("fx_exposure", "환율·통화 노출", "macro", "important", "수출 계약 손익과 valuation에 영향", "BOK ECOS", "company filings"),
        _r("export_license_policy", "수출허가·외교정책", "policy", "required", "수주 실현 가능성의 정책 gate", "DAPA", "government releases"),
        _r("expectation_revision", "수주·이익 revision", "expectations", "required", "신규 수주가 기존 기대를 넘는지 판단", "certified consensus source"),
        _r("catalyst_calendar", "입찰·계약·인도·실적 촉매", "catalyst", "important", "주가 재평가 시점 식별", "OpenDART", "company IR"),
        _r("valuation_regime", "수주잔고·이익 기반 valuation", "valuation", "required", "장기 backlog를 이미 선반영했는지 판단", "OpenDART", "market data"),
        _r("flow_price_confirmation", "수급·상대강도", "market", "important", "정책/수주 thesis의 시장 확인", "KRX", "Kiwoom"),
    ),
)

SHIPBUILDING = SectorVerticalDefinition(
    sector_id="shipbuilding",
    display_name="조선",
    thesis_question="선가·발주·도크 제약과 원가가 수주잔고의 마진 정상화 및 현금흐름으로 언제 전환되는가?",
    requirements=(
        _r("global_order_cycle", "글로벌 선박 발주 사이클", "demand", "required", "수주량의 방향 결정", "Clarksons/official shipping data"),
        _r("newbuild_price", "신조선가", "pricing", "required", "향후 backlog 수익성의 핵심", "industry price source"),
        _r("orderbook", "수주잔고·인도 스케줄", "orders", "required", "매출 가시성과 슬롯 희소성 판단", "company IR", "OpenDART"),
        _r("yard_capacity", "도크·슬롯·인력 생산능력", "supply", "required", "추가 수주와 납기 가능성의 상한", "company IR"),
        _r("steel_input_cost", "후판·강재 원가", "cost", "required", "매출총이익률의 주요 비용 변수", "official commodity data", "company IR"),
        _r("fx_exposure", "USD/KRW 환율", "macro", "important", "달러 계약 매출/마진 영향", "BOK ECOS"),
        _r("vessel_mix", "LNGC·컨테이너·탱커 믹스", "competition", "required", "선종별 선가·마진·기술우위 차이", "company IR"),
        _r("margin_conversion", "저가수주 소진→고선가 매출 전환", "earnings", "required", "수주잔고와 실제 이익 사이의 시차 설명", "OpenDART", "company IR"),
        _r("working_capital", "선수금·건조대금·현금흐름", "financial", "important", "이익과 현금 전환 품질 확인", "OpenDART"),
        _r("expectation_revision", "영업이익 revision", "expectations", "required", "마진 정상화의 시장 기대 차이", "certified consensus source"),
        _r("catalyst_calendar", "대형수주·선가·실적 촉매", "catalyst", "important", "재평가 시점 식별", "OpenDART", "company IR"),
        _r("valuation_regime", "cycle-adjusted valuation", "valuation", "required", "수주 호황 선반영 정도 판단", "OpenDART", "market data"),
        _r("flow_price_confirmation", "수급·상대강도", "market", "important", "업황 thesis 확인", "KRX", "Kiwoom"),
    ),
)

POWER_EQUIPMENT = SectorVerticalDefinition(
    sector_id="power_equipment",
    display_name="전력기기",
    thesis_question="그리드 CAPEX와 공급부족이 backlog·lead time·가격·증설을 통해 얼마나 오래 초과이익을 유지시키는가?",
    requirements=(
        _r("grid_capex", "미국·글로벌 grid CAPEX", "demand", "required", "변압기/배전 수요의 구조적 원천", "utility filings", "government plans"),
        _r("backlog", "수주잔고·북투빌", "orders", "required", "매출 가시성과 초과수요 확인", "company IR"),
        _r("lead_time", "변압기·차단기 lead time", "supply", "required", "공급부족 지속성 판단", "company IR", "utility disclosures"),
        _r("capacity_expansion", "증설·가동시점", "supply", "required", "공급부족 해소 시점과 기업별 성장 차이", "company IR"),
        _r("pricing", "판가·믹스", "pricing", "required", "마진 상승 지속성 판단", "company IR"),
        _r("copper_input", "구리·원재료", "cost", "important", "원가와 가격전가 능력 확인", "official commodity data"),
        _r("us_localization_policy", "IRA/관세/현지생산 정책", "policy", "important", "미국 공급망 경쟁우위 판단", "US government"),
        _r("margin_conversion", "backlog→마진 전환", "earnings", "required", "수주 성장의 이익 실현 검증", "OpenDART"),
        _r("expectation_revision", "이익 revision", "expectations", "required", "공급부족 프리미엄의 추가 상향 여지", "certified consensus source"),
        _r("catalyst_calendar", "증설·수주·실적 촉매", "catalyst", "important", "재평가 시점", "OpenDART", "company IR"),
        _r("valuation_regime", "backlog/ROE 기반 valuation", "valuation", "required", "구조적 성장 선반영 정도", "OpenDART", "market data"),
        _r("flow_price_confirmation", "수급·상대강도", "market", "important", "시장 확인", "KRX", "Kiwoom"),
    ),
)

NUCLEAR = SectorVerticalDefinition(
    sector_id="nuclear",
    display_name="원전",
    thesis_question="정책·인허가·금융조달·EPC 일정이 실제 수주와 매출 인식으로 전환되는 속도와 프로젝트 리스크는 무엇인가?",
    requirements=(
        _r("nuclear_policy", "국가별 원전 정책·용량계획", "policy", "required", "프로젝트 파이프라인의 원천", "energy ministries", "IAEA"),
        _r("project_pipeline", "신규원전·SMR 프로젝트 파이프라인", "orders", "required", "구조적 수요와 기업 수혜 연결", "government/project owners"),
        _r("licensing", "인허가·규제 단계", "policy", "required", "프로젝트 확률과 일정의 핵심 gate", "nuclear regulators"),
        _r("financing", "프로젝트 금융·보증·수출금융", "financial", "required", "대형 프로젝트 실행가능성 판단", "ECA/government"),
        _r("epc_schedule", "EPC 공정·매출인식", "earnings", "required", "수주 발표와 실적 사이 시차", "company IR", "OpenDART"),
        _r("local_content", "현지조달·파트너 구조", "competition", "important", "수주 경제성과 마진에 영향", "project documents"),
        _r("cost_overrun_risk", "원가초과·지연 위험", "risk", "required", "원전 프로젝트의 핵심 downside", "company filings", "project disclosures"),
        _r("expectation_revision", "수주 확률·이익 revision", "expectations", "required", "정책 뉴스와 실제 기대 차이", "certified consensus source"),
        _r("catalyst_calendar", "우협·본계약·인허가 촉매", "catalyst", "important", "binary/event timing 관리", "government", "OpenDART"),
        _r("valuation_regime", "수주확률 조정 valuation", "valuation", "required", "아직 미확정 프로젝트 선반영 정도", "OpenDART", "market data"),
        _r("flow_price_confirmation", "수급·상대강도", "market", "important", "정책 테마와 펀더멘털 구분", "KRX", "Kiwoom"),
    ),
)

CONSTRUCTION = SectorVerticalDefinition(
    sector_id="construction",
    display_name="건설",
    thesis_question="금리·주택·PF·원가·해외수주가 현금흐름과 마진 정상화로 전환되는가, 아니면 회계상 매출만 늘어나는가?",
    requirements=(
        _r("rates_credit", "금리·신용·PF 금융여건", "macro", "required", "분양·PF·자금조달의 핵심", "BOK", "FSS"),
        _r("housing_cycle", "주택거래·분양·미분양", "demand", "required", "국내 주택 매출/리스크 방향", "MOLIT", "KOSIS"),
        _r("pf_exposure", "PF·우발채무·보증", "risk", "required", "건설사 tail risk와 자본 소모 판단", "OpenDART"),
        _r("presales_backlog", "분양·수주잔고", "orders", "required", "향후 매출 가시성", "company IR"),
        _r("input_cost", "원자재·인건비·공사비", "cost", "required", "원가율과 마진 정상화 판단", "KOSIS", "company IR"),
        _r("overseas_orders", "해외 플랜트·인프라 수주", "orders", "important", "국내 주택 의존도 완화와 성장축", "government order data", "company IR"),
        _r("margin_conversion", "매출→마진·현금흐름", "earnings", "required", "저마진 현장 소진과 정상화 확인", "OpenDART"),
        _r("working_capital", "미청구공사·매출채권·현금", "financial", "required", "회계이익 품질과 현금 묶임 판단", "OpenDART"),
        _r("policy_supply", "주택공급·재건축·SOC 정책", "policy", "important", "수주 파이프라인 변화", "MOLIT", "MOEF"),
        _r("expectation_revision", "이익 revision", "expectations", "required", "마진 정상화 선반영 정도", "certified consensus source"),
        _r("catalyst_calendar", "분양·수주·PF 해소 촉매", "catalyst", "important", "재평가 시점", "OpenDART", "company IR"),
        _r("valuation_regime", "P/B·ROE·NAV valuation", "valuation", "required", "사이클 회복 기대의 선반영 판단", "OpenDART", "market data"),
        _r("flow_price_confirmation", "수급·상대강도", "market", "important", "회복 thesis 확인", "KRX", "Kiwoom"),
    ),
)

BATTERY = SectorVerticalDefinition(
    sector_id="battery",
    display_name="2차전지",
    thesis_question="EV 수요·재고·메탈가격·가동률·ASP가 업체별 믹스와 CAPEX를 통해 언제 이익 바닥을 통과시키는가?",
    requirements=(
        _r("ev_demand", "EV 판매·침투율", "demand", "required", "셀/소재 최종수요의 원천", "official auto registrations"),
        _r("channel_inventory", "OEM·셀·소재 재고", "supply_demand", "required", "destocking 종료 시점 판단", "company IR"),
        _r("utilization", "공장 가동률", "supply", "required", "고정비 레버리지와 이익 바닥 판단", "company IR"),
        _r("metal_prices", "리튬·니켈·코발트 가격", "pricing", "required", "ASP·재고평가·소재 마진 영향", "official commodity data"),
        _r("asp_mix", "셀/양극재 ASP·제품믹스", "pricing", "required", "매출 성장과 이익 성장 분리", "company IR"),
        _r("chemistry_mix", "LFP/NCM/고니켈 chemistry", "competition", "important", "원가·고객·지역 경쟁력 차이", "company IR"),
        _r("customer_exposure", "OEM 고객·플랫폼 믹스", "competition", "required", "고객 판매량 변화의 기업별 민감도", "company IR"),
        _r("capex_capacity", "증설·CAPEX·JV", "supply", "required", "과잉공급·현금소모 위험", "OpenDART", "company IR"),
        _r("subsidy_tariff", "IRA·관세·보조금", "policy", "required", "지역별 economics와 공급망 재편", "US/EU government"),
        _r("earnings_transmission", "가동률·ASP→마진", "earnings", "required", "업황 회복의 실제 손익 전환", "OpenDART"),
        _r("expectation_revision", "이익 revision", "expectations", "required", "바닥 통과가 컨센서스에 반영되는 속도", "certified consensus source"),
        _r("catalyst_calendar", "OEM 출시·증설·정책 촉매", "catalyst", "important", "재평가 시점", "company IR", "government"),
        _r("valuation_regime", "cycle-adjusted valuation", "valuation", "required", "성장 프리미엄과 과잉 CAPEX 위험 균형", "OpenDART", "market data"),
        _r("flow_price_confirmation", "수급·상대강도", "market", "important", "사이클 바닥 확인", "KRX", "Kiwoom"),
    ),
)

AUTO = SectorVerticalDefinition(
    sector_id="auto",
    display_name="자동차",
    thesis_question="판매량·가격/인센티브·믹스·환율·관세가 자동차 업체의 마진과 현금창출력을 어떻게 바꾸는가?",
    requirements=(
        _r("global_volume", "지역별 판매량·시장점유율", "demand", "required", "매출 성장의 기본", "official registrations", "company IR"),
        _r("inventory_incentives", "딜러 재고·인센티브", "pricing", "required", "가격결정력과 수요 질 판단", "company IR", "industry data"),
        _r("vehicle_mix", "SUV·럭셔리·HEV·EV 믹스", "competition", "required", "ASP·마진의 핵심", "company IR"),
        _r("fx_exposure", "환율", "macro", "required", "수출·해외생산 환산/거래손익 영향", "BOK"),
        _r("tariff_policy", "관세·현지생산 규정", "policy", "required", "지역별 원가와 판매 economics", "government"),
        _r("ev_transition", "EV/HEV 전환·배터리 비용", "competition", "important", "중장기 제품 경쟁력과 CAPEX", "company IR"),
        _r("warranty_residual", "품질충당·중고차 잔존가치", "risk", "important", "금융/보증 비용과 브랜드 건전성", "OpenDART", "company IR"),
        _r("margin_conversion", "볼륨·믹스→마진", "earnings", "required", "판매 성장의 이익 질 검증", "OpenDART"),
        _r("free_cash_flow", "CAPEX·FCF", "financial", "required", "주주환원 지속성 판단", "OpenDART"),
        _r("expectation_revision", "이익 revision", "expectations", "required", "가격/환율 개선의 추가 상향 여지", "certified consensus source"),
        _r("catalyst_calendar", "신차·관세·주주환원 촉매", "catalyst", "important", "재평가 시점", "company IR", "government"),
        _r("valuation_regime", "P/E·P/B·FCF valuation", "valuation", "required", "저평가와 구조적 discount 구분", "OpenDART", "market data"),
        _r("flow_price_confirmation", "수급·상대강도", "market", "important", "시장 확인", "KRX", "Kiwoom"),
    ),
)

BIO = SectorVerticalDefinition(
    sector_id="bio",
    display_name="바이오",
    thesis_question="임상·규제·상업화 확률과 현금 runway를 반영한 위험조정 가치가 현재 시가총액을 넘어서는가?",
    requirements=(
        _r("pipeline_stage", "파이프라인·임상 단계", "product", "required", "가치의 기본 단위", "ClinicalTrials.gov", "company IR"),
        _r("clinical_readout", "임상 endpoint·readout", "catalyst", "required", "binary 가치 변화의 핵심", "trial registry", "journal/company release"),
        _r("regulatory_path", "FDA/MFDS/EMA 규제 일정", "policy", "required", "승인 확률과 시간", "regulators"),
        _r("competitive_landscape", "표준치료·경쟁 파이프라인", "competition", "required", "TAM과 성공 시 점유율 판단", "trial registries", "regulators"),
        _r("commercial_tam", "환자수·가격·침투율", "demand", "required", "성공 시 매출 잠재력", "epidemiology/official data"),
        _r("reimbursement", "보험·약가", "pricing", "important", "상업화 economics", "payers/government"),
        _r("cash_runway", "현금·burn·runway", "financial", "required", "임상 전 dilution risk", "OpenDART"),
        _r("dilution_financing", "증자·CB·파트너링", "financial", "required", "주당가치 희석 판단", "OpenDART"),
        _r("partner_deals", "기술이전·마일스톤", "catalyst", "important", "외부 검증과 자금조달", "OpenDART", "company IR"),
        _r("probability_adjusted_value", "rNPV/시나리오 valuation", "valuation", "required", "단순 P/E가 무의미한 개발기업 평가", "validated model inputs"),
        _r("expectation_positioning", "시장 기대·포지셔닝", "expectations", "important", "binary event 선반영 정도", "market data"),
        _r("flow_price_confirmation", "수급·event price action", "market", "context", "이벤트 전후 시장 반응 보조", "KRX", "Kiwoom"),
    ),
)

INTERNET_PLATFORM = SectorVerticalDefinition(
    sector_id="internet_platform",
    display_name="인터넷·플랫폼",
    thesis_question="사용자·트래픽·광고/커머스 monetization과 AI CAPEX가 매출 성장과 마진에 어떤 순효과를 만드는가?",
    requirements=(
        _r("user_engagement", "MAU·DAU·체류시간", "demand", "required", "플랫폼 수요의 기본", "company IR"),
        _r("ad_market", "광고 경기·단가", "pricing", "required", "광고 매출 민감도", "official ad data", "company IR"),
        _r("commerce_gmv", "GMV·거래액", "demand", "important", "커머스 성장량", "company IR"),
        _r("take_rate_arpu", "take rate·ARPU", "pricing", "required", "트래픽을 매출로 전환하는 효율", "company IR"),
        _r("ai_capex", "AI 인프라 CAPEX", "cost", "required", "AI 성장 기대와 현금흐름 비용의 균형", "OpenDART", "company IR"),
        _r("ai_monetization", "AI 상품 매출·비용절감", "earnings", "important", "CAPEX의 수익화 검증", "company IR"),
        _r("regulation", "플랫폼·개인정보·경쟁 규제", "policy", "required", "take rate·사업모델 risk", "government/regulators"),
        _r("margin_conversion", "매출성장→영업레버리지", "earnings", "required", "성장 질 판단", "OpenDART"),
        _r("expectation_revision", "매출·이익 revision", "expectations", "required", "AI/광고 회복의 선반영 판단", "certified consensus source"),
        _r("catalyst_calendar", "신제품·실적·규제 촉매", "catalyst", "important", "재평가 시점", "company IR", "government"),
        _r("valuation_regime", "growth-adjusted P/E·FCF", "valuation", "required", "성장률 대비 multiple 적정성", "OpenDART", "market data"),
        _r("flow_price_confirmation", "수급·상대강도", "market", "important", "시장 확인", "KRX", "Kiwoom"),
    ),
)

ROBOTICS = SectorVerticalDefinition(
    sector_id="robotics",
    display_name="로봇·자동화",
    thesis_question="자동화 CAPEX와 로봇 채택이 주문·부품병목·소프트웨어 믹스를 통해 규모의 경제와 이익으로 전환되는가?",
    requirements=(
        _r("automation_capex", "자동차·전자·물류 자동화 CAPEX", "demand", "required", "산업 수요의 원천", "customer capex disclosures"),
        _r("orders_backlog", "수주·backlog", "orders", "required", "수요 가시성", "company IR", "OpenDART"),
        _r("unit_shipments", "로봇 출하·설치 대수", "demand", "required", "매출량 성장 검증", "company IR"),
        _r("component_supply", "감속기·서보·센서 공급", "supply", "required", "생산병목과 원가 구조", "supplier disclosures"),
        _r("bom_cost", "BOM·원가절감", "cost", "important", "규모의 경제와 gross margin", "company IR"),
        _r("software_service_mix", "SW·서비스 반복매출", "competition", "important", "하드웨어 multiple의 구조적 재평가 근거", "company IR"),
        _r("customer_concentration", "고객 집중도", "risk", "required", "CAPEX 사이클 민감도", "OpenDART", "company IR"),
        _r("margin_conversion", "출하증가→마진", "earnings", "required", "성장 실적화 검증", "OpenDART"),
        _r("expectation_revision", "이익 revision", "expectations", "required", "테마와 실제 실적 차이", "certified consensus source"),
        _r("catalyst_calendar", "대형수주·신제품 촉매", "catalyst", "important", "재평가 시점", "OpenDART", "company IR"),
        _r("valuation_regime", "성장/마진 기반 valuation", "valuation", "required", "테마 premium 선반영 정도", "OpenDART", "market data"),
        _r("flow_price_confirmation", "수급·상대강도", "market", "important", "테마 수급과 실적 확인 구분", "KRX", "Kiwoom"),
    ),
)

SECTOR_VERTICALS: dict[str, SectorVerticalDefinition] = {
    definition.sector_id: definition
    for definition in (
        SEMICONDUCTOR,
        DEFENSE,
        SHIPBUILDING,
        POWER_EQUIPMENT,
        NUCLEAR,
        CONSTRUCTION,
        BATTERY,
        AUTO,
        BIO,
        INTERNET_PLATFORM,
        ROBOTICS,
    )
}


def get_sector_vertical(sector_id: str) -> SectorVerticalDefinition:
    normalized = str(sector_id).strip().casefold().replace("-", "_")
    try:
        return SECTOR_VERTICALS[normalized]
    except KeyError as exc:
        raise KeyError(f"Unsupported sector vertical: {sector_id}") from exc


__all__ = [
    "AUTO",
    "BATTERY",
    "BIO",
    "CONSTRUCTION",
    "DEFENSE",
    "INTERNET_PLATFORM",
    "NUCLEAR",
    "POWER_EQUIPMENT",
    "ROBOTICS",
    "SECTOR_VERTICALS",
    "SEMICONDUCTOR",
    "SHIPBUILDING",
    "get_sector_vertical",
]
