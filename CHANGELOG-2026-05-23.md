# GeoSource 작업 정리 — 2026-05-23

## 요약

UN 계열 데이터 출처 3개(WPP·UNHCR·SDG)를 어댑터로 추가하고, FAO 어댑터의 bulk URL 변경에 따른 무성한 빌드 실패를 복구. 커스텀 도메인 `geosource.bgnl.kr` 연결도 완료.

| 변경 | 커밋 | 내용 |
|---|---|---|
| UN WPP 어댑터 신규 | `2192da6` | 인구·기대수명·출산율 등 10종, 2000~2100 추계·전망 |
| UNHCR + UN SDG 어댑터 신규 | `fa1eb74` | 난민 5종 + SDG 5종, 총 10종 |
| FAO bulk URL 수정 | `5d440da` | 누락 13개 지표 복구 + 닭 element 정정 |
| 도메인 연결 | (DNS) | `geosource.bgnl.kr` CNAME → Vercel |

---

## 1. UN WPP 2024 어댑터 (`adapters/un_wpp.py`)

### 경로 선택

UN DataPortal REST API(`population.un.org/dataportalapi`)의 `/data/...` 엔드포인트가 2025년경 Bearer 토큰 인증으로 전환되어 401 반환. 메타데이터(indicators/locations)는 열려있지만 실제 데이터는 막힘.

대안으로 **공개 bulk gzipped CSV**(~16MB 압축, ~40MB 원본) 채택:
```
https://population.un.org/wpp/assets/Excel%20Files/
  1_Indicator%20(Standard)/CSV_FILES/
  WPP2024_Demographic_Indicators_Medium.csv.gz
```

이 한 파일에 67개 지표 컬럼이 와이드 포맷으로 모두 들어있어, 1회 다운로드·캐시로 10개 지표 모두 추출 가능.

### 선정 지표 (10종, category=population)

| dataset_id | 컬럼 | 비고 |
|---|---|---|
| `wpp_total_population` | TPopulation1July | 천 단위 → ×1000 변환 |
| `wpp_population_density` | PopDensity | |
| `wpp_population_growth_rate` | PopGrowthRate | |
| `wpp_median_age` | MedianAgePop | **WB에 없음** |
| `wpp_sex_ratio` | PopSexRatio | **WB에 없음** |
| `wpp_life_expectancy_birth` | LEx | |
| `wpp_life_expectancy_65` | LE65 | **WB에 없음** |
| `wpp_total_fertility_rate` | TFR | |
| `wpp_crude_birth_rate` | CBR | |
| `wpp_crude_death_rate` | CDR | |

WB와 일부 중복되는 지표라도 **2100년까지 전망**이 들어있어 가치 있음.

### 결과

- 40개국 × 101년(2000~2100) = 4,040 records/지표, 총 40,400 records
- 파일당 ~3.3MB, 10개 합 ~33MB
- KOR 검증: 인구 51.86M(2020) → 45.1M(2050) → **21.8M(2100)**, TFR 0.81→1.30, 중위연령 42.8→59.8

---

## 2. UNHCR 어댑터 (`adapters/unhcr.py`)

### API

```
GET https://api.unhcr.org/population/v1/population/
  ?yearFrom=2000&yearTo=2024&coa_all=true&limit=10000
```

- 인증 불필요
- `coa_all=true` 한 번으로 모든 국가의 (refugees, asylum_seekers, idps, stateless, returned_refugees) 5개 필드를 한 응답에 받음
- `coo_id: '-'` 행이 출신국 차원 합산 결과

### 선정 지표 (5종, category=population, subcategory=displacement)

1. `unhcr_refugees_hosted` — 수용 난민 수
2. `unhcr_asylum_seekers` — 망명 신청자
3. `unhcr_idps` — 국내 실향민
4. `unhcr_stateless` — 무국적자
5. `unhcr_returned_refugees` — 본국 귀환 난민

### 결과

- 39/40개국(PRK 제외), 4,820 records
- 톱 호스트 2023: Iran 3.76M · Turkey 3.25M · Germany 2.59M
- 톱 IDP 2023: Nigeria 3.31M
- 무국적자 톱: Thailand 587k (로힝야 등)

---

## 3. UN SDG 어댑터 (`adapters/un_sdg.py`)

### API

```
GET https://unstats.un.org/SDGAPI/v1/sdg/Series/Data
  ?seriesCode=XXX&pageSize=2000&pageNumber=N
```

- 인증 불필요
- 지역 코드는 UN M49 numeric (KOR=410)
- **dimension 처리가 까다로움** — series마다 (Sex, Age, Location, Reporting Type) 조합이 다름. indicator별 `dim_filter` 명시 필요.

### 선정 지표 (5종)

| dataset_id | SDG # | dim_filter |
|---|---|---|
| `sdg_women_in_parliament` | 5.5.1 | Sex=FEMALE, Reporting Type=G |
| `sdg_homicide_rate` | 16.1.1 | Sex=BOTHSEX, Reporting Type=G |
| `sdg_rd_expenditure` | 9.5.1 | Reporting Type=G |
| `sdg_pm25_pollution` | 11.6.2 | Location=ALLAREA, Reporting Type=G |
| `sdg_mobile_ownership` | 5.b.1 | Sex=BOTHSEX, Reporting Type=G |

### M49 → ISO3 매핑

