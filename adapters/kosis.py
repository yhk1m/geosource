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

        parts = indicator_code.split("/")
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
            "prdSe": "Y",                         # 연간
            "startPrdDe": str(year_range[0]),
            "endPrdDe": str(year_range[1]),
        }
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

            # 시도명을 country_* 필드에 시도명으로 채워넣는 비표준 사용.
            # 추후 행정구역 코드 컬럼을 별도로 추가하는 것이 정석.
            region_name = row.get("C1_NM") or "전국"

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
                country_iso3="KOR",
                country_name_ko=f"대한민국 - {region_name}",
                country_name_en=f"Korea - {region_name}",
                region="Eastern Asia",
                year=year,
                period_type="annual",
                period_label=str(year),
                value=value,
                license=self.license,
                fetched_at=fetched_at,
                notes=f"행정구역: {region_name}",
            ))
        return records
