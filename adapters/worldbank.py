"""
World Bank Open Data 어댑터.

API 문서: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
- 인증키 불필요
- CORS 허용 → 브라우저에서도 직접 호출 가능
- 라이선스: CC BY 4.0

엔드포인트 형식:
  https://api.worldbank.org/v2/country/{ISO3};{ISO3}/indicator/{code}
    ?format=json&date=2000:2023&per_page=20000
"""
from __future__ import annotations
import sys
import urllib.request
import urllib.parse
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schema import StandardRecord, IndicatorMeta
from adapters.base import SourceAdapter


# ─── 국가 코드 → 한국어/영어 이름 매핑 (자주 쓰이는 국가 우선) ───
COUNTRY_NAMES: dict[str, tuple[str, str, str]] = {
    # ISO3: (한국어명, 영문명, UN M49 region)
    "KOR": ("대한민국", "Korea, Rep.", "Eastern Asia"),
    "PRK": ("북한", "Korea, Dem. People's Rep.", "Eastern Asia"),
    "JPN": ("일본", "Japan", "Eastern Asia"),
    "CHN": ("중국", "China", "Eastern Asia"),
    "USA": ("미국", "United States", "Northern America"),
    "CAN": ("캐나다", "Canada", "Northern America"),
    "MEX": ("멕시코", "Mexico", "Latin America"),
    "BRA": ("브라질", "Brazil", "Latin America"),
    "ARG": ("아르헨티나", "Argentina", "Latin America"),
    "GBR": ("영국", "United Kingdom", "Northern Europe"),
    "FRA": ("프랑스", "France", "Western Europe"),
    "DEU": ("독일", "Germany", "Western Europe"),
    "ITA": ("이탈리아", "Italy", "Southern Europe"),
    "ESP": ("스페인", "Spain", "Southern Europe"),
    "RUS": ("러시아", "Russian Federation", "Eastern Europe"),
    "IND": ("인도", "India", "Southern Asia"),
    "PAK": ("파키스탄", "Pakistan", "Southern Asia"),
    "IDN": ("인도네시아", "Indonesia", "South-Eastern Asia"),
    "VNM": ("베트남", "Viet Nam", "South-Eastern Asia"),
    "THA": ("태국", "Thailand", "South-Eastern Asia"),
    "PHL": ("필리핀", "Philippines", "South-Eastern Asia"),
    "MYS": ("말레이시아", "Malaysia", "South-Eastern Asia"),
    "SGP": ("싱가포르", "Singapore", "South-Eastern Asia"),
    "AUS": ("호주", "Australia", "Australia and New Zealand"),
    "NZL": ("뉴질랜드", "New Zealand", "Australia and New Zealand"),
    "ZAF": ("남아프리카공화국", "South Africa", "Sub-Saharan Africa"),
    "EGY": ("이집트", "Egypt, Arab Rep.", "Northern Africa"),
    "NGA": ("나이지리아", "Nigeria", "Sub-Saharan Africa"),
    "KEN": ("케냐", "Kenya", "Sub-Saharan Africa"),
    "SAU": ("사우디아라비아", "Saudi Arabia", "Western Asia"),
    "TUR": ("튀르키예", "Türkiye", "Western Asia"),
    "IRN": ("이란", "Iran, Islamic Rep.", "Southern Asia"),
    "ISR": ("이스라엘", "Israel", "Western Asia"),
    "ARE": ("아랍에미리트", "United Arab Emirates", "Western Asia"),
    "NLD": ("네덜란드", "Netherlands", "Western Europe"),
    "SWE": ("스웨덴", "Sweden", "Northern Europe"),
    "NOR": ("노르웨이", "Norway", "Northern Europe"),
    "FIN": ("핀란드", "Finland", "Northern Europe"),
    "POL": ("폴란드", "Poland", "Eastern Europe"),
    "CHE": ("스위스", "Switzerland", "Western Europe"),
}


