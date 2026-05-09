# GeoSource 작업 정리 — 2026-05-09

## 1. 인프라 / 배포

| 항목 | 결과 |
|------|------|
| GitHub 레포 | `yhk1m/geosource` (workflow 스코프 추가 후 push 성공) |
| Vercel 프로젝트 | `yonghyun-kims-projects-42a681fb/geosource` |
| 임시 URL | https://geosource-nine.vercel.app |
| 커스텀 도메인 | `geosource.bgnl.kr` (Vercel에 등록, DNS A 레코드 `76.76.21.21` 또는 CNAME `cname.vercel-dns.com` 필요) |
| GitHub Pages | 비활성화 (Vercel과 중복) |
| GitHub Actions | `Build GeoSource Data` 워크플로우 — admin.html dispatch + 매월 1일 03:00 KST cron |

### GitHub Secrets 등록
- `KOSIS_API_KEY`
- `FAO_USERNAME`, `FAO_PASSWORD`

---

## 2. 어댑터 변경

### 새 어댑터: FAO (`adapters/fao.py`)
- **인증**: JWT Bearer 토큰 (60분 TTL, 자동 갱신)
- **엔드포인트**: `https://faostatservices.fao.org/api/v1/`
- **라이선스**: CC BY-NC-SA 3.0 IGO
- **지표 6종**:
  - 밀/쌀/옥수수 생산량 (`QCL/{15,27,56}/2510`)
  - 소 사육두수 (`QCL/866/2111`)
  - 농경지 면적 (`RL/6610/5110`)
  - 식이에너지 공급 (`FBS/2901/664`)
- **이슈**: 신 API에서 element 코드가 `5xxx → 2xxx`로 재번호. `2510=Production`, `2111=Stocks`.

### KOSIS 어댑터 확장 (`adapters/kosis.py`)
- **indicator_code 형식**: `{org}/{tbl}/{itm}?objL2=...&objL3=...&prdSe=F&newEstPrdCnt=3`
  - 기본: itm + objL1=ALL, prdSe=Y
  - querystring으로 추가 차원 (objL2/objL3) 및 주기(prdSe), 최근 N기(newEstPrdCnt) 지정
  - `newEstPrdCnt` 있으면 startPrdDe/endPrdDe 제거
- **에러 응답 처리**: dict 응답(`{"err":"20",...}`)을 빈 list로 반환
- **시도 코드 정규화**: KOSIS 표마다 옛/신 코드가 섞여있어(21/26 등) `SIDO_NAME_TO_CODE` 맵으로 C1_NM 기반 통일

### 데이터 스키마 (KOSIS records)
```python
country_iso3   = "KR-{KOSIS C1 코드}"  # 2자리=시도, 5자리=시군구, 7+자리=읍면동
country_name_ko = "원본 행정구역명"      # KOSIS C1_NM 그대로
notes           = "코드:{c1}|단위:{level}|이름:{name}"
```

---

## 3. 등록된 KOSIS 지표 (15종)

### 인구
| dataset_id | 표 | 항목 | 단위 |
|---|---|---|---|
| `kosis_101_DT_1B040A3_T20` | 시도별 인구 (한국인) | T20 | 명 |
| `kosis_101_DT_1B040B3_T1` | 시도별 세대수 | T1 | 세대 |
| `kosis_101_DT_1B81A21_T1` | 시도별 합계출산율 | T1 | 명 |
| `kosis_101_DT_1B81A19_T1` | 시도별 출생성비 | T1 | 명 |
| `kosis_101_DT_1B83A03_T10` | 시도별 혼인건수 | T10 (objL2=000) | 건 |
| `kosis_101_DT_1B85003_T10` | 시도별 이혼건수 | T10 (objL2=000) | 건 |
| `kosis_101_DT_1PA2002_T10` | 시도별 거주지 이전 인구 (5년 단위) | T10 (objL2=0/objL3=000/prdSe=F) | 명 |

### 경제
| dataset_id | 표 | 항목 | 단위 |
|---|---|---|---|
| `kosis_101_DT_1C86_T1` | 시도별 1인당 GRDP | T1 | 천원 |
| `kosis_101_DT_1DA7004S_T10` | 시도별 15세이상인구 | T10 | 천명 |
| `kosis_101_DT_1DA7030S_T30` | 시도별 취업자 | T30 (objL2=0) | 천명 |
| `kosis_101_DT_1DA7088S_T40` | 시도별 실업자 | T40 (objL2=0) | 천명 |
| `kosis_101_DT_1DA7104S_T80` | 시도별 실업률 | T80 (objL2=0) | % |
| `kosis_101_DT_1DA7146S_T50` | 시도별 비경제활동인구 | T50 (objL2=00) | 천명 |
| `kosis_101_DT_1F02001_T10` | 시도별 소비자물가지수 | T10 (objL2=0) | 2020=100 |

### 농림
| dataset_id | 표 | 항목 | 단위 |
|---|---|---|---|
| `kosis_101_DT_1ES4F09S_T00` | 시도별 농어가 가구수 | T00 | 천가구 |

> 잘못된 표(`DT_1DA7001S` C1=성별)는 제거. 실업률은 `DT_1DA7104S/T80?objL2=0`로 교체.

---

## 4. 프론트엔드 (`index.html`)

### 세계 / 대한민국 탭
- 헤더에 `🌍 세계` / `🇰🇷 대한민국` 탭
- `state.scope = "world" | "korea"`
- 스코프별 `selectedCountries` 캐시(`scopeCache`) — 탭 전환 시 보존
- 세계: World Bank · IMF · FAO · WMO · IEA
- 대한민국: KOSIS

