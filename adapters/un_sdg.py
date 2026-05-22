# © 2026 김용현
"""
UN SDG (Sustainable Development Goals) Indicators 어댑터.

엔드포인트(공개, 인증 없음):
    https://unstats.un.org/SDGAPI/v1/sdg/Series/Data
      ?seriesCode=XXX&pageSize=2000&pageNumber=N

각 series는 (Sex, Age, Location, Reporting Type, ...) dimension이 다르게
정의되어 있어 indicator 별로 어떤 차원을 기본값으로 잡을지 명시해야 한다.
INDICATORS 리스트의 `dim_filter` 필드가 그 역할을 한다. 비어있으면 모든
차원 조합을 그대로 받아들임.

지역 코드는 UN M49 numeric. 국가 화이트리스트(40개국)는 M49_TO_ISO3 매핑으로 필터.

라이선스: UN SDG 데이터는 일반적으로 출처 표기 시 자유 이용 (UN 공공 데이터).
"""
from __future__ import annotations
import sys
import urllib.request
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schema import StandardRecord, IndicatorMeta
from adapters.base import SourceAdapter
from adapters.worldbank import COUNTRY_NAMES


BASE_URL = "https://unstats.un.org/SDGAPI/v1/sdg/Series/Data"


# M49 numeric ↔ ISO3 (40개국 화이트리스트)
M49_TO_ISO3: dict[str, str] = {
    "32": "ARG", "36": "AUS", "76": "BRA", "124": "CAN", "156": "CHN",
    "246": "FIN", "250": "FRA", "276": "DEU", "356": "IND", "360": "IDN",
    "364": "IRN", "376": "ISR", "380": "ITA", "392": "JPN", "404": "KEN",
    "408": "PRK", "410": "KOR", "458": "MYS", "484": "MEX", "528": "NLD",
    "554": "NZL", "566": "NGA", "578": "NOR", "586": "PAK", "608": "PHL",
    "616": "POL", "643": "RUS", "682": "SAU", "702": "SGP", "704": "VNM",
    "710": "ZAF", "724": "ESP", "752": "SWE", "756": "CHE", "764": "THA",
    "784": "ARE", "792": "TUR", "818": "EGY", "826": "GBR", "840": "USA",
}


@dataclass
class SdgSeries:
    """SDG series별 메타 + 어떤 dimension 조합을 기본값으로 쓸지 정의."""
    series_code: str
    dataset_id: str
    name_ko: str
    name_en: str
    subcategory: str
    unit: str
    description_ko: str
    # dimension 필터 — 비어있으면 모든 행 수용
    dim_filter: dict[str, str] = field(default_factory=dict)


SDG_SERIES: list[SdgSeries] = [
    SdgSeries(
        series_code="SG_GEN_PARL",
        dataset_id="sdg_women_in_parliament",
        name_ko="여성 국회의원 비율 (SDG 5.5.1)",
        name_en="Women in national parliaments (% seats)",
        subcategory="gender",
        unit="%",
        description_ko="단원제 또는 하원에서 여성이 차지하는 의석 비율. SDG 5(성평등) 핵심 지표.",
        dim_filter={"Sex": "FEMALE", "Reporting Type": "G"},
    ),
    SdgSeries(
        series_code="VC_IHR_PSRC",
        dataset_id="sdg_homicide_rate",
        name_ko="의도적 살인율 (SDG 16.1.1)",
        name_en="Intentional homicide victims (per 100,000)",
        subcategory="violence",
        unit="명/10만명",
        description_ko="인구 10만 명당 연간 의도적 살인 피해자 수. 사회 안전·평화 지표.",
        dim_filter={"Sex": "BOTHSEX", "Reporting Type": "G"},
    ),
    SdgSeries(
        series_code="GB_XPD_RSDV",
        dataset_id="sdg_rd_expenditure",
        name_ko="R&D 지출 (% GDP, SDG 9.5.1)",
        name_en="Research and development expenditure (% of GDP)",
        subcategory="innovation",
        unit="%",
        description_ko="국내총생산 대비 연구개발(R&D) 지출 비율. 혁신 역량의 핵심 지표.",
        dim_filter={"Reporting Type": "G"},
    ),
    SdgSeries(
        series_code="EN_ATM_PM25",
        dataset_id="sdg_pm25_pollution",
        name_ko="PM2.5 대기오염 (SDG 11.6.2)",
        name_en="Annual mean PM2.5 concentration",
        subcategory="environment",
        unit="μg/m³",
        description_ko="도시·농촌 가중 평균 초미세먼지 농도. WHO 권고치는 5 µg/m³ 이하.",
        dim_filter={"Location": "ALLAREA", "Reporting Type": "G"},
    ),
    SdgSeries(
        series_code="IT_MOB_OWN",
        dataset_id="sdg_mobile_ownership",
        name_ko="휴대전화 보급률 (SDG 5.b.1)",
        name_en="Proportion of individuals who own a mobile telephone",
        subcategory="ict",
        unit="%",
        description_ko="15세 이상 인구 중 휴대전화를 보유한 비율. 디지털 격차의 기초 지표.",
        dim_filter={"Sex": "BOTHSEX", "Reporting Type": "G"},
    ),
]


