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
