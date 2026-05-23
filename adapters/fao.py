# © 2026 김용현
"""
FAO(Food and Agriculture Organization) FAOSTAT 어댑터 — bulk CSV 방식.

이전 JWT 인증 방식은 별도 AWS Cognito 계정이 필요해 운영이 불안정했음.
이제는 FAO가 공개하는 zip(Normalized CSV) 을 도메인별로 1회 받아 캐시하고,
INDICATORS 의 각 (domain, item, element) 조합을 동일 캐시에서 필터한다.

엔드포인트(공개, 인증 없음):
    https://bulks-faostat.fao.org/production/{DOMAIN}.zip
        → 압축 안에 "{DOMAIN}_E_All_Data_(Normalized).csv" 포함

CSV 정규화 컬럼(도메인·시점에 따라 변형 있음 — 코드에서 후처리):
    Area Code, Area, Item Code, Item, Element Code, Element,
    Year, Unit, Value, Flag

라이선스: CC BY-NC-SA 3.0 IGO (출처 표기 + 비상업 + 동일조건변경허락)
"""
from __future__ import annotations
import csv
import io
import os
import sys
import time
import urllib.request
import urllib.error
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schema import StandardRecord, IndicatorMeta
from adapters.base import SourceAdapter


# FAO bulk 다운로드 URL.
# 2026년 중반에 bulks-faostat.fao.org/production/{domain}.zip 경로가 403으로
# 바뀌어 fenixservices.fao.org/faostat/static/bulkdownloads/ 의 정식 파일명을
# 직접 지정해야 한다.
BULK_BASE = "https://fenixservices.fao.org/faostat/static/bulkdownloads"
DOMAIN_FILES: dict[str, str] = {
    "QCL": "Production_Crops_Livestock_E_All_Data_(Normalized).zip",
    "RL":  "Inputs_LandUse_E_All_Data_(Normalized).zip",
    "FBS": "FoodBalanceSheets_E_All_Data_(Normalized).zip",
}

# 다운로드한 zip을 캐시하는 디렉토리 (.cache/fao/QCL.zip 등)
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "fao"

# 캐시 신선도(초) — 14일 지나면 재다운로드
CACHE_TTL_SECONDS = 14 * 24 * 3600

# Element 코드 별칭 — 구버전 indicator_code(2510, 2111)도 신버전 데이터(5510, 5111/5320)에 매칭
ELEMENT_ALIASES: dict[str, list[str]] = {
    "2510": ["5510", "2510"],          # Production (tonnes)
    "5510": ["5510", "2510"],
    "2111": ["5111", "2111", "5320"],  # Stocks (head)
    "5111": ["5111", "2111", "5320"],
    "5320": ["5320", "5111", "2111"],
}


# ─── FAO area code ↔ ISO3 매핑 ───
FAO_AREAS: dict[str, tuple[int, str, str, str]] = {
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
    "MYS": (135, "말레이시아", "Malaysia", "South-Eastern Asia"),
    "AUS": (10,  "호주", "Australia", "Australia and New Zealand"),
    "NZL": (156, "뉴질랜드", "New Zealand", "Australia and New Zealand"),
    "ZAF": (202, "남아프리카공화국", "South Africa", "Sub-Saharan Africa"),
    "EGY": (59,  "이집트", "Egypt", "Northern Africa"),
    "NGA": (159, "나이지리아", "Nigeria", "Sub-Saharan Africa"),
    "KEN": (114, "케냐", "Kenya", "Sub-Saharan Africa"),
    "ETH": (238, "에티오피아", "Ethiopia", "Sub-Saharan Africa"),
    "CIV": (107, "코트디부아르", "Côte d'Ivoire", "Sub-Saharan Africa"),
    "GHA": (81,  "가나", "Ghana", "Sub-Saharan Africa"),
    "SAU": (194, "사우디아라비아", "Saudi Arabia", "Western Asia"),
    "TUR": (223, "튀르키예", "Türkiye", "Western Asia"),
    "ECU": (58,  "에콰도르", "Ecuador", "Latin America"),
    "COL": (44,  "콜롬비아", "Colombia", "Latin America"),
}