# ─── 큐레이션된 지표 카탈로그 (교육용 핵심 지표) ───
INDICATORS: list[IndicatorMeta] = [
    IndicatorMeta(
        dataset_id="wb_NY.GDP.MKTP.CD",
        source="World Bank",
        indicator_code="NY.GDP.MKTP.CD",
        name_ko="국내총생산(GDP, 명목)",
        name_en="GDP (current US$)",
        category="economy",
        subcategory="national_accounts",
        unit="USD",
        description_ko="현재 미국 달러 기준 명목 국내총생산.",
        license="CC BY 4.0",
        update_frequency="annual",
        coverage_years=(1960, 2023),
    ),
    IndicatorMeta(
        dataset_id="wb_NY.GDP.PCAP.CD",
        source="World Bank",
        indicator_code="NY.GDP.PCAP.CD",
        name_ko="1인당 GDP(명목)",
        name_en="GDP per capita (current US$)",
        category="economy",
        subcategory="national_accounts",
        unit="USD",
        description_ko="명목 GDP를 인구로 나눈 값.",
        license="CC BY 4.0",
        update_frequency="annual",
        coverage_years=(1960, 2023),
    ),
    IndicatorMeta(
        dataset_id="wb_SP.POP.TOTL",
        source="World Bank",
        indicator_code="SP.POP.TOTL",
        name_ko="총인구",
        name_en="Population, total",
        category="population",
        subcategory="size",
        unit="명",
        description_ko="해당 국가의 연앙 총인구.",
        license="CC BY 4.0",
        update_frequency="annual",
        coverage_years=(1960, 2023),
    ),
    IndicatorMeta(
        dataset_id="wb_SP.URB.TOTL.IN.ZS",
        source="World Bank",
        indicator_code="SP.URB.TOTL.IN.ZS",
        name_ko="도시화율",
        name_en="Urban population (% of total)",
        category="population",
        subcategory="urbanization",
        unit="%",
        description_ko="총인구 대비 도시 거주 인구 비율.",
        license="CC BY 4.0",
        update_frequency="annual",
        coverage_years=(1960, 2023),
    ),
    IndicatorMeta(
        dataset_id="wb_EN.GHG.CO2.PC.CE.AR5",
        source="World Bank",
        indicator_code="EN.GHG.CO2.PC.CE.AR5",
        name_ko="1인당 이산화탄소 배출량",
        name_en="CO2 emissions per capita (t)",
        category="environment",
        subcategory="emissions",
        unit="tCO2/명",
        description_ko="1인당 연간 이산화탄소 배출량(톤).",
        license="CC BY 4.0",
        update_frequency="annual",
        coverage_years=(1990, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_AG.LND.FRST.ZS",
        source="World Bank",
        indicator_code="AG.LND.FRST.ZS",
        name_ko="산림 면적 비율",
        name_en="Forest area (% of land area)",
        category="environment",
        subcategory="land_cover",
        unit="%",
        description_ko="국토 면적 중 산림이 차지하는 비율.",
        license="CC BY 4.0",
        update_frequency="annual",
        coverage_years=(1990, 2021),
    ),
    IndicatorMeta(
        dataset_id="wb_EG.USE.PCAP.KG.OE",
        source="World Bank",
        indicator_code="EG.USE.PCAP.KG.OE",
        name_ko="1인당 에너지 사용량",
        name_en="Energy use per capita (kg of oil eq.)",
        category="energy",
        subcategory="consumption",
        unit="kgoe/명",
        description_ko="1인당 연간 에너지 소비(석유환산 kg).",
        license="CC BY 4.0",
        update_frequency="annual",
        coverage_years=(1971, 2015),
    ),
    IndicatorMeta(
        dataset_id="wb_SP.DYN.LE00.IN",
        source="World Bank",
        indicator_code="SP.DYN.LE00.IN",
        name_ko="기대수명",
        name_en="Life expectancy at birth (years)",
        category="population",
        subcategory="health",
        unit="년",
        description_ko="출생 시 기대수명(전체).",
        license="CC BY 4.0",
        update_frequency="annual",
        coverage_years=(1960, 2022),
    ),

    # ─── 인구·인구구조 (세계지리: 인구 / 통합사회: 인구문제) ───
    IndicatorMeta(
        dataset_id="wb_SP.POP.GROW",
        source="World Bank", indicator_code="SP.POP.GROW",
        name_ko="인구 증가율", name_en="Population growth (annual %)",
        category="population", subcategory="growth", unit="%",
        description_ko="전년 대비 연간 인구 증가율.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1961, 2023),
    ),
    IndicatorMeta(
        dataset_id="wb_SP.DYN.TFRT.IN",
        source="World Bank", indicator_code="SP.DYN.TFRT.IN",
        name_ko="합계출산율", name_en="Total fertility rate (births/woman)",
        category="population", subcategory="fertility", unit="명/여성",
        description_ko="여성 1명이 평생 낳을 것으로 기대되는 자녀 수.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_SP.DYN.CBRT.IN",
        source="World Bank", indicator_code="SP.DYN.CBRT.IN",
        name_ko="조출생률", name_en="Crude birth rate (per 1,000)",
        category="population", subcategory="fertility", unit="‰",
        description_ko="인구 1,000명당 연간 출생아 수.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_SP.DYN.CDRT.IN",
        source="World Bank", indicator_code="SP.DYN.CDRT.IN",
        name_ko="조사망률", name_en="Crude death rate (per 1,000)",
        category="population", subcategory="mortality", unit="‰",
        description_ko="인구 1,000명당 연간 사망자 수.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_SP.DYN.IMRT.IN",
        source="World Bank", indicator_code="SP.DYN.IMRT.IN",
        name_ko="영아 사망률", name_en="Infant mortality rate (per 1,000 live births)",
        category="population", subcategory="mortality", unit="‰",
        description_ko="출생 1,000명당 1세 미만 사망 영아 수.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_SP.POP.65UP.TO.ZS",
        source="World Bank", indicator_code="SP.POP.65UP.TO.ZS",
        name_ko="65세 이상 인구 비율", name_en="Population ages 65+ (% of total)",
        category="population", subcategory="age_structure", unit="%",
        description_ko="고령화 지표. 7% 이상=고령화사회, 14%=고령사회, 20%=초고령사회.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2023),
    ),
    IndicatorMeta(
        dataset_id="wb_SP.POP.0014.TO.ZS",
        source="World Bank", indicator_code="SP.POP.0014.TO.ZS",
        name_ko="0-14세 인구 비율", name_en="Population ages 0-14 (% of total)",
        category="population", subcategory="age_structure", unit="%",
        description_ko="유소년 부양 부담을 보여주는 지표.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2023),
    ),
    IndicatorMeta(
        dataset_id="wb_SP.POP.DPND.OL",
        source="World Bank", indicator_code="SP.POP.DPND.OL",
        name_ko="노년 부양비", name_en="Age dependency ratio, old (% of working-age)",
        category="population", subcategory="age_structure", unit="%",
        description_ko="생산가능인구 100명당 65세 이상 인구 수.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2023),
    ),
    IndicatorMeta(
        dataset_id="wb_SP.POP.DPND.YG",
        source="World Bank", indicator_code="SP.POP.DPND.YG",
        name_ko="유년 부양비", name_en="Age dependency ratio, young (% of working-age)",
        category="population", subcategory="age_structure", unit="%",
        description_ko="생산가능인구 100명당 0-14세 인구 수.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2023),
    ),
    IndicatorMeta(
        dataset_id="wb_SM.POP.NETM",
        source="World Bank", indicator_code="SM.POP.NETM",
        name_ko="순이주", name_en="Net migration",
        category="population", subcategory="migration", unit="명",
        description_ko="유입 이주민 - 유출 이주민(5년 누적).",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1962, 2017),
    ),
    IndicatorMeta(
        dataset_id="wb_EN.POP.DNST",
        source="World Bank", indicator_code="EN.POP.DNST",
        name_ko="인구 밀도", name_en="Population density (per km²)",
        category="population", subcategory="size", unit="명/km²",
        description_ko="국토 면적당 인구 수.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1961, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_SP.URB.GROW",
        source="World Bank", indicator_code="SP.URB.GROW",
        name_ko="도시 인구 증가율", name_en="Urban population growth (annual %)",
        category="population", subcategory="urbanization", unit="%",
        description_ko="전년 대비 도시 거주 인구 증가율.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1961, 2023),
    ),

    # ─── 경제·산업구조 (세계지리: 산업 / 통합사회: 시장·정의) ───
    IndicatorMeta(
        dataset_id="wb_NV.AGR.TOTL.ZS",
        source="World Bank", indicator_code="NV.AGR.TOTL.ZS",
        name_ko="농업 부가가치 (GDP 비)", name_en="Agriculture value added (% of GDP)",
        category="economy", subcategory="structure", unit="%",
        description_ko="GDP에서 농림어업이 차지하는 비중.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_NV.IND.TOTL.ZS",
        source="World Bank", indicator_code="NV.IND.TOTL.ZS",
        name_ko="산업 부가가치 (GDP 비)", name_en="Industry value added (% of GDP)",
        category="economy", subcategory="structure", unit="%",
        description_ko="GDP에서 광업·제조업·건설업·전력가스가 차지하는 비중.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_NV.IND.MANF.ZS",
        source="World Bank", indicator_code="NV.IND.MANF.ZS",
        name_ko="제조업 부가가치 (GDP 비)", name_en="Manufacturing value added (% of GDP)",
        category="economy", subcategory="structure", unit="%",
        description_ko="GDP에서 제조업이 차지하는 비중.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_NV.SRV.TOTL.ZS",
        source="World Bank", indicator_code="NV.SRV.TOTL.ZS",
        name_ko="서비스업 부가가치 (GDP 비)", name_en="Services value added (% of GDP)",
        category="economy", subcategory="structure", unit="%",
        description_ko="GDP에서 서비스업이 차지하는 비중. 후기산업화 지표.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_SI.POV.GINI",
        source="World Bank", indicator_code="SI.POV.GINI",
        name_ko="지니계수", name_en="Gini index",
        category="economy", subcategory="inequality", unit="지수",
        description_ko="소득 불평등 정도(0=완전평등, 100=완전불평등).",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1980, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_SI.POV.DDAY",
        source="World Bank", indicator_code="SI.POV.DDAY",
        name_ko="극빈율 ($2.15/일)", name_en="Poverty headcount ratio at $2.15/day (% of pop)",
        category="economy", subcategory="inequality", unit="%",
        description_ko="하루 2.15달러(2017 PPP) 미만으로 사는 인구 비율.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1980, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_SL.UEM.TOTL.ZS",
        source="World Bank", indicator_code="SL.UEM.TOTL.ZS",
        name_ko="실업률", name_en="Unemployment rate (% of labor force)",
        category="economy", subcategory="employment", unit="%",
        description_ko="노동력 대비 실업자 비율(ILO 추정치).",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1991, 2023),
    ),

    # ─── 무역·세계화 ───
    IndicatorMeta(
        dataset_id="wb_NE.EXP.GNFS.ZS",
        source="World Bank", indicator_code="NE.EXP.GNFS.ZS",
        name_ko="수출 (GDP 비)", name_en="Exports of goods and services (% of GDP)",
        category="trade", subcategory="exports", unit="%",
        description_ko="GDP 대비 상품·서비스 수출액. 무역 의존도 지표.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_NE.IMP.GNFS.ZS",
        source="World Bank", indicator_code="NE.IMP.GNFS.ZS",
        name_ko="수입 (GDP 비)", name_en="Imports of goods and services (% of GDP)",
        category="trade", subcategory="imports", unit="%",
        description_ko="GDP 대비 상품·서비스 수입액.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_BX.KLT.DINV.WD.GD.ZS",
        source="World Bank", indicator_code="BX.KLT.DINV.WD.GD.ZS",
        name_ko="외국인직접투자 유입 (GDP 비)", name_en="FDI net inflows (% of GDP)",
        category="trade", subcategory="fdi", unit="%",
        description_ko="GDP 대비 외국인직접투자 순유입. 개방도 지표.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1970, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_NE.TRD.GNFS.ZS",
        source="World Bank", indicator_code="NE.TRD.GNFS.ZS",
        name_ko="무역의존도", name_en="Trade (% of GDP)",
        category="trade", subcategory="openness", unit="%",
        description_ko="GDP 대비 (수출+수입) 합계. 무역 개방도 지표.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_TX.VAL.MRCH.CD.WT",
        source="World Bank", indicator_code="TX.VAL.MRCH.CD.WT",
        name_ko="상품 수출액", name_en="Merchandise exports (current US$)",
        category="trade", subcategory="exports", unit="USD",
        description_ko="상품 수출 총액(명목).",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1960, 2022),
    ),

    # ─── 에너지·자원 (지속가능성) ───
    IndicatorMeta(
        dataset_id="wb_EG.ELC.RNEW.ZS",
        source="World Bank", indicator_code="EG.ELC.RNEW.ZS",
        name_ko="신재생 전력 비중", name_en="Renewable electricity output (% of total)",
        category="energy", subcategory="renewable", unit="%",
        description_ko="전력 생산량 중 신재생에너지(수력 포함) 비중.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1990, 2015),
    ),
    IndicatorMeta(
        dataset_id="wb_EG.FEC.RNEW.ZS",
        source="World Bank", indicator_code="EG.FEC.RNEW.ZS",
        name_ko="신재생에너지 소비 비중", name_en="Renewable energy consumption (% of total)",
        category="energy", subcategory="renewable", unit="%",
        description_ko="최종에너지소비에서 재생가능에너지가 차지하는 비중.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1990, 2021),
    ),
    IndicatorMeta(
        dataset_id="wb_EG.ELC.FOSL.ZS",
        source="World Bank", indicator_code="EG.ELC.FOSL.ZS",
        name_ko="화석연료 전력 비중", name_en="Electricity from fossil fuels (% of total)",
        category="energy", subcategory="fossil", unit="%",
        description_ko="석탄·석유·천연가스 발전 비중.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1990, 2015),
    ),
    IndicatorMeta(
        dataset_id="wb_EG.ELC.ACCS.ZS",
        source="World Bank", indicator_code="EG.ELC.ACCS.ZS",
        name_ko="전력 접근율", name_en="Access to electricity (% of population)",
        category="energy", subcategory="access", unit="%",
        description_ko="전기를 사용할 수 있는 인구 비율.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1990, 2022),
    ),

    # ─── 환경·토지 ───
    IndicatorMeta(
        dataset_id="wb_AG.LND.AGRI.ZS",
        source="World Bank", indicator_code="AG.LND.AGRI.ZS",
        name_ko="농업용지 비율", name_en="Agricultural land (% of land area)",
        category="environment", subcategory="land_cover", unit="%",
        description_ko="국토 중 농경지·목초지 등 농업 용도 비율.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1961, 2021),
    ),
    IndicatorMeta(
        dataset_id="wb_AG.LND.ARBL.ZS",
        source="World Bank", indicator_code="AG.LND.ARBL.ZS",
        name_ko="경작지 비율", name_en="Arable land (% of land area)",
        category="environment", subcategory="land_cover", unit="%",
        description_ko="국토 중 일년생 작물 재배 가능 토지 비율.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1961, 2021),
    ),

    # ─── 개발·사회 (인권·복지) ───
    IndicatorMeta(
        dataset_id="wb_SE.PRM.ENRR",
        source="World Bank", indicator_code="SE.PRM.ENRR",
        name_ko="초등 교육 등록률(총)", name_en="School enrollment, primary (% gross)",
        category="development", subcategory="education", unit="%",
        description_ko="초등학교 등록 인구 / 초등 학령 인구. 100% 초과 가능.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1970, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_SE.SEC.ENRR",
        source="World Bank", indicator_code="SE.SEC.ENRR",
        name_ko="중등 교육 등록률(총)", name_en="School enrollment, secondary (% gross)",
        category="development", subcategory="education", unit="%",
        description_ko="중등학교 등록률.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1970, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_SE.TER.ENRR",
        source="World Bank", indicator_code="SE.TER.ENRR",
        name_ko="고등 교육 등록률(총)", name_en="School enrollment, tertiary (% gross)",
        category="development", subcategory="education", unit="%",
        description_ko="대학·전문대 등록률.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1970, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_SE.ADT.LITR.ZS",
        source="World Bank", indicator_code="SE.ADT.LITR.ZS",
        name_ko="성인 문해율", name_en="Adult literacy rate (% age 15+)",
        category="development", subcategory="education", unit="%",
        description_ko="15세 이상 인구 중 읽고 쓸 줄 아는 인구 비율.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1970, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_SH.STA.MMRT",
        source="World Bank", indicator_code="SH.STA.MMRT",
        name_ko="모성 사망률", name_en="Maternal mortality (per 100,000 live births)",
        category="development", subcategory="health", unit="명/10만명",
        description_ko="출생 10만 명당 임신·출산 관련 사망 산모 수.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(2000, 2020),
    ),
    IndicatorMeta(
        dataset_id="wb_SH.STA.BASS.ZS",
        source="World Bank", indicator_code="SH.STA.BASS.ZS",
        name_ko="기본 위생시설 접근율", name_en="Access to basic sanitation (% of pop)",
        category="development", subcategory="sanitation", unit="%",
        description_ko="개량 위생시설을 이용하는 인구 비율.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(2000, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_SH.H2O.BASW.ZS",
        source="World Bank", indicator_code="SH.H2O.BASW.ZS",
        name_ko="안전한 식수 접근율", name_en="Access to basic drinking water (% of pop)",
        category="development", subcategory="sanitation", unit="%",
        description_ko="안전한 식수원을 이용하는 인구 비율.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(2000, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_IT.NET.USER.ZS",
        source="World Bank", indicator_code="IT.NET.USER.ZS",
        name_ko="인터넷 사용률", name_en="Individuals using the Internet (% of pop)",
        category="development", subcategory="ict", unit="%",
        description_ko="최근 3개월 내 인터넷을 사용한 인구 비율.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1990, 2022),
    ),
    IndicatorMeta(
        dataset_id="wb_IT.CEL.SETS.P2",
        source="World Bank", indicator_code="IT.CEL.SETS.P2",
        name_ko="휴대전화 가입률", name_en="Mobile cellular subscriptions (per 100 people)",
        category="development", subcategory="ict", unit="건/100명",
        description_ko="인구 100명당 휴대전화 가입 건수.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(1990, 2022),
    ),
]


