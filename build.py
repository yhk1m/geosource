"""
GeoSource 빌드 스크립트.

각 어댑터를 호출해 정규화된 JSON을 ./data/ 아래에 생성한다.
프론트엔드(index.html)는 이 정적 JSON을 fetch 한다.

사용:
    python build.py                     # 모든 어댑터, 모든 지표
    python build.py --source worldbank  # 특정 어댑터만

환경변수:
    KOSIS_API_KEY        — KOSIS OpenAPI 인증키
    GEOSOURCE_TRIGGER    — 빌드 트리거 정보 (build-info.json에 기록)
"""
from __future__ import annotations
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from adapters import WorldBankAdapter, KosisAdapter, FaoAdapter, ImfAdapter, OwidAdapter, PewAdapter

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# 기본 대상 국가 (World Bank용). 필요에 따라 확장.
DEFAULT_COUNTRIES = [
    "KOR", "JPN", "CHN", "USA", "GBR", "FRA", "DEU",
    "RUS", "IND", "IDN", "VNM", "BRA", "AUS", "ZAF",
    "SAU", "TUR", "MEX", "CAN", "ITA", "ESP",
]
DEFAULT_YEAR_RANGE = (2000, 2023)


def build_worldbank() -> dict:
    adapter = WorldBankAdapter()
    catalog = []
    for ind in adapter.list_indicators():
        print(f"  → {ind.dataset_id} ({ind.name_ko})")
        try:
            bundle = adapter.build_bundle(
                indicator_code=ind.indicator_code,
                countries=DEFAULT_COUNTRIES,
                year_range=DEFAULT_YEAR_RANGE,
            )
            out_path = DATA_DIR / f"{ind.dataset_id}.json"
            out_path.write_text(bundle.to_json(), encoding="utf-8")
            catalog.append({
                "dataset_id": ind.dataset_id,
                "source": ind.source,
                "name_ko": ind.name_ko,
                "name_en": ind.name_en,
                "category": ind.category,
                "subcategory": ind.subcategory,
                "unit": ind.unit,
                "license": ind.license,
                "file": f"data/{ind.dataset_id}.json",
                "record_count": len(bundle.records),
            })
        except Exception as e:
            print(f"    ! 실패: {e}")
    return {"source": "World Bank", "indicators": catalog}


def build_imf() -> dict:
    adapter = ImfAdapter()
    catalog = []
    for ind in adapter.list_indicators():
        print(f"  → {ind.dataset_id} ({ind.name_ko})")
        try:
            bundle = adapter.build_bundle(
                indicator_code=ind.indicator_code,
                countries=DEFAULT_COUNTRIES,
                year_range=DEFAULT_YEAR_RANGE,
            )
            out_path = DATA_DIR / f"{ind.dataset_id}.json"
            out_path.write_text(bundle.to_json(), encoding="utf-8")
            catalog.append({
                "dataset_id": ind.dataset_id,
                "source": ind.source,
                "name_ko": ind.name_ko,
                "name_en": ind.name_en,
                "category": ind.category,
                "subcategory": ind.subcategory,
                "unit": ind.unit,
                "license": ind.license,
                "file": f"data/{ind.dataset_id}.json",
                "record_count": len(bundle.records),
            })
        except Exception as e:
            print(f"    ! 실패: {e}")
    return {"source": "IMF", "indicators": catalog}


def build_fao() -> dict:
    adapter = FaoAdapter()
    catalog = []
    for ind in adapter.list_indicators():
        print(f"  → {ind.dataset_id} ({ind.name_ko})")
        try:
            bundle = adapter.build_bundle(
                indicator_code=ind.indicator_code,
                countries=DEFAULT_COUNTRIES,
                year_range=DEFAULT_YEAR_RANGE,
            )
            if not bundle.records:
                print("    (스킵: 데이터 없음 - FAO_USERNAME/FAO_PASSWORD 미설정 가능성)")
                continue
            out_path = DATA_DIR / f"{ind.dataset_id}.json"
            out_path.write_text(bundle.to_json(), encoding="utf-8")
            catalog.append({
                "dataset_id": ind.dataset_id,
                "source": ind.source,
                "name_ko": ind.name_ko,
                "name_en": ind.name_en,
                "category": ind.category,
                "subcategory": ind.subcategory,
                "unit": ind.unit,
                "license": ind.license,
                "file": f"data/{ind.dataset_id}.json",
                "record_count": len(bundle.records),
            })
        except Exception as e:
            print(f"    ! 실패: {e}")
    return {"source": "FAO", "indicators": catalog}


def build_owid() -> dict:
    adapter = OwidAdapter()
    catalog = []
    for ind in adapter.list_indicators():
        print(f"  → {ind.dataset_id} ({ind.name_ko})")
        try:
            bundle = adapter.build_bundle(
                indicator_code=ind.indicator_code,
                countries=DEFAULT_COUNTRIES,
                year_range=DEFAULT_YEAR_RANGE,
            )
            out_path = DATA_DIR / f"{ind.dataset_id}.json"
            out_path.write_text(bundle.to_json(), encoding="utf-8")
            catalog.append({
                "dataset_id": ind.dataset_id,
                "source": ind.source,
                "name_ko": ind.name_ko,
                "name_en": ind.name_en,
                "category": ind.category,
                "subcategory": ind.subcategory,
                "unit": ind.unit,
                "license": ind.license,
                "file": f"data/{ind.dataset_id}.json",
                "record_count": len(bundle.records),
            })
        except Exception as e:
            print(f"    ! 실패: {e}")
    return {"source": "OWID", "indicators": catalog}