40개국 화이트리스트 전부 매핑(`M49_TO_ISO3` dict). 매핑 함수 1회 호출로 GeoArea/List에서 빌드.

### 결과

- 3,152 records (지표별 280~996)
- **KOR 데이터 누락 3건**: 여성국회의원·살인율·PM2.5. 한국의 dim 조합이 우리가 지정한 기본값과 다를 가능성. **추후 보강 필요** (issue로 남김).

---

## 4. FAO 어댑터 긴급 수정 (`adapters/fao.py`)

### 증상

사용자가 신고: 콩·감자·보리·사탕수수 외 9종이 사이트에 안 나옴.

조사 결과 — adapter INDICATORS는 21종, 실제 빌드된 데이터는 8종. 13종이 누락된 상태로 catalog에서도 사라져 있었음.

### 원인

FAO가 2026년 중반 bulk 다운로드 도메인을 변경:
- **구**: `https://bulks-faostat.fao.org/production/{domain}.zip` → 403 Forbidden
- **신**: `https://fenixservices.fao.org/faostat/static/bulkdownloads/{풀이름}.zip`

기존 8종 데이터 파일은 URL 변경 이전 캐시일 뿐. 신규 13종은 추가된 적은 있지만 URL 깨진 뒤로 한 번도 빌드된 적 없음.

### 수정

`BULK_URL_TMPL` 상수 → `BULK_BASE` + `DOMAIN_FILES` dict로 리팩터:

```python
BULK_BASE = "https://fenixservices.fao.org/faostat/static/bulkdownloads"
DOMAIN_FILES: dict[str, str] = {
    "QCL": "Production_Crops_Livestock_E_All_Data_(Normalized).zip",
    "RL":  "Inputs_LandUse_E_All_Data_(Normalized).zip",
    "FBS": "FoodBalanceSheets_E_All_Data_(Normalized).zip",
}
```

요청 헤더에 `Referer: https://www.fao.org/faostat/en/`도 추가(403 회피 용).

### 부차 수정: 닭 element 코드

`fao_QCL_1057_5111`(닭, head 단위)가 빌드 0건. 조사 결과 FAOSTAT가 닭만 유일하게 **element 5112 (`1000 An`)** 사용. 다른 가축(소·돼지·양)은 5111(head)인데 닭만 다름.

- `indicator_code`: `QCL/1057/5111` → `QCL/1057/5112`
- `dataset_id`: `fao_QCL_1057_5111` → `fao_QCL_1057_5112`
- `unit`: `마리` → `천 마리`
- `index.html` 카탈로그 항목도 동시 갱신

### 결과

20 → 21 지표, 7,447 records. 검증된 2023 톱:

| 지표 | Top 3 |
|---|---|
| 콩 | Brazil 152M t · USA 113M · China 20M |
| 감자 | China 93M · India 60M · USA 20M |
| 보리 | Russia 20.5M · France 12M · Germany 11M |
| 사탕수수 | Brazil 782M · India 490M · China 105M |
| 닭 | China 5.2B · Indonesia 3.7B · Brazil 1.5B |

---

## 5. 도메인 연결 — geosource.bgnl.kr

### 작업 흐름

1. Vercel 측에 이미 alias 등록되어 있음 확인 (`vercel inspect`)
2. 가비아 DNS 관리에서 CNAME 1줄 추가:
   - 타입: CNAME / 호스트: `geosource` / 값: `cname.vercel-dns.com.`
3. DNS 전파 후 Vercel이 Let's Encrypt 인증서 자동 발급(~수십 초 대기)

### 결과

| 항목 | 결과 |
|---|---|
| DNS | `geosource.bgnl.kr → cname.vercel-dns.com → 76.76.21.x` |
| 인증서 | Let's Encrypt R13, `CN=geosource.bgnl.kr` (5/22~8/20) |
| HTTP→HTTPS | 308 |
| 응답 | 200 OK |

접속: https://geosource.bgnl.kr

---

## 6. 남은 작업

- [ ] **UN Comtrade 어댑터** — 무료 API 키 발급이 필요. 사용자가 키 등록 후 진행 예정.
- [ ] **SDG dim_filter KOR 누락 수정** — `sdg_women_in_parliament` · `sdg_homicide_rate` · `sdg_pm25_pollution` 세 지표에서 KOR 데이터가 빠짐. 각 indicator별로 KOR이 보고하는 dim 조합을 실측해서 `dim_filter` 보강해야 함.
- [ ] **build.py 사일런트 실패 어시션** — FAO가 13종 0건이어도 빌드가 silently 성공한 이번 사례 같은 걸 막기 위해, indicator별 record_count == 0 경고/실패 옵션을 build.py에 도입할 필요.

---

## 회고

- WPP·UNHCR·SDG 모두 "한 번 fetch 후 메모리 캐시 → 여러 indicator로 분해" 패턴. 같은 패턴을 가진 어댑터가 늘면 base 헬퍼로 추출할 만함.
- FAO 사건처럼 **외부 API 호스트 변경**이 사일런트로 모든 지표를 0건으로 만들 수 있으므로, 빌드 후 record_count 0 비율이 갑자기 늘면 알람을 띄우는 게 좋음.
- SDG dim_filter는 indicator마다 실측해야 한다는 부담이 있는데, "기본값으로 가장 흔한 조합을 자동 선택" 같은 어시스트가 가능할 수도.
