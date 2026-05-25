# © 2026 김용현
"""
OWID Energy Data 어댑터.

Energy Institute(전 BP) Statistical Review + EIA + Ember를 OWID가 단일 wide-format
CSV로 종합한 데이터셋을 가져와 35개 에너지 지표(8 에너지원 × 4 측면 + 화석연료
3개 생산량)로 분해한다.

- 데이터 URL: https://github.com/owid/energy-data/raw/master/owid-energy-data.csv
- 라이선스: CC BY 4.0
- 출처 표기: source="Energy Institute" — description에 원자료(OWID 종합본:
  Energy Institute + EIA + Ember) 명시
- 갱신 주기: 연 1회(EI) + 월 단위(Ember 부분)
- CORS: GitHub raw는 허용되지만 안정성/속도 위해 빌드 타임 정적 JSON 처리

CSV 구조 (wide-format, ~130 컬럼):
    country,year,iso_code,population,gdp,
    coal_consumption,coal_share_energy,coal_electricity,coal_share_elec,coal_production,
    oil_consumption,oil_share_energy,oil_electricity,oil_share_elec,oil_production,
    gas_consumption,gas_share_energy,gas_electricity,gas_share_elec,gas_production,
    nuclear_consumption,nuclear_share_energy,nuclear_electricity,nuclear_share_elec,
    hydro_consumption,hydro_share_energy,hydro_electricity,hydro_share_elec,
    wind_consumption,wind_share_energy,wind_electricity,wind_share_elec,
    solar_consumption,solar_share_energy,solar_electricity,solar_share_elec,
    biofuel_consumption,biofuel_share_energy,biofuel_electricity,biofuel_share_elec,
    ...
"""
from __future__ import annotations
import csv
import io
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schema import StandardRecord, IndicatorMeta
from adapters.base import SourceAdapter
from adapters.worldbank import COUNTRY_NAMES


DATA_URL = "https://github.com/owid/energy-data/raw/master/owid-energy-data.csv"
COVERAGE = (1965, 2025)

# ─── 에너지원 정의 (CSV prefix, 한국어, 영문) ────────────────────
FUELS: list[tuple[str, str, str]] = [
    ("coal",    "석탄",   "Coal"),
    ("oil",     "석유",   "Oil"),
    ("gas",     "가스",   "Gas"),
    ("nuclear", "원자력", "Nuclear"),
    ("hydro",   "수력",   "Hydro"),
    ("wind",    "풍력",   "Wind"),
    ("solar",   "태양광", "Solar"),
    ("biofuel", "바이오", "Biofuel"),
]

# ─── 측면 정의 (CSV suffix, 한국어, 영문, 단위, id 단위 suffix) ──
MEASURES: list[tuple[str, str, str, str, str]] = [
    ("consumption",  "1차에너지 소비", "primary energy consumption",
     "TWh", "twh"),
    ("share_energy", "1차에너지 비중", "share of primary energy",
     "%", "pct"),
    ("electricity",  "발전량",         "electricity generation",
     "TWh", "twh"),
    ("share_elec",   "발전 비중",      "share of electricity",
     "%", "pct"),
]

# 생산량 (화석연료만)
PRODUCTION_FUELS: list[tuple[str, str, str]] = [
    ("coal", "석탄", "Coal"),
    ("oil",  "석유", "Oil"),
    ("gas",  "가스", "Gas"),
]

DESC_TEMPLATES = {
    "consumption":  "{ko} 연간 1차에너지 소비량(TWh). 원자료: Energy Institute "
                    "Statistical Review of World Energy (OWID 종합).",
    "share_energy": "{ko}이 전체 1차에너지 소비에서 차지하는 비율(%). 원자료: "
                    "Energy Institute (OWID 종합).",
    "electricity":  "{ko} 연간 발전량(TWh). 원자료: Ember + Energy Institute "
                    "(OWID 종합).",
    "share_elec":   "{ko}이 전체 전력 생산에서 차지하는 비율(%). 원자료: "
                    "Ember + Energy Institute (OWID 종합).",
    "production":   "{ko} 연간 1차에너지 생산량(TWh). 원자료: Energy Institute "
                    "Statistical Review of World Energy (OWID 종합).",
}


