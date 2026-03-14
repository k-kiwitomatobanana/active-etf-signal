# Active ETF Analysis System - 완전 분석 보고서

> 분석 일시: 2026-02-28
> 대상: 전체 코드베이스 (Python 백엔드 + HTML/JS 프론트엔드 + SQLite DB)
> 총 코드 라인: ~2,600줄 (Python ~1,450줄, HTML/JS ~1,160줄, CSS ~120줄)

---

## 1. 시스템 개요

한국 시장의 **액티브 ETF 25개**를 대상으로, 네이버 증권에서 구성종목 데이터를 **매일 자동 크롤링**하고, 매수/매도 시그널을 **6가지 알고리즘**으로 분석하여, **웹 대시보드**로 시각화하는 시스템이다.

### 핵심 아이디어

액티브 ETF는 패시브 ETF와 달리 펀드매니저가 구성종목과 비중을 **능동적으로 조절**한다. 이 시스템은 "프로 투자자(펀드매니저)들이 어떤 종목을 사고 파는지"를 추적하여, 개인 투자자에게 **투자 시그널**을 제공하는 것이 목적이다.

### 기술 스택

| 레이어 | 기술 | 버전 | 역할 |
|--------|------|------|------|
| 런타임 | Python | 3.10+ | 전체 백엔드 |
| 웹 프레임워크 | Flask | 3.0+ | HTTP 서버, API, 템플릿 렌더링 |
| 데이터베이스 | SQLite | 내장 | WAL 모드, 파일 기반 DB |
| 크롤링 | requests + BeautifulSoup4 + lxml | 2.31+ / 4.12+ / 5.0+ | HTTP GET + HTML 파싱 |
| 스케줄러 | APScheduler | 3.10+ | 백그라운드 cron 작업 |
| 프론트엔드 | Bootstrap 5.3 + Chart.js 4.4.7 | CDN | 반응형 UI + 차트 |
| 템플릿 엔진 | Jinja2 | Flask 내장 | 서버사이드 HTML 생성 |

---

## 2. 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│                         사용자 (웹 브라우저)                          │
│   index.html (대시보드) │ signals.html (시그널) │ chart.html (차트)    │
│   Bootstrap 5.3 + JavaScript fetch API + Chart.js 4.4.7            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTP (JSON API)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          app.py (Flask)                             │
│                                                                     │
│   [페이지 3개]           [데이터 API 12개]        [관리 API 2개]      │
│   GET /                  GET /api/top-buy          POST /api/collect │
│   GET /signals           GET /api/top-sell          GET /api/status  │
│   GET /chart             GET /api/overlap                           │
│                          GET /api/weight-increase                   │
│   [스케줄러]             GET /api/weight-decrease                   │
│   APScheduler            GET /api/stock-overview                    │
│   cron 월-금 20:00       GET /api/stock-weight-history              │
│                          GET /api/holdings                          │
│   [동시성 제어]          GET /api/holdings-by-sector                │
│   threading.Lock         GET /api/stocks                            │
│   _collect_running       GET /api/dates                             │
│                          GET /api/last-update                       │
└──────────┬──────────────────────────┬───────────────────────────────┘
           │                          │
           ▼                          ▼
┌──────────────────────┐   ┌──────────────────────────────────────────┐
│  crawler/naver_etf.py │   │           analyzer/signal.py              │
│                       │   │                                          │
│  fetch_holdings()     │   │  get_top_buy_increase()     매수 증가    │
│  _parse_holdings_html │   │  get_top_sell_increase()    매도 청산    │
│  is_data_changed()    │   │  get_overlapping_stocks()   중복 매수    │
│  save_holdings()      │   │  get_weight_increase_signals() 비중 증가 │
│  collect_single_etf() │   │  get_weight_decrease_signals() 비중 감소 │
│  collect_all_etf_data │   │  get_stock_overview()       종목 요약    │
│                       │   │  get_stock_weight_history() 시계열 이력  │
│  [외부 의존]          │   │  get_etf_holdings()         ETF 보유종목 │
│  네이버 증권 HTTP     │   │  get_unique_stock_names()   종목명 목록  │
│  1.5~2.2초 간격       │   │  get_last_update_info()     최종 업데이트│
└──────────┬───────────┘   └──────────────────┬───────────────────────┘
           │ INSERT/REPLACE                    │ SELECT (읽기 전용)
           ▼                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       db/active_etf.db (SQLite)                     │
│                                                                     │
│  etf_master (25행)                                                  │
│  ├── etf_code TEXT PK    ('494220')                                 │
│  └── etf_name TEXT       ('UNICORN SK하이닉스밸류체인액티브')          │
│                                                                     │
│  etf_holdings (누적, ~500행/일)                                      │
│  ├── etf_code TEXT       FK → etf_master                            │
│  ├── collect_date DATE   ('2026-02-27')                             │
│  ├── stock_name TEXT     ('삼성전자')                                 │
│  ├── stock_count INT     (보유주식수)                                 │
│  ├── weight REAL         (비중 %)                                    │
│  ├── stock_price INT     (현재가, 나중 추가 컬럼)                     │
│  └── UNIQUE(etf_code, collect_date, stock_name)                     │
│                                                                     │
│  인덱스 3개:                                                         │
│  ├── idx_holdings_date (collect_date)                               │
│  ├── idx_holdings_etf_date (etf_code, collect_date)                 │
│  └── idx_holdings_stock (stock_name, collect_date)                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 프로젝트 파일 구조

```
active-etf-analisys/
├── app.py                  (255줄)  Flask 메인앱, 라우팅, 스케줄러, 수집 관리
├── config.py               (97줄)   ETF 목록, DB 경로, 상수
├── requirements.txt        (5줄)    Python 패키지 의존성
├── .gitignore              (6줄)    venv, __pycache__, db, .env 제외
│
├── crawler/
│   ├── __init__.py         (빈 파일) 패키지 선언
│   └── naver_etf.py        (328줄)  네이버 증권 크롤러 + DB 초기화
│
├── analyzer/
│   ├── __init__.py         (빈 파일) 패키지 선언
│   └── signal.py           (771줄)  시그널 분석 엔진 (6종 + 보조 5종)
│
├── templates/
│   ├── base.html           (137줄)  공통 레이아웃 (네비, 푸터, 테마, 수집)
│   ├── index.html          (303줄)  대시보드 (매수/매도 Top + 섹터별 보유)
│   ├── signals.html        (216줄)  시그널 (중복/비중증가/비중감소)
│   └── chart.html          (507줄)  차트 (종목 드릴다운 + 수평 바 차트)
│
├── static/css/
│   └── custom.css          (117줄)  커스텀 스타일
│
├── db/
│   └── active_etf.db       (SQLite) .gitignore로 제외
│
├── CLAUDE.md               프로젝트 규칙 (Claude Code 용)
├── CLAUDE_CODE_PROMPT.md   개발 가이드 (575줄)
├── README.md               사용자 문서 (112줄)
└── research.md             이 문서
```

---

## 4. 설정 파일 상세 (config.py)

### 4.1 경로 및 서버 설정

```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # 프로젝트 루트
DB_PATH  = os.path.join(BASE_DIR, "db", "active_etf.db")
HOST     = "0.0.0.0"   # 모든 인터페이스 바인드
PORT     = 8787
```

### 4.2 크롤링 설정

