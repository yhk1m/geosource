# © 2026 김용현
"""
WHO Global Health Observatory (GHO) OData 어댑터.

API 문서: https://www.who.int/data/gho/info/gho-odata-api
- 인증 불필요
- 엔드포인트: https://ghoapi.azureedge.net/api/{IndicatorCode}
- 응답: { "value": [ {SpatialDim, TimeDim, NumericValue, Dim1, ...}, ... ] }
  · SpatialDim = ISO3 (대부분, 일부는 지역코드)
  · TimeDim    = 연도(int)
  · NumericValue = 수치
  · Dim1        = SEX (BTSX/MLE/FMLE) 등 — 가능하면 BTSX만 사용
- 라이선스: WHO 데이터는 일반적으로 CC BY-NC-SA 3.0 IGO
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


BASE_URL = "https://ghoapi.azureedge.net/api"


INDICATORS: list[IndicatorMeta] = [
    IndicatorMeta(
        dataset_id="who_physicians_density",
        source="WHO", indicator_code="HWF_0001",
        name_ko="의사 밀도 (인구 1만 명당)", name_en="Medical doctors (per 10,000)",
        category="development", subcategory="health",
        unit="명/만명",
        description_ko="인구 1만 명당 의사 수. 의료 접근성 지표.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2022),
    ),
    IndicatorMeta(
        dataset_id="who_hospital_beds",
        source="WHO", indicator_code="WHS6_102",
        name_ko="병상 수 (인구 1만 명당)", name_en="Hospital beds (per 10,000)",
        category="development", subcategory="health",
        unit="개/만명",
        description_ko="인구 1만 명당 병상 수.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2017),
    ),
    IndicatorMeta(
        dataset_id="who_alcohol_consumption",
        source="WHO", indicator_code="SA_0000001688",
        name_ko="1인당 알코올 소비량", name_en="Alcohol consumption per capita (15+, liters)",
        category="development", subcategory="health",
        unit="L/년",
        description_ko="15세 이상 1인당 연간 순수 알코올 소비량(리터).",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2019),
    ),
    IndicatorMeta(
        dataset_id="who_suicide_rate",
        source="WHO", indicator_code="MH_12",
        name_ko="자살률 (10만 명당)", name_en="Suicide mortality rate (per 100,000)",
        category="development", subcategory="health",
        unit="명/10만명",
        description_ko="연간 자살 사망률, 인구 10만 명당, 연령표준화.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2019),
    ),
    IndicatorMeta(
        dataset_id="who_obesity_adults",
        source="WHO", indicator_code="NCD_BMI_30A",
        name_ko="성인 비만율", name_en="Obesity prevalence (BMI≥30, age-std, 18+)",
        category="development", subcategory="health",
        unit="%",
        description_ko="18세 이상 성인 중 BMI 30 이상 비율(연령표준화).",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2022),
    ),
    IndicatorMeta(
        dataset_id="who_tobacco_use",
        source="WHO", indicator_code="M_Est_smk_curr_std",
        name_ko="흡연율 (성인, 연령표준화)", name_en="Current tobacco use (15+, age-std)",
        category="development", subcategory="health",
        unit="%",
        description_ko="15세 이상 인구 중 현재 흡연 비율(연령표준화).",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2025),
    ),
]


class WhoAdapter(SourceAdapter):
    source_name = "WHO"
    license = "CC BY-NC-SA 3.0 IGO"
    base_url = BASE_URL

    def list_indicators(self) -> list[IndicatorMeta]:
        return INDICATORS

    def fetch(self, indicator_code: str, countries: list[str],
              year_range: tuple[int, int]) -> list[dict]:
        """WHO GHO OData API 호출. countries는 무시하고 전체 받아 transform에서 필터."""
        url = f"{self.base_url}/{indicator_code}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "GeoSource/1.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read())
        return payload.get("value", []) or []

    def transform(self, raw: list[dict], indicator: IndicatorMeta) -> list[StandardRecord]:
        records: list[StandardRecord] = []
        fetched_at = datetime.utcnow().isoformat() + "Z"

        for row in raw:
            iso3 = (row.get("SpatialDim") or "").upper()
            if not iso3 or len(iso3) != 3 or iso3 not in COUNTRY_NAMES:
                continue

            # 성별 차원(Dim1)이 있으면 BTSX(양성 합계)만 사용
            sex = row.get("Dim1")
            if sex and sex not in ("BTSX",):
                continue

            try:
                year = int(row.get("TimeDim"))
            except (TypeError, ValueError):
                continue

            value = row.get("NumericValue")
            try:
                value = float(value) if value is not None else None
            except (TypeError, ValueError):
                value = None

            name_ko, name_en, region = COUNTRY_NAMES[iso3]
            records.append(StandardRecord(
                dataset_id=indicator.dataset_id,
                source=self.source_name,
                source_url=f"{self.base_url}/{indicator.indicator_code}",
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
