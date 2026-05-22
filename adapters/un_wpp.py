# © 2026 김용현
"""
UN World Population Prospects (WPP 2024) 어댑터 — bulk CSV 방식.

UN DataPortal REST API의 `/data/...` 엔드포인트가 2025년경 Bearer 토큰 인증으로
전환되어 무료 키 없이 호출이 불가능해졌다. 반면 WPP가 공개하는 압축 CSV는
여전히 인증 없이 다운로드 가능하므로 이 경로로 우회한다.

엔드포인트(공개):
    https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/
        CSV_FILES/WPP2024_Demographic_Indicators_Medium.csv.gz
        (gzip ~16MB → CSV ~40MB)

CSV는 한 행에 (Location, Variant, Time) 단위로 67개 지표 컬럼이 모두 들어 있는
와이드 포맷이라, 한 번 받아 캐시하면 카탈로그 안의 모든 지표를 같은 데이터에서
컬럼만 바꿔 추출할 수 있다.

라이선스: CC BY 3.0 IGO (출처 표기 시 자유 이용)
"""
from __future__ import annotations
import csv
import gzip
import io
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schema import StandardRecord, IndicatorMeta
from adapters.base import SourceAdapter
from adapters.worldbank import COUNTRY_NAMES


CSV_URL = (
    "https://population.un.org/wpp/assets/Excel%20Files/"
    "1_Indicator%20(Standard)/CSV_FILES/"
    "WPP2024_Demographic_Indicators_Medium.csv.gz"
)

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "un_wpp"
CACHE_FILE = CACHE_DIR / "WPP2024_Demographic_Indicators_Medium.csv.gz"

# 14일 신선도 — WPP는 1년에 한 번 갱신되므로 충분
CACHE_TTL_SECONDS = 14 * 24 * 3600

# WPP CSV의 연도 범위는 1950~2100이지만 페이로드 절감을 위해 2000~2100만 사용
WPP_YEAR_RANGE = (2000, 2100)


# ─── 컬럼 → 지표 매핑 ────────────────────────────────────────
# (column, unit_in_csv, scale) — scale=1000은 'thousands → 절대수' 변환
#
# indicator_code = "WPP/{컬럼명}" 형식. 빌드 시 컬럼명을 다시 사용해 추출.
INDICATORS: list[IndicatorMeta] = [
    IndicatorMeta(
        dataset_id="wpp_total_population",
        source="UN WPP", indicator_code="WPP/TPopulation1July",
        name_ko="총인구 (UN 추계·전망)", name_en="Total population (mid-year, est+projection)",
        category="population", subcategory="size",
        unit="명",
        description_ko="7월 1일 기준 총인구. 1950~2100 전망(중위 시나리오). UN Population Division WPP 2024.",
        license="CC BY 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2100),
    ),
    IndicatorMeta(
        dataset_id="wpp_population_density",
        source="UN WPP", indicator_code="WPP/PopDensity",
        name_ko="인구밀도 (UN 추계·전망)", name_en="Population density (est+projection)",
        category="population", subcategory="density",
        unit="명/km²",
        description_ko="단위 면적당 인구. WPP 2024 중위 시나리오, 2100년까지 전망 포함.",
        license="CC BY 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2100),
    ),
    IndicatorMeta(
        dataset_id="wpp_population_growth_rate",
        source="UN WPP", indicator_code="WPP/PopGrowthRate",
        name_ko="인구성장률 (UN 전망)", name_en="Population growth rate (est+projection)",
        category="population", subcategory="change",
        unit="%",
        description_ko="연평균 인구증가율. 2100년까지 중위 시나리오 전망.",
        license="CC BY 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2100),
    ),
    IndicatorMeta(
        dataset_id="wpp_median_age",
        source="UN WPP", indicator_code="WPP/MedianAgePop",
        name_ko="중위연령", name_en="Median age of population",
        category="population", subcategory="structure",
        unit="세",
        description_ko="인구를 나이순으로 줄세웠을 때 가운데 사람의 나이. 인구 고령화의 핵심 지표. WPP 2024.",
        license="CC BY 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2100),
    ),
    IndicatorMeta(
        dataset_id="wpp_sex_ratio",
        source="UN WPP", indicator_code="WPP/PopSexRatio",
        name_ko="성비 (여 100명당 남)", name_en="Sex ratio (males per 100 females)",
        category="population", subcategory="structure",
        unit="남/여100",
        description_ko="여성 100명당 남성 수. 100보다 크면 남초, 작으면 여초.",
        license="CC BY 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2100),
    ),
    IndicatorMeta(
        dataset_id="wpp_life_expectancy_birth",
        source="UN WPP", indicator_code="WPP/LEx",
        name_ko="출생시 기대수명 (UN 전망)", name_en="Life expectancy at birth (est+projection)",
        category="population", subcategory="mortality",
        unit="세",
        description_ko="신생아가 평균적으로 생존할 것으로 예상되는 햇수. 남녀 합계, WPP 2024.",
        license="CC BY 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2100),
    ),
    IndicatorMeta(
        dataset_id="wpp_life_expectancy_65",
        source="UN WPP", indicator_code="WPP/LE65",
        name_ko="65세 기대여명", name_en="Life expectancy at age 65",
        category="population", subcategory="mortality",
        unit="세",
        description_ko="65세 인구가 추가로 살 것으로 기대되는 햇수. 노년기 건강수명·연금설계의 기초 지표.",
        license="CC BY 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2100),
    ),
    IndicatorMeta(
        dataset_id="wpp_total_fertility_rate",
        source="UN WPP", indicator_code="WPP/TFR",
        name_ko="합계출산율 (UN 전망)", name_en="Total fertility rate (est+projection)",
        category="population", subcategory="fertility",
        unit="명/여",
        description_ko="가임여성 1명이 평생 낳을 평균 자녀 수. 2.1 미만이면 인구 자연감소. WPP 2024 중위 시나리오.",
        license="CC BY 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2100),
    ),
    IndicatorMeta(
        dataset_id="wpp_crude_birth_rate",
        source="UN WPP", indicator_code="WPP/CBR",
        name_ko="조출생률 (UN 전망)", name_en="Crude birth rate (est+projection)",
        category="population", subcategory="fertility",
        unit="명/1000",
        description_ko="인구 1,000명당 연간 출생아 수. 2100년까지 중위 시나리오 전망.",
        license="CC BY 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2100),
    ),
    IndicatorMeta(
        dataset_id="wpp_crude_death_rate",
        source="UN WPP", indicator_code="WPP/CDR",
        name_ko="조사망률 (UN 전망)", name_en="Crude death rate (est+projection)",
        category="population", subcategory="mortality",
        unit="명/1000",
        description_ko="인구 1,000명당 연간 사망자 수. 2100년까지 중위 시나리오 전망.",
        license="CC BY 3.0 IGO", update_frequency="annual",
        coverage_years=(2000, 2100),
    ),
]


