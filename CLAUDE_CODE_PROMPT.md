# Active ETF Analysis 프로젝트 업그레이드 - Claude Code 개발 프롬프트

## 프로젝트 개요

기존 GitHub 레포지토리(https://github.com/k-kiwitomatobanana/active-etf-analysis)를 업그레이드하여, 네이버 증권에서 한국 액티브 ETF의 구성종목 데이터를 수집·분석하고 투자 시그널을 제공하는 웹 대시보드를 개발한다.

---

## 1. 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.10+ |
| 가상환경 | **venv** (Python 내장 가상환경) |
| 웹 프레임워크 | Flask |
| 데이터베이스 | SQLite |
| 프론트엔드 | Bootstrap 5.3 (CDN), Jinja2 템플릿 |
| 스크래핑 | requests + BeautifulSoup4 |
| 스케줄링 | APScheduler (매일 20:00 자동 실행) |
| 패키지 관리 | requirements.txt (venv 환경에서 설치) |

---

## 2. 프로젝트 구조

```
active-etf-analysis/
├── app.py                    # Flask 메인 앱 + 스케줄러 설정
├── config.py                 # ETF 목록, DB 설정, 상수 정의
├── requirements.txt
├── README.md
├── CLAUDE.md                 # Claude Code 프로젝트 컨텍스트
├── .gitignore                # venv/, db/*.db, __pycache__/ 등
├── venv/                     # Python 가상환경 (git 제외)
├── db/
│   └── active_etf.db         # SQLite DB 파일
├── crawler/
│   ├── __init__.py
│   └── naver_etf.py          # 네이버 증권 크롤러
├── analyzer/
│   ├── __init__.py
│   └── signal.py             # 시그널 분석 로직
├── templates/
│   ├── base.html             # 공통 레이아웃 (Bootstrap 5.3)
│   ├── index.html            # 메인 대시보드
│   └── signals.html          # 시그널 대시보드
└── static/
    └── css/
        └── custom.css         # 커스텀 스타일
```

---

## 3. 환경 설정 (venv)

### 3.1 초기 설정

```bash
# 가상환경 생성
python -m venv venv

# 가상환경 활성화
# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt
```

### 3.2 requirements.txt

```
flask>=3.0
requests>=2.31
beautifulsoup4>=4.12
apscheduler>=3.10
lxml>=5.0
```

### 3.3 .gitignore

```
venv/
__pycache__/
*.pyc
db/*.db
.env
```

### 3.4 실행

```bash
# 가상환경 활성화 후
source venv/bin/activate   # Linux/Mac
python app.py              # http://localhost:8787
```

---

## 4. 분석 대상 ETF 목록

아래 ETF들의 네이버 증권 종목코드를 확인하여 `config.py`에 딕셔너리로 관리한다. 네이버 증권 URL 패턴: `https://finance.naver.com/item/main.naver?code={종목코드}`

```python
ETF_LIST = {
    "UNICORN SK하이닉스밸류체인액티브": "종목코드",
    "WON 반도체밸류체인액티브": "종목코드",
    "RISE 비메모리반도체액티브": "종목코드",
    "WON K-글로벌수급상위": "종목코드",
    "KoAct 배당성장액티브": "종목코드",
    "TIMEFOLIO Korea플러스배당액티브": "종목코드",
    "KODEX 신재생에너지액티브": "종목코드",
    "TIMEFOLIO K신재생에너지액티브": "종목코드",
    "RISE 2차전지액티브": "종목코드",
    "TIMEFOLIO K이노베이션액티브": "종목코드",
    "VITA MZ소비액티브": "종목코드",
    "KoAct AI인프라액티브": "종목코드",
    "TIMEFOLIO 코스피액티브": "종목코드",
    "KODEX 친환경조선해운액티브": "종목코드",
    "TIGER 코리아테크액티브": "종목코드",
    "KoAct K수출핵심기업TOP30액티브": "종목코드",
    "KODEX 로봇액티브": "종목코드",
    "TIMEFOLIO K컬처액티브": "종목코드",
    "TIMEFOLIO 코리아밸류업액티브": "종목코드",
    "KoAct 코리아밸류업액티브": "종목코드",
    "TRUSTON 코리아밸류업액티브": "종목코드",
    "TIMEFOLIO K바이오액티브": "종목코드",
    "KoAct 바이오헬스케어액티브": "종목코드",
    "RISE 바이오TOP10액티브": "종목코드",
    "KODEX 200액티브": "종목코드",
}
```

> **중요**: 각 ETF의 실제 종목코드는 네이버 증권에서 검색하여 채워넣을 것. 예시: `https://finance.naver.com/item/main.naver?code=494890`

---

## 5. 데이터베이스 스키마 (SQLite)

### 5.1 ETF 마스터 테이블

```sql
CREATE TABLE IF NOT EXISTS etf_master (
    etf_code TEXT PRIMARY KEY,          -- 네이버 증권 종목코드
    etf_name TEXT NOT NULL,             -- ETF 이름
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 5.2 ETF 구성종목 테이블 (날짜별 스냅샷)

**핵심 설계**: 수집된 데이터를 **날짜별로 저장**한다. 대시보드의 모든 분석(매수/매도 변화, 비중 추이, 시그널)은 이 날짜별 데이터를 기반으로 계산한다.

```sql
CREATE TABLE IF NOT EXISTS etf_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    etf_code TEXT NOT NULL,             -- ETF 종목코드
    collect_date DATE NOT NULL,         -- 수집 날짜 (YYYY-MM-DD), 날짜별 스냅샷 키
    stock_name TEXT NOT NULL,           -- 구성종목명
    stock_count INTEGER,                -- 주식수(계약수)
    weight REAL,                        -- 구성비중 (%)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(etf_code, collect_date, stock_name)
);
```

### 5.3 인덱스

```sql
CREATE INDEX idx_holdings_date ON etf_holdings(collect_date);
CREATE INDEX idx_holdings_etf_date ON etf_holdings(etf_code, collect_date);
CREATE INDEX idx_holdings_stock ON etf_holdings(stock_name, collect_date);
```

### 5.4 날짜별 저장 및 중복 방지 로직

```
매일 20:00 수집 실행 시 흐름:

1. 네이버 증권에서 ETF 구성종목 크롤링
2. 직전 수집일(DB에서 해당 ETF의 최신 collect_date) 데이터 조회
3. 비교:
   - 모든 구성종목의 종목명, 주식수, 비중이 100% 동일 → 저장 안함 (날짜 추가 안함)
   - 하나라도 변경됨 → 오늘 날짜(collect_date)로 전체 구성종목 INSERT
4. 대시보드는 항상 DB의 날짜별 데이터를 쿼리하여 분석 결과를 표시
```

---

## 6. 핵심 기능 상세

### 6.1 데이터 수집 (crawler/naver_etf.py)

**크롤링 대상 페이지**: 네이버 증권 ETF 포트폴리오 구성 페이지

각 ETF의 네이버 증권 페이지에서 **ETF 구성종목** 섹션을 파싱한다.

- URL 패턴: `https://finance.naver.com/item/coinfo.naver?code={종목코드}` 또는 ETF 상세 페이지의 구성종목 탭
- 네이버 증권의 ETF 구성종목 정보가 있는 정확한 URL을 탐색하여 사용할 것
- 추출 데이터: **구성종목명**, **주식수(계약수)**, **구성비중(%)**

**크롤링 구현 시 주의사항:**

```python
# 요청 헤더 설정 (User-Agent 필수)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# ETF 간 요청 간격: 1~2초 sleep (서버 부하 방지)
import time
time.sleep(1.5)
```

**중복 데이터 방지 로직:**

```python
def is_data_changed(etf_code: str, new_holdings: list, db_conn) -> bool:
    """
    직전 수집일 데이터와 비교하여 변경 여부 확인.
    
    비교 방법:
    1. DB에서 해당 ETF의 최신 collect_date 데이터 조회
    2. 새로 크롤링한 데이터와 1:1 비교 (종목명, 주식수, 비중)
    3. 모든 항목이 동일하면 False → 오늘 날짜로 저장하지 않음
    4. 하나라도 다르면 True → 오늘 날짜(collect_date)로 전체 저장
    """
    pass


def save_holdings(etf_code: str, holdings: list, collect_date: str, db_conn):
    """
    구성종목 데이터를 날짜별로 저장.
    
    - collect_date: 오늘 날짜 (YYYY-MM-DD)
    - holdings: [{"stock_name": "삼성전자", "stock_count": 15000, "weight": 25.3}, ...]
    - UNIQUE(etf_code, collect_date, stock_name) 제약조건으로 중복 방지
    """
    pass
```

