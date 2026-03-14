# CLAUDE.md - Active ETF Analysis Project

## 프로젝트 요약
네이버 증권에서 한국 액티브 ETF 구성종목 데이터를 매일 수집하여, 매수/매도 시그널을 분석하고 웹 대시보드로 제공하는 Python 애플리케이션.

## 기술 스택
- Python 3.10+ / Flask / SQLite / Bootstrap 5.3 / BeautifulSoup4 / APScheduler
- **venv 가상환경 사용**

## 빌드 & 실행
```bash
python -m venv venv
source venv/bin/activate       # Linux/Mac
pip install -r requirements.txt
python app.py                  # http://localhost:8787
```

## 프로젝트 구조
- `app.py` - Flask 메인 앱, 라우팅, 스케줄러
- `config.py` - ETF 목록(종목코드 딕셔너리), DB 경로, 상수
- `crawler/naver_etf.py` - 네이버 증권 크롤러
- `analyzer/signal.py` - 시그널 분석 로직
- `templates/` - Jinja2 + Bootstrap 5.3 템플릿
- `db/active_etf.db` - SQLite 데이터베이스
- `venv/` - Python 가상환경 (git 제외)

## 핵심 데이터 설계
- 크롤링 데이터는 **날짜별(collect_date)로 SQLite에 저장**
- 대시보드의 모든 분석은 이 날짜별 스냅샷 데이터를 쿼리하여 계산
- 수집 데이터가 직전 수집일과 동일하면 새 날짜 저장하지 않음

## 핵심 규칙
- 크롤링 시 ETF 간 1.5초 sleep 필수 (서버 부하 방지)
- 크롤링 실패 시 해당 ETF만 스킵, 나머지 계속 수집
- 모든 함수에 docstring 작성
- 한글 인코딩: UTF-8 일관 적용, 네이버 응답은 euc-kr 가능성 있음

## 기존 코드 참조
- GitHub: https://github.com/k-kiwitomatobanana/active-etf-signal

## 대상 ETF (28개)
config.py의 ETF_LIST 딕셔너리 참조. 네이버 증권 URL: `https://finance.naver.com/item/main.naver?code={종목코드}`
