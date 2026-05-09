# © 2026 김용현
"""
IMF DataMapper API 어댑터.

IMF DataMapper는 World Economic Outlook (WEO) 등 핵심 거시경제 지표를 제공.
- 인증 불필요
- 응답: {"values": {"<INDICATOR>": {"<ISO3>": {"<YEAR>": <value>, ...}}}}
- 라이선스: IMF Open Data (출처 표기, 재배포 가능)

CORS 미허용 → 브라우저 직접 호출 불가 → 빌드 타임에 정적 JSON 생성 필수.
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
from adapters.worldbank import COUNTRY_NAMES  # 같은 ISO3 → 한국어명 매핑 재사용


INDICATORS: list[IndicatorMeta] = [
    IndicatorMeta(
        dataset_id="imf_NGDP_RPCH",
        source="IMF",
        indicator_code="NGDP_RPCH",
        name_ko="실질 GDP 성장률",
        name_en="Real GDP growth (annual %)",
        category="economy",
        subcategory="growth",
        unit="%",
        description_ko="전년 대비 실질 GDP 증가율 (IMF World Economic Outlook).",
        license="IMF Open Data",
        update_frequency="annual",
        coverage_years=(1980, 2030),
    ),
    IndicatorMeta(
        dataset_id="imf_PCPIPCH",
        source="IMF",
        indicator_code="PCPIPCH",
        name_ko="소비자물가 상승률",
        name_en="Inflation, average consumer prices (%)",
        category="economy",
        subcategory="prices",
        unit="%",
        description_ko="연평균 소비자물가지수 변동률 (IMF WEO).",
        license="IMF Open Data",
        update_frequency="annual",
        coverage_years=(1980, 2030),
    ),
    IndicatorMeta(
        dataset_id="imf_LUR",
        source="IMF",
        indicator_code="LUR",
        name_ko="실업률",
        name_en="Unemployment rate (%)",
        category="economy",
        subcategory="unemployment",
        unit="%",
        description_ko="노동가능인구 대비 실업자 비율 (IMF WEO).",
        license="IMF Open Data",
        update_frequency="annual",
        coverage_years=(1980, 2030),
    ),
    IndicatorMeta(
        dataset_id="imf_GGXWDG_NGDP",
        source="IMF",
        indicator_code="GGXWDG_NGDP",
        name_ko="정부부채 (GDP비)",
        name_en="General government gross debt (% of GDP)",
        category="economy",
        subcategory="public_debt",
        unit="%",
        description_ko="일반정부 총부채 / GDP (IMF WEO).",
        license="IMF Open Data",
        update_frequency="annual",
        coverage_years=(1980, 2030),
    ),
    IndicatorMeta(
        dataset_id="imf_GGXCNL_NGDP",
        source="IMF",
        indicator_code="GGXCNL_NGDP",
        name_ko="정부 재정수지 (GDP비)",
        name_en="General government net lending/borrowing (% of GDP)",
        category="economy",
        subcategory="fiscal_balance",
        unit="%",
        description_ko="일반정부 순대여(+)/순차입(−) / GDP (IMF WEO).",
        license="IMF Open Data",
        update_frequency="annual",
        coverage_years=(1980, 2030),
    ),
    IndicatorMeta(
        dataset_id="imf_BCA_NGDPD",
        source="IMF",
        indicator_code="BCA_NGDPD",
        name_ko="경상수지 (GDP비)",
        name_en="Current account balance (% of GDP)",
        category="trade",
        subcategory="current_account",
        unit="%",
        description_ko="경상수지 / GDP (IMF WEO).",
        license="IMF Open Data",
        update_frequency="annual",
        coverage_years=(1980, 2030),
    ),
]


class ImfAdapter(SourceAdapter):
    source_name = "IMF"
    license = "IMF Open Data"
    base_url = "https://www.imf.org/external/datamapper/api/v1"

    def list_indicators(self) -> list[IndicatorMeta]:
        return INDICATORS

    def fetch(self, indicator_code: str, countries: list[str],
              year_range: tuple[int, int]) -> dict:
        """IMF DataMapper API 호출. countries는 무시(전체 받아 클라이언트가 필터).
        URL 경로에 ISO3들을 슬래시로 연결할 수도 있지만 응답 구조는 동일하므로 전체 fetch."""
        url = f"{self.base_url}/{indicator_code}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; GeoSource/1.0)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())

    def transform(self, raw: dict, indicator: IndicatorMeta) -> list[StandardRecord]:
        records: list[StandardRecord] = []
        fetched_at = datetime.utcnow().isoformat() + "Z"

        block = (raw.get("values") or {}).get(indicator.indicator_code) or {}
        for iso3, year_map in block.items():
            iso3 = (iso3 or "").upper()
            if not isinstance(year_map, dict):
                continue
            # 매핑되지 않은 국가도 영문 ISO3 그대로 포함 (후속 frontend 라벨링)
            name_ko, name_en, region = COUNTRY_NAMES.get(iso3, (iso3, iso3, ""))
            for yr, val in year_map.items():
                try:
                    year = int(yr)
                except (TypeError, ValueError):
                    continue
                try:
                    value = float(val) if val not in (None, "", "n/a") else None
                except (TypeError, ValueError):
                    value = None
                records.append(StandardRecord(
                    dataset_id=indicator.dataset_id,
                    source=self.source_name,
                    source_url=f"{self.base_url}/{indicator.indicator_code}/{iso3}",
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
