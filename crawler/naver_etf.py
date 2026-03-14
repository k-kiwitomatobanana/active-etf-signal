"""
네이버 증권 ETF 구성종목 크롤러.
각 ETF의 구성종목(종목명, 주식수, 비중)을 수집하여 SQLite에 날짜별로 저장한다.
"""

import logging
import random
import re
import sqlite3
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

from config import CRAWL_HEADERS, CRAWL_SLEEP, DB_PATH, ETF_LIST

logger = logging.getLogger(__name__)


def get_db_connection() -> sqlite3.Connection:
    """SQLite DB 연결을 반환한다."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """DB 테이블 및 인덱스를 초기화한다."""
    conn = get_db_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS etf_master (
                etf_code TEXT PRIMARY KEY,
                etf_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS etf_holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                etf_code TEXT NOT NULL,
                collect_date DATE NOT NULL,
                stock_name TEXT NOT NULL,
                stock_count INTEGER,
                weight REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(etf_code, collect_date, stock_name)
            );

            CREATE INDEX IF NOT EXISTS idx_holdings_date
                ON etf_holdings(collect_date);
            CREATE INDEX IF NOT EXISTS idx_holdings_etf_date
                ON etf_holdings(etf_code, collect_date);
            CREATE INDEX IF NOT EXISTS idx_holdings_stock
                ON etf_holdings(stock_name, collect_date);
        """)

        # stock_price 컬럼 추가 (기존 데이터 보존)
        cols = [
            r[1] for r in conn.execute("PRAGMA table_info(etf_holdings)").fetchall()
        ]
        if "stock_price" not in cols:
            conn.execute("ALTER TABLE etf_holdings ADD COLUMN stock_price INTEGER")
            logger.info("etf_holdings 테이블에 stock_price 컬럼 추가")

        conn.commit()
        logger.info("DB 테이블 및 인덱스 초기화 완료")
    finally:
        conn.close()


def seed_etf_master():
    """config.py의 ETF_LIST를 etf_master 테이블에 시드한다."""
    conn = get_db_connection()
    try:
        for etf_name, etf_code in ETF_LIST.items():
            conn.execute(
                "INSERT OR REPLACE INTO etf_master (etf_code, etf_name) VALUES (?, ?)",
                (etf_code, etf_name),
            )
        conn.commit()
        logger.info("ETF 마스터 테이블 시드 완료: %d건", len(ETF_LIST))
    finally:
        conn.close()


def fetch_holdings(etf_code: str) -> list:
    """
    네이버 증권에서 ETF 구성종목 데이터를 크롤링한다.
    main.naver 페이지의 etf_asset 섹션에서 구성종목을 파싱한다.

    Args:
        etf_code: ETF 종목코드

    Returns:
        구성종목 리스트 [{"stock_name": str, "stock_count": int, "weight": float, "stock_price": int|None}, ...]
    """
    url = f"https://finance.naver.com/item/main.naver?code={etf_code}"

    try:
        resp = requests.get(url, headers=CRAWL_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("크롤링 요청 실패 [%s]: %s", etf_code, e)
        return []

    # 인코딩 처리: Content-Type은 euc-kr이지만 실제는 utf-8인 경우가 있음
    # meta charset을 우선 확인하고, utf-8 시도 후 실패하면 euc-kr로 fallback
    try:
        html = resp.content.decode("utf-8")
    except UnicodeDecodeError:
        html = resp.content.decode("euc-kr", errors="replace")

    return _parse_holdings_html(html, etf_code)


def _parse_holdings_html(html: str, etf_code: str) -> list:
    """
    ETF 구성종목 HTML의 etf_asset 섹션을 파싱한다.

    Args:
        html: HTML 문자열
        etf_code: ETF 종목코드 (로깅용)

    Returns:
        구성종목 리스트
    """
    holdings = []

    # etf_asset 섹션 추출
    soup = BeautifulSoup(html, "lxml")
    section = soup.find("div", class_="section etf_asset")
    if not section:
        logger.warning("etf_asset 섹션 없음 [%s]", etf_code)
        return []

    rows = section.find_all("tr")

    for row in rows:
        # 종목 링크가 있는 행만 처리
        link = row.find("a", href=re.compile(r"/item/main\.naver\?code="))
        if not link:
            continue

        tds = row.find_all("td")
        if len(tds) < 3:
            continue

        try:
            stock_name = tds[0].get_text(strip=True)
            if not stock_name:
                continue

            count_text = tds[1].get_text(strip=True).replace(",", "")
            stock_count = int(count_text) if count_text else None

            weight_text = tds[2].get_text(strip=True).replace("%", "")
            weight = float(weight_text) if weight_text else None

            if stock_count is None or weight is None:
                continue

            # td[3]: 시세(현재가)
            stock_price = None
            if len(tds) > 3:
                price_text = tds[3].get_text(strip=True).replace(",", "")
                stock_price = int(price_text) if price_text.isdigit() else None

            holdings.append({
                "stock_name": stock_name,
                "stock_count": stock_count,
                "weight": weight,
                "stock_price": stock_price,
            })
        except (ValueError, IndexError) as e:
            logger.warning("파싱 오류 [%s] row: %s - %s", etf_code, row.get_text(), e)
            continue

    return holdings


def is_data_changed(etf_code: str, new_holdings: list, conn: sqlite3.Connection) -> bool:
    """
    직전 수집일 데이터와 비교하여 변경 여부를 확인한다.

    Args:
        etf_code: ETF 종목코드
        new_holdings: 새로 크롤링한 구성종목 리스트
        conn: DB 연결

    Returns:
        True면 변경됨 (저장 필요), False면 동일 (저장 불필요)
    """
    if not new_holdings:
        return False

    # 직전 수집일의 데이터 조회
    row = conn.execute(
        "SELECT MAX(collect_date) as latest_date FROM etf_holdings WHERE etf_code = ?",
        (etf_code,),
    ).fetchone()

    if not row or not row["latest_date"]:
        return True  # 이전 데이터 없음 → 저장 필요

    latest_date = row["latest_date"]
    prev_holdings = conn.execute(
        "SELECT stock_name, stock_count, weight, stock_price FROM etf_holdings "
        "WHERE etf_code = ? AND collect_date = ? ORDER BY stock_name",
        (etf_code, latest_date),
    ).fetchall()

    if len(prev_holdings) != len(new_holdings):
        return True

    # 새 데이터를 종목명 기준으로 정렬하여 비교 (stock_price 포함)
    prev_set = {
        (r["stock_name"], r["stock_count"], r["weight"], r["stock_price"])
        for r in prev_holdings
    }
    new_set = {
        (h["stock_name"], h["stock_count"], h["weight"], h.get("stock_price"))
        for h in new_holdings
    }

    return prev_set != new_set


def save_holdings(
    etf_code: str, holdings: list, collect_date: str, conn: sqlite3.Connection
):
    """
    구성종목 데이터를 날짜별로 저장한다.

    Args:
        etf_code: ETF 종목코드
        holdings: 구성종목 리스트
        collect_date: 수집 날짜 (YYYY-MM-DD)
        conn: DB 연결
    """
    for h in holdings:
        conn.execute(
            "INSERT OR REPLACE INTO etf_holdings "
            "(etf_code, collect_date, stock_name, stock_count, weight, stock_price) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                etf_code, collect_date, h["stock_name"],
                h["stock_count"], h["weight"], h.get("stock_price"),
            ),
        )