class WorldBankAdapter(SourceAdapter):
    source_name = "World Bank"
    license = "CC BY 4.0"
    base_url = "https://api.worldbank.org/v2"

    def list_indicators(self) -> list[IndicatorMeta]:
        return INDICATORS

    def fetch(self, indicator_code: str, countries: list[str],
              year_range: tuple[int, int]) -> list[dict]:
        """World Bank API 호출. countries는 ISO3 리스트."""
        country_str = ";".join(countries) if countries else "all"
        date_str = f"{year_range[0]}:{year_range[1]}"
        params = urllib.parse.urlencode({
            "format": "json",
            "date": date_str,
            "per_page": 20000,
        })
        url = f"{self.base_url}/country/{country_str}/indicator/{indicator_code}?{params}"

        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())

        # World Bank API의 응답: [meta, [records...]]
        if not isinstance(data, list) or len(data) < 2:
            return []
        return data[1] or []

    def transform(self, raw: list[dict], indicator: IndicatorMeta) -> list[StandardRecord]:
        records: list[StandardRecord] = []
        fetched_at = datetime.utcnow().isoformat() + "Z"

        for row in raw:
            if not row:
                continue
            iso3 = (row.get("countryiso3code") or "").upper()
            if not iso3 or iso3 not in COUNTRY_NAMES:
                # 미매핑 국가는 건너뛰되, 영문명만으로 저장하는 옵션도 가능
                continue
            name_ko, name_en, region = COUNTRY_NAMES[iso3]

            try:
                year = int(row.get("date"))
            except (TypeError, ValueError):
                continue

            value = row.get("value")
            value = float(value) if value is not None else None

            records.append(StandardRecord(
                dataset_id=indicator.dataset_id,
                source=self.source_name,
                source_url=(f"{self.base_url}/country/{iso3}/indicator/"
                            f"{indicator.indicator_code}?format=json"),
                indicator_code=indicator.indicator_code,
                indicator_name_ko=indicator.name_ko,
                indicator_name_en=indicator.name_en,
                category=indicator.category,
                subcategory=indicator.subcategory,
                unit=indicator.unit,
                country_iso3=iso3,
                country_name_ko=name_ko,
                country_name_en=name_en,
                region=region,
                year=year,
                period_type="annual",
                period_label=str(year),
                value=value,
                license=self.license,
                fetched_at=fetched_at,
                last_updated_at_source=None,
            ))
        return records