```python
CRAWL_SLEEP = 1.5  # ETF 간 최소 대기(초). 실제는 +random(0, 0.7)로 1.5~2.2초
CRAWL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
    "Referer": "https://finance.naver.com/",
}
```

- **User-Agent**: Chrome 123으로 위장하여 봇 차단 회피
- **Referer**: 네이버 증권 도메인 설정으로 직접 접근 차단 우회
- **Sleep**: 서버 부하 방지 + 차단 회피를 위한 랜덤 지연

### 4.3 스케줄러 설정

```python
SCHEDULE_HOUR   = 20  # 오후 8시
SCHEDULE_MINUTE = 0
```

한국 주식시장 폐장(15:30) 이후 충분한 시간을 두고 수집. 네이버 증권의 ETF 구성종목 데이터 갱신 시점을 고려한 설정.

### 4.4 대상 ETF 25개

| 섹터 | ETF명 | 코드 |
|------|--------|------|
| **반도체** (5) | UNICORN SK하이닉스밸류체인액티브 | 494220 |
| | WON 반도체밸류체인액티브 | 474590 |
| | RISE 비메모리반도체액티브 | 388420 |
| | KoAct AI인프라액티브 | 487130 |
| | TIGER 코리아테크액티브 | 471780 |
| **바이오** (3) | TIMEFOLIO K바이오액티브 | 463050 |
| | KoAct 바이오헬스케어액티브 | 462900 |
| | RISE 바이오TOP10액티브 | 0000Z0 |
| **배당/밸류업** (5) | KoAct 배당성장액티브 | 476850 |
| | TIMEFOLIO Korea플러스배당액티브 | 441800 |
| | TIMEFOLIO 코리아밸류업액티브 | 495060 |
| | KoAct 코리아밸류업액티브 | 495230 |
| | TRUSTON 코리아밸류업액티브 | 496130 |
| **신재생/2차전지** (4) | KODEX 신재생에너지액티브 | 385510 |
| | TIMEFOLIO K신재생에너지액티브 | 404120 |
| | RISE 2차전지액티브 | 422420 |
| | TIMEFOLIO K이노베이션액티브 | 385710 |
| **로봇/우주/조선** (3) | KODEX 친환경조선해운액티브 | 445150 |
| | KoAct K수출핵심기업TOP30액티브 | 0074K0 |
| | KODEX 로봇액티브 | 445290 |
| **소비/컬처** (2) | VITA MZ소비액티브 | 422260 |
| | TIMEFOLIO K컬처액티브 | 410870 |
| **기타** (3) | WON K-글로벌수급상위 | 0088N0 |
| | TIMEFOLIO 코스피액티브 | 385720 |
| | KODEX 200액티브 | 494890 |

### 4.5 섹터 탭 순서

```python
SECTOR_ORDER = ["전체", "반도체", "바이오", "배당/밸류업", "신재생/2차전지", "로봇/우주/조선", "소비/컬처", "기타"]
```

---

## 5. 데이터베이스 설계 상세

### 5.1 테이블: etf_master

```sql
CREATE TABLE etf_master (
    etf_code   TEXT PRIMARY KEY,           -- '494220' (네이버 증권 종목코드)
    etf_name   TEXT NOT NULL,              -- 'UNICORN SK하이닉스밸류체인액티브'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- **용도**: ETF 코드 → 이름 매핑 (config.py의 ETF_LIST를 DB에 복사)
- **행 수**: 항상 25개 (고정)
- **시딩**: `seed_etf_master()` → INSERT OR REPLACE로 매번 덮어쓰기

### 5.2 테이블: etf_holdings (핵심 테이블)

```sql
CREATE TABLE etf_holdings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    etf_code      TEXT NOT NULL,            -- '494220'
    collect_date  DATE NOT NULL,            -- '2026-02-27' (수집 날짜)
    stock_name    TEXT NOT NULL,            -- '삼성전자'
    stock_count   INTEGER,                  -- 보유 주식수 (예: 15000)
    weight        REAL,                     -- 비중 % (예: 12.53)
    stock_price   INTEGER,                  -- 시세/현재가 (예: 73400) ← ALTER TABLE로 나중 추가
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(etf_code, collect_date, stock_name)  -- 동일 날짜 + ETF + 종목 중복 방지
);
```

- **핵심 설계**: 날짜별 스냅샷 방식. 매 수집일마다 전체 구성종목을 저장
- **데이터 규모**: 25 ETF × 평균 20종목 = ~500행/일, 연간 ~125,000행
- **UNIQUE 제약**: `(etf_code, collect_date, stock_name)` → INSERT OR REPLACE로 같은 날 재수집 시 덮어쓰기

### 5.3 인덱스 설계

| 인덱스 | 컬럼 | 주요 쿼리 |
|--------|------|-----------|
| `idx_holdings_date` | `(collect_date)` | 날짜별 전체 데이터 조회 |
| `idx_holdings_etf_date` | `(etf_code, collect_date)` | 특정 ETF의 날짜별 데이터 조회 |
| `idx_holdings_stock` | `(stock_name, collect_date)` | 특정 종목의 시계열 조회 |

### 5.4 stock_price 마이그레이션

```python
# init_db() 내부 (naver_etf.py:59-65)
cols = [r[1] for r in conn.execute("PRAGMA table_info(etf_holdings)").fetchall()]
if "stock_price" not in cols:
    conn.execute("ALTER TABLE etf_holdings ADD COLUMN stock_price INTEGER")
```

- 기존 데이터를 보존하면서 컬럼 추가
- stock_price는 `stock_count × stock_price`로 매수금액 계산에 사용
- ALTER TABLE은 SQLite에서 기존 행에 NULL로 추가됨

### 5.5 데이터 저장 정책

1. **매일 크롤링**: 스케줄러가 20:00에 25개 ETF 순회
2. **변경 감지**: 직전 수집일 데이터와 비교 → `{(name, count, weight, price)}` set 비교
3. **동일하면 스킵**: 주말이나 공휴일처럼 구성이 안 바뀌면 새 날짜 저장 안 함
4. **INSERT OR REPLACE**: UNIQUE 제약에 의해 같은 날짜 재수집 시 기존 데이터 덮어쓰기

---

## 6. 크롤러 상세 (crawler/naver_etf.py)

### 6.1 전체 함수 목록

| 함수 | 줄 | 입력 | 출력 | 역할 |
|------|-----|------|------|------|
| `get_db_connection()` | 21-26 | - | Connection | SQLite 연결 (WAL 모드) |
| `init_db()` | 29-70 | - | None | 테이블/인덱스 생성 + 마이그레이션 |
| `seed_etf_master()` | 73-85 | - | None | config → etf_master 시딩 |
| `fetch_holdings(etf_code)` | 88-115 | ETF코드 | list[dict] | HTTP GET + HTML 파싱 |
| `_parse_holdings_html(html, etf_code)` | 118-180 | HTML문자열 | list[dict] | BeautifulSoup로 테이블 파싱 |
| `is_data_changed(etf_code, new_holdings, conn)` | 183-227 | ETF코드, 데이터 | bool | 변경 여부 판단 |
| `save_holdings(etf_code, holdings, date, conn)` | 230-251 | ETF코드, 데이터, 날짜 | None | DB에 INSERT OR REPLACE |
| `collect_single_etf(etf_name, etf_code, date)` | 254-295 | ETF이름, 코드, 날짜 | dict | 단일 ETF 수집 + 저장 |
| `collect_all_etf_data()` | 298-327 | - | list[dict] | 전체 25개 ETF 순회 수집 |

### 6.2 크롤링 대상 URL 및 HTML 구조

**URL 패턴**: `https://finance.naver.com/item/main.naver?code={etf_code}`

