# © 2026 김용현
"""
WMO World Weather Information Service (WWIS) 어댑터.

기후 normal(평년값) 데이터:
- 출처: WWIS (worldweather.wmo.int) — WMO 공식 회원국 기상청 데이터 통합
- 데이터 단위: 도시(station)별 × 월(1~12)별 단일 normal
- 갱신 주기: 10년 1회 (현재 1991-2020 기준이 표준이나 도시마다 보고 기간 상이)
- 라이선스: 회원국 기상청 (출처 표기 시 공익 사용 가능)

기존 StandardRecord(country × year × value) 구조와 호환 불가 →
단일 출력 파일 `data/wmo_climate_normal.json`에 자체 스키마로 저장:
    {
      "indicator": { dataset_id, source, custom_view, period, ... },
      "cities": [
        { id, name_en, country, country_iso3, lat, lon, period,
          months: [{m, tmean, tmax, tmin, rain, raindays}, ...12개] },
        ...
      ]
    }
프론트엔드는 이 파일을 직접 fetch하여 별도 뷰(renderClimateViewer)에서 처리.
"""
from __future__ import annotations
import concurrent.futures
import csv
import io
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapters.worldbank import COUNTRY_NAMES

CITY_LIST_URL = "https://worldweather.wmo.int/en/json/full_city_list.txt"
CITY_JSON_URL = "https://worldweather.wmo.int/en/json/{city_id}_en.json"

DATASET_ID = "wmo_climate_normal"
PERIOD_LABEL = "1991-2020 (표준)"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GeoSource/1.0)",
    "Accept": "application/json,text/plain,*/*",
}

# WMO가 사용하는 국가명 → ISO3 매핑 보조 테이블
# COUNTRY_NAMES는 ISO3 → (ko, en, region) 매핑이므로 역매핑이 필요.
# WWIS의 country 표기와 World Bank 표기가 다른 경우 별칭 추가.
COUNTRY_ALIAS = {
    "Republic of Korea": "KOR",
    "Korea (Republic of)": "KOR",
    "Korea, Republic of": "KOR",
    "Korea, Rep.": "KOR",
    "Democratic People's Republic of Korea": "PRK",
    "Russian Federation": "RUS",
    "United States of America": "USA",
    "United States": "USA",
    "United Kingdom of Great Britain and Northern Ireland": "GBR",
    "United Kingdom": "GBR",
    "United Arab Emirates": "ARE",
    "Iran (Islamic Republic of)": "IRN",
    "Iran, Islamic Rep.": "IRN",
    "Viet Nam": "VNM",
    "Vietnam": "VNM",
    "Lao People's Democratic Republic": "LAO",
    "Syrian Arab Republic": "SYR",
    "Brunei Darussalam": "BRN",
    "Bolivia (Plurinational State of)": "BOL",
    "Venezuela (Bolivarian Republic of)": "VEN",
    "Tanzania, United Republic of": "TZA",
    "Czechia": "CZE",
    "Czech Republic": "CZE",
    "Türkiye": "TUR",
    "Turkiye": "TUR",
    "Turkey": "TUR",
    "Cabo Verde": "CPV",
    "Eswatini": "SWZ",
    "Côte d'Ivoire": "CIV",
    "North Macedonia": "MKD",
    "Macedonia, North": "MKD",
    "Republic of Moldova": "MDA",
    "Moldova, Republic of": "MDA",
    "Republic of North Macedonia": "MKD",
    "Hong Kong, China": "HKG",
    "Macao, China": "MAC",
    "China, Hong Kong SAR": "HKG",
    "China, Macao SAR": "MAC",
}