def _build_indicators() -> list[IndicatorMeta]:
    out: list[IndicatorMeta] = []
    for fuel_key, fuel_ko, fuel_en in FUELS:
        for m_suffix, m_ko, m_en, unit, id_suf in MEASURES:
            out.append(IndicatorMeta(
                dataset_id=f"ei_{fuel_key}_{m_suffix}_{id_suf}",
                source="Energy Institute",
                indicator_code=f"{fuel_key}_{m_suffix}",
                name_ko=f"{fuel_ko} {m_ko}",
                name_en=f"{fuel_en} {m_en}",
                category="energy",
                subcategory=fuel_key,
                unit=unit,
                description_ko=DESC_TEMPLATES[m_suffix].format(ko=fuel_ko),
                license="CC BY 4.0",
                update_frequency="annual",
                coverage_years=COVERAGE,
            ))
    for fuel_key, fuel_ko, fuel_en in PRODUCTION_FUELS:
        out.append(IndicatorMeta(
            dataset_id=f"ei_{fuel_key}_production_twh",
            source="Energy Institute",
            indicator_code=f"{fuel_key}_production",
            name_ko=f"{fuel_ko} 생산량",
            name_en=f"{fuel_en} production",
            category="energy",
            subcategory=fuel_key,
            unit="TWh",
            description_ko=DESC_TEMPLATES["production"].format(ko=fuel_ko),
            license="CC BY 4.0",
            update_frequency="annual",
            coverage_years=COVERAGE,
        ))
    return out


INDICATORS: list[IndicatorMeta] = _build_indicators()


class OwidEnergyAdapter(SourceAdapter):
    source_name = "Energy Institute"
    license = "CC BY 4.0"
    base_url = DATA_URL

    def __init__(self) -> None:
        self._rows: Optional[list[dict[str, str]]] = None  # 캐시 (35회 빌드 1회 fetch)

    def list_indicators(self) -> list[IndicatorMeta]:
        return INDICATORS

    def _load_csv(self) -> list[dict[str, str]]:
        if self._rows is not None:
            return self._rows
        req = urllib.request.Request(DATA_URL, headers={
            "User-Agent": "Mozilla/5.0 (compatible; GeoSource/1.0)",
            "Accept": "text/csv",
        })
        with urllib.request.urlopen(req, timeout=180) as resp:
            text = resp.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        self._rows = list(reader)
        return self._rows

    def fetch(self, indicator_code: str, countries: list[str],
              year_range: tuple[int, int]) -> dict:
        """CSV 전체를 1회만 로드해 캐싱. countries는 무시(전체 entity 통과)."""
        rows = self._load_csv()
        return {"column": indicator_code, "rows": rows}

    def transform(self, raw: dict, indicator: IndicatorMeta) -> list[StandardRecord]:
        col = raw["column"]
        rows = raw["rows"]
        fetched_at = datetime.utcnow().isoformat() + "Z"
        records: list[StandardRecord] = []

        for row in rows:
            iso3 = (row.get("iso_code") or "").strip().upper()
            if not iso3 or len(iso3) != 3:
                continue  # World / Africa 같은 집계 entity 스킵
            try:
                year = int(row["year"])
            except (KeyError, TypeError, ValueError):
                continue
            raw_val = (row.get(col) or "").strip()
            if raw_val in ("", "NA", "n/a"):
                value: Optional[float] = None
            else:
                try:
                    value = float(raw_val)
                except ValueError:
                    value = None

            name_ko, name_en, region = COUNTRY_NAMES.get(iso3, (iso3, iso3, ""))
            records.append(StandardRecord(
                dataset_id=indicator.dataset_id,
                source=self.source_name,
                source_url=DATA_URL,
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
