# © 2026 김용현
"""
FAO(Food and Agriculture Organization) FAOSTAT 어댑터.

API 문서: FAOSTAT Developer Portal (https://www.fao.org/faostat/)
- JWT Bearer 토큰 인증 필요 (60분 TTL)
- 라이선스: CC BY-NC-SA 3.0 IGO (출처 표기 + 비상업 + 동일조건변경허락)
- 응답 형식: JSON (`output_type=objects`)

엔드포인트:
  로그인:  POST https://faostatservices.fao.org/api/v1/auth/login
           form data: username, password
           응답: {"AuthenticationResult": {"AccessToken": "..."}}

  데이터:  GET  https://faostatservices.fao.org/api/v1/en/data/{DOMAIN}
           헤더: Authorization: Bearer {token}
           쿼리: area, item, element, year, output_type=objects, ...

환경변수:
  FAO_USERNAME, FAO_PASSWORD — 키 없으면 빌드 시 빈 결과 반환 (KOSIS와 동일 패턴)
"""
from __future__ import annotations
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schema import StandardRecord, IndicatorMeta
from adapters.base import SourceAdapter


AUTH_URL = "https://faostatservices.fao.org/api/v1/auth/login"
DATA_BASE = "https://faostatservices.fao.org/api/v1/en/data"


# ─── FAO area code ↔ ISO3 매핑 (주요국) ───
# FAO는 자체 numeric 코드를 사용한다. 변환표가 필요.
FAO_AREAS: dict[str, tuple[int, str, str, str]] = {
    # ISO3: (FAO area code, 한국어명, 영문명, UN M49 region)
    "KOR": (117, "대한민국", "Republic of Korea", "Eastern Asia"),
    "PRK": (116, "북한", "Democratic People's Republic of Korea", "Eastern Asia"),
    "JPN": (110, "일본", "Japan", "Eastern Asia"),
    "CHN": (41,  "중국", "China, mainland", "Eastern Asia"),
    "USA": (231, "미국", "United States of America", "Northern America"),
    "CAN": (33,  "캐나다", "Canada", "Northern America"),
    "MEX": (138, "멕시코", "Mexico", "Latin America"),
    "BRA": (21,  "브라질", "Brazil", "Latin America"),
    "ARG": (9,   "아르헨티나", "Argentina", "Latin America"),
    "GBR": (229, "영국", "United Kingdom of Great Britain and Northern Ireland", "Northern Europe"),
    "FRA": (68,  "프랑스", "France", "Western Europe"),
    "DEU": (79,  "독일", "Germany", "Western Europe"),
    "ITA": (106, "이탈리아", "Italy", "Southern Europe"),
    "ESP": (203, "스페인", "Spain", "Southern Europe"),
    "NLD": (150, "네덜란드", "Netherlands (Kingdom of the)", "Western Europe"),
    "RUS": (185, "러시아", "Russian Federation", "Eastern Europe"),
    "POL": (173, "폴란드", "Poland", "Eastern Europe"),
    "IND": (100, "인도", "India", "Southern Asia"),
    "PAK": (165, "파키스탄", "Pakistan", "Southern Asia"),
    "IDN": (101, "인도네시아", "Indonesia", "South-Eastern Asia"),
    "VNM": (237, "베트남", "Viet Nam", "South-Eastern Asia"),
    "THA": (216, "태국", "Thailand", "South-Eastern Asia"),
    "PHL": (171, "필리핀", "Philippines", "South-Eastern Asia"),
    "AUS": (10,  "호주", "Australia", "Australia and New Zealand"),
    "NZL": (156, "뉴질랜드", "New Zealand", "Australia and New Zealand"),
    "ZAF": (202, "남아프리카공화국", "South Africa", "Sub-Saharan Africa"),
    "EGY": (59,  "이집트", "Egypt", "Northern Africa"),
    "NGA": (159, "나이지리아", "Nigeria", "Sub-Saharan Africa"),
    "KEN": (114, "케냐", "Kenya", "Sub-Saharan Africa"),
    "SAU": (194, "사우디아라비아", "Saudi Arabia", "Western Asia"),
    "TUR": (223, "튀르키예", "Türkiye", "Western Asia"),
}