# ─── CSV 다운로드·캐시·파싱 ─────────────────────────────────
def _ensure_csv() -> Path:
    """CSV.gz 캐시 보장. 실패 시 만료된 캐시라도 사용."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if CACHE_FILE.exists():
        age = time.time() - CACHE_FILE.stat().st_mtime
        if age < CACHE_TTL_SECONDS:
            return CACHE_FILE

    req = urllib.request.Request(CSV_URL, headers={
        "User-Agent": "Mozilla/5.0 (compatible; GeoSource/1.0)",
        "Accept": "*/*",
    })
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = resp.read()
        CACHE_FILE.write_bytes(data)
    except urllib.error.HTTPError as e:
        if CACHE_FILE.exists():
            print(f"[UN WPP] 다운로드 실패({e.code}) — 기존 캐시 사용")
            return CACHE_FILE
        raise RuntimeError(
            f"UN WPP bulk 다운로드 실패: HTTP {e.code}. "
            f"수동으로 {CSV_URL} 을 받아 {CACHE_FILE} 에 두세요."
        ) from None
    return CACHE_FILE


# CSV는 매우 크므로(40MB) Variant=Medium·COUNTRY·연도 필터를 적용한 슬림 캐시로 보관
_ROWS_CACHE: list[dict] | None = None


def _load_rows() -> list[dict]:
    """1회 로드 후 메모리 캐시. 필터 후의 dict 리스트를 반환."""
    global _ROWS_CACHE
    if _ROWS_CACHE is not None:
        return _ROWS_CACHE

    path = _ensure_csv()
    with gzip.open(path, "rt", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        y0, y1 = WPP_YEAR_RANGE
        rows: list[dict] = []
        for r in reader:
            iso3 = (r.get("ISO3_code") or "").strip().upper()
            if not iso3 or iso3 not in COUNTRY_NAMES:
                continue
            if (r.get("Variant") or "").strip() != "Medium":
                continue
            try:
                year = int(r.get("Time"))
            except (TypeError, ValueError):
                continue
            if not (y0 <= year <= y1):
                continue
            rows.append(r)

    _ROWS_CACHE = rows
    return rows


# ─── 어댑터 ───────────────────────────────────────────────
class UnWppAdapter(SourceAdapter):
    source_name = "UN WPP"
    license = "CC BY 3.0 IGO"
    base_url = "https://population.un.org/wpp"

    # 일부 컬럼은 천 단위 → 절대값으로 스케일
    _SCALE = {
        "TPopulation1July": 1000,
    }

    def list_indicators(self) -> list[IndicatorMeta]:
        return INDICATORS

    def fetch(self, indicator_code: str, countries: list[str],
              year_range: tuple[int, int]) -> list[dict]:
        """countries·year_range는 무시(WPP는 자체 범위 사용)."""
        column = indicator_code.split("/", 1)[1]
        scale = self._SCALE.get(column, 1)

        out: list[dict] = []
        for r in _load_rows():
            v = r.get(column)
            if v in (None, ""):
                continue
            try:
                value = float(v) * scale
            except ValueError:
                continue
            out.append({
                "iso3": r["ISO3_code"].upper(),
                "year": int(r["Time"]),
                "value": value,
            })
        return out

    def transform(self, raw: list[dict], indicator: IndicatorMeta) -> list[StandardRecord]:
        records: list[StandardRecord] = []
        fetched_at = datetime.utcnow().isoformat() + "Z"
        source_url = (
            f"{self.base_url}/Download/Standard/CSV — column {indicator.indicator_code.split('/',1)[1]}"
        )

        for row in raw:
            iso3 = row["iso3"]
            name_ko, name_en, region = COUNTRY_NAMES[iso3]
            records.append(StandardRecord(
                dataset_id=indicator.dataset_id,
                source=self.source_name,
                source_url=source_url,
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
                value=row["value"],
                license=self.license,
                fetched_at=fetched_at,
            ))
        return records