def collect_single_etf(etf_name: str, etf_code: str, collect_date: str) -> dict:
    """
    단일 ETF의 구성종목을 수집하고 DB에 저장한다.

    Args:
        etf_name: ETF 이름
        etf_code: ETF 종목코드
        collect_date: 수집 날짜

    Returns:
        수집 결과 {"etf_name": str, "status": str, "count": int}
    """
    result = {"etf_name": etf_name, "etf_code": etf_code, "status": "skip", "count": 0}

    try:
        holdings = fetch_holdings(etf_code)
        if not holdings:
            result["status"] = "empty"
            logger.warning("구성종목 데이터 없음: %s [%s]", etf_name, etf_code)
            return result

        conn = get_db_connection()
        try:
            if is_data_changed(etf_code, holdings, conn):
                save_holdings(etf_code, holdings, collect_date, conn)
                conn.commit()
                result["status"] = "saved"
                result["count"] = len(holdings)
                logger.info(
                    "저장 완료: %s [%s] - %d종목", etf_name, etf_code, len(holdings)
                )
            else:
                result["status"] = "unchanged"
                logger.info("변경 없음 (저장 스킵): %s [%s]", etf_name, etf_code)
        finally:
            conn.close()

    except Exception as e:
        result["status"] = "error"
        logger.error("수집 실패: %s [%s] - %s", etf_name, etf_code, e)

    return result


def collect_all_etf_data() -> list:
    """
    모든 ETF의 구성종목 데이터를 수집한다.
    크롤링 실패 시 해당 ETF만 스킵하고 나머지를 계속 수집한다.

    Returns:
        각 ETF의 수집 결과 리스트
    """
    today = date.today().strftime("%Y-%m-%d")
    results = []

    logger.info("=== 전체 ETF 데이터 수집 시작 (%s) ===", today)

    for i, (etf_name, etf_code) in enumerate(ETF_LIST.items()):
        if i > 0:
            time.sleep(CRAWL_SLEEP + random.uniform(0.0, 0.7))

        result = collect_single_etf(etf_name, etf_code, today)
        results.append(result)

    saved = sum(1 for r in results if r["status"] == "saved")
    unchanged = sum(1 for r in results if r["status"] == "unchanged")
    errors = sum(1 for r in results if r["status"] in ("error", "empty"))

    logger.info(
        "=== 수집 완료: 저장 %d / 변경없음 %d / 오류 %d ===",
        saved, unchanged, errors,
    )

    return results