### 통계기관 클릭 필터
- 출처 뱃지 클릭 → `state.selectedSource` 토글
- 동일 클릭 시 해제
- 인디케이터 리스트가 출처 + 카테고리 + 검색어 모두 교집합으로 필터

### Entity 차원 확장 (한국 행정구역)
- `KOREA_REGIONS` (시도 17개 + 전국, KR-{2자리} 코드)
  - KR-11 서울 / 26 부산 / 27 대구 / 28 인천 / 29 광주 / 30 대전 / 31 울산
  - KR-36 세종 / 41 경기 / 43 충북 / 44 충남 / 46 전남 / 47 경북 / 48 경남
  - KR-50 제주 / 51 강원 / 52 전북
- `KOREA_DISTRICTS` (시군구·읍면동) — 지표 로드 후 records에서 동적 추출
- 검색박스 `country-search`가 스코프별 분기:
  - world → ALL_COUNTRIES (WB API)
  - korea → KOREA_REGIONS + KOREA_DISTRICTS
- 검색 결과 클릭 → 칩으로 추가, 차트 시리즈 추가

### 차트 개선
1. **막대그래프 로딩 멈춤**: `renderViewer()`가 chart-card에서 `loaded` 클래스를 제거하던 것 → `renderChart()` 끝에서 `setLoading(false)` 추가
2. **파이 연도 선택**: `state.pieYear` + chart-types 옆 연도 드롭다운, 선택 연도 데이터 없으면 최신 폴백
3. **지수(=100) 기준 연도**: `state.indexBaseYear` + 연산 옆 드롭다운, compute() unary index에서 사용

---

## 5. 알려진 한계 / 향후 작업

- **읍면동 데이터**: 현재 등록된 KOSIS 표는 시도 + 시군구까지만 노출. 읍면동까지 가진 표를 별도로 등록해야 함
- **WMO / IEA**: README에 카드 있지만 어댑터 미구현 (WMO는 통합 API 없음, IEA는 대부분 유료)
- **IMF**: client-side 직접 fetch로 6종 등록됨 (별도 어댑터 불필요)
- **자동 발견 (KOSIS 시도/시군구별 모든 표)**: KOSIS 트리에 ~3000 leaf 표 존재. C1_OBJ_NM='시도별' 필터로 ~58개 후보까지 좁혀지지만 항목명·단위가 표마다 달라 자동 라벨링은 한계. 사용자가 OpenAPI URL을 보내주는 방식이 가장 정확

---

## 6. KOSIS 표 추가 방법

### 사용자 → AI에게 보내는 방법
KOSIS 통계표 페이지에서 **OpenAPI** 버튼 → 항목·분류·시점 선택 → "URL 생성" 클릭 → 생성된 URL을 그대로 메시지로 전달

```
https://kosis.kr/openapi/Param/statisticsParameterData.do?
method=getList&apiKey=인증키없음&itmId=T10+&objL1=ALL&objL2=ALL&
prdSe=Y&startPrdDe=2000&endPrdDe=2024&format=json&jsonVD=Y&
orgId=101&tblId=DT_1B040A3
```

### AI 처리 흐름
1. 우리 `KOSIS_API_KEY`로 apiKey 교체해서 1년치 검증 호출
2. C1_OBJ_NM에 "시도" 포함 여부 확인
3. C2/C3 dimension 있으면 "계" 코드(0/00/000) 자동 탐지
4. ITM_ID 후보 중 의미있는 것 선택 (또는 사용자 지정)
5. `IndicatorMeta` (kosis.py) + `INDICATORS` (index.html) 양쪽에 등록
6. workflow_dispatch로 데이터 빌드 → Vercel 자동 재배포

---

## 7. 커밋 로그 요약 (이 세션)

- `feat(adapters): FAO STAT 어댑터 추가 (JWT 인증)`
- `fix(adapters): FAOSTAT 신 API element 코드 + KOSIS 필수 파라미터`
- `feat(frontend): INDICATORS에 FAO 6종 + KOSIS 1종 등록`
- `feat(kosis): 합계출산율, 세대수 지표 추가`
- `feat(frontend): 세계/대한민국 탭 분리 + 통계기관 클릭 필터`
- `fix(chart): 막대 로딩 멈춤 + 파이/지수 연도 선택기`
- `feat(kosis): 경제활동인구·실업률·고용률·1인당 GRDP 추가`
- `fix(kosis): 시도별 실업률 정상화 + 잘못된 표 제거`
- `feat(kosis): 인구동향·노동·물가·농림 9종 시도 통계 추가`
- `feat(kosis): 시군구·읍면동 단위 지원 (entity 차원 확장)`
- `fix(frontend): KOREA_REGIONS 코드를 KOSIS 실제 행정구역코드로 정정`
- `feat(kosis): 거주지 이전 인구 (DT_1PA2002) + 시도코드 이름기반 정규화`

---

## 8. 데이터 카탈로그 현황

| 출처 | 지표 수 | 호출 방식 |
|------|--------|-----------|
| World Bank | 11 | 브라우저 직접 fetch (CORS, 실시간) |
| IMF | 6 | 브라우저 직접 fetch (DataMapper API) |
| FAO | 6 | GitHub Actions에서 빌드 → 정적 JSON |
| KOSIS | 15 | GitHub Actions에서 빌드 → 정적 JSON |
| **합계** | **38** | |

데이터 갱신:
- World Bank/IMF: 매번 최신
- FAO/KOSIS: admin.html에서 dispatch 또는 매월 1일 03:00 KST cron
