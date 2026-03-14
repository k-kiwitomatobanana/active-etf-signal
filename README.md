# Active ETF Analysis

네이버 증권에서 한국 액티브 ETF 구성종목 데이터를 매일 수집하여, 매수/매도 시그널을 분석하고 웹 대시보드로 제공하는 Python 애플리케이션.

## 시스템 소개

### 주요 기능

- **매수/매도 Top 50 대시보드**: 기간별(1/3/5/10일 + 직접입력) 비중 변화 기준 매수/매도 Top 50, 날짜별 증감 추이 포함
- **날짜별 비중 변화**: 달력으로 특정 날짜 선택 → 당일 전 종목의 비중 변화 한눈에 확인, ETF별 드릴다운
- **비중 변화 시그널**: 비중 증가/감소 종목 + 연속 증가/감소일 + 증가 날짜별 거래대금
- **종목 비중 차트**: 종목별 ETF 비중 시계열 차트 + 종목 요약 테이블
- **중복 매수 분석**: 여러 ETF가 동시에 보유한 종목 집계
- **ETF 구성종목 자동 수집**: 25개 액티브 ETF 구성종목을 네이버 증권에서 매일 크롤링
- **자동 스케줄링**: 매일 20:00 자동 수집 (월~금, APScheduler)
- **웹 대시보드**: Bootstrap 5.3 기반 반응형 UI, 다크모드 지원

### 분석 대상 ETF (25개)

| 섹터 | ETF |
|------|-----|
| 반도체 | UNICORN SK하이닉스밸류체인, WON 반도체밸류체인, RISE 비메모리반도체, KoAct AI인프라, TIGER 코리아테크 |
| 바이오 | TIMEFOLIO K바이오, KoAct 바이오헬스케어, RISE 바이오TOP10 |
| 배당/밸류업 | KoAct 배당성장, TIMEFOLIO Korea플러스배당, TIMEFOLIO 코리아밸류업, KoAct 코리아밸류업, TRUSTON 코리아밸류업 |
| 신재생/2차전지 | KODEX 신재생에너지, TIMEFOLIO K신재생에너지, RISE 2차전지, TIMEFOLIO K이노베이션 |
| 로봇/우주/조선 | KODEX 친환경조선해운, KoAct K수출핵심기업TOP30, KODEX 로봇 |
| 소비/컬처 | VITA MZ소비, TIMEFOLIO K컬처 |
| 기타 | WON K-글로벌수급상위, TIMEFOLIO 코스피, KODEX 200 |

### 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.10+ |
| 웹 프레임워크 | Flask |
| 데이터베이스 | SQLite |
| 프론트엔드 | Bootstrap 5.3 (CDN), Jinja2 |
| 스크래핑 | requests + BeautifulSoup4 |
| 스케줄링 | APScheduler (매일 20:00, 월~금) |

## 사용 방법

### 1. 환경 설정

```bash
# 저장소 클론
git clone https://github.com/k-kiwitomatobanana/active-etf-sinho.git
cd active-etf-sinho

# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows

# 패키지 설치
pip install -r requirements.txt
```

### 2. 실행

```bash
source venv/bin/activate
python3 app.py
```

서버가 시작되면 브라우저에서 접속:
- **대시보드**: http://localhost:8787
- **날짜별**: http://localhost:8787/daily
- **시그널**: http://localhost:8787/signals
- **차트**: http://localhost:8787/chart

### 3. 데이터 수집

- **자동 수집**: 매일 20:00 자동 실행 (월~금)
- **수동 수집**: 웹 대시보드 우측 상단 `수동 수집` 버튼 클릭

### 4. 웹 대시보드 사용법

#### 대시보드 (/)
- **기간 선택**: 1일/3일/5일/10일 버튼 + 숫자 직접 입력
- **매수 증가 Top 50**: 선택 기간 동안 비중이 증가한 종목, 거래대금 순 정렬
- **매도 증가 Top 50**: 선택 기간 동안 비중이 감소한 종목, 거래대금 순 정렬
- **날짜별 증감**: 각 종목의 기간 내 날짜별 거래대금 증감 표시 (증가=빨강, 감소=파랑)
- **종목 클릭 드릴다운**: 날짜별 상세 (거래대금/ETF수/비중/주식수)