**파싱 대상 HTML 구조**:
```html
<div class="section etf_asset">
  <table>
    <tr>
      <td><a href="/item/main.naver?code=005930">삼성전자</a></td>
      <td>15,000</td>          <!-- stock_count -->
      <td>12.53%</td>          <!-- weight -->
      <td>73,400</td>          <!-- stock_price (있는 경우) -->
    </tr>
    ...
  </table>
</div>
```

### 6.3 파싱 로직 상세 (_parse_holdings_html)

```
1. BeautifulSoup(html, "lxml")로 DOM 파싱
2. soup.find("div", class_="section etf_asset") → 구성종목 섹션 찾기
3. section.find_all("tr") → 모든 행 순회
4. 각 행에서:
   a. row.find("a", href=re.compile(r"/item/main\.naver\?code=")) → 종목 링크 확인
   b. 링크 없는 행은 스킵 (헤더, 합계 등)
   c. tds = row.find_all("td") → 최소 3개 이상
   d. tds[0].get_text(strip=True) → stock_name
   e. tds[1].get_text(strip=True).replace(",", "") → stock_count (int)
   f. tds[2].get_text(strip=True).replace("%", "") → weight (float)
   g. len(tds) > 3이면: tds[3].get_text(strip=True).replace(",", "") → stock_price (int)
   h. stock_count나 weight가 None이면 해당 행 스킵
```

### 6.4 인코딩 처리

```python
try:
    html = resp.content.decode("utf-8")
except UnicodeDecodeError:
    html = resp.content.decode("euc-kr", errors="replace")
```

- 네이버 증권은 Content-Type 헤더에 euc-kr을 명시하지만 실제 본문은 UTF-8인 경우가 있음
- UTF-8을 먼저 시도하고, 실패하면 euc-kr로 fallback
- `errors="replace"`로 디코딩 불가 문자는 ? 로 대체

### 6.5 변경 감지 알고리즘 (is_data_changed)

```python
# 직전 수집일의 데이터를 4-tuple set으로 변환
prev_set = {(r["stock_name"], r["stock_count"], r["weight"], r["stock_price"]) for r in prev_holdings}
new_set  = {(h["stock_name"], h["stock_count"], h["weight"], h.get("stock_price")) for h in new_holdings}

return prev_set != new_set  # set 비교로 순서 무관 비교
```

**판단 기준**:
1. 이전 데이터 없음(첫 수집) → True (저장 필요)
2. 행 수가 다름 → True (종목 수 변경)
3. 4-tuple set 불일치 → True (수량, 비중, 가격 등 변경)
4. 모두 동일 → False (저장 스킵)

### 6.6 수집 흐름도

```
collect_all_etf_data()
│
├── today = "2026-02-28"
├── for i, (etf_name, etf_code) in enumerate(ETF_LIST):
│   │
│   ├── i > 0이면: sleep(1.5 + random(0, 0.7))   ← 봇 탐지 회피
│   │
│   └── collect_single_etf(etf_name, etf_code, today)
│       │
│       ├── fetch_holdings(etf_code)
│       │   ├── HTTP GET → 네이버 증권 (timeout=15초)
│       │   └── _parse_holdings_html() → [{stock_name, stock_count, weight, stock_price}, ...]
│       │
│       ├── holdings가 비어있으면 → status="empty"
│       │
│       ├── is_data_changed(etf_code, holdings, conn)
│       │   ├── True  → save_holdings() + commit → status="saved"
│       │   └── False → status="unchanged"
│       │
│       └── 예외 발생 시 → status="error" (해당 ETF만 스킵, 나머지 계속)
│
└── 결과 집계: saved / unchanged / error 카운트 로그 출력
```

### 6.7 에러 처리 전략

- **네트워크 오류**: `requests.RequestException` 캐치 → 빈 리스트 반환 → status="empty"
- **파싱 오류**: `ValueError/IndexError` 캐치 → 해당 행만 스킵, 나머지 계속
- **수집 오류**: 최상위 `Exception` 캐치 → status="error", 다음 ETF로 계속
- **원칙**: 한 ETF 실패가 전체 수집을 중단시키지 않음

---

## 7. 시그널 분석 엔진 상세 (analyzer/signal.py)

### 7.1 함수 전체 목록

| # | 함수 | 줄 범위 | 카테고리 | 설명 |
|---|------|---------|----------|------|
| 1 | `get_db_connection()` | 15-19 | 유틸 | DB 연결 (WAL 없음, 읽기 전용) |
| 2 | `get_collect_dates(conn, limit)` | 22-38 | 유틸 | 수집 날짜 목록 (최신순) |
| 3 | `get_top_buy_increase(days, top_n)` | 41-123 | 시그널 | 매수 증가 Top N |
| 4 | `get_top_sell_increase(days, top_n)` | 126-193 | 시그널 | 매도 청산 Top N |
| 5 | `get_overlapping_stocks(top_n)` | 196-257 | 시그널 | 중복 매수 분석 |
| 6 | `get_weight_increase_signals(top_n)` | 260-339 | 시그널 | 비중 증가 시그널 |
| 7 | `get_weight_decrease_signals(top_n)` | 342-413 | 시그널 | 비중 감소 시그널 |
| 8 | `_calc_consecutive_days(conn, stock_name, dates, direction)` | 416-460 | 내부 | 연속 증감일 계산 |
| 9 | `get_etf_holdings(etf_code)` | 463-494 | 조회 | ETF별 최신 보유종목 |
| 10 | `get_unique_stock_names()` | 497-512 | 조회 | 전체 종목명 목록 |
| 11 | `get_stock_weight_history(stock_name)` | 515-631 | 조회 | 종목 시계열 데이터 |
| 12 | `get_stock_overview()` | 634-730 | 조회 | 전체 종목 요약 |
| 13 | `get_last_update_info()` | 733-770 | 조회 | 마지막 수집 정보 |

### 7.2 시그널 #1: 매수 증가 (get_top_buy_increase)

**목적**: N일 동안 여러 ETF에서 주식수가 증가한 종목을 찾아 "펀드매니저들이 매수 중인 종목" 시그널 생성

**알고리즘**:

```
입력: days=3, top_n=20

1. dates = get_collect_dates()  → ['2026-02-28', '2026-02-27', '2026-02-26', ...]
2. latest_date = dates[0]  → '2026-02-28'
3. older_date  = dates[min(3, len-1)]  → '2026-02-25' (3일 전)

4. latest = SELECT etf_code, stock_name, stock_count, weight
            FROM etf_holdings WHERE collect_date = latest_date

5. older  = SELECT ... WHERE collect_date = older_date

6. older_map = { (etf_code, stock_name): {stock_count, weight} }

7. for each row in latest:
   key = (etf_code, stock_name)
   if key not in older_map:
       # 신규 편입 → stock_count 전체가 증가분
       increase = stock_count
       weight_change = weight
   else:
       increase = latest.stock_count - older.stock_count
       weight_change = latest.weight - older.weight

   if increase > 0:
       stock_increases[stock_name].total_increase += increase
       stock_increases[stock_name].etf_count += 1
       stock_increases[stock_name].weight_change += weight_change

8. 정렬: total_increase DESC, etf_count DESC
9. 상위 top_n개 반환
```