# IndicatorMeta로 변환 (build 시스템 호환용)
INDICATORS: list[IndicatorMeta] = [
    IndicatorMeta(
        dataset_id=s.dataset_id,
        source="UN SDG", indicator_code=f"SDG/{s.series_code}",
        name_ko=s.name_ko, name_en=s.name_en,
        category="development", subcategory=s.subcategory,
        unit=s.unit,
        description_ko=s.description_ko,
        license="UN public data (출처 표기 시 자유 이용)",
        update_frequency="annual",
        coverage_years=(2000, 2024),
    )
    for s in SDG_SERIES
]

_SERIES_BY_CODE = {s.series_code: s for s in SDG_SERIES}


# series_code별 페이지 로드 결과 캐시
_PAGE_CACHE: dict[str, list[dict]] = {}


def _fetch_series(series_code: str) -> list[dict]:
    """단일 series 의 모든 페이지를 받아 dim_filter로 미리 거른 행들을 반환."""
    if series_code in _PAGE_CACHE:
        return _PAGE_CACHE[series_code]

    series = _SERIES_BY_CODE[series_code]
    out: list[dict] = []
    page = 1
    while True:
        url = (
            f"{BASE_URL}?seriesCode={series_code}"
            f"&pageSize=2000&pageNumber={page}"
        )
        req = urllib.request.Request(url, headers={
            "User-Agent": "GeoSource/1.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read())
        for item in payload.get("data", []):
            dims = item.get("dimensions") or {}
            if all(dims.get(k) == v for k, v in series.dim_filter.items()):
                out.append(item)
        total_pages = payload.get("totalPages", 1)
        if page >= total_pages:
            break
        page += 1
    _PAGE_CACHE[series_code] = out
    return out


def _as_float(v) -> float | None:
    if v in (None, "", "NA", "-"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class UnSdgAdapter(SourceAdapter):
    source_name = "UN SDG"
    license = "UN public data"
    base_url = BASE_URL

    def list_indicators(self) -> list[IndicatorMeta]:
        return INDICATORS

    def fetch(self, indicator_code: str, countries: list[str],
              year_range: tuple[int, int]) -> list[dict]:
        series_code = indicator_code.split("/", 1)[1]
        return _fetch_series(series_code)

    def transform(self, raw: list[dict], indicator: IndicatorMeta) -> list[StandardRecord]:
        records: list[StandardRecord] = []
        fetched_at = datetime.utcnow().isoformat() + "Z"

        for item in raw:
            m49 = str(item.get("geoAreaCode") or "")
            iso3 = M49_TO_ISO3.get(m49)
            if not iso3 or iso3 not in COUNTRY_NAMES:
                continue

            value = _as_float(item.get("value"))
            if value is None:
                continue

            try:
                year = int(float(item.get("timePeriodStart")))
            except (TypeError, ValueError):
                continue

            name_ko, name_en, region = COUNTRY_NAMES[iso3]
            records.append(StandardRecord(
                dataset_id=indicator.dataset_id,
                source=self.source_name,
                source_url=f"{BASE_URL}?seriesCode={indicator.indicator_code.split('/',1)[1]}",
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
            ))
        return records