# 주요 도시 한국어명 (WWIS 영문 cityName → 한국어).
# 한국 7개 + 세계 약 130개 도시. 매핑 안 된 도시는 영문명 그대로 사용
# (검색은 영문/한글/국가명 모두 매칭).
KO_CITY_NAMES = {
    # 한국
    "Seoul": "서울", "Busan": "부산", "Daegu": "대구", "Incheon": "인천",
    "Gwangju": "광주", "Daejeon": "대전", "Ulsan": "울산",
    "Jeju": "제주", "Gangneung": "강릉",
    # 동아시아
    "Tokyo": "도쿄", "Osaka": "오사카", "Kyoto": "교토", "Sapporo": "삿포로",
    "Fukuoka": "후쿠오카", "Naha": "나하", "Nagoya": "나고야", "Yokohama": "요코하마",
    "Hiroshima": "히로시마", "Sendai": "센다이",
    "Beijing": "베이징", "Shanghai": "상하이", "Guangzhou": "광저우",
    "Shenzhen": "선전", "Chongqing": "충칭", "Chengdu": "청두",
    "Xi'an": "시안", "Wuhan": "우한", "Hangzhou": "항저우", "Tianjin": "톈진",
    "Nanjing": "난징", "Qingdao": "칭다오", "Dalian": "다롄", "Harbin": "하얼빈",
    "Kunming": "쿤밍", "Lhasa": "라싸", "Urumqi": "우루무치",
    "Hong Kong": "홍콩", "Macau": "마카오", "Taipei": "타이베이",
    "Kaohsiung": "가오슝", "Pyongyang": "평양", "Ulaanbaatar": "울란바토르",
    # 동남아
    "Bangkok": "방콕", "Chiang Mai": "치앙마이", "Phuket": "푸껫",
    "Hanoi": "하노이", "Ho Chi Minh City": "호치민", "Da Nang": "다낭",
    "Manila": "마닐라", "Cebu": "세부", "Jakarta": "자카르타", "Bali": "발리",
    "Denpasar": "덴파사르", "Singapore": "싱가포르",
    "Kuala Lumpur": "쿠알라룸푸르", "Phnom Penh": "프놈펜",
    "Siem Reap": "씨엠립", "Vientiane": "비엔티안", "Yangon": "양곤",
    "Bandar Seri Begawan": "반다르스리브가완",
    # 남아시아
    "New Delhi": "뉴델리", "Mumbai": "뭄바이", "Kolkata": "콜카타",
    "Chennai": "첸나이", "Bangalore": "벵갈루루", "Bengaluru": "벵갈루루",
    "Hyderabad": "하이데라바드", "Ahmedabad": "아흐메다바드",
    "Karachi": "카라치", "Lahore": "라호르", "Islamabad": "이슬라마바드",
    "Dhaka": "다카", "Kathmandu": "카트만두", "Colombo": "콜롬보",
    "Male": "말레", "Thimphu": "팀푸",
    # 중동
    "Dubai": "두바이", "Abu Dhabi": "아부다비", "Doha": "도하",
    "Riyadh": "리야드", "Jeddah": "제다", "Mecca": "메카", "Medina": "메디나",
    "Kuwait City": "쿠웨이트시티", "Manama": "마나마", "Muscat": "무스카트",
    "Sanaa": "사나", "Tehran": "테헤란", "Baghdad": "바그다드",
    "Jerusalem": "예루살렘", "Tel Aviv": "텔아비브", "Amman": "암만",
    "Beirut": "베이루트", "Damascus": "다마스쿠스",
    "Istanbul": "이스탄불", "Ankara": "앙카라", "Izmir": "이즈미르",
    "Antalya": "안탈리아",
    # 서·중유럽
    "London": "런던", "Manchester": "맨체스터", "Liverpool": "리버풀",
    "Edinburgh": "에든버러", "Glasgow": "글래스고", "Dublin": "더블린",
    "Paris": "파리", "Marseille": "마르세유", "Lyon": "리옹", "Nice": "니스",
    "Toulouse": "툴루즈", "Berlin": "베를린", "Hamburg": "함부르크",
    "Munich": "뮌헨", "Frankfurt": "프랑크푸르트", "Cologne": "쾰른",
    "Stuttgart": "슈투트가르트", "Düsseldorf": "뒤셀도르프",
    "Amsterdam": "암스테르담", "Rotterdam": "로테르담", "The Hague": "헤이그",
    "Brussels": "브뤼셀", "Antwerp": "안트베르펜", "Luxembourg": "룩셈부르크",
    "Vienna": "빈", "Zurich": "취리히", "Geneva": "제네바", "Bern": "베른",
    "Basel": "바젤",
    # 남유럽
    "Rome": "로마", "Milan": "밀라노", "Venice": "베니스", "Florence": "피렌체",
    "Naples": "나폴리", "Turin": "토리노", "Palermo": "팔레르모",
    "Madrid": "마드리드", "Barcelona": "바르셀로나", "Seville": "세비야",
    "Valencia": "발렌시아", "Bilbao": "빌바오", "Granada": "그라나다",
    "Lisbon": "리스본", "Porto": "포르투",
    "Athens": "아테네", "Thessaloniki": "테살로니키",
    # 북유럽
    "Stockholm": "스톡홀름", "Gothenburg": "예테보리", "Malmö": "말뫼",
    "Oslo": "오슬로", "Bergen": "베르겐",
    "Copenhagen": "코펜하겐", "Helsinki": "헬싱키", "Reykjavik": "레이캬비크",
    # 동유럽
    "Moscow": "모스크바", "St Petersburg": "상트페테르부르크",
    "Saint Petersburg": "상트페테르부르크", "Novosibirsk": "노보시비르스크",
    "Vladivostok": "블라디보스토크", "Yekaterinburg": "예카테린부르크",
    "Kazan": "카잔", "Sochi": "소치",
    "Kyiv": "키이우", "Kiev": "키이우", "Lviv": "리비우",
    "Warsaw": "바르샤바", "Krakow": "크라쿠프", "Gdansk": "그단스크",
    "Prague": "프라하", "Brno": "브르노",
    "Budapest": "부다페스트", "Bucharest": "부쿠레슈티",
    "Sofia": "소피아", "Belgrade": "베오그라드", "Zagreb": "자그레브",
    "Ljubljana": "류블랴나", "Bratislava": "브라티슬라바",
    "Sarajevo": "사라예보", "Skopje": "스코페", "Tirana": "티라나",
    "Vilnius": "빌뉴스", "Riga": "리가", "Tallinn": "탈린", "Minsk": "민스크",
    # 북미 - 미국
    "New York": "뉴욕", "Los Angeles": "로스앤젤레스",
    "San Francisco": "샌프란시스코", "Chicago": "시카고", "Boston": "보스턴",
    "Washington": "워싱턴", "Washington, D.C.": "워싱턴", "Seattle": "시애틀",
    "Las Vegas": "라스베이거스", "Miami": "마이애미", "Houston": "휴스턴",
    "Dallas": "댈러스", "Atlanta": "애틀랜타", "Philadelphia": "필라델피아",
    "Honolulu": "호놀룰루", "Anchorage": "앵커리지", "Denver": "덴버",
    "Phoenix": "피닉스", "San Diego": "샌디에이고", "Portland": "포틀랜드",
    "Detroit": "디트로이트", "Minneapolis": "미니애폴리스",
    "New Orleans": "뉴올리언스", "Salt Lake City": "솔트레이크시티",
    # 캐나다
    "Toronto": "토론토", "Vancouver": "밴쿠버", "Montreal": "몬트리올",
    "Ottawa": "오타와", "Calgary": "캘거리", "Edmonton": "에드먼턴",
    "Quebec": "퀘벡",
    # 멕시코·중미·카리브
    "Mexico City": "멕시코시티", "Cancun": "칸쿤", "Guadalajara": "과달라하라",
    "Monterrey": "몬테레이", "Havana": "아바나", "San Juan": "산후안",
    "Santo Domingo": "산토도밍고", "Kingston": "킹스턴",
    "San José": "산호세", "Panama City": "파나마시티",
    "Guatemala City": "과테말라시티", "San Salvador": "산살바도르",
    "Tegucigalpa": "테구시갈파", "Managua": "마나과",
    # 남미
    "Bogotá": "보고타", "Bogota": "보고타", "Medellin": "메데인",
    "Cartagena": "카르타헤나", "Lima": "리마", "Cusco": "쿠스코",
    "Santiago": "산티아고", "Valparaiso": "발파라이소",
    "Buenos Aires": "부에노스아이레스", "Cordoba": "코르도바",
    "Rio de Janeiro": "리우데자네이루", "São Paulo": "상파울루",
    "Sao Paulo": "상파울루", "Brasilia": "브라질리아", "Salvador": "살바도르",
    "Caracas": "카라카스", "Quito": "키토", "Guayaquil": "과야킬",
    "La Paz": "라파스", "Asunción": "아순시온", "Asuncion": "아순시온",
    "Montevideo": "몬테비데오",
    # 오세아니아
    "Sydney": "시드니", "Melbourne": "멜버른", "Brisbane": "브리즈번",
    "Perth": "퍼스", "Adelaide": "애들레이드", "Canberra": "캔버라",
    "Darwin": "다윈", "Hobart": "호바트", "Cairns": "케언스",
    "Gold Coast": "골드코스트", "Auckland": "오클랜드",
    "Wellington": "웰링턴", "Christchurch": "크라이스트처치",
    "Suva": "수바", "Port Moresby": "포트모르즈비",
    # 아프리카
    "Cairo": "카이로", "Alexandria": "알렉산드리아", "Johannesburg": "요하네스버그",
    "Cape Town": "케이프타운", "Durban": "더반", "Pretoria": "프리토리아",
    "Nairobi": "나이로비", "Mombasa": "몸바사", "Lagos": "라고스",
    "Abuja": "아부자", "Casablanca": "카사블랑카", "Rabat": "라바트",
    "Marrakech": "마라케시", "Addis Ababa": "아디스아바바",
    "Algiers": "알제", "Accra": "아크라", "Dakar": "다카르",
    "Tunis": "튀니스", "Tripoli": "트리폴리", "Khartoum": "하르툼",
    "Dar es Salaam": "다르에스살람", "Kampala": "캄팔라", "Kigali": "키갈리",
    "Luanda": "루안다", "Maputo": "마푸투", "Harare": "하라레",
    "Windhoek": "빈트후크", "Antananarivo": "안타나나리보",
}