**반환 필드**:
- `stock_name`: 종목명
- `etf_count`: 해당 종목이 증가한 ETF 수
- `total_increase`: 전 ETF에서의 총 증가 주식수
- `weight_change`: 전 ETF에서의 총 비중 변화 합계 (%p)

**핵심 인사이트**: increase > 0 조건만 보므로, 주식수가 감소한 ETF는 무시. 신규 편입 종목은 전체 주식수가 increase로 잡히므로 상위에 올라올 가능성이 높음.

### 7.3 시그널 #2: 매도 청산 (get_top_sell_increase)

**목적**: N일 전에 보유하고 있었지만 최신일에 완전히 제거된 종목을 찾아 "펀드매니저들이 청산한 종목" 시그널 생성

**알고리즘**:

```
1. latest_set = {(etf_code, stock_name)} from latest_date
2. for each row in older_date:
   if (etf_code, stock_name) NOT IN latest_set:
       # 이전에 있었는데 지금 없음 = 완전 청산
       stock_sells[stock_name].etf_count += 1
       stock_sells[stock_name].total_decrease += stock_count
       stock_sells[stock_name].prev_weight += weight

3. 정렬: etf_count DESC, total_decrease DESC
```

**주의**: "부분 매도(주식수 감소)"는 이 시그널에 포함되지 않음. 오직 **완전 청산(구성종목에서 제거)**만 감지. 부분 매도는 get_top_buy_increase에서 음수 increase로 나타날 수 있지만, 현재 로직은 increase > 0만 필터하므로 별도 시그널 없음.

### 7.4 시그널 #3: 중복 매수 (get_overlapping_stocks)

**목적**: 여러 액티브 ETF가 동시에 보유 중인 종목을 찾아 "컨센서스가 높은 종목" 시그널 생성

**알고리즘**:

```
1. latest_date의 모든 (stock_name, etf_code, weight, etf_name) 조회
   (etf_master JOIN으로 ETF 이름도 함께)

2. 종목별 집계:
   stock_map[stock_name] = {
       etf_count: 보유 ETF 수,
       etf_names: [ETF명 리스트],
       total_weight: 전 ETF 비중 합계
   }

3. 필터: etf_count >= 2 인 것만
4. avg_weight = total_weight / etf_count
5. 정렬: etf_count DESC, total_weight DESC
```

**투자적 의미**: 삼성전자가 15개 ETF에 동시 보유되어 있다면, 15명의 펀드매니저가 모두 삼성전자를 긍정적으로 보고 있다는 뜻.

### 7.5 시그널 #4: 비중 증가 (get_weight_increase_signals)

**목적**: 최신일 대비 직전일의 비중 증가분을 합산하여 "펀드매니저들이 비중을 높이고 있는 종목" 시그널 생성

**알고리즘**:

```
1. latest_date, prev_date (직전 1일)
2. for each (etf_code, stock_name) in latest_date:
   delta = latest.weight - prev.weight
   if delta > 0:
       stock_signals[stock_name].weight_increase += delta
       stock_signals[stock_name].etf_count += 1

3. 연속 증가일 계산: _calc_consecutive_days(direction="up")
4. 정렬: weight_increase DESC, etf_count DESC
```

**매수 증가 vs 비중 증가의 차이**:
- 매수 증가: stock_count(주식수) 변화. N일 간 비교. 절대적 수량.
- 비중 증가: weight(비중%) 변화. 직전 1일 비교. 포트폴리오 내 비중 변화.
- 주가가 올라서 비중이 자동 증가하는 것과, 펀드매니저가 의도적으로 비중을 높이는 것을 구분하기 어려움.

### 7.6 시그널 #5: 비중 감소 (get_weight_decrease_signals)

비중 증가의 역방향. `delta < 0`인 경우만 집계. `direction="down"`.

### 7.7 연속일 계산 (_calc_consecutive_days)

**목적**: "최근 며칠 연속으로 비중이 증가/감소하고 있는가"를 측정

```python
def _calc_consecutive_days(conn, stock_name, dates, direction):
    consecutive = 0
    for i in range(len(dates) - 1):  # 최대 9번 반복 (dates limit=10)
        curr_avg = AVG(weight) WHERE stock_name=? AND collect_date=dates[i]
        prev_avg = AVG(weight) WHERE stock_name=? AND collect_date=dates[i+1]

        if direction == "up" and curr_avg > prev_avg:
            consecutive += 1
        elif direction == "down" and curr_avg < prev_avg:
            consecutive += 1
        else:
            break  # 추세 반전 시 즉시 종료
    return consecutive
```

**특징**:
- 모든 ETF의 평균 비중(AVG)으로 비교 → 개별 ETF가 아닌 "전체 펀드매니저 컨센서스"
- 최대 9일(dates 10개에서 9번 비교)
- 추세가 깨지면 즉시 중단 (연속성만 측정)
- **성능 주의**: 종목마다 날짜 쌍별로 SELECT AVG() 쿼리 2개씩 실행 → N종목 × M일 쌍 × 2 쿼리

### 7.8 보조 함수: get_stock_overview (가장 복잡한 함수)

**목적**: chart.html의 종목 요약 테이블에 사용. 모든 종목의 요약 정보를 한 번에 반환.

```
1. latest_date의 전체 데이터 조회 (etf_master JOIN)
2. 종목별 집계:
   - etf_count: 보유 ETF 수
   - total_weight: 비중 합계
   - max_weight: 최대 비중
   - total_amount: Σ(stock_count × stock_price) 전 ETF
   - etf_names: [보유 ETF명 리스트]

3. 직전일 데이터로 비중 변화 계산:
   prev_avg = AVG(weight) GROUP BY stock_name WHERE collect_date = prev_date
   weight_change = current_avg - prev_avg

4. 정렬: etf_count DESC, total_weight DESC
```

**반환 필드**:
| 필드 | 타입 | 설명 |
|------|------|------|
| stock_name | str | 종목명 |
| etf_count | int | 보유 ETF 수 |
| avg_weight | float | 평균 비중 (%) |
| total_weight | float | 총 비중 합 (%) |
| max_weight | float | 최대 비중 (%) |
| weight_change | float | 전일 대비 평균 비중 변화 (%p) |
| total_amount | int | 총 매수금액 (원) |
| etf_names | list[str] | 보유 ETF명 리스트 |

### 7.9 보조 함수: get_stock_weight_history (시계열 데이터)

**목적**: chart.html의 드릴다운 차트 + 데이터 테이블에 사용. 특정 종목의 모든 날짜 × 모든 ETF 매트릭스.

```
1. 해당 종목이 포함된 모든 날짜 조회 (오름차순)
2. 해당 종목을 보유한 모든 ETF 조회
3. 날짜 × ETF 전체 데이터 조회
4. (날짜, ETF코드) → {weight, stock_count, stock_price} 매핑
5. ETF별 시계열 구성:
   weights: [null, 5.23, 5.45, ...]  (해당 날짜에 보유 안 했으면 null)
   amounts: [null, 38500000, ...]     (stock_count × stock_price)
6. 날짜별 평균 비중 + 합산 금액 계산
```