# ─── 큐레이션된 지표 카탈로그 ───
# indicator_code 형식: "{DOMAIN}/{item}/{element}"
INDICATORS: list[IndicatorMeta] = [
    IndicatorMeta(
        dataset_id="fao_QCL_15_2510",
        source="FAO",
        indicator_code="QCL/15/2510",
        name_ko="밀 생산량",
        name_en="Wheat production",
        category="agriculture",
        subcategory="crop_production",
        unit="t",
        description_ko="연간 밀 생산량(톤). FAOSTAT QCL 도메인.",
        license="CC BY-NC-SA 3.0 IGO",
        update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_27_2510",
        source="FAO",
        indicator_code="QCL/27/2510",
        name_ko="쌀(벼) 생산량",
        name_en="Rice (paddy) production",
        category="agriculture",
        subcategory="crop_production",
        unit="t",
        description_ko="연간 벼(쌀) 생산량(톤). 도정 전 paddy 기준.",
        license="CC BY-NC-SA 3.0 IGO",
        update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_56_2510",
        source="FAO",
        indicator_code="QCL/56/2510",
        name_ko="옥수수 생산량",
        name_en="Maize (corn) production",
        category="agriculture",
        subcategory="crop_production",
        unit="t",
        description_ko="연간 옥수수 생산량(톤).",
        license="CC BY-NC-SA 3.0 IGO",
        update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_866_2111",
        source="FAO",
        indicator_code="QCL/866/2111",
        name_ko="소 사육두수",
        name_en="Cattle stocks",
        category="agriculture",
        subcategory="livestock",
        unit="head",
        description_ko="연말 시점 소 사육두수(마리).",
        license="CC BY-NC-SA 3.0 IGO",
        update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_1034_2111",
        source="FAO",
        indicator_code="QCL/1034/2111",
        name_ko="돼지 사육두수",
        name_en="Swine / pigs stocks",
        category="agriculture",
        subcategory="livestock",
        unit="head",
        description_ko="연말 시점 돼지 사육두수(마리).",
        license="CC BY-NC-SA 3.0 IGO",
        update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_976_2111",
        source="FAO",
        indicator_code="QCL/976/2111",
        name_ko="양 사육두수",
        name_en="Sheep stocks",
        category="agriculture",
        subcategory="livestock",
        unit="head",
        description_ko="연말 시점 양 사육두수(마리).",
        license="CC BY-NC-SA 3.0 IGO",
        update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_RL_6610_5110",
        source="FAO",
        indicator_code="RL/6610/5110",
        name_ko="농경지 면적",
        name_en="Agricultural land area",
        category="agriculture",
        subcategory="land_use",
        unit="1000 ha",
        description_ko="농경지(경작지+영구작물지+목초지) 총 면적(천 ha). FAOSTAT Land Use 도메인.",
        license="CC BY-NC-SA 3.0 IGO",
        update_frequency="annual",
        coverage_years=(2000, 2022),
    ),
    IndicatorMeta(
        dataset_id="fao_FBS_2901_664",
        source="FAO",
        indicator_code="FBS/2901/664",
        name_ko="1인당 일일 식이에너지 공급",
        name_en="Dietary energy supply (kcal/cap/day)",
        category="agriculture",
        subcategory="food_supply",
        unit="kcal/cap/day",
        description_ko="1인당 1일 식이에너지 공급량. Food Balance Sheets.",
        license="CC BY-NC-SA 3.0 IGO",
        update_frequency="annual",
        coverage_years=(2010, 2022),
    ),
]


class FaoAdapter(SourceAdapter):
    source_name = "FAO"
    license = "CC BY-NC-SA 3.0 IGO"
    base_url = DATA_BASE

    def __init__(self, username: str | None = None, password: str | None = None):
        self.username = username or os.environ.get("FAO_USERNAME", "")
        self.password = password or os.environ.get("FAO_PASSWORD", "")
        self._token: str | None = None
        self._token_acquired_at: float = 0.0
        if not (self.username and self.password):
            print("[FAO] 경고: FAO_USERNAME/FAO_PASSWORD 미설정. 빌드 시 빈 결과 반환.")

    def list_indicators(self) -> list[IndicatorMeta]:
        return INDICATORS

    def _get_token(self) -> str | None:
        """JWT 토큰 획득(60분 TTL). 50분 지나면 재발급."""
        if not (self.username and self.password):
            return None
        if self._token and (time.time() - self._token_acquired_at) < 3000:
            return self._token

        body = urllib.parse.urlencode({
            "username": self.username,
            "password": self.password,
        }).encode("utf-8")
        req = urllib.request.Request(
            AUTH_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "GeoSource/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read())
        self._token = payload["AuthenticationResult"]["AccessToken"]
        self._token_acquired_at = time.time()
        return self._token

    def fetch(self, indicator_code: str, countries: list[str],
              year_range: tuple[int, int]) -> list[dict]:
        """FAOSTAT API 호출. countries는 ISO3 → FAO area code로 변환."""
        token = self._get_token()
        if not token:
            return []

        domain, item_code, element_code = indicator_code.split("/")

        fao_codes = [
            str(FAO_AREAS[iso3][0]) for iso3 in countries if iso3 in FAO_AREAS
        ]
        if not fao_codes:
            return []

        years = ",".join(str(y) for y in range(year_range[0], year_range[1] + 1))

        params = urllib.parse.urlencode({
            "area": ",".join(fao_codes),
            "item": item_code,
            "element": element_code,
            "year": years,
            "show_codes": "true",
            "show_unit": "true",
            "show_flags": "false",
            "output_type": "objects",
        })
        url = f"{self.base_url}/{domain}?{params}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "GeoSource/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read())
        return payload.get("data") or []

    def transform(self, raw: list[dict], indicator: IndicatorMeta) -> list[StandardRecord]:
        records: list[StandardRecord] = []
        fetched_at = datetime.utcnow().isoformat() + "Z"

        # FAO area code → ISO3 역방향 매핑
        fao_to_iso3 = {info[0]: iso3 for iso3, info in FAO_AREAS.items()}

        for row in raw:
            try:
                fao_code = int(row.get("Area Code") or row.get("area_code") or 0)
            except (TypeError, ValueError):
                continue
            iso3 = fao_to_iso3.get(fao_code)
            if not iso3:
                continue
            _, name_ko, name_en, region = FAO_AREAS[iso3]

            try:
                year = int(row.get("Year") or row.get("year"))
            except (TypeError, ValueError):
                continue

            raw_value = row.get("Value") if "Value" in row else row.get("value")
            try:
                value = float(raw_value) if raw_value not in (None, "", "..") else None
            except (TypeError, ValueError):
                value = None

            records.append(StandardRecord(
                dataset_id=indicator.dataset_id,
                source=self.source_name,
                source_url=(f"https://www.fao.org/faostat/en/#data/"
                            f"{indicator.indicator_code.split('/')[0]}"),
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