# 국가명 한국어 보강 (COUNTRY_NAMES에 누락된 경우 대비)
KO_COUNTRY_FALLBACK = {
    "KOR": "대한민국", "USA": "미국", "JPN": "일본", "CHN": "중국",
    "GBR": "영국", "FRA": "프랑스", "DEU": "독일",
}


def _country_to_iso3(name: str) -> Optional[str]:
    """WWIS 국가명 → ISO3 변환. 직접 매칭 → alias → COUNTRY_NAMES 역검색."""
    if not name:
        return None
    name = name.strip()
    if name in COUNTRY_ALIAS:
        return COUNTRY_ALIAS[name]
    for iso, (ko, en, _region) in COUNTRY_NAMES.items():
        if en == name or ko == name:
            return iso
    return None


def _country_ko(iso3: Optional[str], fallback_en: str) -> str:
    if not iso3:
        return fallback_en
    info = COUNTRY_NAMES.get(iso3)
    if info and info[0]:
        return info[0]
    return KO_COUNTRY_FALLBACK.get(iso3, fallback_en)


def _to_float(v) -> Optional[float]:
    if v is None or v == "" or v == "N/A":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_city_list() -> list[tuple[str, str, str]]:
    """full_city_list.txt → [(country, city, city_id), ...]"""
    req = urllib.request.Request(CITY_LIST_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8")
    reader = csv.reader(io.StringIO(text), delimiter=";", quotechar='"')
    rows = [tuple(r) for r in reader if len(r) == 3]
    # 헤더 제거
    if rows and rows[0][0].lower() == "country":
        rows = rows[1:]
    return rows


def fetch_city(city_id: str) -> Optional[dict]:
    """단일 도시 JSON. 실패 시 None."""
    url = CITY_JSON_URL.format(city_id=city_id)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            TimeoutError, ConnectionError):
        return None