### 6.2 스케줄링

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(
    func=collect_all_etf_data,
    trigger='cron',
    hour=20,
    minute=0,
    id='daily_etf_collection'
)
scheduler.start()
```

- 앱 시작 시 스케줄러 자동 등록
- 수동 실행 버튼도 웹 UI에 제공 (관리자용)

### 6.3 시그널 분석 (analyzer/signal.py)

**모든 분석 함수는 SQLite에 날짜별로 저장된 etf_holdings 테이블을 기반으로 동작한다.**

#### 6.3.1 매수 증가 종목 Top N

```python
def get_top_buy_increase(days: int, top_n: int = 20) -> list:
    """
    최근 N일간 액티브 ETF들에서 주식수(계약수)가 증가한 종목을 집계.
    
    계산 로직 (DB의 날짜별 데이터 활용):
    1. DB에서 최신 collect_date와 N일 전 collect_date를 확인
    2. 각 ETF별로 두 날짜의 구성종목 비교
    3. 주식수가 증가한 종목 추출 (새로 편입된 종목 포함)
    4. 전체 ETF에서 해당 종목의 증가분 합산
    5. 증가분 기준 내림차순 정렬 후 Top N 반환
    
    반환 데이터: 종목명, 매수증가 ETF 수, 총 증가 주식수, 총 비중 변화
    """
    pass
```

#### 6.3.2 매도 증가(청산완료) 종목 Top N

```python
def get_top_sell_increase(days: int, top_n: int = 20) -> list:
    """
    최근 N일간 액티브 ETF들에서 완전히 제거된(청산) 종목을 집계.
    
    계산 로직 (DB의 날짜별 데이터 활용):
    1. DB에서 최신 collect_date와 N일 전 collect_date를 확인
    2. 각 ETF별로 N일 전에는 있었지만 최신일에는 없는 종목 추출
    3. 전체 ETF에서 해당 종목의 청산 건수 합산
    4. 청산 건수 기준 내림차순 정렬 후 Top N 반환
    
    반환 데이터: 종목명, 매도(청산) ETF 수, 총 감소 주식수, 이전 비중 합계
    """
    pass
```

#### 6.3.3 중복 매수 종목 분석

```python
def get_overlapping_stocks(top_n: int = 30) -> list:
    """
    최신일 기준 여러 액티브 ETF가 동시에 보유한 종목을 분석.
    
    계산 로직 (DB의 최신 collect_date 데이터 활용):
    1. DB에서 최신 collect_date의 모든 ETF 구성종목 조회
    2. 종목별로 보유 ETF 수 카운트
    3. 2개 이상 ETF가 보유한 종목만 필터
    4. 보유 ETF 수 기준 내림차순, 동률 시 총 비중합 기준 정렬
    
    반환 데이터: 종목명, 보유 ETF 수, 보유 ETF 목록, 총 비중합, 평균 비중
    """
    pass
```

#### 6.3.4 비중 변화 시그널

```python
def get_weight_increase_signals(top_n: int = 30) -> list:
    """
    최신일 기준 비중 증가 시그널.
    
    계산 로직 (DB의 연속 날짜 데이터 활용):
    1. DB에서 최근 수집된 날짜들(collect_date 목록) 조회
    2. 각 날짜 간 종목별 비중 변화량 계산
    3. 비중 증가합 = 모든 ETF에서 해당 종목의 비중 증가분 합산
    4. 증가 ETF 수 = 해당 종목의 비중이 증가한 ETF 개수
    5. 연속 증가일 = 최신일부터 역순으로 비중이 연속 증가한 일수
       (DB에 저장된 날짜 기준으로 역산)
    
    반환 데이터: 종목명, 비중 증가합, 증가 ETF 수, 연속 증가일
    """
    pass

def get_weight_decrease_signals(top_n: int = 30) -> list:
    """
    최신일 기준 비중 감소 시그널.
    
    계산 로직: 위와 동일하되 감소 방향
    (DB에 저장된 날짜별 데이터로 감소 추이 추적)
    
    반환 데이터: 종목명, 비중 감소합, 감소 ETF 수, 연속 감소일
    """
    pass
