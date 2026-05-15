# GeoSource 작업 정리 — 2026-05-15

## 1. UI 정돈 (`index.html`)

### 헤더 단순화
- 우상단 **위경도(LAT/LON)** + **UTC 시계** 제거 (`updateClock` 함수·`setInterval` 호출 제거)
- 좌상단 태그라인 "세계 공식 데이터 허브 · bgnl.kr" 제거
- 브라우저 탭 타이틀: `GeoSource — 세계 공식 데이터 허브` → `GeoSource`

### 폰트 통일
- **Pretendard 단일화** — `--font-mono`까지 Pretendard로 통일, JetBrains Mono CDN 링크 제거
- admin.html도 Cormorant Garamond + JetBrains Mono 제거하고 Pretendard 단일

### Footer 카피라이트
- 좌하단에 `Copyright 2026. 양정고등학교 김용현 | https://bgnl.kr` 추가 (URL 하이퍼링크, `target=_blank`)
- index.html / admin.html 양쪽 동일 적용

---

## 2. 관리자 페이지 디자인 통일 (`admin.html`)

### 팔레트·폰트 본 사이트와 일치
| 항목 | Before | After |
|---|---|---|
| 배경 | 베이지 (`#f5f1e8`) | 화이트 (`#ffffff`) |
| 잉크 | `#1c2321` | 네이비 `#0b1f3a` |
| 액센트 | terra/forest/gold | ocean `#0b3a7a` 단일 |
| h1 타이포 | Cormorant Garamond 이탤릭 | Pretendard 700, 네이비 강조 |
| 그리드 배경 opacity | 0.35 | 0.5 |

### 브랜드 마크 보강
- `.meridian` / `.meridian-2` 자손 div 추가 (메인사이트와 동일한 경위선 디자인)
- 56px 원형 + 적도·본초자오선 십자선

### 갱신 카드 누락 보충
build.py가 지원하는데 admin source-grid에 빠져있던 카드 추가:
- IMF · WEO 지표 (성장률·인플레·실업·재정·경상수지 6종)
- Our World in Data · 종교 데이터 재배포 (3종)
- Pew Research Center · Religious Composition Projections 2010~2050 (8종)

---

## 3. 출처 표시명 정리

### `SOURCE_DISPLAY` 매핑 도입
내부 `source` 키와 UI 라벨을 분리. Pew/OWID만 풀네임으로 표시, 나머지는 약어 유지.

```js
const SOURCE_DISPLAY = {
  "OWID": "Our World in Data",
};
```

적용 위치: 출처 뱃지(상단), 지표 카탈로그 항목, 데이터 뷰어 breadcrumb, footer "마지막 갱신".

### OWID 단일 출처로 통합
- `"OWID (Pew Research)"` × 2 + `"OWID (Pew/WVS)"` × 1 → **`"OWID"` 하나**
- `index.html` INDICATORS의 종교 지표 3건 + `adapters/owid.py` IndicatorMeta 3건 모두 `"OWID"`로 통일
- `SCOPE_SOURCES.world`도 단일 항목으로 정리

---

## 4. 데이터 테이블 개선

### 칸 너비 축소
- `width: 100%` → **`width: auto`** + 셀에 `white-space: nowrap`
- 패딩 정돈 (`7px 12px` → `6px 14px`)
- 양 끝 셀 좌·우 패딩 16px

### 3컬럼 그리드 분할
하단 데이터 테이블을 3등분해 좌→우 순차로 채우는 그리드 레이아웃.

| 변경 | 내용 |
|---|---|
| `.table-wrap` | `display: grid; grid-template-columns: repeat(3, 1fr)` |
| HTML | 단일 `<table id="data-table">` → JS가 3개 테이블 동적 생성 |
| JS | `renderTable()`에서 정렬된 records를 `Math.ceil(N/3)`개씩 chunk |
| sticky thead | 각 컬럼이 thead 따로 가지므로 스크롤시에도 헤더 유지 |
| 반응형 | 1100px↓ 2컬럼 / 700px↓ 1컬럼 |

같은 max-height 400px 안에 약 3배의 행이 들어가 공간 효율 개선.

---

## 5. FAO 지표 추가

### 신규 IndicatorMeta 2종 (`adapters/fao.py` + `index.html`)

| dataset_id | indicator_code | 한국어명 | 영문명 |
|---|---|---|---|
| `fao_QCL_1034_2111` | `QCL/1034/2111` | 돼지 사육두수 | Swine / pigs stocks |
| `fao_QCL_976_2111` | `QCL/976/2111` | 양 사육두수 | Sheep stocks |

기존 소(Cattle, item 866) 항목과 동일한 element code 2111(Stocks) 패턴.

### 빌드 트리거 결과
- `gh workflow run build-data.yml -f source=fao` → run #25899143459 (✓ success, 20초)
- 자동 커밋: `a61267c chore(data): refresh fao (2026-05-15)`
- 생성된 JSON 파일:
  - `data/fao_QCL_1034_2111.json` (+10,510줄)
  - `data/fao_QCL_976_2111.json` (+10,510줄)
- 기존 FAO 6종 데이터도 함께 최신화

---

## 6. 커밋 로그 요약 (이 세션)

- `refactor(ui): 헤더 단순화 + admin 디자인 통일 + 출처 표시명 정리`
- `refactor(owid): OWID 출처를 단일 'Our World in Data'로 통일`
- `style(table): 데이터 테이블 칸 너비를 내용 길이에 맞춰 축소`
- `feat(fao): 돼지·양 사육두수 지표 추가`
- `chore(data): refresh fao (2026-05-15)` (github-actions[bot])
- `style(table): 데이터 테이블을 3컬럼 그리드로 분할`

---

## 7. 데이터 카탈로그 현황 (변동)

| 출처 | 2026-05-09 | 2026-05-15 | 비고 |
|---|---|---|---|
| World Bank | 11 | 11 | 변동 없음 |
| IMF | 6 | 6 | 변동 없음 |
| FAO | 6 | **8** | 돼지·양 사육두수 추가 |
| KOSIS | 16 | 16 | 변동 없음 |
| OWID | — | 3 | (직전 세션에서 추가, 표시명만 통합) |
| Pew Research | — | 8 | (직전 세션에서 추가) |
| **합계** | **39** | **52** | |