# ─── 큐레이션된 지표 카탈로그 ───
# indicator_code 형식: "{DOMAIN}/{item_code}/{element_code}"
INDICATORS: list[IndicatorMeta] = [
    # ─── 주요 곡물 ───
    IndicatorMeta(
        dataset_id="fao_QCL_15_5510",
        source="FAO", indicator_code="QCL/15/5510",
        name_ko="밀 생산량", name_en="Wheat production",
        category="agriculture", subcategory="crop_production", unit="t",
        description_ko="연간 밀 생산량(톤). FAOSTAT QCL 도메인.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_27_5510",
        source="FAO", indicator_code="QCL/27/5510",
        name_ko="쌀(벼) 생산량", name_en="Rice (paddy) production",
        category="agriculture", subcategory="crop_production", unit="t",
        description_ko="연간 벼(쌀) 생산량(톤). 도정 전 paddy 기준.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_56_5510",
        source="FAO", indicator_code="QCL/56/5510",
        name_ko="옥수수 생산량", name_en="Maize (corn) production",
        category="agriculture", subcategory="crop_production", unit="t",
        description_ko="연간 옥수수 생산량(톤).",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_44_5510",
        source="FAO", indicator_code="QCL/44/5510",
        name_ko="보리 생산량", name_en="Barley production",
        category="agriculture", subcategory="crop_production", unit="t",
        description_ko="연간 보리 생산량(톤).",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_236_5510",
        source="FAO", indicator_code="QCL/236/5510",
        name_ko="콩(대두) 생산량", name_en="Soybean production",
        category="agriculture", subcategory="crop_production", unit="t",
        description_ko="연간 대두 생산량(톤). 주요 단백질 작물.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_116_5510",
        source="FAO", indicator_code="QCL/116/5510",
        name_ko="감자 생산량", name_en="Potato production",
        category="agriculture", subcategory="crop_production", unit="t",
        description_ko="연간 감자 생산량(톤).",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_156_5510",
        source="FAO", indicator_code="QCL/156/5510",
        name_ko="사탕수수 생산량", name_en="Sugar cane production",
        category="agriculture", subcategory="crop_production", unit="t",
        description_ko="연간 사탕수수 생산량(톤). 열대·아열대 주요 작물.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),

    # ─── 축산물 ───
    IndicatorMeta(
        dataset_id="fao_QCL_866_5111",
        source="FAO", indicator_code="QCL/866/5111",
        name_ko="소 사육두수", name_en="Cattle stocks",
        category="agriculture", subcategory="livestock", unit="마리",
        description_ko="연말 시점 소 사육두수(마리).",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_1034_5111",
        source="FAO", indicator_code="QCL/1034/5111",
        name_ko="돼지 사육두수", name_en="Swine/pigs stocks",
        category="agriculture", subcategory="livestock", unit="마리",
        description_ko="연말 시점 돼지 사육두수(마리).",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_976_5111",
        source="FAO", indicator_code="QCL/976/5111",
        name_ko="양 사육두수", name_en="Sheep stocks",
        category="agriculture", subcategory="livestock", unit="마리",
        description_ko="연말 시점 양 사육두수(마리).",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_1057_5112",
        source="FAO", indicator_code="QCL/1057/5112",
        name_ko="닭 사육수", name_en="Chicken stocks",
        category="agriculture", subcategory="livestock", unit="천 마리",
        description_ko="연말 시점 닭 사육수(1,000마리 단위). FAOSTAT는 닭만 5112 코드를 사용.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_882_5510",
        source="FAO", indicator_code="QCL/882/5510",
        name_ko="우유 생산량", name_en="Milk production (cow, whole fresh)",
        category="agriculture", subcategory="livestock", unit="t",
        description_ko="연간 생우유 생산량(톤). 젖소 기준.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),

    # ─── 토지·식량 ───
    IndicatorMeta(
        dataset_id="fao_RL_6610_5110",
        source="FAO", indicator_code="RL/6610/5110",
        name_ko="농경지 면적", name_en="Agricultural land area",
        category="agriculture", subcategory="land_use", unit="1000 ha",
        description_ko="농경지(경작지+영구작물지+목초지) 총 면적(천 ha). FAOSTAT Land Use 도메인.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2022),
    ),
    IndicatorMeta(
        dataset_id="fao_FBS_2901_664",
        source="FAO", indicator_code="FBS/2901/664",
        name_ko="1인당 일일 식이에너지 공급", name_en="Dietary energy supply (kcal/cap/day)",
        category="agriculture", subcategory="food_supply", unit="kcal/cap/day",
        description_ko="1인당 1일 식이에너지 공급량. Food Balance Sheets.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2010, 2022),
    ),

    # ─── 열대·상품작물 (세계지리 농업·세계화 단원) ───
    IndicatorMeta(
        dataset_id="fao_QCL_656_5510",
        source="FAO", indicator_code="QCL/656/5510",
        name_ko="커피 생산량", name_en="Coffee, green production",
        category="agriculture", subcategory="crop_production", unit="t",
        description_ko="연간 생두 생산량(톤). 브라질·베트남·콜롬비아 등 열대 핵심 수출 작물.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_661_5510",
        source="FAO", indicator_code="QCL/661/5510",
        name_ko="카카오 생산량", name_en="Cocoa beans production",
        category="agriculture", subcategory="crop_production", unit="t",
        description_ko="연간 카카오 콩 생산량(톤). 코트디부아르·가나·인도네시아.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_254_5510",
        source="FAO", indicator_code="QCL/254/5510",
        name_ko="야자열매(팜오일 원료) 생산량", name_en="Oil palm fruit production",
        category="agriculture", subcategory="crop_production", unit="t",
        description_ko="연간 야자열매 생산량(톤). 팜오일 원료, 인도네시아·말레이시아 세계 80%.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_667_5510",
        source="FAO", indicator_code="QCL/667/5510",
        name_ko="차(잎) 생산량", name_en="Tea leaves production",
        category="agriculture", subcategory="crop_production", unit="t",
        description_ko="연간 차잎 생산량(톤). 중국·인도·케냐가 주요 생산국.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_329_5510",
        source="FAO", indicator_code="QCL/329/5510",
        name_ko="면화(린트) 생산량", name_en="Cotton lint production",
        category="agriculture", subcategory="crop_production", unit="t",
        description_ko="연간 면화 린트 생산량(톤). 중국·인도·미국·중앙아시아.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_836_5510",
        source="FAO", indicator_code="QCL/836/5510",
        name_ko="천연고무 생산량", name_en="Natural rubber production",
        category="agriculture", subcategory="crop_production", unit="t",
        description_ko="연간 천연고무 생산량(톤). 태국·인도네시아·베트남 등 동남아 집중.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
    IndicatorMeta(
        dataset_id="fao_QCL_486_5510",
        source="FAO", indicator_code="QCL/486/5510",
        name_ko="바나나 생산량", name_en="Banana production",
        category="agriculture", subcategory="crop_production", unit="t",
        description_ko="연간 바나나 생산량(톤). 인도·중국·필리핀·에콰도르.",
        license="CC BY-NC-SA 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2023),
    ),
]


def _ensure_zip(domain: str) -> Path:
    """도메인별 zip 캐시 보장 — 없거나 신선도 초과면 재다운로드.

    수동으로 CACHE_DIR/{domain}.zip 을 미리 넣어 두면 네트워크 없이도 동작."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    local = CACHE_DIR / f"{domain}.zip"

    if local.exists():
        age = time.time() - local.stat().st_mtime
        if age < CACHE_TTL_SECONDS:
            return local

    fname = DOMAIN_FILES.get(domain)
    if not fname:
        raise RuntimeError(f"FAO 도메인 {domain} 에 대한 bulk 파일명 매핑이 없습니다 (adapters/fao.py:DOMAIN_FILES)")
    url = f"{BULK_BASE}/{fname}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "Referer": "https://www.fao.org/faostat/en/",
    })
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
        local.write_bytes(data)
    except urllib.error.HTTPError as e:
        if local.exists():
            # 다운로드 실패 시 만료된 캐시라도 사용
            print(f"[FAO] {domain} 다운로드 실패({e.code}) — 기존 캐시 사용")
            return local
        raise RuntimeError(
            f"FAO {domain} bulk 다운로드 실패: HTTP {e.code}. "
            f"수동으로 {url} 을 브라우저에서 받아 {local} 에 두세요."
        ) from None
    return local


def _load_csv(domain: str) -> list[dict]:
    """zip 내 CSV를 dict 리스트로 반환. 컬럼은 정규화(공백/별칭 처리)."""
    zip_path = _ensure_zip(domain)
    with zipfile.ZipFile(zip_path) as zf:
        # 압축 내 CSV 파일 자동 탐색 (도메인별 명명이 약간씩 다름)
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise RuntimeError(f"FAO {domain} zip에 CSV 없음")
        # 'Normalized' 우선
        csv_names.sort(key=lambda n: 0 if "normalized" in n.lower() else 1)
        with zf.open(csv_names[0]) as f:
            # FAO CSV는 보통 UTF-8, 일부 라틴1
            try:
                text = f.read().decode("utf-8")
            except UnicodeDecodeError:
                with zf.open(csv_names[0]) as f2:
                    text = f2.read().decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


# 도메인별 CSV 메모리 캐시 (어댑터 인스턴스 수명 동안 유지)
_DOMAIN_ROWS_CACHE: dict[str, list[dict]] = {}


def _get_domain_rows(domain: str) -> list[dict]:
    if domain not in _DOMAIN_ROWS_CACHE:
        _DOMAIN_ROWS_CACHE[domain] = _load_csv(domain)
    return _DOMAIN_ROWS_CACHE[domain]


def _col(row: dict, *aliases: str) -> str:
    """대소문자·공백 무관하게 컬럼 값 찾기."""
    norm = {k.strip().lower(): v for k, v in row.items()}
    for a in aliases:
        v = norm.get(a.strip().lower())
        if v not in (None, ""):
            return v
    return ""


class FaoAdapter(SourceAdapter):
    source_name = "FAO"
    license = "CC BY-NC-SA 3.0 IGO"
    base_url = "https://bulks-faostat.fao.org/production"

    def list_indicators(self) -> list[IndicatorMeta]:
        return INDICATORS

    def fetch(self, indicator_code: str, countries: list[str],
              year_range: tuple[int, int]) -> list[dict]:
        domain, item_code, element_code = indicator_code.split("/")
        try:
            rows = _get_domain_rows(domain)
        except Exception as e:
            raise RuntimeError(f"FAO {domain} CSV 로드 실패: {e}") from None

        # FAO area code 화이트리스트
        wanted_areas = {FAO_AREAS[iso3][0] for iso3 in countries if iso3 in FAO_AREAS}
        if not wanted_areas:
            return []

        element_targets = set(ELEMENT_ALIASES.get(element_code, [element_code]))
        y0, y1 = year_range

        out: list[dict] = []
        for row in rows:
            # Item Code 매칭
            item_v = _col(row, "Item Code", "Item Code (FAO)")
            if item_v != item_code:
                continue
            # Element Code 매칭(별칭 허용)
            el_v = _col(row, "Element Code")
            if el_v not in element_targets:
                continue
            # Area Code 매칭
            area_v = _col(row, "Area Code", "Area Code (FAO)")
            try:
                area_int = int(area_v)
            except ValueError:
                continue
            if area_int not in wanted_areas:
                continue
            # 연도 범위
            try:
                year = int(_col(row, "Year", "Year Code"))
            except ValueError:
                continue
            if not (y0 <= year <= y1):
                continue
            out.append({
                "area_code": area_int,
                "year": year,
                "value": _col(row, "Value"),
                "unit": _col(row, "Unit"),
                "flag": _col(row, "Flag"),
            })
        return out

    def transform(self, raw: list[dict], indicator: IndicatorMeta) -> list[StandardRecord]:
        records: list[StandardRecord] = []
        fetched_at = datetime.utcnow().isoformat() + "Z"

        fao_to_iso3 = {info[0]: iso3 for iso3, info in FAO_AREAS.items()}

        for row in raw:
            iso3 = fao_to_iso3.get(row["area_code"])
            if not iso3:
                continue
            _fao_code, name_ko, name_en, region = FAO_AREAS[iso3]
            try:
                value = float(row["value"]) if row["value"] not in ("", None) else None
            except (TypeError, ValueError):
                value = None

            records.append(StandardRecord(
                dataset_id=indicator.dataset_id,
                source=self.source_name,
                source_url=f"{BULK_BASE}/{DOMAIN_FILES.get(indicator.indicator_code.split('/')[0], '')}",
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
                year=row["year"],
                period_type="annual",
                period_label=str(row["year"]),
                value=value,
                license=self.license,
                fetched_at=fetched_at,
            ))
        return records
