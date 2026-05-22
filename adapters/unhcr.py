# © 2026 김용현
"""
UNHCR Refugee Statistics 어댑터 — Refugee Data Finder REST API.

엔드포인트(공개, 인증 없음):
    https://api.unhcr.org/population/v1/population/
      ?yearFrom=YYYY&yearTo=YYYY&coa_all=true&limit=10000

`coa_all=true` 로 호출하면 모든 망명국(country of asylum)에 대해
출신국(coo) 차원을 합산한 집계 행을 한 번에 반환한다. 한 응답에
(refugees, asylum_seekers, idps, stateless, returned_refugees ...) 컬럼이
모두 포함되므로 5개 지표 모두 단일 호출로 추출.

라이선스: UNHCR 데이터는 일반적으로 CC BY 4.0 (출처 표기 시 자유 이용)
"""
from __future__ import annotations
import sys
import urllib.request
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schema import StandardRecord, IndicatorMeta
from adapters.base import SourceAdapter
from adapters.worldbank import COUNTRY_NAMES


BASE_URL = "https://api.unhcr.org/population/v1/population/"

# UNHCR 첫 통계 데이터가 정돈된 2000년부터
YEAR_FROM = 2000
YEAR_TO = 2024


INDICATORS: list[IndicatorMeta] = [
    IndicatorMeta(
        dataset_id="unhcr_refugees_hosted",
        source="UNHCR", indicator_code="UNHCR/refugees",
        name_ko="수용 난민 수", name_en="Refugees hosted",
        category="population", subcategory="displacement",
        unit="명",
        description_ko="해당 국가가 망명국으로 수용 중인 난민 인원수(연말 기준). 박해를 피해 자국을 떠나 국제 보호를 받는 사람.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    IndicatorMeta(
        dataset_id="unhcr_asylum_seekers",
        source="UNHCR", indicator_code="UNHCR/asylum_seekers",
        name_ko="망명 신청자 수", name_en="Asylum-seekers",
        category="population", subcategory="displacement",
        unit="명",
        description_ko="망명 신청 후 심사가 계류 중인 인원수. 난민 인정을 기다리는 단계.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    IndicatorMeta(
        dataset_id="unhcr_idps",
        source="UNHCR", indicator_code="UNHCR/idps",
        name_ko="국내 실향민 (IDP)", name_en="Internally displaced persons",
        category="population", subcategory="displacement",
        unit="명",
        description_ko="분쟁·박해로 자국 내에서 거처를 잃은 사람. 국경을 넘지 않아 난민으로 분류되지 않음. 시리아·우크라이나·수단 등.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    IndicatorMeta(
        dataset_id="unhcr_stateless",
        source="UNHCR", indicator_code="UNHCR/stateless",
        name_ko="무국적자 수", name_en="Stateless persons",
        category="population", subcategory="displacement",
        unit="명",
        description_ko="어느 국가에서도 국민으로 인정받지 못한 사람. 로힝야·일부 발트국 거주민 등.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
    IndicatorMeta(
        dataset_id="unhcr_returned_refugees",
        source="UNHCR", indicator_code="UNHCR/returned_refugees",
        name_ko="본국 귀환 난민", name_en="Returned refugees",
        category="population", subcategory="displacement",
        unit="명",
        description_ko="해당 연도에 자발적으로 본국으로 돌아온 난민 수. 분쟁 종료·정세 안정의 지표.",
        license="CC BY 4.0", update_frequency="annual",
        coverage_years=(2000, 2024),
    ),
]


# 단일 호출 결과 메모리 캐시 (어댑터 인스턴스 수명 동안 유지)
_ITEMS_CACHE: list[dict] | None = None


def _fetch_all() -> list[dict]:
    """전체 (연도×망명국) 집계를 1회 호출로 받아 캐시."""
    global _ITEMS_CACHE
    if _ITEMS_CACHE is not None:
        return _ITEMS_CACHE

    url = (
        f"{BASE_URL}?yearFrom={YEAR_FROM}&yearTo={YEAR_TO}"
        f"&coa_all=true&limit=10000"
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "GeoSource/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read())
    _ITEMS_CACHE = payload.get("items", []) or []
    return _ITEMS_CACHE


def _as_int(v) -> int | None:
    """UNHCR 응답은 문자열 '0'/'-' 와 정수가 섞여 있음. 결측은 None."""
    if v in (None, "", "-"):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


class UnhcrAdapter(SourceAdapter):
    source_name = "UNHCR"
    license = "CC BY 4.0"
    base_url = BASE_URL

    def list_indicators(self) -> list[IndicatorMeta]:
        return INDICATORS

    def fetch(self, indicator_code: str, countries: list[str],
              year_range: tuple[int, int]) -> list[dict]:
        """countries·year_range는 무시 — 전체 받은 뒤 transform에서 화이트리스트 필터."""
        return _fetch_all()

    def transform(self, raw: list[dict], indicator: IndicatorMeta) -> list[StandardRecord]:
        # indicator_code = "UNHCR/<field>" — 필드명만 추출
        field = indicator.indicator_code.split("/", 1)[1]

        records: list[StandardRecord] = []
        fetched_at = datetime.utcnow().isoformat() + "Z"

        for item in raw:
            iso3 = (item.get("coa_iso") or "").upper()
            if not iso3 or iso3 not in COUNTRY_NAMES:
                continue

            value = _as_int(item.get(field))
            # 결측·0 모두 그대로 반영 (난민 0명도 의미 있는 정보)
            if value is None:
                continue

            try:
                year = int(item.get("year"))
            except (TypeError, ValueError):
                continue

            name_ko, name_en, region = COUNTRY_NAMES[iso3]
            records.append(StandardRecord(
                dataset_id=indicator.dataset_id,
                source=self.source_name,
                source_url=BASE_URL,
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
                value=float(value),
                license=self.license,
                fetched_at=fetched_at,
            ))
        return records