**반환 구조**:
```json
{
    "stock_name": "삼성전자",
    "dates": ["2026-02-25", "2026-02-26", "2026-02-27"],
    "etfs": [
        {
            "etf_code": "494220",
            "etf_name": "UNICORN SK하이닉스밸류체인액티브",
            "weights": [12.5, 12.8, 13.1],
            "amounts": [918750000, 940800000, 962350000]
        },
        ...
    ],
    "avg_weights": [10.2, 10.5, 10.8],
    "total_amounts": [5918750000, 6040800000, 6162350000]
}
```

---

## 8. Flask 앱 상세 (app.py)

### 8.1 앱 초기화 흐름

```python
if __name__ == "__main__":
    # 1. db/ 디렉토리 생성
    os.makedirs("db", exist_ok=True)

    # 2. DB 테이블 및 인덱스 초기화
    init_db()

    # 3. ETF 마스터 데이터 시딩
    seed_etf_master()

    # 4. APScheduler 시작 (월-금 20:00)
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=run_collection, trigger="cron",
                      day_of_week="mon-fri", hour=20, minute=0,
                      id="daily_etf_collection", replace_existing=True)
    scheduler.start()

    # 5. Flask 서버 시작
    app.run(host="0.0.0.0", port=8787, debug=False)
```

### 8.2 페이지 라우트 (3개)

| 경로 | 함수 | 템플릿 | 전달 데이터 |
|------|------|--------|-------------|
| `GET /` | `index()` | index.html | etf_list, etf_sectors, sector_order, sector_counts |
| `GET /signals` | `signals()` | signals.html | (없음) |
| `GET /chart` | `chart()` | chart.html | (없음) |

**index만 서버사이드 데이터 전달**: 섹터 탭 구성에 필요한 ETF 목록과 카운트. 나머지 데이터는 클라이언트 JavaScript에서 API 호출.

### 8.3 데이터 API (12개)

| # | 경로 | 메서드 | 파라미터 | 분석 함수 | 설명 |
|---|------|--------|----------|-----------|------|
| 1 | `/api/stock-overview` | GET | - | get_stock_overview() | 전체 종목 요약 |
| 2 | `/api/stocks` | GET | - | get_unique_stock_names() | 종목명 리스트 |
| 3 | `/api/stock-weight-history` | GET | stock_name (필수) | get_stock_weight_history() | 종목 시계열 |
| 4 | `/api/top-buy` | GET | days=3, top_n=20 | get_top_buy_increase() | 매수 증가 Top N |
| 5 | `/api/top-sell` | GET | days=3, top_n=20 | get_top_sell_increase() | 매도 청산 Top N |
| 6 | `/api/holdings` | GET | etf_code (필수) | get_etf_holdings() | ETF 보유종목 |
| 7 | `/api/holdings-by-sector` | GET | sector="전체" | 복합 (반복 호출) | 섹터별 ETF 보유종목 |
| 8 | `/api/overlap` | GET | top_n=30 | get_overlapping_stocks() | 중복 매수 종목 |
| 9 | `/api/weight-increase` | GET | top_n=30 | get_weight_increase_signals() | 비중 증가 시그널 |
| 10 | `/api/weight-decrease` | GET | top_n=30 | get_weight_decrease_signals() | 비중 감소 시그널 |
| 11 | `/api/dates` | GET | - | get_collect_dates() | 수집 날짜 목록 |
| 12 | `/api/last-update` | GET | - | get_last_update_info() | 마지막 수집 정보 |

### 8.4 관리 API (2개)

| 경로 | 메서드 | 역할 | 반환 |
|------|--------|------|------|
| `/api/collect` | POST | 수동 수집 시작 | `{"status": "started" \| "already_running"}` |
| `/api/collect-status` | GET | 수집 상태 조회 | `{"running": bool, "progress": str}` |

### 8.5 동시성 제어 메커니즘

```python
_collect_lock = threading.Lock()    # 뮤텍스
_collect_running = False             # 실행 중 플래그
_collect_progress = ""               # 진행 상태 문자열

def run_collection():
    global _collect_running, _collect_progress
    with _collect_lock:
        if _collect_running:
            return                   # 이미 실행 중이면 즉시 반환
        _collect_running = True
        _collect_progress = "시작됨"

    try:
        results = collect_all_etf_data()
        saved = sum(1 for r in results if r["status"] == "saved")
        errors = sum(1 for r in results if r["status"] in ("error", "empty"))
        _collect_progress = f"완료: 저장 {saved}, 오류 {errors}"
    except Exception as e:
        _collect_progress = f"오류: {e}"
    finally:
        with _collect_lock:
            _collect_running = False
```

**동시 수집 방지**: Lock으로 `_collect_running` 체크 → 이미 실행 중이면 스킵
**상태 업데이트**: 수집 완료/실패 시 progress 문자열 업데이트
**수동 수집**: daemon Thread로 실행 → 메인 스레드 비차단

### 8.6 holdings-by-sector API 패턴

이 API만 유일하게 **서버에서 반복 호출**하는 패턴:

```python
@app.route("/api/holdings-by-sector")
def api_holdings_by_sector():
    sector = request.args.get("sector", "전체")
    result = []
    for etf_name, etf_code in ETF_LIST.items():
        if sector != "전체" and ETF_SECTORS.get(etf_name) != sector:
            continue
        holdings = get_etf_holdings(etf_code)  # 매 ETF마다 DB 연결/해제
        result.append({...})
    return jsonify(result)
```

**성능 이슈**: 전체 섹터(25개 ETF) 조회 시 get_etf_holdings()를 25번 호출 → 25번 DB 연결/해제. 최적화 가능하지만 현재 규모에서는 문제 없음.

---

## 9. 프론트엔드 상세

### 9.1 공통 레이아웃 (base.html)

**구조**:
```
<html data-bs-theme="light">
  <head>
    Bootstrap 5.3.3 CDN
    custom.css
  </head>
  <body>
    <nav> 브랜드 | 대시보드 | 시그널 | 차트 | 수동수집 | 테마토글 </nav>
    <main> {% block content %} </main>
    <footer> 마지막 업데이트 정보 | 수집 상태 </footer>
    Bootstrap JS CDN
    테마/수집/업데이트 스크립트
  </body>
</html>
```

**JavaScript 기능**:

1. **테마 토글**: `data-bs-theme` 속성을 `light`↔`dark` 전환. `localStorage.setItem('etf_theme', ...)` 저장. 아이콘도 `🌙`↔`☀️` 전환.

2. **마지막 업데이트**: 페이지 로드 시 `fetch('/api/last-update')` → "최신: 2026-02-28 | ETF 24개 | 종목 387개" 표시

3. **수동 수집**: POST `/api/collect` → 3초 폴링 `/api/collect-status` → "수집 완료! 페이지를 새로고침하세요."

### 9.2 대시보드 (index.html)

**섹션 1: 기간별 매수/매도 Top**

```
[3일] [5일] [10일]  ← 기간 선택 버튼

┌─────────────────────┐  ┌─────────────────────┐
│ 매수 증가 Top 20     │  │ 매도 증가(청산) Top 20│
│ (녹색 헤더)          │  │ (빨간 헤더)          │
│                     │  │                     │
│ #  종목  ETF수      │  │ #  종목  ETF수      │
│    증가주식수 비중변화│  │    감소주식수 이전비중 │
│ 1  삼성전자 5        │  │ 1  LG화학  3        │
│    +15,000 +0.82    │  │    -8,000  2.51     │
│ ...                 │  │ ...                 │
└─────────────────────┘  └─────────────────────┘
```

