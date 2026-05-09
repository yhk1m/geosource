"""
KOSIS(통계청 국가통계포털) 어댑터.

KOSIS OpenAPI 문서: https://kosis.kr/openapi/index/index.jsp
- 인증키 필요 (kosis.kr에서 발급)
- 라이선스: 공공누리(KOGL) — 출처별로 1~4유형 상이, 항목 단위 확인 필요
- CORS 미허용 → 반드시 서버사이드(또는 빌드 타임) 호출

이 모듈은 골격만 제공한다. 실제 호출 시 KOSIS_API_KEY 환경변수를 채워주세요.
"""
from __future__ import annotations
import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schema import StandardRecord, IndicatorMeta
from adapters.base import SourceAdapter


# KOSIS는 통계표(orgId, tblId) 단위로 호출하는 구조라
# World Bank처럼 단일 indicator_code로 매핑하기 어렵다.
# → indicator_code에 "{orgId}/{tblId}/{itmId}" 합성 ID를 부여한다.
# → fetch에 추가로 objL1 인자(분류1) 필요. KOSIS는 itmId·objL1 누락 시 err=20 반환.

# 시도명 → 표준 행정구역분류코드 (KOSIS 표마다 옛/신 코드가 섞여있어 이름 기반 정규화)
SIDO_NAME_TO_CODE = {
    "전국": "00",
    "서울특별시": "11",
    "부산광역시": "26",
    "대구광역시": "27",
    "인천광역시": "28",
    "광주광역시": "29",
    "대전광역시": "30",
    "울산광역시": "31",
    "세종특별자치시": "36",
    "세종시": "36",
    "경기도": "41",
    "강원특별자치도": "51",
    "강원도": "51",  # 옛 이름
    "충청북도": "43",
    "충청남도": "44",
    "전북특별자치도": "52",
    "전라북도": "52",  # 옛 이름
    "전라남도": "46",
    "경상북도": "47",
    "경상남도": "48",
    "제주특별자치도": "50",
    "제주도": "50",  # 옛 이름
}
INDICATORS: list[IndicatorMeta] = [
    IndicatorMeta(
        dataset_id="kosis_101_DT_1B040A3_T20",
        source="KOSIS",
        indicator_code="101/DT_1B040A3/T20",  # orgId/tblId/itmId (T20 = 한국인 인구)
        name_ko="시도별 인구",
        name_en="Population by Province (Korea)",
        category="population",
        subcategory="size",
        unit="명",
        description_ko="대한민국 시도/시군구 단위 주민등록 한국인 인구. 통계청.",
        license="KOGL Type 1",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    IndicatorMeta(
        dataset_id="kosis_101_DT_1B81A21_T1",
        source="KOSIS",
        indicator_code="101/DT_1B81A21/T1",  # T1 = 합계출산율
        name_ko="시도별 합계출산율",
        name_en="Total Fertility Rate by Province",
        category="population",
        subcategory="fertility",
        unit="명",
        description_ko="시도 단위 합계출산율(여성 1인이 평생 낳을 것으로 기대되는 평균 출생아 수). 통계청 인구동향조사.",
        license="KOGL Type 1",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    IndicatorMeta(
        dataset_id="kosis_101_DT_1B040B3_T1",
        source="KOSIS",
        indicator_code="101/DT_1B040B3/T1",  # T1 = 세대수
        name_ko="시도별 세대수",
        name_en="Number of Households by Province",
        category="population",
        subcategory="household",
        unit="세대",
        description_ko="시도/시군구 단위 주민등록 세대수. 통계청.",
        license="KOGL Type 1",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    IndicatorMeta(
        dataset_id="kosis_101_DT_1DA7104S_T80",
        source="KOSIS",
        indicator_code="101/DT_1DA7104S/T80?objL2=0",  # 시도별 실업률, 성별=계
        name_ko="시도별 실업률",
        name_en="Unemployment Rate by Province",
        category="economy",
        subcategory="unemployment",
        unit="%",
        description_ko="경제활동인구 대비 실업자 비율. 시도별 (성별 계). 경제활동인구조사.",
        license="KOGL Type 1",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    IndicatorMeta(
        dataset_id="kosis_101_DT_1C86_T1",
        source="KOSIS",
        indicator_code="101/DT_1C86/T1",        # T1 = 1인당 지역내총생산
        name_ko="시도별 1인당 GRDP",
        name_en="GRDP per capita by Province",
        category="economy",
        subcategory="grdp",
        unit="천원",
        description_ko="시도 인구로 나눈 1인당 지역내총생산. 통계청 지역소득.",
        license="KOGL Type 1",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    # 인구동향
    IndicatorMeta(
        dataset_id="kosis_101_DT_1B81A19_T1",
        source="KOSIS",
        indicator_code="101/DT_1B81A19/T1",
        name_ko="시도별 출생성비",
        name_en="Sex Ratio at Birth by Province",
        category="population",
        subcategory="births",
        unit="명",
        description_ko="여아 100명당 남아 출생 수. 통계청 인구동향조사.",
        license="KOGL Type 1",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    IndicatorMeta(
        dataset_id="kosis_101_DT_1B83A03_T10",
        source="KOSIS",
        indicator_code="101/DT_1B83A03/T10?objL2=000",  # 연령별=계
        name_ko="시도별 혼인건수",
        name_en="Number of Marriages by Province",
        category="population",
        subcategory="marriage",
        unit="건",
        description_ko="연간 혼인 신고 건수. 통계청 인구동향조사.",
        license="KOGL Type 1",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    IndicatorMeta(
        dataset_id="kosis_101_DT_1B85003_T10",
        source="KOSIS",
        indicator_code="101/DT_1B85003/T10?objL2=000",  # 연령별=계
        name_ko="시도별 이혼건수",
        name_en="Number of Divorces by Province",
        category="population",
        subcategory="divorce",
        unit="건",
        description_ko="연간 이혼 신고 건수. 통계청 인구동향조사.",
        license="KOGL Type 1",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    # 노동/고용 (모두 시도별 표, 성별/활동상태=계)
    IndicatorMeta(
        dataset_id="kosis_101_DT_1DA7004S_T10",
        source="KOSIS",
        indicator_code="101/DT_1DA7004S/T10",
        name_ko="시도별 15세이상인구",
        name_en="Population aged 15+ by Province",
        category="economy",
        subcategory="labor_force",
        unit="천명",
        description_ko="노동가능 연령 인구. 경제활동인구조사.",
        license="KOGL Type 1",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    IndicatorMeta(
        dataset_id="kosis_101_DT_1DA7030S_T30",
        source="KOSIS",
        indicator_code="101/DT_1DA7030S/T30?objL2=0",  # 성별=계
        name_ko="시도별 취업자",
        name_en="Employed Persons by Province",
        category="economy",
        subcategory="employment",
        unit="천명",
        description_ko="취업자 수 (성별 계). 경제활동인구조사.",
        license="KOGL Type 1",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    IndicatorMeta(
        dataset_id="kosis_101_DT_1DA7088S_T40",
        source="KOSIS",
        indicator_code="101/DT_1DA7088S/T40?objL2=0",  # 성별=계
        name_ko="시도별 실업자",
        name_en="Unemployed Persons by Province",
        category="economy",
        subcategory="unemployment",
        unit="천명",
        description_ko="실업자 수 (성별 계). 경제활동인구조사.",
        license="KOGL Type 1",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    IndicatorMeta(
        dataset_id="kosis_101_DT_1DA7146S_T50",
        source="KOSIS",
        indicator_code="101/DT_1DA7146S/T50?objL2=00",  # 활동상태별=계
        name_ko="시도별 비경제활동인구",
        name_en="Economically Inactive Population by Province",
        category="economy",
        subcategory="labor_inactive",
        unit="천명",
        description_ko="경제활동에 참여하지 않는 15세 이상 인구. 경제활동인구조사.",
        license="KOGL Type 1",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    # 경제 — 소비자물가
    IndicatorMeta(
        dataset_id="kosis_101_DT_1F02001_T10",
        source="KOSIS",
        indicator_code="101/DT_1F02001/T10?objL2=0",  # 품목별=총지수
        name_ko="시도별 소비자물가지수",
        name_en="Consumer Price Index by Province",
        category="economy",
        subcategory="cpi",
        unit="2020=100",
        description_ko="2020년=100 기준 소비자물가지수 총지수. 통계청.",
        license="KOGL Type 1",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    # 농림
    IndicatorMeta(
        dataset_id="kosis_101_DT_1ES4F09S_T00",
        source="KOSIS",
        indicator_code="101/DT_1ES4F09S/T00",
        name_ko="시도별 농어가 가구수",
        name_en="Farm and Fishery Households by Province",
        category="agriculture",
        subcategory="farm_household",
        unit="천가구",
        description_ko="농가+어가 가구 수. 통계청.",
        license="KOGL Type 1",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    # 인구이동 (인구총조사 5년 단위, 시도+시군구)
    IndicatorMeta(
        dataset_id="kosis_101_DT_1PA2002_T10",
        source="KOSIS",
        indicator_code="101/DT_1PA2002/T10?objL2=0&objL3=000&prdSe=F&newEstPrdCnt=3",
        name_ko="시도별 거주지 이전 인구",
        name_en="Population by Migration Type",
        category="population",
        subcategory="migration",
        unit="명",
        description_ko="12세 이상 인구 중 5년 내 거주지를 이전한 인구 (성·연령 계). 인구총조사 5년 단위.",
        license="KOGL Type 1",
        update_frequency="annual",  # 표시는 연간이지만 실제 5년 단위
        coverage_years=(2010, 2020),
    ),
    # 필요한 통계표를 여기에 계속 추가
]


class KosisAdapter(SourceAdapter):
    source_name = "KOSIS"
    license = "KOGL Type 1"
    base_url = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("KOSIS_API_KEY", "")
        if not self.api_key:
            print("[KOSIS] 경고: KOSIS_API_KEY 미설정. 빌드 시 .env 또는 환경변수 필요.")

    def list_indicators(self) -> list[IndicatorMeta]:
        return INDICATORS

    def fetch(self, indicator_code: str, countries: list[str],
              year_range: tuple[int, int]) -> list[dict]:
        """
        KOSIS는 'countries' 개념이 없고 시도/시군구 단위라
        countries 인자는 무시한다. (대신 prdSe/startPrdDe/endPrdDe 사용)
        """
        if not self.api_key:
            return []  # 키 없으면 빈 결과

        # indicator_code 형식:
        #   "{org}/{tbl}/{itm}"             — 기본
        #   "{org}/{tbl}/{itm}?objL2=ALL"   — 2차 차원 추가
        # objL2/objL3는 querystring 형태로 부착해 일부 테이블의 필수 파라미터를 채운다.
        code, _, extra = indicator_code.partition("?")
        parts = code.split("/")
        org_id, tbl_id = parts[0], parts[1]
        itm_id = parts[2] if len(parts) > 2 else "ALL"

        params = {
            "method": "getList",
            "apiKey": self.api_key,
            "format": "json",
            "jsonVD": "Y",
            "orgId": org_id,
            "tblId": tbl_id,
            "itmId": itm_id,                      # 항목 ID (필수)
            "objL1": "ALL",                       # 분류1 = 전체 행정구역 (필수)
            "prdSe": "Y",                         # 연간 (querystring으로 override 가능: F=5년 등)
            "startPrdDe": str(year_range[0]),
            "endPrdDe": str(year_range[1]),
        }
        # 추가 파라미터 (예: ?objL2=ALL&objL3=ALL&prdSe=F&newEstPrdCnt=3)
        # newEstPrdCnt가 있으면 startPrdDe/endPrdDe는 제거 (충돌)
        for kv in extra.split("&"):
            if "=" in kv:
                k, v = kv.split("=", 1)
                params[k] = v
        if "newEstPrdCnt" in params:
            params.pop("startPrdDe", None)
            params.pop("endPrdDe", None)

        url = f"{self.base_url}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            payload = json.loads(resp.read())

        # KOSIS 에러 응답: {"err":"20","errMsg":"..."}
        if isinstance(payload, dict):
            print(f"[KOSIS] API 오류 (err={payload.get('err')}): {payload.get('errMsg')}")
            return []
        return payload

    def transform(self, raw: list[dict], indicator: IndicatorMeta) -> list[StandardRecord]:
        records: list[StandardRecord] = []
        fetched_at = datetime.utcnow().isoformat() + "Z"

        for row in raw:
            try:
                year = int(row.get("PRD_DE"))
                value = float(row.get("DT")) if row.get("DT") else None
            except (TypeError, ValueError):
                continue

            # KOSIS C1 코드를 entity 키로 사용 (KR- 프리픽스로 다른 출처와 분리)
            #   2자리 → 시도 (00=전국, 11=서울 ...)
            #   5자리 → 시군구 (11010=종로구 ...)
            #   7~10자리 → 읍면동
            # 시도 레벨은 표마다 옛/신 코드가 다르므로 이름 기반 정규화로 통일.
            c1_code = (row.get("C1") or "00").strip()
            region_name = row.get("C1_NM") or "전국"
            level = "sido" if len(c1_code) <= 2 else (
                "sigungu" if len(c1_code) == 5 else "eupmyeondong"
            )
            if level == "sido" and region_name in SIDO_NAME_TO_CODE:
                c1_code = SIDO_NAME_TO_CODE[region_name]
            iso_key = f"KR-{c1_code}"

            records.append(StandardRecord(
                dataset_id=indicator.dataset_id,
                source=self.source_name,
                source_url="https://kosis.kr/statHtml/statHtml.do?orgId="
                           f"{indicator.indicator_code.replace('/', '&tblId=')}",
                indicator_code=indicator.indicator_code,
                indicator_name_ko=indicator.name_ko,
                indicator_name_en=indicator.name_en,
                category=indicator.category,
                subcategory=indicator.subcategory,
                unit=indicator.unit,
                country_iso3=iso_key,
                country_name_ko=region_name,
                country_name_en=region_name,
                region="Eastern Asia",
                year=year,
                period_type="annual",
                period_label=str(year),
                value=value,
                license=self.license,
                fetched_at=fetched_at,
                notes=f"코드:{c1_code}|단위:{level}|이름:{region_name}",
            ))
        return records