def transform_city(raw: dict) -> Optional[dict]:
    """WWIS city JSON → 우리 스키마. climate 데이터 없으면 None."""
    city = raw.get("city") if isinstance(raw, dict) else None
    if not city:
        return None
    climate = city.get("climate") or {}
    months_raw = climate.get("climateMonth") or []
    if not months_raw:
        return None

    member = city.get("member") or {}
    country_en = (member.get("memName") if isinstance(member, dict) else "") or ""
    iso3 = _country_to_iso3(country_en)
    name_en = (city.get("cityName") or "").strip()
    name_ko = KO_CITY_NAMES.get(name_en, name_en)

    months = []
    has_any = False
    for m in months_raw:
        if not isinstance(m, dict):
            continue
        try:
            month_num = int(m.get("month"))
        except (TypeError, ValueError):
            continue
        tmax = _to_float(m.get("maxTemp"))
        tmin = _to_float(m.get("minTemp"))
        tmean = _to_float(m.get("meanTemp"))
        if tmean is None and tmax is not None and tmin is not None:
            tmean = round((tmax + tmin) / 2, 1)
        rain = _to_float(m.get("rainfall"))
        raindays = _to_float(m.get("raindays"))
        if tmean is not None or rain is not None:
            has_any = True
        months.append({
            "m": month_num,
            "tmean": tmean,
            "tmax": tmax,
            "tmin": tmin,
            "rain": rain,
            "raindays": raindays,
        })
    if not has_any:
        return None
    months.sort(key=lambda x: x["m"])

    return {
        "id": str(city.get("cityId") or ""),
        "name_en": name_en,
        "name_ko": name_ko,
        "country_en": country_en,
        "country_ko": _country_ko(iso3, country_en),
        "country_iso3": iso3 or "",
        "lat": _to_float(city.get("cityLatitude")),
        "lon": _to_float(city.get("cityLongitude")),
        "period_begin": _to_float(climate.get("datab")),
        "period_end": _to_float(climate.get("datae")),
        "months": months,
    }


