"""
시그널 분석 모듈.
SQLite에 날짜별로 저장된 ETF 구성종목 데이터를 기반으로
매수/매도 시그널, 중복 매수 분석, 비중 변화 추적을 수행한다.
"""

import logging
import sqlite3

from config import DB_PATH

logger = logging.getLogger(__name__)


def get_db_connection() -> sqlite3.Connection:
    """SQLite DB 연결을 반환한다."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_collect_dates(conn: sqlite3.Connection, limit: int = 30) -> list:
    """
    DB에 저장된 수집 날짜 목록을 최신순으로 반환한다.

    Args:
        conn: DB 연결
        limit: 최대 반환 개수

    Returns:
        날짜 문자열 리스트 (최신순)
    """
    rows = conn.execute(
        "SELECT DISTINCT collect_date FROM etf_holdings "
        "ORDER BY collect_date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [r["collect_date"] for r in rows]


def get_top_buy_increase(days: int = 3, top_n: int = 50) -> list:
    """
    최근 N일간 액티브 ETF들에서 비중이 증가한 종목을 집계한다.

    계산 로직 (v3 - 날짜별 순차 비교):
    1. 기간 내 수집 날짜 목록 조회 (예: 3일 → [03-13, 03-12, 03-11, 03-10])
    2. 연속 날짜쌍별 비교 (03-13↔03-12, 03-12↔03-11, 03-11↔03-10)
    3. 각 날짜쌍에서 ETF별 비중 변화 → ETF별 개별 판단
    4. 기간 내 비중이 증가한 날이 1일이라도 있으면 매수 Top 후보
    5. 정렬: 거래대금 순증감 합계 > 비중 순증감 > ETF수

    Args:
        days: 비교 기간 (일)
        top_n: 반환할 상위 종목 수

    Returns:
        [{"stock_name", "etf_count", "total_increase", "weight_change",
          "stock_price", "trade_amount", "daily_changes"}, ...]
    """
    conn = get_db_connection()
    try:
        # 기간 + 1개의 날짜 필요 (days개 날짜쌍 = days+1개 날짜)
        all_dates = get_collect_dates(conn, limit=days + 1)
        if len(all_dates) < 2:
            return []

        # 사용할 날짜 목록 (최대 days+1개, 최신순)
        date_window = all_dates[:days + 1]

        # 종목별 집계 딕셔너리
        # stock_map[stock_name] = {
        #   "daily_changes": [{"date", "trade_amount", "weight_change", "stock_change", "etf_count"}, ...],
        #   "total_trade_amount": int,
        #   "total_weight_change": float,
        #   "total_stock_change": int,
        #   "max_etf_count": int,
        #   "has_increase": bool,  # 비중 증가한 날이 1일이라도 있는지
        #   "stock_price": int,
        # }
        stock_map = {}

        # 연속 날짜쌍별 비교 (최신→과거 방향)
        for i in range(len(date_window) - 1):
            curr_date = date_window[i]
            prev_date = date_window[i + 1]

            # 현재일 구성종목 조회
            curr_rows = conn.execute(
                "SELECT etf_code, stock_name, stock_count, weight, stock_price "
                "FROM etf_holdings WHERE collect_date = ?",
                (curr_date,),
            ).fetchall()

            # 이전일 구성종목 조회 (청산 종목의 가격 참조를 위해 stock_price 포함)
            prev_rows = conn.execute(
                "SELECT etf_code, stock_name, stock_count, weight, stock_price "
                "FROM etf_holdings WHERE collect_date = ?",
                (prev_date,),
            ).fetchall()

            # 현재일/이전일 데이터 매핑: (etf_code, stock_name) → {stock_count, weight, stock_price}
            curr_map = {}
            for r in curr_rows:
                curr_map[(r["etf_code"], r["stock_name"])] = {
                    "stock_count": r["stock_count"] or 0,
                    "weight": r["weight"] or 0,
                    "stock_price": r["stock_price"] or 0,
                }

            prev_map = {}
            for r in prev_rows:
                prev_map[(r["etf_code"], r["stock_name"])] = {
                    "stock_count": r["stock_count"] or 0,
                    "weight": r["weight"] or 0,
                    "stock_price": r["stock_price"] or 0,
                }

            # 날짜쌍별 종목 집계 (curr + prev 합집합으로 비교, 신규편입·청산 모두 감지)
            day_stock = {}
            all_keys = set(curr_map.keys()) | set(prev_map.keys())
            for key in all_keys:
                curr = curr_map.get(key, {"stock_count": 0, "weight": 0, "stock_price": 0})
                prev = prev_map.get(key, {"stock_count": 0, "weight": 0, "stock_price": 0})

                sc = curr["stock_count"] - prev["stock_count"]
                wc = curr["weight"] - prev["weight"]

                # 비중 변화가 없으면 건너뜀
                if sc == 0 and abs(wc) < 0.0001:
                    continue

                name = key[1]  # stock_name
                # 가격: 현재일 우선, 없으면 이전일 (청산 종목 대비)
                price = curr["stock_price"] or prev["stock_price"]

                if name not in day_stock:
                    day_stock[name] = {
                        "stock_change": 0,
                        "weight_change": 0.0,
                        "etf_count": 0,
                        "stock_price": 0,
                    }

                day_stock[name]["stock_change"] += sc
                day_stock[name]["weight_change"] += wc
                day_stock[name]["etf_count"] += 1
                if price and not day_stock[name]["stock_price"]:
                    day_stock[name]["stock_price"] = price

            # 종목별 누적 집계
            for name, ds in day_stock.items():
                price = ds["stock_price"]
                # 거래대금 = 주식수 변화(절댓값) × 종가, 부호는 stock_change를 따름
                if ds["stock_change"] > 0:
                    trade_amount = ds["stock_change"] * price
                elif ds["stock_change"] < 0:
                    trade_amount = ds["stock_change"] * price  # 음수
                else:
                    # 주식수 변화 없지만 비중 변화 있는 경우
                    trade_amount = 0

                daily_entry = {
                    "date": curr_date,
                    "trade_amount": trade_amount,
                    "weight_change": round(ds["weight_change"], 2),
                    "stock_change": ds["stock_change"],
                    "etf_count": ds["etf_count"],
                }

                if name not in stock_map:
                    stock_map[name] = {
                        "stock_name": name,
                        "daily_changes": [],
                        "total_trade_amount": 0,
                        "total_weight_change": 0.0,
                        "total_stock_change": 0,
                        "max_etf_count": 0,
                        "has_increase": False,
                        "stock_price": 0,
                    }

                stock_map[name]["daily_changes"].append(daily_entry)
                stock_map[name]["total_trade_amount"] += trade_amount
                stock_map[name]["total_weight_change"] += ds["weight_change"]
                stock_map[name]["total_stock_change"] += ds["stock_change"]
                if ds["etf_count"] > stock_map[name]["max_etf_count"]:
                    stock_map[name]["max_etf_count"] = ds["etf_count"]
                if price and not stock_map[name]["stock_price"]:
                    stock_map[name]["stock_price"] = price

                # 비중 증가한 날이 있으면 매수 후보
                if ds["weight_change"] > 0:
                    stock_map[name]["has_increase"] = True

        # 매수 후보: 비중 증가한 날이 1일이라도 있는 종목
        result = []
        for name, s in stock_map.items():
            if not s["has_increase"]:
                continue

            result.append({
                "stock_name": s["stock_name"],
                "etf_count": s["max_etf_count"],
                "total_increase": max(s["total_stock_change"], 0),  # 순증가 합계
                "weight_change": round(s["total_weight_change"], 2),
                "stock_price": s["stock_price"],
                "trade_amount": s["total_trade_amount"],
                "daily_changes": s["daily_changes"],  # 최신→과거 순
            })

        # 정렬: 거래대금 순증감 합계 > 비중 순증감 > ETF수
        result.sort(key=lambda x: (-x["trade_amount"], -x["weight_change"], -x["etf_count"]))
        return result[:top_n]

    finally:
        conn.close()


def get_top_sell_increase(days: int = 3, top_n: int = 50) -> list:
    """
    최근 N일간 액티브 ETF들에서 비중이 감소한 종목을 집계한다.
    부분 매도(주식수 감소)와 완전 청산 모두 포함.

    계산 로직 (v3 - 날짜별 순차 비교):
    1. 기간 내 수집 날짜 목록 조회 (예: 3일 → [03-13, 03-12, 03-11, 03-10])
    2. 연속 날짜쌍별 비교 (03-13↔03-12, 03-12↔03-11, 03-11↔03-10)
    3. 각 날짜쌍에서 ETF별 비중 변화 → ETF별 개별 판단
    4. 기간 내 비중이 감소한 날이 1일이라도 있으면 매도 Top 후보
    5. 정렬: 거래대금 순감소 합계가 큰 순 (가장 많이 빠진 게 1위)

    Args:
        days: 비교 기간 (일)
        top_n: 반환할 상위 종목 수

    Returns:
        [{"stock_name", "etf_count", "total_decrease", "weight_change",
          "stock_price", "trade_amount", "daily_changes"}, ...]
    """
    conn = get_db_connection()
    try:
        # 기간 + 1개의 날짜 필요 (days개 날짜쌍 = days+1개 날짜)
        all_dates = get_collect_dates(conn, limit=days + 1)
        if len(all_dates) < 2:
            return []

        # 사용할 날짜 목록 (최대 days+1개, 최신순)
        date_window = all_dates[:days + 1]

        # 종목별 집계 딕셔너리
        stock_map = {}

        # 연속 날짜쌍별 비교 (최신→과거 방향)
        for i in range(len(date_window) - 1):
            curr_date = date_window[i]
            prev_date = date_window[i + 1]

            # 현재일 구성종목 조회
            curr_rows = conn.execute(
                "SELECT etf_code, stock_name, stock_count, weight, stock_price "
                "FROM etf_holdings WHERE collect_date = ?",
                (curr_date,),
            ).fetchall()

            # 이전일 구성종목 조회 (완전 청산 감지를 위해 stock_price 포함)
            prev_rows = conn.execute(
                "SELECT etf_code, stock_name, stock_count, weight, stock_price "
                "FROM etf_holdings WHERE collect_date = ?",
                (prev_date,),
            ).fetchall()

            # 현재일/이전일 데이터 매핑
            curr_map = {}
            for r in curr_rows:
                curr_map[(r["etf_code"], r["stock_name"])] = {
                    "stock_count": r["stock_count"] or 0,
                    "weight": r["weight"] or 0,
                    "stock_price": r["stock_price"] or 0,
                }

            prev_map = {}
            for r in prev_rows:
                prev_map[(r["etf_code"], r["stock_name"])] = {
                    "stock_count": r["stock_count"] or 0,
                    "weight": r["weight"] or 0,
                    "stock_price": r["stock_price"] or 0,
                }

            # 날짜쌍별 종목 집계 (curr + prev 합집합으로 비교, 신규편입·청산 모두 감지)
            day_stock = {}
            all_keys = set(curr_map.keys()) | set(prev_map.keys())
            for key in all_keys:
                curr = curr_map.get(key, {"stock_count": 0, "weight": 0, "stock_price": 0})
                prev = prev_map.get(key, {"stock_count": 0, "weight": 0, "stock_price": 0})

                sc = curr["stock_count"] - prev["stock_count"]
                wc = curr["weight"] - prev["weight"]

                # 비중 변화가 없으면 건너뜀
                if sc == 0 and abs(wc) < 0.0001:
                    continue

                name = key[1]  # stock_name
                # 가격: 현재일 우선, 없으면 이전일
                price = curr["stock_price"] or prev["stock_price"]

                if name not in day_stock:
                    day_stock[name] = {
                        "stock_change": 0,
                        "weight_change": 0.0,
                        "etf_count": 0,
                        "stock_price": 0,
                    }

                day_stock[name]["stock_change"] += sc
                day_stock[name]["weight_change"] += wc
                day_stock[name]["etf_count"] += 1
                if price and not day_stock[name]["stock_price"]:
                    day_stock[name]["stock_price"] = price

            # 종목별 누적 집계
            for name, ds in day_stock.items():
                price = ds["stock_price"]
                # 거래대금: 주식수 변화에 종가 곱셈 (부호 포함)
                if ds["stock_change"] != 0:
                    trade_amount = ds["stock_change"] * price
                else:
                    trade_amount = 0

                daily_entry = {
                    "date": curr_date,
                    "trade_amount": trade_amount,
                    "weight_change": round(ds["weight_change"], 2),
                    "stock_change": ds["stock_change"],
                    "etf_count": ds["etf_count"],
                }

                if name not in stock_map:
                    stock_map[name] = {
                        "stock_name": name,
                        "daily_changes": [],
                        "total_trade_amount": 0,
                        "total_weight_change": 0.0,
                        "total_stock_change": 0,
                        "max_etf_count": 0,
                        "has_decrease": False,
                        "stock_price": 0,
                    }

                stock_map[name]["daily_changes"].append(daily_entry)
                stock_map[name]["total_trade_amount"] += trade_amount
                stock_map[name]["total_weight_change"] += ds["weight_change"]
                stock_map[name]["total_stock_change"] += ds["stock_change"]
                if ds["etf_count"] > stock_map[name]["max_etf_count"]:
                    stock_map[name]["max_etf_count"] = ds["etf_count"]
                if price and not stock_map[name]["stock_price"]:
                    stock_map[name]["stock_price"] = price

                # 비중 감소한 날이 있으면 매도 후보
                if ds["weight_change"] < 0:
                    stock_map[name]["has_decrease"] = True

        # 매도 후보: 비중 감소한 날이 1일이라도 있는 종목
        result = []
        for name, s in stock_map.items():
            if not s["has_decrease"]:
                continue

            # total_decrease: 순감소 합계 (양수로 표현)
            total_decrease = abs(min(s["total_stock_change"], 0))

            result.append({
                "stock_name": s["stock_name"],
                "etf_count": s["max_etf_count"],
                "total_decrease": total_decrease,
                "weight_change": round(s["total_weight_change"], 2),
                "stock_price": s["stock_price"],
                "trade_amount": s["total_trade_amount"],
                "daily_changes": s["daily_changes"],  # 최신→과거 순
            })

        # 정렬: 거래대금 순감소 합계(가장 음수인 것이 1위) → 비중 감소 → ETF수
        result.sort(key=lambda x: (x["trade_amount"], x["weight_change"], -x["etf_count"]))
        return result[:top_n]

    finally:
        conn.close()


def get_stock_daily_changes(stock_name: str, days: int = 10) -> dict:
    """
    특정 종목의 날짜별 전체 ETF 합산 주식수 변화·비중 변화·거래대금을 반환한다.

    Args:
        stock_name: 종목명
        days: 최근 N개 날짜쌍 (연속 수집일 기준)

    Returns:
        {
            "stock_name": str,
            "changes": [
                {"date", "prev_date", "stock_change", "weight_change",
                 "trade_amount", "etf_count", "stock_price"}, ...
            ]
        }
    """
    conn = get_db_connection()
    try:
        dates = get_collect_dates(conn, limit=days + 1)
        if len(dates) < 2:
            return {"stock_name": stock_name, "changes": []}

        changes = []
        for i in range(len(dates) - 1):
            curr_date = dates[i]
            prev_date = dates[i + 1]

            # 현재일 데이터
            curr_rows = conn.execute(
                "SELECT etf_code, stock_count, weight, stock_price "
                "FROM etf_holdings WHERE stock_name = ? AND collect_date = ?",
                (stock_name, curr_date),
            ).fetchall()

            # 이전일 데이터
            prev_rows = conn.execute(
                "SELECT etf_code, stock_count, weight, stock_price "
                "FROM etf_holdings WHERE stock_name = ? AND collect_date = ?",
                (stock_name, prev_date),
            ).fetchall()

            curr_map = {
                r["etf_code"]: {
                    "stock_count": r["stock_count"] or 0,
                    "weight": r["weight"] or 0,
                    "stock_price": r["stock_price"] or 0,
                }
                for r in curr_rows
            }
            prev_map = {
                r["etf_code"]: {
                    "stock_count": r["stock_count"] or 0,
                    "weight": r["weight"] or 0,
                    "stock_price": r["stock_price"] or 0,
                }
                for r in prev_rows
            }

            all_etfs = set(curr_map.keys()) | set(prev_map.keys())
            total_stock_change = 0
            total_weight_change = 0.0
            etf_count = 0
            stock_price = 0

            for etf in all_etfs:
                curr = curr_map.get(etf, {"stock_count": 0, "weight": 0, "stock_price": 0})
                prev = prev_map.get(etf, {"stock_count": 0, "weight": 0, "stock_price": 0})
                sc = curr["stock_count"] - prev["stock_count"]
                wc = curr["weight"] - prev["weight"]

                if sc != 0 or wc != 0:
                    total_stock_change += sc
                    total_weight_change += wc
                    etf_count += 1

                # 대표 가격: 현재일 가격 우선
                if not stock_price and curr["stock_price"]:
                    stock_price = curr["stock_price"]
                if not stock_price and prev["stock_price"]:
                    stock_price = prev["stock_price"]

            changes.append({
                "date": curr_date,
                "prev_date": prev_date,
                "stock_change": total_stock_change,
                "weight_change": round(total_weight_change, 2),
                "trade_amount": abs(total_stock_change) * stock_price,
                "etf_count": etf_count,
                "stock_price": stock_price,
            })

        return {"stock_name": stock_name, "changes": changes}

    finally:
        conn.close()


def get_overlapping_stocks(top_n: int = 30) -> list:
    """
    최신일 기준 여러 액티브 ETF가 동시에 보유한 종목을 분석한다.

    계산 로직:
    1. DB에서 최신 collect_date의 모든 ETF 구성종목 조회
    2. 종목별로 보유 ETF 수 카운트
    3. 2개 이상 ETF가 보유한 종목만 필터
    4. 보유 ETF 수 기준 내림차순, 동률 시 총 비중합 기준 정렬

    Args:
        top_n: 반환할 상위 종목 수

    Returns:
        [{"stock_name", "etf_count", "etf_names", "total_weight", "avg_weight"}, ...]
    """
    conn = get_db_connection()
    try:
        dates = get_collect_dates(conn, limit=1)
        if not dates:
            return []

        latest_date = dates[0]

        rows = conn.execute(
            "SELECT h.stock_name, h.etf_code, h.weight, m.etf_name "
            "FROM etf_holdings h "
            "LEFT JOIN etf_master m ON h.etf_code = m.etf_code "
            "WHERE h.collect_date = ?",
            (latest_date,),
        ).fetchall()

        # 종목별 집계
        stock_map = {}
        for r in rows:
            name = r["stock_name"]
            if name not in stock_map:
                stock_map[name] = {
                    "stock_name": name,
                    "etf_count": 0,
                    "etf_names": [],
                    "total_weight": 0.0,
                }
            stock_map[name]["etf_count"] += 1
            etf_display = r["etf_name"] or r["etf_code"]
            stock_map[name]["etf_names"].append(etf_display)
            stock_map[name]["total_weight"] += r["weight"] or 0

        # 2개 이상 보유 필터 + 평균 비중 계산
        result = []
        for s in stock_map.values():
            if s["etf_count"] >= 2:
                s["total_weight"] = round(s["total_weight"], 2)
                s["avg_weight"] = round(s["total_weight"] / s["etf_count"], 2)
                s["etf_names"] = sorted(s["etf_names"])
                result.append(s)

        result.sort(key=lambda x: (-x["etf_count"], -x["total_weight"]))
        return result[:top_n]

    finally:
        conn.close()


def get_weight_increase_signals(top_n: int = 30) -> list:
    """
    최신일 기준 비중 증가 시그널을 계산한다.

    계산 로직:
    1. DB에서 최근 수집된 날짜들 조회
    2. 연속 날짜 간 종목별 비중 변화량 계산
    3. 비중 증가합 = 모든 ETF에서 해당 종목의 비중 증가분 합산
    4. 증가 ETF 수 = 해당 종목의 비중이 증가한 ETF 개수
    5. 연속 증가일 = 최신일부터 역순으로 비중이 연속 증가한 일수

    Args:
        top_n: 반환할 상위 종목 수

    Returns:
        [{"stock_name", "weight_increase", "etf_count", "consecutive_days"}, ...]
    """
    conn = get_db_connection()
    try:
        dates = get_collect_dates(conn, limit=10)
        if len(dates) < 2:
            return []

        latest_date = dates[0]
        prev_date = dates[1]

        # 최신일과 직전일의 비중 변화 계산
        latest_data = conn.execute(
            "SELECT etf_code, stock_name, weight "
            "FROM etf_holdings WHERE collect_date = ?",
            (latest_date,),
        ).fetchall()

        prev_data = conn.execute(
            "SELECT etf_code, stock_name, weight "
            "FROM etf_holdings WHERE collect_date = ?",
            (prev_date,),
        ).fetchall()

        prev_map = {}
        for r in prev_data:
            prev_map[(r["etf_code"], r["stock_name"])] = r["weight"] or 0

        # 종목별 비중 증가 집계
        stock_signals = {}
        for r in latest_data:
            key = (r["etf_code"], r["stock_name"])
            curr_weight = r["weight"] or 0
            prev_weight = prev_map.get(key, 0)
            delta = curr_weight - prev_weight

            if delta > 0:
                name = r["stock_name"]
                if name not in stock_signals:
                    stock_signals[name] = {
                        "stock_name": name,
                        "weight_increase": 0.0,
                        "etf_count": 0,
                        "consecutive_days": 0,
                    }
                stock_signals[name]["weight_increase"] += round(delta, 4)
                stock_signals[name]["etf_count"] += 1

        # 연속 증가일 계산 + 증가 날짜 목록
        for stock_name in stock_signals:
            cons_result = _calc_consecutive_days(
                conn, stock_name, dates, direction="up"
            )
            stock_signals[stock_name]["consecutive_days"] = cons_result["count"]
            stock_signals[stock_name]["increase_dates"] = cons_result["dates"]
            stock_signals[stock_name]["weight_increase"] = round(
                stock_signals[stock_name]["weight_increase"], 2
            )

        result = sorted(
            stock_signals.values(),
            key=lambda x: (-x["weight_increase"], -x["etf_count"]),
        )
        return result[:top_n]

    finally:
        conn.close()


def get_weight_decrease_signals(top_n: int = 30) -> list:
    """
    최신일 기준 비중 감소 시그널을 계산한다.

    계산 로직: 비중 증가 시그널과 동일하되 감소 방향.

    Args:
        top_n: 반환할 상위 종목 수

    Returns:
        [{"stock_name", "weight_decrease", "etf_count", "consecutive_days"}, ...]
    """
    conn = get_db_connection()
    try:
        dates = get_collect_dates(conn, limit=10)
        if len(dates) < 2:
            return []

        latest_date = dates[0]
        prev_date = dates[1]

        latest_data = conn.execute(
            "SELECT etf_code, stock_name, weight "
            "FROM etf_holdings WHERE collect_date = ?",
            (latest_date,),
        ).fetchall()

        prev_data = conn.execute(
            "SELECT etf_code, stock_name, weight "
            "FROM etf_holdings WHERE collect_date = ?",
            (prev_date,),
        ).fetchall()

        prev_map = {}
        for r in prev_data:
            prev_map[(r["etf_code"], r["stock_name"])] = r["weight"] or 0

        stock_signals = {}
        for r in latest_data:
            key = (r["etf_code"], r["stock_name"])
            curr_weight = r["weight"] or 0
            prev_weight = prev_map.get(key, 0)
            delta = curr_weight - prev_weight

            if delta < 0:
                name = r["stock_name"]
                if name not in stock_signals:
                    stock_signals[name] = {
                        "stock_name": name,
                        "weight_decrease": 0.0,
                        "etf_count": 0,
                        "consecutive_days": 0,
                    }
                stock_signals[name]["weight_decrease"] += round(abs(delta), 4)
                stock_signals[name]["etf_count"] += 1

        for stock_name in stock_signals:
            cons_result = _calc_consecutive_days(
                conn, stock_name, dates, direction="down"
            )
            stock_signals[stock_name]["consecutive_days"] = cons_result["count"]
            stock_signals[stock_name]["decrease_dates"] = cons_result["dates"]
            stock_signals[stock_name]["weight_decrease"] = round(
                stock_signals[stock_name]["weight_decrease"], 2
            )

        result = sorted(
            stock_signals.values(),
            key=lambda x: (-x["weight_decrease"], -x["etf_count"]),
        )
        return result[:top_n]

    finally:
        conn.close()


def _calc_consecutive_days(
    conn: sqlite3.Connection, stock_name: str, dates: list, direction: str
) -> dict:
    """
    특정 종목의 비중이 연속으로 증가/감소한 일수, 해당 날짜, 날짜별 거래대금을 계산한다.

    Args:
        conn: DB 연결
        stock_name: 종목명
        dates: 수집 날짜 리스트 (최신순)
        direction: "up" 또는 "down"

    Returns:
        {"count": 연속일수,
         "dates": [{"date": "YYYY-MM-DD", "trade_amount": int}, ...] (최신순)}
    """
    consecutive = 0
    change_dates = []

    for i in range(len(dates) - 1):
        curr_date = dates[i]
        prev_date = dates[i + 1]

        # 현재/이전 날짜의 해당 종목 비중·주식수·가격 조회
        curr_rows = conn.execute(
            "SELECT etf_code, weight, stock_count, stock_price "
            "FROM etf_holdings WHERE stock_name = ? AND collect_date = ?",
            (stock_name, curr_date),
        ).fetchall()

        prev_rows = conn.execute(
            "SELECT etf_code, weight, stock_count, stock_price "
            "FROM etf_holdings WHERE stock_name = ? AND collect_date = ?",
            (stock_name, prev_date),
        ).fetchall()

        # 평균 비중 계산
        curr_weights = [r["weight"] for r in curr_rows if r["weight"] is not None]
        prev_weights = [r["weight"] for r in prev_rows if r["weight"] is not None]
        curr_avg = sum(curr_weights) / len(curr_weights) if curr_weights else 0
        prev_avg = sum(prev_weights) / len(prev_weights) if prev_weights else 0

        if direction == "up" and curr_avg > prev_avg:
            consecutive += 1
        elif direction == "down" and curr_avg < prev_avg:
            consecutive += 1
        else:
            break

        # 날짜별 거래대금 계산 (주식수 변화 × 가격)
        curr_map = {r["etf_code"]: r for r in curr_rows}
        prev_map = {r["etf_code"]: r for r in prev_rows}
        total_trade = 0
        stock_price = 0

        for etf_code in set(curr_map.keys()) | set(prev_map.keys()):
            c = curr_map.get(etf_code)
            p = prev_map.get(etf_code)
            c_count = (c["stock_count"] or 0) if c else 0
            p_count = (p["stock_count"] or 0) if p else 0
            diff = c_count - p_count
            # 대표 가격
            price = 0
            if c and c["stock_price"]:
                price = c["stock_price"]
            elif p and p["stock_price"]:
                price = p["stock_price"]
            total_trade += abs(diff) * price
            if not stock_price and price:
                stock_price = price

        change_dates.append({"date": curr_date, "trade_amount": total_trade})

    return {"count": consecutive, "dates": change_dates}


def get_etf_holdings(etf_code: str) -> list:
    """
    특정 ETF의 최신 구성종목을 조회한다.

    Args:
        etf_code: ETF 종목코드

    Returns:
        [{"stock_name", "stock_count", "weight"}, ...]
    """
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT MAX(collect_date) as latest_date "
            "FROM etf_holdings WHERE etf_code = ?",
            (etf_code,),
        ).fetchone()

        if not row or not row["latest_date"]:
            return []

        rows = conn.execute(
            "SELECT stock_name, stock_count, weight "
            "FROM etf_holdings WHERE etf_code = ? AND collect_date = ? "
            "ORDER BY weight DESC",
            (etf_code, row["latest_date"]),
        ).fetchall()

        return [dict(r) for r in rows]

    finally:
        conn.close()


def get_unique_stock_names() -> list:
    """
    DB 내 모든 고유 종목명을 가나다순으로 반환한다. (검색 자동완성용)

    Returns:
        종목명 문자열 리스트 (가나다순)
    """
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT stock_name FROM etf_holdings "
            "ORDER BY stock_name"
        ).fetchall()
        return [r["stock_name"] for r in rows]
    finally:
        conn.close()


def get_stock_weight_history(stock_name: str) -> dict:
    """
    특정 종목의 ETF별 비중 시계열 데이터를 반환한다.

    Args:
        stock_name: 종목명

    Returns:
        {
            "stock_name": str,
            "dates": [str, ...],
            "etfs": [{"etf_code": str, "etf_name": str,
                       "weights": [float|None, ...],
                       "amounts": [int|None, ...]}, ...],
            "avg_weights": [float|None, ...],
            "total_amounts": [int|None, ...]
        }
    """
    conn = get_db_connection()
    try:
        # 해당 종목이 포함된 모든 날짜 (오름차순)
        date_rows = conn.execute(
            "SELECT DISTINCT collect_date FROM etf_holdings "
            "WHERE stock_name = ? ORDER BY collect_date ASC",
            (stock_name,),
        ).fetchall()
        dates = [r["collect_date"] for r in date_rows]

        if not dates:
            return {
                "stock_name": stock_name,
                "dates": [],
                "etfs": [],
                "avg_weights": [],
                "total_amounts": [],
            }

        # 해당 종목을 보유한 모든 ETF 조회
        etf_rows = conn.execute(
            "SELECT DISTINCT h.etf_code, COALESCE(m.etf_name, h.etf_code) as etf_name "
            "FROM etf_holdings h "
            "LEFT JOIN etf_master m ON h.etf_code = m.etf_code "
            "WHERE h.stock_name = ? "
            "ORDER BY etf_name",
            (stock_name,),
        ).fetchall()

        # 날짜×ETF별 비중·수량·가격 데이터 조회
        placeholders = ",".join("?" for _ in dates)
        rows = conn.execute(
            "SELECT collect_date, etf_code, weight, stock_count, stock_price "
            "FROM etf_holdings "
            f"WHERE stock_name = ? AND collect_date IN ({placeholders}) "
            "ORDER BY collect_date",
            (stock_name, *dates),
        ).fetchall()

        # (날짜, ETF코드) → {weight, stock_count, stock_price} 매핑
        data_map = {}
        for r in rows:
            data_map[(r["collect_date"], r["etf_code"])] = {
                "weight": r["weight"],
                "stock_count": r["stock_count"],
                "stock_price": r["stock_price"],
            }

        # ETF별 시계열 구성
        etfs = []
        for etf in etf_rows:
            weights = []
            amounts = []
            for d in dates:
                entry = data_map.get((d, etf["etf_code"]))
                if entry and entry["weight"] is not None:
                    weights.append(round(entry["weight"], 4))
                else:
                    weights.append(None)
                if (entry and entry["stock_count"] is not None
                        and entry["stock_price"] is not None):
                    amounts.append(entry["stock_count"] * entry["stock_price"])
                else:
                    amounts.append(None)
            etfs.append({
                "etf_code": etf["etf_code"],
                "etf_name": etf["etf_name"],
                "weights": weights,
                "amounts": amounts,
            })

        # 날짜별 평균 비중 계산
        avg_weights = []
        for i, d in enumerate(dates):
            vals = [e["weights"][i] for e in etfs if e["weights"][i] is not None]
            if vals:
                avg_weights.append(round(sum(vals) / len(vals), 4))
            else:
                avg_weights.append(None)

        # 날짜별 전체 ETF 합산 금액
        total_amounts = []
        for i, d in enumerate(dates):
            vals = [e["amounts"][i] for e in etfs if e["amounts"][i] is not None]
            if vals:
                total_amounts.append(sum(vals))
            else:
                total_amounts.append(None)

        return {
            "stock_name": stock_name,
            "dates": dates,
            "etfs": etfs,
            "avg_weights": avg_weights,
            "total_amounts": total_amounts,
        }

    finally:
        conn.close()


def get_stock_overview() -> list:
    """
    최신 수집일 기준 전체 종목의 요약 정보를 반환한다.

    계산 로직:
    1. 최신 수집일의 모든 종목 조회
    2. 종목별 보유 ETF 수, 평균/총 비중 계산
    3. 직전 수집일 대비 평균 비중 변화 계산

    Returns:
        [{stock_name, etf_count, avg_weight, total_weight, max_weight,
          weight_change, total_amount, etf_names[]}, ...]
        etf_count DESC, total_weight DESC 정렬
    """
    conn = get_db_connection()
    try:
        dates = get_collect_dates(conn, limit=2)
        if not dates:
            return []

        latest_date = dates[0]

        # 최신일 전체 종목 조회 (stock_count, stock_price 포함)
        rows = conn.execute(
            "SELECT h.stock_name, h.etf_code, h.weight, "
            "h.stock_count, h.stock_price, "
            "COALESCE(m.etf_name, h.etf_code) as etf_name "
            "FROM etf_holdings h "
            "LEFT JOIN etf_master m ON h.etf_code = m.etf_code "
            "WHERE h.collect_date = ?",
            (latest_date,),
        ).fetchall()

        # 종목별 집계
        stock_map = {}
        for r in rows:
            name = r["stock_name"]
            weight = r["weight"] or 0
            if name not in stock_map:
                stock_map[name] = {
                    "stock_name": name,
                    "etf_count": 0,
                    "total_weight": 0.0,
                    "max_weight": 0.0,
                    "total_amount": 0,
                    "etf_names": [],
                    "weights": [],
                }
            stock_map[name]["etf_count"] += 1
            stock_map[name]["total_weight"] += weight
            stock_map[name]["weights"].append(weight)
            if weight > stock_map[name]["max_weight"]:
                stock_map[name]["max_weight"] = weight
            stock_map[name]["etf_names"].append(r["etf_name"])

            # 매수 금액 합산
            count = r["stock_count"]
            price = r["stock_price"]
            if count is not None and price is not None:
                stock_map[name]["total_amount"] += count * price

        # 직전일 데이터로 비중 변화 계산
        prev_avg_map = {}
        if len(dates) >= 2:
            prev_date = dates[1]
            prev_rows = conn.execute(
                "SELECT stock_name, AVG(weight) as avg_w "
                "FROM etf_holdings WHERE collect_date = ? "
                "GROUP BY stock_name",
                (prev_date,),
            ).fetchall()
            for r in prev_rows:
                prev_avg_map[r["stock_name"]] = r["avg_w"] or 0

        # 결과 조립
        result = []
        for s in stock_map.values():
            avg_weight = s["total_weight"] / s["etf_count"] if s["etf_count"] > 0 else 0
            prev_avg = prev_avg_map.get(s["stock_name"], 0)
            weight_change = avg_weight - prev_avg

            result.append({
                "stock_name": s["stock_name"],
                "etf_count": s["etf_count"],
                "avg_weight": round(avg_weight, 2),
                "total_weight": round(s["total_weight"], 2),
                "max_weight": round(s["max_weight"], 2),
                "weight_change": round(weight_change, 2),
                "total_amount": s["total_amount"],
                "etf_names": sorted(s["etf_names"]),
            })

        result.sort(key=lambda x: (-x["etf_count"], -x["total_weight"]))
        return result

    finally:
        conn.close()


def get_daily_snapshot(target_date: str = None) -> dict:
    """
    특정 날짜 하루 동안 액티브 ETF 전체에서 비중이 변한 종목을 집계한다.

    계산 로직:
    1. target_date가 None이면 최신 수집일 사용
    2. target_date가 수집일이 아니면 가장 가까운 이전 수집일로 스냅
    3. target_date와 직전 수집일 비교
    4. 종목별 집계: 거래대금(주식수변화×종가), ETF수, 비중변화합, 주식변화합, 종가
    5. curr + prev 합집합으로 비교 (신규편입·청산 모두 감지)
    6. 정렬: 거래대금 내림차순 (양수 위, 음수 아래)

    Args:
        target_date: 조회 날짜 (YYYY-MM-DD). None이면 최신 수집일.

    Returns:
        {
            "target_date": str,
            "prev_date": str,
            "stocks": [
                {"stock_name", "trade_amount", "etf_count",
                 "weight_change", "stock_change", "stock_price"}, ...
            ]
        }
    """
    conn = get_db_connection()
    try:
        # 전체 수집 날짜 목록 (최신순)
        all_dates = get_collect_dates(conn, limit=100)
        if len(all_dates) < 2:
            return {"target_date": None, "prev_date": None, "stocks": []}

        # target_date 결정: None이면 최신 수집일
        if target_date is None:
            snap_date = all_dates[0]
        else:
            # target_date가 수집일이 아니면 가장 가까운 이전 수집일로 스냅
            snap_date = None
            for d in all_dates:
                if d <= target_date:
                    snap_date = d
                    break
            if snap_date is None:
                snap_date = all_dates[-1]

        # snap_date의 직전 수집일 찾기
        snap_idx = all_dates.index(snap_date) if snap_date in all_dates else None
        if snap_idx is None or snap_idx + 1 >= len(all_dates):
            return {"target_date": snap_date, "prev_date": None, "stocks": []}

        prev_date = all_dates[snap_idx + 1]

        # target_date(curr) 구성종목 조회
        curr_rows = conn.execute(
            "SELECT etf_code, stock_name, stock_count, weight, stock_price "
            "FROM etf_holdings WHERE collect_date = ?",
            (snap_date,),
        ).fetchall()

        # 직전일(prev) 구성종목 조회
        prev_rows = conn.execute(
            "SELECT etf_code, stock_name, stock_count, weight, stock_price "
            "FROM etf_holdings WHERE collect_date = ?",
            (prev_date,),
        ).fetchall()

        # (etf_code, stock_name) → {stock_count, weight, stock_price} 매핑
        curr_map = {}
        for r in curr_rows:
            curr_map[(r["etf_code"], r["stock_name"])] = {
                "stock_count": r["stock_count"] or 0,
                "weight": r["weight"] or 0,
                "stock_price": r["stock_price"] or 0,
            }

        prev_map = {}
        for r in prev_rows:
            prev_map[(r["etf_code"], r["stock_name"])] = {
                "stock_count": r["stock_count"] or 0,
                "weight": r["weight"] or 0,
                "stock_price": r["stock_price"] or 0,
            }

        # curr + prev 합집합으로 비교 (신규편입·청산 모두 감지)
        stock_map = {}
        all_keys = set(curr_map.keys()) | set(prev_map.keys())
        for key in all_keys:
            curr = curr_map.get(key, {"stock_count": 0, "weight": 0, "stock_price": 0})
            prev = prev_map.get(key, {"stock_count": 0, "weight": 0, "stock_price": 0})

            sc = curr["stock_count"] - prev["stock_count"]
            wc = curr["weight"] - prev["weight"]

            # 비중·주식수 변화가 없으면 건너뜀
            if sc == 0 and abs(wc) < 0.0001:
                continue

            name = key[1]  # stock_name
            # 가격: 현재일 우선, 없으면 이전일
            price = curr["stock_price"] or prev["stock_price"]

            if name not in stock_map:
                stock_map[name] = {
                    "stock_name": name,
                    "stock_change": 0,
                    "weight_change": 0.0,
                    "etf_count": 0,
                    "stock_price": 0,
                }

            stock_map[name]["stock_change"] += sc
            stock_map[name]["weight_change"] += wc
            stock_map[name]["etf_count"] += 1
            if price and not stock_map[name]["stock_price"]:
                stock_map[name]["stock_price"] = price

        # 거래대금 계산 및 결과 조립
        result = []
        for name, s in stock_map.items():
            price = s["stock_price"]
            # 거래대금 = 주식수 변화 × 종가 (부호 포함)
            trade_amount = s["stock_change"] * price if s["stock_change"] != 0 else 0

            result.append({
                "stock_name": s["stock_name"],
                "trade_amount": trade_amount,
                "etf_count": s["etf_count"],
                "weight_change": round(s["weight_change"], 2),
                "stock_change": s["stock_change"],
                "stock_price": price,
            })

        # 정렬: 거래대금 내림차순 (양수 위, 음수 아래)
        result.sort(key=lambda x: -x["trade_amount"])

        return {
            "target_date": snap_date,
            "prev_date": prev_date,
            "stocks": result,
        }

    finally:
        conn.close()


def get_stock_etf_detail(stock_name: str, target_date: str) -> dict:
    """
    특정 날짜에 해당 종목을 보유한 모든 ETF의 상세 정보를 반환한다.

    계산 로직:
    1. target_date와 직전 수집일의 해당 종목 ETF별 데이터 조회
    2. curr + prev 합집합으로 보유한 모든 ETF 표시 (신규편입·청산 포함)
    3. 변화 없는 ETF도 보유 현황 출력 (변화값 0)

    Args:
        stock_name: 종목명
        target_date: 조회 날짜 (YYYY-MM-DD)

    Returns:
        {
            "stock_name": str,
            "target_date": str,
            "prev_date": str,
            "etfs": [
                {"etf_name", "etf_code", "stock_count", "holding_amount",
                 "weight", "stock_change", "weight_change", "trade_amount"}, ...
            ]
        }
    """
    conn = get_db_connection()
    try:
        # 전체 수집 날짜 목록 (최신순)
        all_dates = get_collect_dates(conn, limit=100)
        if len(all_dates) < 2:
            return {"stock_name": stock_name, "target_date": target_date,
                    "prev_date": None, "etfs": []}

        # target_date가 수집일이 아니면 가장 가까운 이전 수집일로 스냅
        snap_date = None
        for d in all_dates:
            if d <= target_date:
                snap_date = d
                break
        if snap_date is None:
            snap_date = all_dates[-1]

        # snap_date의 직전 수집일 찾기
        snap_idx = all_dates.index(snap_date) if snap_date in all_dates else None
        if snap_idx is None or snap_idx + 1 >= len(all_dates):
            return {"stock_name": stock_name, "target_date": snap_date,
                    "prev_date": None, "etfs": []}

        prev_date = all_dates[snap_idx + 1]

        # target_date 해당 종목 ETF별 데이터 조회 (etf_name JOIN 포함)
        curr_rows = conn.execute(
            "SELECT h.etf_code, COALESCE(m.etf_name, h.etf_code) as etf_name, "
            "h.stock_count, h.weight, h.stock_price "
            "FROM etf_holdings h "
            "LEFT JOIN etf_master m ON h.etf_code = m.etf_code "
            "WHERE h.stock_name = ? AND h.collect_date = ?",
            (stock_name, snap_date),
        ).fetchall()

        # 직전일 해당 종목 ETF별 데이터 조회
        prev_rows = conn.execute(
            "SELECT h.etf_code, COALESCE(m.etf_name, h.etf_code) as etf_name, "
            "h.stock_count, h.weight, h.stock_price "
            "FROM etf_holdings h "
            "LEFT JOIN etf_master m ON h.etf_code = m.etf_code "
            "WHERE h.stock_name = ? AND h.collect_date = ?",
            (stock_name, prev_date),
        ).fetchall()

        # etf_code → {etf_name, stock_count, weight, stock_price} 매핑
        curr_map = {}
        for r in curr_rows:
            curr_map[r["etf_code"]] = {
                "etf_name": r["etf_name"],
                "stock_count": r["stock_count"] or 0,
                "weight": r["weight"] or 0,
                "stock_price": r["stock_price"] or 0,
            }

        prev_map = {}
        for r in prev_rows:
            prev_map[r["etf_code"]] = {
                "etf_name": r["etf_name"],
                "stock_count": r["stock_count"] or 0,
                "weight": r["weight"] or 0,
                "stock_price": r["stock_price"] or 0,
            }

        # curr + prev 합집합: 보유한 모든 ETF 표시
        all_etf_codes = set(curr_map.keys()) | set(prev_map.keys())

        # ETF 이름 조회 (prev_map에만 있는 ETF는 curr_map에 이름이 없을 수 있음)
        etf_name_map = {}
        for etf_code in all_etf_codes:
            if etf_code in curr_map:
                etf_name_map[etf_code] = curr_map[etf_code]["etf_name"]
            elif etf_code in prev_map:
                etf_name_map[etf_code] = prev_map[etf_code]["etf_name"]

        etfs = []
        for etf_code in sorted(all_etf_codes):
            curr = curr_map.get(etf_code, {"stock_count": 0, "weight": 0, "stock_price": 0})
            prev = prev_map.get(etf_code, {"stock_count": 0, "weight": 0, "stock_price": 0})

            stock_change = curr["stock_count"] - prev["stock_count"]
            weight_change = curr["weight"] - prev["weight"]

            # 가격: 현재일 우선, 없으면 이전일
            price = curr["stock_price"] or prev["stock_price"]

            # 보유금액 = 현재 주식수 × 종가
            holding_amount = curr["stock_count"] * price if price else 0

            # 거래대금(변화) = 주식수 변화 × 종가 (부호 포함)
            trade_amount = stock_change * price if stock_change != 0 else 0

            etfs.append({
                "etf_name": etf_name_map.get(etf_code, etf_code),
                "etf_code": etf_code,
                "stock_count": curr["stock_count"],     # 현재 보유 주식수
                "holding_amount": holding_amount,        # 보유금액(현재)
                "weight": round(curr["weight"], 2),      # 현재 비중
                "stock_change": stock_change,
                "weight_change": round(weight_change, 2),
                "trade_amount": trade_amount,            # 변화 거래대금
            })

        # 정렬: 거래대금 변화 내림차순 (변화 큰 ETF 위)
        etfs.sort(key=lambda x: -x["trade_amount"])

        return {
            "stock_name": stock_name,
            "target_date": snap_date,
            "prev_date": prev_date,
            "etfs": etfs,
        }

    finally:
        conn.close()


def get_last_update_info() -> dict:
    """
    마지막 데이터 수집 정보를 반환한다.

    Returns:
        {"last_date": str, "etf_count": int, "stock_count": int}
    """
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT MAX(collect_date) as last_date FROM etf_holdings"
        ).fetchone()

        if not row or not row["last_date"]:
            return {"last_date": None, "etf_count": 0, "stock_count": 0}

        last_date = row["last_date"]

        etf_count = conn.execute(
            "SELECT COUNT(DISTINCT etf_code) as cnt "
            "FROM etf_holdings WHERE collect_date = ?",
            (last_date,),
        ).fetchone()["cnt"]

        stock_count = conn.execute(
            "SELECT COUNT(DISTINCT stock_name) as cnt "
            "FROM etf_holdings WHERE collect_date = ?",
            (last_date,),
        ).fetchone()["cnt"]

        return {
            "last_date": last_date,
            "etf_count": etf_count,
            "stock_count": stock_count,
        }

    finally:
        conn.close()