```

---

## 7. 웹 대시보드 UI 상세

### 7.1 공통 레이아웃 (base.html)

```
┌──────────────────────────────────────────────────────────┐
│  [로고/제목] Active ETF Analysis    [대시보드] [시그널]   │
│  네비게이션 바 (Bootstrap navbar)                         │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  {% block content %}{% endblock %}                        │
│                                                          │
├──────────────────────────────────────────────────────────┤
│  Footer: 최종 데이터 수집일시 표시 | 수동 수집 버튼       │
└──────────────────────────────────────────────────────────┘
```

- Bootstrap 5.3 CDN 사용
- 다크 테마 지원 (선택)
- 반응형 레이아웃

### 7.2 메인 대시보드 (index.html) - 경로: `/`

**기존 개발된 http://localhost:8787/ 페이지와 동일한 UI를 구현한다.**

#### 상단 영역: 기간별 매수/매도 Top N

```
┌───────────────────────────────────────────────────────┐
│  [3일] [5일] [10일]  ← 기간 선택 탭/버튼              │
├─────────────────────────┬─────────────────────────────┤
│  📈 매수 증가 Top N      │  📉 매도 증가(청산) Top N    │
│                         │                             │
│  순위 | 종목 | ETF수 |   │  순위 | 종목 | ETF수 |      │
│       | 증가주식수 |비중  │       | 감소주식수 | 비중    │
│  ─────────────────────  │  ───────────────────────    │
│  1. 삼성전자  3  +500    │  1. LG에너지  2  -300      │
│  2. SK하이닉스 2 +300    │  2. 카카오    1  -200      │
│  ...                    │  ...                        │
└─────────────────────────┴─────────────────────────────┘
```

#### 하단 영역: ETF별 보유종목 상세

```
┌───────────────────────────────────────────────────────┐
│  ETF 선택: [드롭다운 또는 탭]                          │
│                                                       │
│  ┌─────────────────────────────────────────────────┐  │
│  │ UNICORN SK하이닉스밸류체인액티브                  │  │
│  │                                                 │  │
│  │ 순위 | 구성종목    | 주식수  | 구성비중(%)      │  │
│  │ ───────────────────────────────────────────     │  │
│  │  1   | SK하이닉스  | 15,000  | 25.30           │  │
│  │  2   | 삼성전자    | 8,000   | 18.50           │  │
│  │  3   | 한미반도체  | 3,500   | 8.20            │  │
│  │ ...                                            │  │
│  └─────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────┘
```

- ETF별 보유종목은 DB의 **최신 collect_date** 데이터를 조회하여 표시

### 7.3 시그널 대시보드 (signals.html) - 경로: `/signals`

**기존 개발된 http://localhost:8787/signals 페이지와 동일한 UI를 구현한다.**

#### 영역 1: 중복 매수 종목 (상단)

```
┌───────────────────────────────────────────────────────┐
│  🔥 중복 매수 종목 Top N (최신일 기준)                  │
│                                                       │
│  순위 | 종목명    | 보유ETF수 | 보유ETF목록  | 비중합   │
│  ────────────────────────────────────────────────     │
│  1   | 삼성전자   | 8        | UNICORN, WON,| 45.2%  │
│      |           |          | RISE, ...    |        │
│  2   | SK하이닉스 | 6        | UNICORN, WON | 32.1%  │
│  ...                                                  │
└───────────────────────────────────────────────────────┘
```

#### 영역 2: 비중 증가 시그널 (중단)

```
┌───────────────────────────────────────────────────────┐
│  🟢 비중 증가 시그널 Top N                             │
│                                                       │
│  순위 | 종목명    | 비중증가합 | 증가ETF수 | 연속증가일 │
│  ────────────────────────────────────────────────     │
│  1   | 한화에어로 | +3.50%    | 4         | 3일       │
│  2   | 현대로템   | +2.80%    | 3         | 5일       │
│  ...                                                  │
└───────────────────────────────────────────────────────┘
```

#### 영역 3: 비중 감소 시그널 (하단)

```
┌───────────────────────────────────────────────────────┐
│  🔴 비중 감소 시그널 Top N                             │
│                                                       │
│  순위 | 종목명   | 비중감소합 | 감소ETF수 | 연속감소일  │
│  ────────────────────────────────────────────────     │
│  1   | LG화학   | -4.20%    | 5         | 4일        │
│  2   | 포스코   | -2.10%    | 3         | 2일        │
│  ...                                                  │
└───────────────────────────────────────────────────────┘
```

- 시그널 대시보드의 모든 데이터는 DB에 저장된 **날짜별 스냅샷** 데이터를 쿼리하여 계산

---

## 8. API 엔드포인트

```python
# 메인 대시보드
GET /                          # 메인 대시보드 페이지

# 시그널 대시보드
GET /signals                   # 시그널 대시보드 페이지

