# © 2026 김용현
"""
Our World in Data (OWID) 어댑터.

OWID는 Pew Research, UN, WHO 등 다양한 출처의 데이터를 표준 CSV로 재배포한다.
- 인증 불필요
- CSV 엔드포인트: https://ourworldindata.org/grapher/{slug}.csv
- 라이선스: CC BY 4.0 (OWID 자체) + 원출처(예: Pew Research) 표기
- CORS: 허용되지만 안정성을 위해 빌드 타임 정적 JSON으로 처리

CSV 형식:
    Entity,Code,Year,<value-column>
    Afghanistan,AFG,2010,99.99
"""
from __future__ import annotations
import csv
import io
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schema import StandardRecord, IndicatorMeta
from adapters.base import SourceAdapter
from adapters.worldbank import COUNTRY_NAMES


# OWID grapher slug → indicator_code로 사용
INDICATORS: list[IndicatorMeta] = [
    IndicatorMeta(
        dataset_id="owid_religious_composition",
        source="OWID (Pew Research)",
        indicator_code="religious-composition",
        name_ko="종교 인구 비율",
        name_en="Share of population who are religious",
        category="development",
        subcategory="religion",
        unit="%",
        description_ko="국가별 종교인 인구 비율 (Pew Research Center 추정). OWID 재배포.",
        license="CC BY 4.0",
        update_frequency="annual",
        coverage_years=(2010, 2020),
    ),
    IndicatorMeta(
        dataset_id="owid_religiosity_change",
        source="OWID (Pew Research)",
        indicator_code="percentage-point-change-religiosity",
        name_ko="종교성 변화 (2010-2020)",
        name_en="Percentage point change in share religious",
        category="development",
        subcategory="religion",
        unit="%p",
        description_ko="2010년 대비 2020년 종교인 비율의 % 포인트 변화 (Pew). OWID.",
        license="CC BY 4.0",
        update_frequency="annual",
        coverage_years=(2020, 2020),
    ),
    IndicatorMeta(
        dataset_id="owid_attend_religious_services",
        source="OWID (Pew/WVS)",
        indicator_code="share-attending-religious-services",
        name_ko="종교의식 참석 비율",
        name_en="Share attending religious services frequently",
        category="development",
        subcategory="religion",
        unit="%",
        description_ko="종교의식에 정기적으로 참석하는 인구 비율. World Values Survey + Pew Research.",
        license="CC BY 4.0",
        update_frequency="annual",
        coverage_years=(1981, 2022),
    ),
]


class OwidAdapter(SourceAdapter):
    source_name = "OWID"
    license = "CC BY 4.0"
    base_url = "https://ourworldindata.org/grapher"

    def list_indicators(self) -> list[IndicatorMeta]:
        return INDICATORS

    def fetch(self, indicator_code: str, countries: list[str],
              year_range: tuple[int, int]) -> list[dict]:
        """OWID grapher CSV를 받아 dict 리스트로 반환."""
        url = f"{self.base_url}/{indicator_code}.csv"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; GeoSource/1.0)",
            "Accept": "text/csv",
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)

    def transform(self, raw: list[dict], indicator: IndicatorMeta) -> list[StandardRecord]:
        records: list[StandardRecord] = []
        fetched_at = datetime.utcnow().isoformat() + "Z"

        # 값 컬럼 자동 탐지 — Entity/Code/Year 외 첫 번째 numeric 컬럼
        if not raw:
            return records
        meta_cols = {"Entity", "Code", "Year"}
        candidates = [c for c in raw[0].keys() if c not in meta_cols and "Annotations" not in c]
        if not candidates:
            return records
        value_col = candidates[0]

        for row in raw:
            iso3 = (row.get("Code") or "").upper()
            if not iso3 or len(iso3) != 3:
                continue
            try:
                year = int(row.get("Year"))
            except (TypeError, ValueError):
                continue
            raw_val = row.get(value_col)
            try:
                value = float(raw_val) if raw_val not in (None, "", "NA") else None
            except (TypeError, ValueError):
                value = None
            name_ko, name_en, region = COUNTRY_NAMES.get(iso3, (iso3, row.get("Entity") or iso3, ""))

            records.append(StandardRecord(
                dataset_id=indicator.dataset_id,
                source=indicator.source,
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
