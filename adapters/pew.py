# © 2026 김용현
"""
Pew Research Center 어댑터 — Religious Composition Projections (2010-2050).

데이터 출처: GitHub `datasets/world-religion-projections` (Pew Research 원본을
정리한 공개 CSV).
- 라이선스: Public Domain (PD) / CC BY 4.0 (Pew 표기 유지)
- 7대 종교 + 무종교 비율 by country, 5년 단위 (2010, 2020, 2030, 2040, 2050)
- 약 235개국·지역 + 지역 합계

CSV 형식 (wide):
    Year, Region, Country, Buddhists, Christians, Folk Religions, Hindus,
                            Jews, Muslims, Other Religions, Unaffiliated

각 종교 컬럼을 별도 indicator로 등록. country English name → ISO3 매핑은
pycountry 사용 (workflow에서 pip install pycountry 보장).
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


CSV_URL = "https://raw.githubusercontent.com/datasets/world-religion-projections/main/rounded_percentage.csv"


# 종교 컬럼 → 한국어/영문/카테고리
RELIGIONS = [
    ("Christians",       "기독교 신자 비율",  "Christians (% of population)",       "christian"),
    ("Muslims",          "이슬람 신자 비율",   "Muslims (% of population)",          "muslim"),
    ("Hindus",           "힌두교 신자 비율",   "Hindus (% of population)",           "hindu"),
    ("Buddhists",        "불교 신자 비율",     "Buddhists (% of population)",        "buddhist"),
    ("Jews",             "유대교 신자 비율",   "Jews (% of population)",             "jewish"),
    ("Unaffiliated",     "무종교 인구 비율",   "Religiously unaffiliated (%)",       "unaffiliated"),
    ("Folk Religions",   "민속종교 신자 비율", "Folk religions (% of population)",   "folk"),
    ("Other Religions",  "기타 종교 신자 비율","Other religions (% of population)",  "other"),
]


# 국가명 → ISO3 (CSV의 영문 country 값 기준). pycountry로 fuzzy 매칭, 실패는 None.
def _build_country_map() -> dict[str, str]:
    try:
        import pycountry
    except ImportError:
        pycountry = None

    # 자주 쓰이는 alias 직접 매핑 (pycountry의 search_fuzzy가 모호한 케이스 보완)
    alias = {
        "South Korea": "KOR", "Korea, Republic of": "KOR", "Republic of Korea": "KOR",
        "North Korea": "PRK", "Korea, Democratic People's Republic of": "PRK",
        "United States": "USA",
        "United Kingdom": "GBR",
        "Czech Republic": "CZE", "Czechia": "CZE",
        "Russia": "RUS", "Russian Federation": "RUS",
        "Iran": "IRN", "Iran, Islamic Republic of": "IRN",
        "Vietnam": "VNM", "Viet Nam": "VNM",
        "Syria": "SYR",
        "Tanzania": "TZA",
        "Venezuela": "VEN",
        "Bolivia": "BOL",
        "Moldova": "MDA",
        "Macedonia": "MKD", "North Macedonia": "MKD",
        "Laos": "LAO", "Lao People's Democratic Republic": "LAO",
        "Brunei": "BRN",
        "Cape Verde": "CPV",
        "Ivory Coast": "CIV", "Cote d'Ivoire": "CIV", "Côte d'Ivoire": "CIV",
        "Congo": "COG", "Republic of the Congo": "COG",
        "DR Congo": "COD", "Democratic Republic of the Congo": "COD",
        "Burma": "MMR", "Myanmar": "MMR",
        "Macao": "MAC", "Macau": "MAC",
        "Hong Kong": "HKG",
        "Taiwan": "TWN",
        "Palestinian territories": "PSE", "Palestine": "PSE",
        "Western Sahara": "ESH",
        "Channel Islands": "GBR",
        "Kosovo": "XKX",
        "Saint Kitts and Nevis": "KNA", "St. Kitts and Nevis": "KNA",
        "Saint Lucia": "LCA",
        "Saint Vincent and the Grenadines": "VCT", "St. Vincent and the Grenadines": "VCT",
        "Trinidad and Tobago": "TTO",
        "Bosnia-Herzegovina": "BIH", "Bosnia and Herzegovina": "BIH",
        "Timor-Leste": "TLS", "East Timor": "TLS",
        "Swaziland": "SWZ", "Eswatini": "SWZ",
    }
    out = dict(alias)
    if pycountry:
        for c in pycountry.countries:
            out.setdefault(c.name, c.alpha_3)
            if hasattr(c, "official_name"):
                out.setdefault(c.official_name, c.alpha_3)
    return out


_COUNTRY_MAP: dict[str, str] | None = None


def _country_to_iso3(name: str) -> str | None:
    global _COUNTRY_MAP
    if _COUNTRY_MAP is None:
        _COUNTRY_MAP = _build_country_map()
    name = (name or "").strip()
    if not name or name == "All Countries":
        return None
    if name in _COUNTRY_MAP:
        return _COUNTRY_MAP[name]
    try:
        import pycountry
        m = pycountry.countries.search_fuzzy(name)
        if m:
            return m[0].alpha_3
    except (ImportError, LookupError):
        pass
    return None


# 8개 종교 indicator 자동 생성
INDICATORS: list[IndicatorMeta] = [
    IndicatorMeta(
        dataset_id=f"pew_religion_{key}",
        source="Pew Research Center",
        indicator_code=col,                     # CSV 컬럼명을 코드로
        name_ko=name_ko,
        name_en=name_en,
        category="development",
        subcategory=f"religion_{key}",
        unit="%",
        description_ko=f"전체 인구 대비 {name_ko}. Pew Research Center Religious Composition Projections (2010–2050).",
        license="Public Domain (Pew 출처 표기)",
        update_frequency="annual",
        coverage_years=(2010, 2050),
    )
    for col, name_ko, name_en, key in RELIGIONS
]


class PewAdapter(SourceAdapter):
    source_name = "Pew Research Center"
    license = "Public Domain (Pew 출처 표기)"
    base_url = CSV_URL
    _cached_rows: list[dict] | None = None

    def list_indicators(self) -> list[IndicatorMeta]:
        return INDICATORS

    def _load_csv(self) -> list[dict]:
        if PewAdapter._cached_rows is not None:
            return PewAdapter._cached_rows
        req = urllib.request.Request(CSV_URL, headers={
            "User-Agent": "Mozilla/5.0 (compatible; GeoSource/1.0)",
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8")
        rows = list(csv.DictReader(io.StringIO(text)))
        PewAdapter._cached_rows = rows
        return rows

    def fetch(self, indicator_code: str, countries: list[str],
              year_range: tuple[int, int]) -> list[dict]:
        # 모든 indicator가 같은 CSV 사용 (메모리 캐시)
        return self._load_csv()

    def transform(self, raw: list[dict], indicator: IndicatorMeta) -> list[StandardRecord]:
        records: list[StandardRecord] = []
        fetched_at = datetime.utcnow().isoformat() + "Z"
        col = indicator.indicator_code

        for row in raw:
            country_name = (row.get("Country") or "").strip()
            iso3 = _country_to_iso3(country_name)
            if not iso3:
                continue  # 지역 합계('All Countries'), 미매핑 등은 스킵
            try:
                year = int(row.get("Year"))
            except (TypeError, ValueError):
                continue
            raw_val = row.get(col)
            try:
                value = float(raw_val) if raw_val not in (None, "", "NA") else None
            except (TypeError, ValueError):
                value = None

            name_ko, name_en, region = COUNTRY_NAMES.get(iso3, (country_name, country_name, ""))
            records.append(StandardRecord(
                dataset_id=indicator.dataset_id,
                source=self.source_name,
                source_url="https://www.pewresearch.org/religion/feature/religious-composition-by-country-2010-2020/",
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
