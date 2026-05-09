# GeoSource

세계 공식 데이터 허브. World Bank · IMF · FAO · WMO · IEA · KOSIS · 기상청 등 공식 통계기관의 지리·통계 데이터를 단일 표준 스키마로 모아 제공합니다.

bgnl.kr 생태계의 데이터 허브 / 백엔드 레이어. 시각화 도구(GeoStatAtlas, GeoGrapher)는 GeoSource를 데이터 소스로 사용할 수 있습니다.

## 구조

```
geosource/
├── index.html              # 단일 파일 프론트엔드 (GitHub Pages 배포)
├── schema.py               # 표준 스키마 (StandardRecord, IndicatorMeta)
├── adapters/
│   ├── base.py             # 추상 SourceAdapter
│   ├── worldbank.py        # World Bank Open Data 어댑터 (인증 불필요)
│   ├── fao.py              # FAOSTAT 어댑터 (JWT 인증 필요)
│   └── kosis.py            # KOSIS OpenAPI 어댑터 (API 키 필요)
├── build.py                # 어댑터 호출 → /data/*.json 생성
└── data/                   # 정규화된 정적 JSON (KOSIS 등 CORS 막힌 출처용)
```

## 두 트랙 운영

| 출처 | 호출 방식 | 비고 |
|------|-----------|------|
| World Bank | 브라우저에서 직접 fetch | CORS 허용. 실시간 데이터. |
| FAO, KOSIS, IEA, WMO 등 | `python build.py` → 정적 JSON | CORS·인증 이슈 회피. cron으로 갱신. |

## 표준 스키마 핵심 필드

```json
{
  "dataset_id": "wb_NY.GDP.MKTP.CD",
  "source": "World Bank",
  "indicator_code": "NY.GDP.MKTP.CD",
  "indicator_name_ko": "국내총생산(GDP, 명목)",
  "category": "economy",
  "unit": "USD",
  "country_iso3": "KOR",
  "country_name_ko": "대한민국",
  "region": "Eastern Asia",
  "year": 2023,
  "period_type": "annual",
  "value": 1712792000000,
  "license": "CC BY 4.0",
  "fetched_at": "2026-05-08T..."
}
```

- 국가코드: **ISO 3166-1 alpha-3** 통일
- 지역: UN M49
- 시간: ISO 8601
- 통화: ISO 4217
- 결측: 모두 `null` 정규화

## 새 출처 추가하는 법

`adapters/base.py`의 `SourceAdapter`를 상속하고 세 메서드만 구현:

```python
class FaoAdapter(SourceAdapter):
    def list_indicators(self) -> list[IndicatorMeta]: ...
    def fetch(self, indicator_code, countries, year_range): ...
    def transform(self, raw, indicator) -> list[StandardRecord]: ...
```

`adapters/__init__.py`에 등록하면 `build.py`가 자동으로 호출.

## 빌드

```bash
# KOSIS 키 (선택)
export KOSIS_API_KEY="..."

# FAOSTAT 인증 (선택) — Developer Portal에서 가입 후 발급
export FAO_USERNAME="..."
export FAO_PASSWORD="..."

python build.py                       # 전체
python build.py --source worldbank    # 특정 어댑터만 (worldbank | fao | kosis)
```

결과는 `data/{dataset_id}.json` 파일들과 마스터 `data/catalog.json`, 메타정보 `data/build-info.json`.

## 데이터 갱신 (관리자)

`/admin.html` 에서 GitHub PAT으로 인증 → 출처 선택 → 갱신 버튼 한 번이면 끝.

내부 동작:
1. 관리자가 갱신 버튼 클릭
2. `POST /repos/{owner}/{repo}/dispatches` API 호출 (`event_type: build-data`)
3. `.github/workflows/build-data.yml` 워크플로우가 트리거되어 `python build.py` 실행
4. `data/*.json` 변경분 자동 커밋 → GitHub Pages 재배포
5. admin.html이 워크플로우 진행 상태를 5초마다 폴링해 표시

자동 백업: 매월 1일 03:00 KST 에 전체 빌드가 자동 실행됩니다.

### 필요한 GitHub 설정

**1. PAT 발급** — `https://github.com/settings/personal-access-tokens/new`
   - 대상 레포: GeoSource 레포만 선택
   - 권한:
     - `Contents: Read and write` (data/ 커밋용 — workflow 자체는 GITHUB_TOKEN 사용하지만, dispatch 호출에 필요)
     - `Actions: Read and write`
     - `Metadata: Read-only` (자동)

**2. 외부 API 키 등록** — 레포 Settings → Secrets and variables → Actions
   - `KOSIS_API_KEY` (KOSIS 어댑터)
   - `FAO_USERNAME`, `FAO_PASSWORD` (FAOSTAT 어댑터; Developer Portal 가입 후 발급, JWT 토큰 60분 TTL은 어댑터가 자동 처리)

**3. Workflow 권한 확인** — 레포 Settings → Actions → General → Workflow permissions
   - "Read and write permissions" 선택 (data/ 자동 커밋용)

## 프론트엔드 (index.html)

`index.html` 만 GitHub Pages에 올리면 끝. World Bank 데이터는 클라이언트가 직접 API 호출, KOSIS·기타는 같은 디렉토리의 `data/*.json` fetch.

기능:
- 카테고리/검색으로 지표 필터
- 국가 다중 선택(최대 8개) · 연도 범위 지정
- 꺾은선 / 막대 / 파이 차트 토글
- 데이터 테이블 정렬 표시
- CSV(엑셀 호환 BOM 포함) / JSON 다운로드

## 라이선스 주의사항

각 레코드에 `license` 필드를 항상 포함합니다. 프론트엔드에서 라이선스별 필터를 추가하면 IEA(유료·재배포 제한) 같은 출처를 추가하더라도 안전하게 운영할 수 있습니다.

| 출처 | 라이선스 | 재배포 |
|------|---------|--------|
| World Bank | CC BY 4.0 | 가능 (출처 표기) |
| FAO | CC BY 4.0 | 가능 |
| IMF | 항목별 상이 | 대부분 가능 |
| KOSIS | KOGL Type 1~4 | 항목별 확인 |
| 기상청 | 공공데이터포털 약관 | 가능 |
| **IEA** | **대부분 유료** | **재배포 불가** |

## 다음 단계

- [x] FAO STAT 어댑터 (JWT 인증, CC BY-NC-SA 3.0 IGO)
- [ ] IMF SDMX 어댑터 (WEO, IFS)
- [ ] 지도 시각화 (GeoStatAtlas와 연동, choropleth)
- [ ] 시계열 비교 (지표 ÷ 지표, 예: GDP/인구)
- [ ] 즐겨찾기 + 공유 URL