#### 날짜별 비중 변화 (/daily)
- **달력 날짜 선택**: 수집일만 선택 가능, 미수집일은 가장 가까운 이전 수집일로 자동 스냅
- **전 종목 비중 변화**: 선택 날짜 vs 직전 수집일 비교, 거래대금 순 정렬 (매수 위, 매도 아래)
- **ETF별 드릴다운**: 종목 클릭 시 해당 종목을 보유한 모든 ETF 상세 (보유주식수/보유금액/비중/변화량)

#### 시그널 (/signals)
- **중복 매수 종목**: 여러 ETF가 동시에 보유한 종목 (보유 ETF 목록 포함)
- **비중 증가 시그널**: 비중 증가 종목 + 연속 증가일 + 증가 날짜별 거래대금
- **비중 감소 시그널**: 비중 감소 종목 + 연속 감소일 + 감소 날짜별 거래대금

#### 종목 비중 차트 (/chart)
- **종목 검색/선택**: 전체 종목 요약 테이블에서 선택 또는 검색
- **ETF별 비중 시계열 차트**: 선택 종목의 ETF별 비중 변화 추이

## API 목록

| API | 설명 |
|-----|------|
| `GET /api/top-buy?days=3&top_n=50` | 매수 증가 Top N (daily_changes 포함) |
| `GET /api/top-sell?days=3&top_n=50` | 매도 증가 Top N (daily_changes 포함) |
| `GET /api/daily-snapshot?date=2026-03-13` | 특정 날짜 전 종목 비중 변화 |
| `GET /api/stock-etf-detail?stock_name=X&date=2026-03-13` | 종목의 ETF별 상세 |
| `GET /api/stock-daily-changes?stock_name=X&days=10` | 종목 날짜별 매매 상세 |
| `GET /api/stock-overview` | 전체 종목 요약 |
| `GET /api/stock-weight-history?stock_name=X` | 종목 ETF별 비중 시계열 |
| `GET /api/stocks` | 전체 종목명 목록 |
| `GET /api/holdings?etf_code=X` | ETF별 보유종목 |
| `GET /api/holdings-by-sector?sector=반도체` | 섹터별 ETF 보유종목 |
| `GET /api/overlap?top_n=30` | 중복 매수 종목 |
| `GET /api/weight-increase?top_n=30` | 비중 증가 시그널 |
| `GET /api/weight-decrease?top_n=30` | 비중 감소 시그널 |
| `GET /api/dates` | 수집 날짜 목록 |
| `GET /api/last-update` | 마지막 수집 일시 |
| `POST /api/collect` | 수동 데이터 수집 실행 |
| `GET /api/collect-status` | 수집 상태 조회 |

## 프로젝트 구조

```
active-etf-analysis/
├── app.py                  # Flask 메인 앱 + 스케줄러 + API 라우팅
├── config.py               # ETF 목록, 섹터 분류, DB 설정
├── requirements.txt
├── README.md
├── CLAUDE.md               # Claude Code 프로젝트 컨텍스트
├── .gitignore
├── db/
│   └── active_etf.db       # SQLite DB (자동 생성, git 제외)
├── crawler/
│   ├── __init__.py
│   └── naver_etf.py        # 네이버 증권 크롤러
├── analyzer/
│   ├── __init__.py
│   └── signal.py           # 시그널 분석 로직
├── templates/
│   ├── base.html            # 공통 레이아웃 (네비게이션 포함)
│   ├── index.html           # 메인 대시보드 (매수/매도 Top 50)
│   ├── daily.html           # 날짜별 비중 변화 페이지
│   ├── signals.html         # 시그널 대시보드
│   └── chart.html           # 종목 비중 차트 페이지
└── static/css/
    └── custom.css           # 커스텀 스타일
```

## 서버 운영

- **Watchdog**: crontab 주기로 앱 생존 확인, 응답 없으면 자동 재시작
- **로그 로테이션**: 매일 자정
- **상세 분석**: `server-collection-report.md` 참조