- 기간 버튼 클릭 시 `currentDays` 변수 업데이트 → `loadTopData()` → 매수/매도 API 병렬 호출
- 로딩 중 스피너 표시 (Bootstrap spinner)

**섹션 2: 섹터별 ETF 보유종목**

```
[전체(25)] [반도체(5)] [바이오(3)] [배당/밸류업(5)] ...

Top 5 중복종목 요약 테이블:
#  종목명    중복ETF수  비중합(%)
1  삼성전자   15        42.31

ETF 카드 그리드 (col-xl-4 col-lg-6):
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ UNICORN SK하이닉스 │ │ WON 반도체밸류체인 │ │ RISE 비메모리반도체│
│ [23종목]          │ │ [18종목]          │ │ [20종목]          │
│ # 종목 주식수 비중 │ │ # 종목 주식수 비중 │ │ # 종목 주식수 비중 │
│ 1 삼성전자 15000.. │ │ 1 SK하이닉스 ...  │ │ ...              │
│ (max-height:320px │ │                  │ │                  │
│  스크롤)          │ │                  │ │                  │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

- `fetch('/api/holdings-by-sector?sector=...')` 호출
- 클라이언트에서 Top 5 중복종목 집계 (JavaScript로 stockMap 구성)
- ETF 카드 내부 테이블 max-height: 320px + overflow-y: auto

### 9.3 시그널 (signals.html)

```
[10] [20] [30]  ← TOP N 선택

┌─────────────────────────────────────────────────┐
│ 중복 매수 종목 Top N (최신일 기준)  (파란 보더)     │
│ #  종목명  보유ETF수  보유 ETF 목록       비중합 평균│
│ 1  삼성전자  15      [UNICORN] [WON] ... 42.3  2.82│
│ (ETF 목록은 badge로 표시, 15자 초과 시 truncate) │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ 비중 증가 시그널 Top N  (녹색 보더)                │
│ #  종목명  비중증가합(%p)  증가ETF수  연속증가일     │
│ 1  SK하이닉스  +2.31      8        3일           │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ 비중 감소 시그널 Top N  (빨간 보더)                │
│ #  종목명  비중감소합(%p)  감소ETF수  연속감소일     │
│ 1  LG에너지솔루션  -1.85   4        5일           │
└─────────────────────────────────────────────────┘
```

### 9.4 차트 (chart.html) - 가장 복잡한 페이지

**Part 1: 종목 요약 테이블**

```
[종목명 검색...] (전체) (중복종목 2+ETF)        327개 종목

┌────────────────────────────────────────────────────────┐
│ #  종목명   보유ETF수↓  평균비중  총비중  비중변화  총매수금액 │
│ 1  삼성전자  15         2.82%   42.31%  +0.15%   523.1억  │
│ 2  SK하이닉스 12        3.45%   41.40%  -0.08%   412.8억  │
│ (클릭 가능, 선택 시 파란 하이라이트 + 좌측 보더)             │
└────────────────────────────────────────────────────────┘
```

- 정렬 가능 (헤더 클릭): etf_count, avg_weight, total_weight, weight_change, total_amount
- 필터: 텍스트 검색 (includes 매칭) + 라디오 (전체/중복종목)
- 행 클릭 시 상세 패널 열기

**JavaScript 상태 관리**:
```javascript
let overviewData = [];      // API에서 받은 전체 데이터
let filteredData = [];      // 필터/정렬 적용 후 데이터
let chartInstance = null;   // Chart.js 인스턴스
let currentData = null;     // 현재 선택된 종목의 시계열 데이터
let currentDateRange = 5;   // 5 | 10 | 0(전체)
let viewMode = 'weight';   // 'weight' | 'amount'
let sortKey = 'etf_count';
let sortAsc = false;
let filterTab = 'all';     // 'all' | 'overlap'
let filterText = '';
let selectedStock = null;   // 현재 선택된 종목명
```

**Part 2: 상세 패널 (행 클릭 시 등장)**

```
┌──────────────────────────────────────────────────────┐
│ 삼성전자  [최근5일] [최근10일] [전체]  [비중%] [금액억원]  │
│                                                      │
│  수평 바 차트 (Chart.js)                               │
│  Y축: ETF명                                           │
│  X축: 비중(%) 또는 금액(억원)                            │
│                                                      │
│  ████████████████ UNICORN SK하이닉스 (2/28: 12.53%)    │
│  ██████████████   WON 반도체밸류체인 (2/28: 11.20%)     │
│  █████████       RISE 비메모리 (2/28: 8.45%)           │
│  ...                                                 │
│                                                      │
│  [범례: 2/25 (연한색) ... 2/28 (진한색)]                │
└──────────────────────────────────────────────────────┘
```

**차트 그라데이션 색상 생성**:
```javascript
function getBarColors(dateCount) {
    const colors = [];
    for (let i = 0; i < dateCount; i++) {
        const ratio = dateCount === 1 ? 1 : i / (dateCount - 1);
        const alpha = 0.25 + 0.65 * ratio;  // 0.25(연한) ~ 0.90(진한)
        colors.push(`rgba(33, 150, 243, ${alpha})`);
    }
    return colors;
}
```

- 과거 날짜 → 연한 파란색 (alpha=0.25)
- 최신 날짜 → 진한 파란색 (alpha=0.90)
- 날짜가 1개면 ratio=1 → 항상 진한색

**차트 높이 동적 계산**:
```javascript
const dynamicHeight = Math.max(200, labels.length * recentDates.length * barHeight + padding);
chartArea.style.height = Math.min(dynamicHeight, 800) + 'px';
```

- ETF 수 × 날짜 수 × 25px + 80px
- 최소 200px, 최대 800px

**Part 3: 데이터 테이블**

```
┌────────────────────────────────────────────────────┐
│ 삼성전자 - ETF별 비중 데이터                          │
│ 날짜      UNICORN  WON   RISE   ...    평균         │
│ 2026-02-28  12.53%  11.20%  8.45%  ...   10.80%    │
│ 2026-02-27  12.31%  11.05%  8.38%  ...   10.60%    │
│ 2026-02-26  12.15%  10.92%  8.30%  ...   10.45%    │
└────────────────────────────────────────────────────┘
```

- viewMode가 'amount'이면 억원 단위로 표시
- 날짜는 최신→과거 순서 (역순)

**테마 변경 감지**:
```javascript
const observer = new MutationObserver(() => {
    if (currentData) renderChart(currentData);
});
observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-bs-theme'] });
```

- `data-bs-theme` 속성 변경 시 차트 자동 재렌더링 (그리드/텍스트 색상 업데이트)

### 9.5 커스텀 CSS (custom.css)

| 클래스 | 역할 |
|--------|------|
| `.table-buy th` | 매수 테이블 헤더 (녹색 10% 배경) |
| `.table-sell th` | 매도 테이블 헤더 (빨간 10% 배경) |
| `.card-header-buy` | 매수 카드 헤더 |
| `.card-header-sell` | 매도 카드 헤더 |
| `.card-header-info` | 정보 카드 헤더 (파란 10% 배경) |
| `.badge-etf` | ETF 이름 뱃지 (0.7rem) |
| `.text-num` | 숫자 우측 정렬 + tabular-nums |
| `.spinner-inline` | 인라인 로딩 스피너 (1rem) |
| `.chart-container` | 차트 영역 (min-height: 300px) |
| `.horizontal-bar` | 수평 바 차트 (max-height: 800px, 스크롤) |
| `.stock-overview-row` | 종목 행 (hover, selected 효과) |
| `.sortable-header` | 정렬 가능 헤더 (포인터 커서) |
| `.weight-change-pos` | 비중 상승 (빨간색 #dc3545) |
| `.weight-change-neg` | 비중 하락 (파란색 #0d6efd) |

**반응형**: 768px 이하에서 폰트 0.85rem, 패딩 0.4rem으로 축소

**색상 규칙**:
- 매수/증가: 녹색 계열 (rgba(25, 135, 84, 0.1))
- 매도/감소: 빨간 계열 (rgba(220, 53, 69, 0.1))
- 정보/중립: 파란 계열 (rgba(13, 110, 253, 0.1))
- 비중 변화: 상승=빨간(한국 주식 관례), 하락=파란

---

## 10. 데이터 수집 파이프라인 전체 흐름

### 10.1 자동 수집 (월-금 20:00)

```
[APScheduler cron trigger] ──── 월~금 20:00
         │
         ▼
    run_collection()        ← app.py:47
         │
         ├── Lock 획득 시도
         │   ├── 이미 실행 중 → 즉시 return
         │   └── Lock 획득 → _collect_running = True
         │
         ▼
    collect_all_etf_data()  ← naver_etf.py:298
         │
         ├── today = "2026-02-28"
         │
         ├── ETF #1: UNICORN SK하이닉스밸류체인액티브 (494220)
         │   ├── fetch_holdings("494220")
         │   │   ├── GET https://finance.naver.com/item/main.naver?code=494220
         │   │   ├── HTML 파싱 → [{"stock_name": "삼성전자", "stock_count": 15000, ...}, ...]
         │   │   └── 인코딩: UTF-8 → euc-kr fallback
         │   ├── is_data_changed("494220", holdings, conn)
         │   │   ├── MAX(collect_date) 조회 → "2026-02-27"
         │   │   ├── 직전일 데이터 로드 → set 비교
         │   │   └── 변경됨? → True
         │   └── save_holdings("494220", holdings, "2026-02-28", conn)
         │       └── INSERT OR REPLACE × 23행
         │
         ├── sleep(1.5 + random(0, 0.7))  ← 1.5~2.2초 대기
         │
         ├── ETF #2: WON 반도체밸류체인액티브 (474590)
         │   └── (같은 패턴 반복)
         │
         ├── ... (총 25개 ETF)
         │
         └── 결과 집계 로그:
             "=== 수집 완료: 저장 20 / 변경없음 3 / 오류 2 ==="