def build_pew() -> dict:
    adapter = PewAdapter()
    catalog = []
    for ind in adapter.list_indicators():
        print(f"  → {ind.dataset_id} ({ind.name_ko})")
        try:
            bundle = adapter.build_bundle(
                indicator_code=ind.indicator_code,
                countries=DEFAULT_COUNTRIES,
                year_range=DEFAULT_YEAR_RANGE,
            )
            out_path = DATA_DIR / f"{ind.dataset_id}.json"
            out_path.write_text(bundle.to_json(), encoding="utf-8")
            catalog.append({
                "dataset_id": ind.dataset_id,
                "source": ind.source,
                "name_ko": ind.name_ko,
                "name_en": ind.name_en,
                "category": ind.category,
                "subcategory": ind.subcategory,
                "unit": ind.unit,
                "license": ind.license,
                "file": f"data/{ind.dataset_id}.json",
                "record_count": len(bundle.records),
            })
        except Exception as e:
            print(f"    ! 실패: {e}")
    return {"source": "Pew Research Center", "indicators": catalog}


def build_kosis() -> dict:
    adapter = KosisAdapter()
    catalog = []
    for ind in adapter.list_indicators():
        print(f"  → {ind.dataset_id} ({ind.name_ko})")
        try:
            bundle = adapter.build_bundle(
                indicator_code=ind.indicator_code,
                countries=[],
                year_range=DEFAULT_YEAR_RANGE,
            )
            if not bundle.records:
                print("    (스킵: 데이터 없음 — API 키 미설정 가능성)")
                continue
            out_path = DATA_DIR / f"{ind.dataset_id}.json"
            out_path.write_text(bundle.to_json(), encoding="utf-8")
            catalog.append({
                "dataset_id": ind.dataset_id,
                "source": ind.source,
                "name_ko": ind.name_ko,
                "name_en": ind.name_en,
                "category": ind.category,
                "subcategory": ind.subcategory,
                "unit": ind.unit,
                "license": ind.license,
                "file": f"data/{ind.dataset_id}.json",
                "record_count": len(bundle.records),
            })
        except Exception as e:
            print(f"    ! 실패: {e}")
    return {"source": "KOSIS", "indicators": catalog}


def write_build_info(sources: list[dict], requested_source: str) -> dict:
    """프론트엔드가 푸터에 표시할 메타정보.

    per_source는 출처별로 누적 — 이번에 빌드되지 않은 출처의 기존 last_built_at은 그대로 유지.
    """
    now = datetime.utcnow().isoformat() + "Z"

    # 기존 build-info.json의 per_source 보존
    existing_per_source = {}
    bi_path = DATA_DIR / "build-info.json"
    if bi_path.exists():
        try:
            existing = json.loads(bi_path.read_text(encoding="utf-8"))
            existing_per_source = existing.get("per_source", {}) or {}
        except Exception:
            existing_per_source = {}

    # 이번에 빌드한 출처는 덮어쓰기, 나머지는 기존값 유지
    per_source = dict(existing_per_source)
    for s in sources:
        per_source[s["source"]] = {
            "last_built_at": now,
            "indicator_count": len(s["indicators"]),
            "record_count": sum(i.get("record_count", 0) for i in s["indicators"]),
        }

    info = {
        "last_built_at": now,
        "triggered_by": os.environ.get("GEOSOURCE_TRIGGER", "local"),
        "requested_source": requested_source,
        "sources_built": [s["source"] for s in sources],
        "indicator_count": sum(len(s["indicators"]) for s in sources),
        "record_count_total": sum(
            i.get("record_count", 0) for s in sources for i in s["indicators"]
        ),
        "per_source": per_source,
    }
    bi_path.write_text(
        json.dumps(info, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source",
        choices=["worldbank", "imf", "fao", "owid", "pew", "kosis", "all"], default="all")
    args = parser.parse_args()

    sources = []
    if args.source in ("worldbank", "all"):
        print("[1/6] World Bank 빌드 중…")
        sources.append(build_worldbank())
    if args.source in ("imf", "all"):
        print("[2/6] IMF 빌드 중…")
        sources.append(build_imf())
    if args.source in ("fao", "all"):
        print("[3/6] FAO 빌드 중…")
        sources.append(build_fao())
    if args.source in ("owid", "all"):
        print("[4/6] OWID 빌드 중…")
        sources.append(build_owid())
    if args.source in ("pew", "all"):
        print("[5/6] Pew Research 빌드 중…")
        sources.append(build_pew())
    if args.source in ("kosis", "all"):
        print("[6/6] KOSIS 빌드 중…")
        sources.append(build_kosis())

    # 마스터 카탈로그 작성 (프론트엔드 진입점)
    catalog_path = DATA_DIR / "catalog.json"
    catalog_path.write_text(
        json.dumps({"sources": sources}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 빌드 메타정보 (프론트엔드 푸터 표시용)
    info = write_build_info(sources, requested_source=args.source)

    print(f"\n✓ 카탈로그 작성: {catalog_path}")
    print(f"✓ 빌드 정보:    {DATA_DIR / 'build-info.json'}")
    print(f"  · 트리거:     {info['triggered_by']}")
    print(f"  · 총 지표 수: {info['indicator_count']}")
    print(f"  · 총 레코드:  {info['record_count_total']:,}")


if __name__ == "__main__":
    main()
