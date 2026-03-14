"""
Active ETF Analysis 프로젝트 설정 파일.
ETF 목록, DB 경로, 상수 정의.
"""

import os

# 프로젝트 루트 디렉토리
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# SQLite DB 경로
DB_PATH = os.path.join(BASE_DIR, "db", "active_etf.db")

# Flask 서버 설정
HOST = "0.0.0.0"
PORT = 8787

# 크롤링 설정
CRAWL_SLEEP = 1.5  # ETF 간 요청 간격 (초)
CRAWL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/123.0 Safari/537.36",
    "Referer": "https://finance.naver.com/",
}

# 스케줄러 설정 (월~금 수집 시간)
SCHEDULE_HOURS = [19, 20]  # 19:00, 20:00 두 번 수집
SCHEDULE_MINUTE = 0

# 텔레그램 알림 설정 (환경변수에서 로드, .env 파일 참조)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# 분석 대상 ETF 목록 (ETF 이름 -> 네이버 증권 종목코드)
ETF_LIST = {
    "UNICORN SK하이닉스밸류체인액티브": "494220",
    "WON 반도체밸류체인액티브": "474590",
    "RISE 비메모리반도체액티브": "388420",
    "WON K-글로벌수급상위": "0088N0",
    "KoAct 배당성장액티브": "476850",
    "TIMEFOLIO Korea플러스배당액티브": "441800",
    "KODEX 신재생에너지액티브": "385510",
    "TIMEFOLIO K신재생에너지액티브": "404120",
    "RISE 2차전지액티브": "422420",
    "TIMEFOLIO K이노베이션액티브": "385710",
    "VITA MZ소비액티브": "422260",
    "KoAct AI인프라액티브": "487130",
    "TIMEFOLIO 코스피액티브": "385720",
    "KODEX 친환경조선해운액티브": "445150",
    "TIGER 코리아테크액티브": "471780",
    "KoAct K수출핵심기업TOP30액티브": "0074K0",
    "KODEX 로봇액티브": "445290",
    "TIMEFOLIO K컬처액티브": "410870",
    "TIMEFOLIO 코리아밸류업액티브": "495060",
    "KoAct 코리아밸류업액티브": "495230",
    "TRUSTON 코리아밸류업액티브": "496130",
    "TIMEFOLIO K바이오액티브": "463050",
    "KoAct 바이오헬스케어액티브": "462900",
    "RISE 바이오TOP10액티브": "0000Z0",
    "KODEX 200액티브": "494890",
    "KoAct 코스닥액티브": "0163Y0",
    "TIMEFOLIO 코스닥액티브": "0162Y0",
    "SOL 코리아메가테크액티브": "444200",
}

# 섹터 분류 (ETF 이름 → 섹터)
ETF_SECTORS = {
    # 반도체
    "UNICORN SK하이닉스밸류체인액티브": "반도체",
    "WON 반도체밸류체인액티브": "반도체",
    "RISE 비메모리반도체액티브": "반도체",
    "KoAct AI인프라액티브": "반도체",
    "TIGER 코리아테크액티브": "반도체",
    # 바이오
    "TIMEFOLIO K바이오액티브": "바이오",
    "KoAct 바이오헬스케어액티브": "바이오",
    "RISE 바이오TOP10액티브": "바이오",
    # 배당/밸류업
    "KoAct 배당성장액티브": "배당/밸류업",
    "TIMEFOLIO Korea플러스배당액티브": "배당/밸류업",
    "TIMEFOLIO 코리아밸류업액티브": "배당/밸류업",
    "KoAct 코리아밸류업액티브": "배당/밸류업",
    "TRUSTON 코리아밸류업액티브": "배당/밸류업",
    # 신재생/2차전지
    "KODEX 신재생에너지액티브": "신재생/2차전지",
    "TIMEFOLIO K신재생에너지액티브": "신재생/2차전지",
    "RISE 2차전지액티브": "신재생/2차전지",
    "TIMEFOLIO K이노베이션액티브": "신재생/2차전지",
    # 로봇/우주/조선
    "KODEX 친환경조선해운액티브": "로봇/우주/조선",
    "KoAct K수출핵심기업TOP30액티브": "로봇/우주/조선",
    "KODEX 로봇액티브": "로봇/우주/조선",
    # 소비/컬처
    "VITA MZ소비액티브": "소비/컬처",
    "TIMEFOLIO K컬처액티브": "소비/컬처",
    # 코스닥
    "KoAct 코스닥액티브": "코스닥",
    "TIMEFOLIO 코스닥액티브": "코스닥",
    # 대형/테크
    "SOL 코리아메가테크액티브": "대형/테크",
    # 기타
    "WON K-글로벌수급상위": "기타",
    "TIMEFOLIO 코스피액티브": "기타",
    "KODEX 200액티브": "기타",
}

# 섹터 탭 표시 순서
SECTOR_ORDER = ["전체", "반도체", "바이오", "배당/밸류업", "신재생/2차전지", "로봇/우주/조선", "소비/컬처", "코스닥", "대형/테크", "기타"]
