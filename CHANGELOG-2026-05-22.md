# GeoSource 작업 정리 — 2026-05-22

## 요약

WHO 어댑터 진단 결과, 알코올·비만·흡연·자살률 4개 지표가 모두 0건이었던 원인은 ISO3 매핑 문제가 아니라 **Dim1 성별 필터의 키 불일치**였다. WHO GHO API가 `SEX_BTSX`(접두 포함)를 반환하는데 어댑터는 `BTSX`만 허용하고 있었다. 필터를 고치고 자살률 지표는 콘텐츠 톤상 제거.

추가로 미커밋 상태였던 KOSIS 전국사업체조사 지표 4종을 별도 커밋으로 분리해 함께 푸시.

---

## 1. 진단 단계

### 처음 가정 — "알코올 데이터의 SpatialDim 코드 체계가 달라서 매칭이 안 된다"

`diagnose_who.py` 1차 출력:

| Indicator | Rows | Dim1 | SpatialDimType |
|---|---|---|---|
| `SA_0000001688` (알코올) | 5,405 | SEX_BTSX만 | COUNTRY/GLOBAL/REGION/UNREGION |
| `MH_12` (자살률) | 12,936 | BTSX/FMLE/MLE | COUNTRY/GLOBAL/REGION/WORLDBANKINCOMEGROUP |
| `NCD_BMI_30A` (비만) | 20,790 | BTSX/FMLE/MLE | COUNTRY/GLOBAL/REGION/WORLDBANKINCOMEGROUP |
| `M_Est_smk_curr_std` (흡연) | 5,511 | BTSX/FMLE/MLE | COUNTRY만 |

샘플 SpatialDim에 `['11', '13', '14', '142', '143']` 같은 숫자 코드가 보여 처음엔 M49 numeric → ISO3 매핑이 필요하다고 판단.

### 재진단 — 실제 COUNTRY 행은 이미 ISO3였다

```
SpatialDimType counts: Counter({'COUNTRY': 4324, 'UNREGION': 920, 'REGION': 138, 'GLOBAL': 23})
ISO3-like count: 4324, Numeric count: 0
Sample COUNTRY SpatialDim: ['KOR', 'UZB', 'HND', 'RUS', 'HTI', ...]
```

알코올의 COUNTRY 행 4,324건 전부가 ISO3 코드. 숫자 코드 `'11', '13', '142'` 등은 UNREGION/REGION 행에서만 사용되고 있어 기존 `iso3 not in COUNTRY_NAMES` 필터로 이미 걸러지고 있었다.

### 진짜 원인

```python
Dim1 values in COUNTRY: Counter({'SEX_BTSX': 4324})
```

어댑터 코드:
```python
sex = row.get("Dim1")
if sex and sex not in ("BTSX",):   # ← 'SEX_BTSX'를 거부
    continue
```

WHO GHO가 `SEX_BTSX`(접두 `SEX_` 포함)를 반환하는데 필터는 `BTSX`만 허용 → 알코올의 COUNTRY 행 전체가 누락. 같은 버그가 자살률(MH_12), 비만(NCD_BMI_30A), 흡연(M_Est_smk_curr_std)에도 영향. SEX 차원이 없는 의사 밀도·병상 수만 정상 작동.

---

## 2. 수정

### `adapters/who.py`

**Dim1 필터 수정** — `SEX_BTSX`도 허용:

```python
# 성별 차원(Dim1)이 있으면 양성 합계만 사용
# WHO GHO는 'SEX_BTSX'(접두 포함) 또는 'BTSX' 둘 다 반환할 수 있음.
sex = row.get("Dim1")
if sex and sex not in ("BTSX", "SEX_BTSX"):
    continue
```

**자살률 indicator 제거** — `IndicatorMeta(dataset_id="who_suicide_rate", ...)` 블록 삭제.

### `index.html`

`who_suicide_rate` 카드 정의(L1512–1516) 삭제.

### 파일 정리

- `data/who_suicide_rate.json` 삭제
- `python build.py --source who` 재실행 → catalog.json·build-info.json 자동 갱신, WHO 5개 지표 JSON 재생성

---

## 3. 결과

| 지표 | Before | After |
|---|---|---|
| 알코올 (`who_alcohol_consumption`) | 0 records | **897 records** (예: IND 2019 = 4.66 L) |
| 비만 (`who_obesity_adults`) | 0 records | **1,320 records** |
| 흡연 (`who_tobacco_use`) | 0 records | **440 records** |
| 의사 밀도 (`who_physicians_density`) | 1,026 records | 1,026 records (영향 없음) |
| 병상 수 (`who_hospital_beds`) | 797 records | 797 records (영향 없음) |
| 자살률 (`who_suicide_rate`) | 0 records | **제거** |

WHO 총 레코드: 1,823 → **4,480**

---

## 4. 커밋·푸시

미커밋 상태였던 `adapters/kosis.py` 변경(시도별 사업체/종사자/제조업 지표 4종 추가)을 발견. 별도 커밋으로 분리.

`diagnose_who.py`는 1회성 진단 도구라 삭제.

```
d547369 feat(kosis): 전국사업체조사·광공업 시도별 지표 4종 추가
031f8e9 fix(who): Dim1 SEX_BTSX 매칭 + 자살률 지표 제거
c7c4968 fix(fao): FAO 데이터 파일을 신 element 코드(5510/5111)로 재명명  (이전 작업)
```

`origin/main`에 푸시 완료 (`c7c4968..d547369`).

---

## 회고 — 다음 작업 때 빠르게 잡으려면

- WHO GHO의 차원 키는 prefix 포함/미포함 둘 다 나올 수 있다는 걸 어댑터 주석에 명시해두는 게 안전.
- 새 WHO 지표를 추가할 때 build 후 `record_count == 0`이면 **즉시 진단**할 것 (다른 지표가 멀쩡해도 SEX 차원 유무로 갈림).
- `build.py`에 "record_count가 0인데 raw가 0이 아니면 경고" 같은 빌드 어시션을 넣으면 같은 부류의 사일런트 실패를 막을 수 있음. (TODO)