```

### 10.2 수동 수집 (웹 UI)

```
[사용자] "수동 수집" 버튼 클릭
    │
    ▼
POST /api/collect
    │
    ├── Lock 체크 → 이미 실행 중이면 {"status": "already_running"}
    │
    ├── 새 daemon Thread 생성 → run_collection() 실행
    │
    └── {"status": "started"} 즉시 반환
         │
         ▼
    [프론트엔드]
    ├── setInterval(3000)  ← 3초마다 폴링
    │   └── GET /api/collect-status
    │       └── {"running": true, "progress": "시작됨"}
    │       └── {"running": true, "progress": "시작됨"}
    │       └── {"running": false, "progress": "완료: 저장 20, 오류 2"}
    │
    └── "수집 완료! 페이지를 새로고침하세요." 표시
```

---

## 11. 시그널 분석 데이터 흐름

### 11.1 대시보드 (index.html) 로딩

```
페이지 로드 시:
    ├── loadBuyTop()   → GET /api/top-buy?days=3&top_n=20   → 매수 증가 테이블
    ├── loadSellTop()  → GET /api/top-sell?days=3&top_n=20  → 매도 청산 테이블
    └── loadSector('전체') → GET /api/holdings-by-sector?sector=전체
                           → 25개 ETF 보유종목 카드 + Top 5 중복종목
```

### 11.2 시그널 (signals.html) 로딩

```
페이지 로드 시:
    ├── loadOverlap()    → GET /api/overlap?top_n=20        → 중복 매수 테이블
    ├── loadWeightUp()   → GET /api/weight-increase?top_n=20 → 비중 증가 테이블
    └── loadWeightDown() → GET /api/weight-decrease?top_n=20 → 비중 감소 테이블
```

### 11.3 차트 (chart.html) 로딩

```
페이지 로드 시:
    └── GET /api/stock-overview  → 전체 종목 요약 테이블

행 클릭 시:
    └── GET /api/stock-weight-history?stock_name=삼성전자
        → 수평 바 차트 + 데이터 테이블
