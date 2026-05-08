"""
GeoSource 표준 스키마

모든 출처(World Bank, IMF, FAO, WMO, IEA, KOSIS, KMA 등)의 데이터를
이 단일 스키마로 정규화한다. 이렇게 하면 프론트엔드는 출처가 늘어나도
단일 인터페이스만 다루면 된다.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional, Literal
import json


# ─────────────────────────────────────────────────────────────
# 카테고리 분류 체계 (자체 정의)
# ─────────────────────────────────────────────────────────────
Category = Literal[
    "climate",       # 기상·기후 (WMO, KMA)
    "population",    # 인구 (UN, KOSIS, World Bank)
    "economy",       # 경제 (World Bank, IMF, KOSIS)
    "energy",        # 에너지 (IEA, World Bank)
    "agriculture",   # 농업·식량 (FAO)
    "trade",         # 무역 (UN Comtrade, IMF DOTS)
    "development",   # 개발지표 (UNDP, World Bank WDI)
    "environment",   # 환경 (FAO, World Bank)
]

PeriodType = Literal["annual", "quarterly", "monthly", "daily", "hourly"]


# ─────────────────────────────────────────────────────────────
# 단일 데이터 레코드
# ─────────────────────────────────────────────────────────────
@dataclass
class StandardRecord:
    """모든 출처 데이터의 정규화된 단위 레코드"""

    # 식별
    dataset_id: str              # 예: "wb_NY.GDP.MKTP.CD"
    source: str                  # 예: "World Bank"
    source_url: str              # 원본 데이터 URL
    indicator_code: str          # 출처 고유 지표 코드
    indicator_name_ko: str
    indicator_name_en: str

    # 분류
    category: Category
    subcategory: str             # 예: "national_accounts"

    # 단위 / 차원
    unit: str                    # SI 또는 ISO 4217 통화
    country_iso3: str            # ISO 3166-1 alpha-3 (예: "KOR")
    country_name_ko: str
    country_name_en: str
    region: str                  # UN M49 대륙·소지역

    # 시간
    year: int
    period_type: PeriodType
    period_label: str            # 예: "2023", "2023-Q1", "2023-08"

    # 값
    value: Optional[float]       # 결측은 None으로 통일

    # 메타
    license: str                 # 예: "CC BY 4.0", "KOGL Type 1"
    fetched_at: str              # ISO 8601 UTC
    last_updated_at_source: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────
# 지표 메타데이터 (카탈로그)
# ─────────────────────────────────────────────────────────────
@dataclass
class IndicatorMeta:
    """지표 정의 — 데이터 페이지의 검색·필터에 사용"""
    dataset_id: str
    source: str
    indicator_code: str
    name_ko: str
    name_en: str
    category: Category
    subcategory: str
    unit: str
    description_ko: str
    license: str
    update_frequency: PeriodType
    coverage_years: tuple[int, int]   # (시작년, 끝년)


# ─────────────────────────────────────────────────────────────
# 출처별 데이터셋 묶음 (직렬화 단위)
# ─────────────────────────────────────────────────────────────
@dataclass
class DatasetBundle:
    """하나의 (지표 × 다국가 × 다년도) 묶음. JSON 파일 1개에 대응."""
    indicator: IndicatorMeta
    records: list[StandardRecord] = field(default_factory=list)
    built_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(
            {
                "indicator": asdict(self.indicator),
                "records": [r.to_dict() for r in self.records],
                "built_at": self.built_at,
            },
            ensure_ascii=False,
            indent=indent,
        )