def build_all(max_workers: int = 10) -> dict:
    """모든 도시 fetch + transform → 최종 번들 dict (저장 대상)."""
    print(f"[wmo] city list 다운로드 중…")
    rows = load_city_list()
    print(f"[wmo] {len(rows)}개 도시 발견. fetch 시작 (병렬 {max_workers})…")

    cities: list[dict] = []
    failed = 0
    empty = 0
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_city, cid): (country, city, cid)
                   for country, city, cid in rows}
        for fut in concurrent.futures.as_completed(futures):
            country, city, cid = futures[fut]
            done += 1
            if done % 200 == 0:
                print(f"  [{done}/{len(rows)}] cities={len(cities)} "
                      f"failed={failed} empty={empty}")
            raw = fut.result()
            if raw is None:
                failed += 1
                continue
            parsed = transform_city(raw)
            if parsed is None:
                empty += 1
                continue
            cities.append(parsed)

    cities.sort(key=lambda c: (c["country_en"] or "", c["name_en"] or ""))

    print(f"[wmo] 완료: {len(cities)} cities, fetch_fail={failed}, "
          f"no_climate={empty}")

    return {
        "indicator": {
            "dataset_id": DATASET_ID,
            "source": "WMO",
            "indicator_code": "climate_normal",
            "name_ko": "월별 기후 평년값 (WMO)",
            "name_en": "Monthly climate normals (WMO/WWIS)",
            "category": "climate",
            "subcategory": "normals",
            "unit": "°C / mm",
            "description_ko": "WMO 회원국 기상청이 제공하는 도시별 월별 평년값 "
                              "(기온·강수). 1991~2020 기준이 표준이나 도시별 "
                              "보고 기간 상이. WWIS 종합.",
            "license": "WMO/회원국 기상청 (출처 표기 공익)",
            "update_frequency": "decadal",
            "coverage_years": [1991, 2020],
            "custom_view": "climate_city",
            "period_label": PERIOD_LABEL,
            "data_file": f"data/{DATASET_ID}.json",
            "city_count": len(cities),
        },
        "cities": cities,
        "built_at": datetime.utcnow().isoformat() + "Z",
        "source_urls": {
            "city_list": CITY_LIST_URL,
            "city_json_template": CITY_JSON_URL,
        },
    }