```

---

## 12. 성능 분석

### 12.1 수집 시간

| 항목 | 값 |
|------|-----|
| ETF 수 | 25개 |
| ETF 간 대기 | 1.5~2.2초 |
| HTTP 요청 + 파싱 | ~0.5~1초/ETF |
| **총 수집 시간** | **약 50~80초 (1~1.5분)** |
| 네트워크 불안정 시 | 최대 2~3분 |

### 12.2 DB 크기 추정

| 기간 | 행 수 | 예상 크기 |
|------|-------|----------|
| 1일 | ~500행 | ~50KB |
| 1개월 (22거래일) | ~11,000행 | ~1.1MB |
| 1년 (250거래일) | ~125,000행 | ~12.5MB |
| 5년 | ~625,000행 | ~62.5MB |

SQLite는 수백만 행까지 무리 없이 처리 가능.

### 12.3 API 응답 시간 (추정)

| API | 쿼리 복잡도 | 예상 시간 |
|-----|-------------|----------|
| /api/top-buy | 2번 SELECT + Python 집계 | <50ms |
| /api/top-sell | 2번 SELECT + Python 집계 | <50ms |
| /api/overlap | 1번 SELECT + Python 집계 | <30ms |
| /api/weight-increase | 2번 SELECT + N×M×2 쿼리 (연속일) | 50~200ms |
| /api/weight-decrease | 동일 | 50~200ms |
| /api/stock-overview | 2번 SELECT + Python 집계 | <50ms |
| /api/stock-weight-history | 3번 SELECT + Python 매트릭스 | 50~150ms |
| /api/holdings-by-sector | 25×(1 SELECT) | 50~100ms |

**병목**: `_calc_consecutive_days()`의 반복 DB 쿼리. 종목 수 × 날짜 쌍 × 2 쿼리.

### 12.4 프론트엔드 로드

| 리소스 | 크기 (gzip) |
|--------|------------|
| Bootstrap 5.3.3 CSS | ~25KB |
| Bootstrap 5.3.3 JS | ~40KB |
| Chart.js 4.4.7 | ~65KB |
| custom.css | ~2KB |
| **합계** | **~132KB** |

---

## 13. 배포 정보

| 항목 | 값 |
|------|-----|
| 서버 | stockss.cafe24.com |
| 사용자 | erpy |
| 원격 경로 | ~/active-etf/src/ |
| 가상환경 | /home/erpy/active-etf/venv/ |
| 시작 스크립트 | ~/active-etf/start.sh (watchdog 방식) |
| 로그 | ~/active-etf/app.log |
| 배포 방법 | sshpass + scp로 개별 파일 전송 → kill → start.sh 재시작 |
| 포트 | 8787 |

---

## 14. 시스템 한계 및 잠재적 개선점

### 14.1 존재하지 않는 기능

| 기능 | 현재 상태 | 코드 근거 |
|------|----------|-----------|
| **알림/통보 시스템** | 없음 | SMTP, 텔레그램, 슬랙, 푸시 등 일체 없음 |
| **사용자 인증** | 없음 | 로그인, 세션, JWT 없음 |
| **실시간 통신** | 없음 | WebSocket, SSE 없음 |
| **데이터 캐싱** | 없음 | Redis, in-memory cache 없음 |
| **자동 재시도** | 없음 | 크롤링 실패 시 재시도 로직 없음 |
| **데이터 백업** | 없음 | SQLite 파일 백업 없음 |
| **API Rate Limiting** | 없음 | 무제한 API 접근 가능 |
| **로그 로테이션** | 없음 | app.log 무한 증가 |
| **헬스체크** | 없음 | 서버 상태 모니터링 없음 |

### 14.2 잠재적 위험

1. **네이버 HTML 구조 변경**: `div.section.etf_asset` 클래스명이 바뀌면 파싱 전체 실패. 모니터링 없음.
2. **SQLite 동시 쓰기**: WAL 모드로 완화되었으나, 다중 프로세스 접근 시 문제 가능.
3. **단일 프로세스**: Flask 서버 크래시 시 자동 복구 없음 (start.sh의 watchdog이 담당).
4. **크롤링 차단**: User-Agent 고정 + 일정한 패턴 → 장기적으로 차단 가능성.
5. **시그널 오해 가능성**: 주가 변동에 의한 비중 변화와 의도적 매매를 구분 불가.

### 14.3 알림 시스템 삽입 가능 지점

```python
# app.py:run_collection() 완료 후
def run_collection():
    results = collect_all_etf_data()
    saved = sum(1 for r in results if r["status"] == "saved")
    # ★ 여기서 알림 발송 가능:
    # if saved > 0:
    #     signals = compute_all_signals()  # 시그널 자동 계산
    #     alerts = check_thresholds(signals)  # 임계값 체크
    #     send_telegram(alerts)  # 텔레그램 발송
```

잠재적 알림 시나리오:
| 시그널 | 알림 조건 | 예시 메시지 |
|--------|----------|------------|
| 매수 증가 | total_increase > 임계값 | "삼성전자: 3개 ETF에서 총 50,000주 매수 증가" |
| 매도 청산 | 특정 종목 청산 | "LG화학: 2개 ETF에서 완전 청산" |
| 비중 증가 | consecutive_days >= N | "SK하이닉스: 3일 연속 비중 증가 (+2.31%p)" |
| 비중 감소 | consecutive_days >= N | "LG에너지솔루션: 5일 연속 비중 감소" |
| 신규 편입 | 이전 없던 종목 등장 | "한화에어로스페이스: 4개 ETF에 신규 편입" |
| 수집 실패 | errors > 임계값 | "⚠️ 수집 오류: 5개 ETF 실패" |

---

## 15. 코드 품질 분석

### 15.1 장점

- **모듈 분리**: 크롤러/분석기/앱이 명확히 분리
- **docstring**: 모든 함수에 한글 docstring + Args/Returns 명시
- **에러 처리**: 크롤링 실패 시 graceful degradation (단일 ETF 실패 → 나머지 계속)
- **DB 설계**: UNIQUE 제약으로 데이터 무결성 보장, 인덱스로 쿼리 최적화
- **UI/UX**: 다크모드, 반응형, 로딩 스피너, 에러 메시지 등 세심한 처리
- **동시성**: Lock으로 중복 수집 방지

### 15.2 코드 패턴

- **DB 연결**: 함수 내에서 connect → try/finally → close (Context Manager 미사용)
- **데이터 처리**: Python dict/list 기반 in-memory 집계 (Pandas 미사용)
- **API 설계**: RESTful JSON API (전부 GET, 수집만 POST)
- **프론트엔드**: SPA 유사 패턴 (JavaScript fetch → 동적 HTML 생성)
- **로깅**: Python logging 모듈 사용, INFO 레벨

### 15.3 잠재적 개선 사항 (코드 수준)

1. **DB 연결 관리**: `with` 문(Context Manager) 사용으로 간결화 가능
2. **`_calc_consecutive_days` 최적화**: 반복 쿼리 대신 한 번에 모든 날짜 데이터 조회 후 Python에서 계산
3. **`/api/holdings-by-sector` 최적화**: 25번 반복 호출 대신 한 번의 배치 쿼리
4. **XSS 방어**: JavaScript에서 `innerHTML`에 직접 데이터 삽입 → `textContent` 사용 고려
5. **타입 힌트**: 반환값에 `-> list[dict]` 대신 TypedDict 또는 dataclass 사용 가능

---

## 16. 의존성 분석

### 16.1 Python 패키지

```
flask>=3.0          → 웹 프레임워크 (Werkzeug + Jinja2 포함)
requests>=2.31      → HTTP 클라이언트 (크롤링)
beautifulsoup4>=4.12 → HTML 파싱
apscheduler>=3.10   → 백그라운드 cron 스케줄러
lxml>=5.0           → BS4용 XML/HTML 파서 (속도 우수)
```

### 16.2 CDN 의존성

```
Bootstrap 5.3.3     → CSS + JS 프레임워크
Chart.js 4.4.7      → 차트 라이브러리 (chart.html에서만 사용)
```

### 16.3 외부 서비스 의존성

- **네이버 증권** (finance.naver.com): 크롤링 대상. HTML 구조 변경 시 파싱 실패
- **CDN** (cdn.jsdelivr.net): Bootstrap + Chart.js. CDN 장애 시 UI 깨짐

---

## 17. 종합 결론

### 시스템 핵심 가치

1. **프로 투자자 추적**: 25개 액티브 ETF 펀드매니저의 매매 행동을 일별로 기록
2. **6가지 시그널**: 매수 증가, 매도 청산, 중복 보유, 비중 증가, 비중 감소, 연속일
3. **시각적 대시보드**: 테이블 + 차트 + 필터 + 다크모드로 직관적 분석

### 아키텍처 요약

```
크롤링 (네이버 → SQLite) → 분석 (SQL + Python 집계) → API (Flask JSON) → UI (Bootstrap + Chart.js)
```

단일 서버, 단일 프로세스, 파일 기반 DB로 구성된 **경량 모놀리식** 아키텍처. 개인 투자자 1인이 사용하기에 충분한 규모와 성능. 알림 시스템은 미구현이지만, run_collection() 완료 시점에 시그널 계산 + 알림 발송 로직을 삽입하는 것이 가장 자연스러운 확장 방향.

### 코드 총량

| 구분 | 파일 수 | 줄 수 |
|------|---------|-------|
| Python (백엔드) | 4개 | ~1,450줄 |
| HTML/JS (프론트엔드) | 4개 | ~1,160줄 |
| CSS | 1개 | ~120줄 |
| **합계** | **9개** | **~2,730줄** |