# 데이터 API (AJAX용)
GET /api/top-buy?days=3&top_n=20       # 매수 증가 Top N
GET /api/top-sell?days=3&top_n=20      # 매도 증가 Top N
GET /api/holdings?etf_code=494890      # ETF별 보유종목 (최신 collect_date)
GET /api/overlap?top_n=30              # 중복 매수 종목
GET /api/weight-increase?top_n=30      # 비중 증가 시그널
GET /api/weight-decrease?top_n=30      # 비중 감소 시그널
GET /api/dates                         # DB에 저장된 수집 날짜 목록

# 관리 API
POST /api/collect                      # 수동 데이터 수집 실행
GET /api/collect-status                # 수집 상태 조회
GET /api/last-update                   # 마지막 수집 일시 조회
```

---

## 9. 개발 순서 (권장)

1단계부터 순서대로 진행하되, 각 단계 완료 후 테스트를 수행한다.

### 1단계: 프로젝트 초기 설정
- 프로젝트 구조 생성
- **venv 가상환경 생성 및 활성화**
- requirements.txt 작성 및 패키지 설치
- .gitignore 작성 (venv/, __pycache__/, db/*.db)
- config.py에 ETF 목록 및 종목코드 정의
- SQLite DB 초기화 스크립트 (테이블 + 인덱스 생성)

### 2단계: 데이터 수집 모듈
- 네이버 증권 크롤러 구현 (구성종목 파싱)
- 크롤링 테스트 (1개 ETF로 먼저 테스트)
- 날짜별 저장 로직 구현 (collect_date 기반)
- 중복 데이터 방지 로직 구현 (직전 수집일과 비교)
- 전체 ETF 수집 함수 구현

### 3단계: 분석 모듈
- 매수 증가 종목 분석 함수 (DB 날짜별 데이터 기반)
- 매도 증가(청산) 종목 분석 함수
- 중복 매수 종목 분석 함수
- 비중 변화 시그널 함수 (연속 증가/감소일 계산 포함)

### 4단계: 웹 대시보드
- Flask 앱 설정 + 라우팅
- base.html 레이아웃 (Bootstrap 5.3)
- 메인 대시보드 구현 (기존 UI 참고)
- 시그널 대시보드 구현 (기존 UI 참고)
- AJAX 기반 데이터 로딩

### 5단계: 스케줄링 및 마무리
- APScheduler 설정 (매일 20:00)
- 수동 수집 버튼 연동
- 에러 핸들링 및 로깅
- README.md 작성 (venv 설정 가이드 포함)

---

## 10. 네이버 증권 크롤링 참고사항

### 10.1 ETF 구성종목 페이지 구조

네이버 증권에서 ETF 구성종목 정보를 가져오는 방법을 탐색할 것. 주요 확인 포인트:

1. `https://finance.naver.com/item/main.naver?code={종목코드}` 페이지에서 구성종목 탭 확인
2. ETF 상세 페이지의 iframe 또는 API 호출 확인
3. `https://navercomp.wisereport.co.kr/` 등 관련 API 확인
4. 네이버 금융의 ETF 전용 API가 있는지 확인

### 10.2 파싱 시 주의사항

- 네이버 증권은 iframe을 많이 사용하므로, 실제 데이터가 로드되는 URL을 정확히 파악할 것
- JavaScript 렌더링이 필요한 경우 API 직접 호출 방식을 우선 시도
- 구성종목 데이터가 테이블 형태인 경우 pandas의 `read_html()` 활용 가능
- 인코딩 처리: `euc-kr` 또는 `cp949` 인코딩 주의

---

## 11. 기존 코드 참조

기존 GitHub 레포지토리(https://github.com/k-kiwitomatobanana/active-etf-analysis)의 코드를 먼저 분석한 후:

1. **유지할 것**: 기존에 잘 동작하는 크롤링 로직, DB 스키마
2. **개선할 것**: 코드 구조화, 에러 핸들링, 모듈 분리
3. **새로 추가할 것**: 시그널 분석 기능, 비중 변화 추적, Bootstrap 5.3 UI 업그레이드

> **핵심 원칙**: 기존 코드가 있으면 그것을 기반으로 업그레이드하고, 없는 기능만 새로 구현한다. 기존 UI(http://localhost:8787/)를 최대한 동일하게 재현한다.

---

## 12. 품질 요구사항

- 모든 함수에 docstring 작성
- 에러 발생 시 로그 기록 (logging 모듈 사용)
- 크롤링 실패 시 해당 ETF만 스킵하고 나머지 계속 수집
- DB 트랜잭션 관리 (수집 중 오류 시 롤백)
- 웹 페이지 로딩 시 데이터 없으면 안내 메시지 표시
- 한글 인코딩 문제 없도록 UTF-8 일관 적용
