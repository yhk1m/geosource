"""
SourceAdapter 추상 베이스.

새 출처(IMF, FAO, WMO ...)를 추가할 때 이 클래스를 상속하고
fetch / transform 두 메서드만 구현하면 된다.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from schema import StandardRecord, IndicatorMeta, DatasetBundle


class SourceAdapter(ABC):
    """모든 출처별 어댑터의 베이스 클래스"""

    source_name: str = ""
    license: str = ""
    base_url: str = ""

    # ── 구현해야 하는 메서드 ──────────────────────────────────
    @abstractmethod
    def list_indicators(self) -> list[IndicatorMeta]:
        """이 출처에서 지원하는 지표 카탈로그를 반환"""
        ...

    @abstractmethod
    def fetch(self, indicator_code: str, countries: list[str],
              year_range: tuple[int, int]) -> Any:
        """원본 응답 그대로 반환 (raw layer 보관용)"""
        ...

    @abstractmethod
    def transform(self, raw: Any, indicator: IndicatorMeta) -> list[StandardRecord]:
        """원본 → 표준 스키마"""
        ...

    # ── 공통 헬퍼 ─────────────────────────────────────────────
    def build_bundle(self, indicator_code: str, countries: list[str],
                     year_range: tuple[int, int]) -> DatasetBundle:
        """fetch + transform 을 묶은 편의 메서드"""
        indicator = self._get_indicator(indicator_code)
        raw = self.fetch(indicator_code, countries, year_range)
        records = self.transform(raw, indicator)
        return DatasetBundle(indicator=indicator, records=records)

    def _get_indicator(self, code: str) -> IndicatorMeta:
        for ind in self.list_indicators():
            if ind.indicator_code == code:
                return ind
        raise KeyError(f"Unknown indicator: {code}")
