"""
Active ETF Analysis - Flask 메인 앱.
네이버 증권에서 한국 액티브 ETF 구성종목 데이터를 수집·분석하고
투자 시그널을 제공하는 웹 대시보드.
"""

import logging
import os
import threading
from datetime import datetime

import requests as http_requests
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, render_template, request

from analyzer.signal import (
    get_collect_dates,
    get_daily_snapshot,
    get_db_connection,
    get_etf_holdings,
    get_last_update_info,
    get_overlapping_stocks,
    get_stock_daily_changes,
    get_stock_etf_detail,
    get_stock_overview,
    get_stock_weight_history,
    get_top_buy_increase,
    get_top_sell_increase,
    get_unique_stock_names,
    get_weight_decrease_signals,
    get_weight_increase_signals,
)
from config import ETF_LIST, ETF_SECTORS, SECTOR_ORDER, HOST, PORT, SCHEDULE_HOURS, SCHEDULE_MINUTE, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from crawler.naver_etf import collect_all_etf_data, init_db, seed_etf_master

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 수집 상태 관리
_collect_lock = threading.Lock()
_collect_running = False
_collect_progress = ""


def send_telegram(message):
    """텔레그램으로 알림 메시지를 발송한다."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = http_requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
        }, timeout=10)
        if not resp.json().get("ok"):
            logger.warning("텔레그램 발송 실패: %s", resp.text)
    except Exception as e:
        logger.warning("텔레그램 발송 오류: %s", e)


def run_collection():
    """백그라운드에서 데이터 수집을 실행한다."""
    global _collect_running, _collect_progress
    with _collect_lock:
        if _collect_running:
            return
        _collect_running = True
        _collect_progress = "시작됨"

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        results = collect_all_etf_data()
        saved = sum(1 for r in results if r["status"] == "saved")
        errors = sum(1 for r in results if r["status"] in ("error", "empty"))
        skipped = sum(1 for r in results if r["status"] == "skipped")
        _collect_progress = f"완료: 저장 {saved}, 오류 {errors}"
        # 텔레그램 알림 발송
        send_telegram(
            f"📊 Active ETF 수집 완료\n"
            f"시간: {now}\n"
            f"저장: {saved} / 스킵: {skipped} / 오류: {errors}"
        )
    except Exception as e:
        logger.error("수집 중 오류: %s", e)
        _collect_progress = f"오류: {e}"
        send_telegram(f"❌ Active ETF 수집 실패\n시간: {now}\n오류: {e}")
    finally:
        with _collect_lock:
            _collect_running = False


# --- 페이지 라우팅 ---

@app.route("/")
def index():
    """메인 대시보드 페이지."""
    return render_template("index.html")


@app.route("/signals")
def signals():
    """시그널 대시보드 페이지."""
    return render_template("signals.html")


@app.route("/chart")
def chart():
    """종목 비중 변화 차트 페이지."""
    return render_template("chart.html")


@app.route("/daily")
def daily():
    """날짜별 비중 변화 페이지."""
    return render_template("daily.html")


# --- 데이터 API ---

@app.route("/api/stock-overview")
def api_stock_overview():
    """전체 종목 요약 정보 API."""
    return jsonify(get_stock_overview())


@app.route("/api/stocks")
def api_stocks():
    """DB 내 모든 고유 종목명 목록 API."""
    return jsonify(get_unique_stock_names())


@app.route("/api/stock-weight-history")
def api_stock_weight_history():
    """특정 종목의 ETF별 비중 시계열 데이터 API."""
    stock_name = request.args.get("stock_name", "")
    if not stock_name:
        return jsonify({"error": "stock_name 파라미터가 필요합니다."}), 400
    return jsonify(get_stock_weight_history(stock_name))


@app.route("/api/top-buy")
def api_top_buy():
    """매수 증가 Top N API. top_n 기본값 50, daily_changes 포함."""
    days = request.args.get("days", 3, type=int)
    top_n = request.args.get("top_n", 50, type=int)
    return jsonify(get_top_buy_increase(days=days, top_n=top_n))


@app.route("/api/top-sell")
def api_top_sell():
    """매도 증가(청산) Top N API. top_n 기본값 50, daily_changes 포함."""
    days = request.args.get("days", 3, type=int)
    top_n = request.args.get("top_n", 50, type=int)
    return jsonify(get_top_sell_increase(days=days, top_n=top_n))


@app.route("/api/stock-daily-changes")
def api_stock_daily_changes():
    """특정 종목의 날짜별 매매 상세 API."""
    stock_name = request.args.get("stock_name", "")
    days = request.args.get("days", 10, type=int)
    if not stock_name:
        return jsonify({"error": "stock_name 필요"}), 400
    return jsonify(get_stock_daily_changes(stock_name, days))


@app.route("/api/holdings")
def api_holdings():
    """ETF별 보유종목 API."""
    etf_code = request.args.get("etf_code", "")
    if not etf_code:
        return jsonify([])
    return jsonify(get_etf_holdings(etf_code))


@app.route("/api/holdings-by-sector")
def api_holdings_by_sector():
    """섹터별 ETF 보유종목 일괄 조회 API."""
    sector = request.args.get("sector", "전체")
    result = []
    for etf_name, etf_code in ETF_LIST.items():
        if sector != "전체" and ETF_SECTORS.get(etf_name) != sector:
            continue
        holdings = get_etf_holdings(etf_code)
        result.append({
            "etf_name": etf_name,
            "etf_code": etf_code,
            "sector": ETF_SECTORS.get(etf_name, "기타"),
            "holdings": holdings,
        })
    return jsonify(result)


@app.route("/api/overlap")
def api_overlap():
    """중복 매수 종목 API."""
    top_n = request.args.get("top_n", 30, type=int)
    return jsonify(get_overlapping_stocks(top_n=top_n))


@app.route("/api/weight-increase")
def api_weight_increase():
    """비중 증가 시그널 API."""
    top_n = request.args.get("top_n", 30, type=int)
    return jsonify(get_weight_increase_signals(top_n=top_n))


@app.route("/api/weight-decrease")
def api_weight_decrease():
    """비중 감소 시그널 API."""
    top_n = request.args.get("top_n", 30, type=int)
    return jsonify(get_weight_decrease_signals(top_n=top_n))


@app.route("/api/dates")
def api_dates():
    """DB에 저장된 수집 날짜 목록 API."""
    conn = get_db_connection()
    try:
        dates = get_collect_dates(conn)
        return jsonify(dates)
    finally:
        conn.close()


@app.route("/api/daily-snapshot")
def api_daily_snapshot():
    """특정 날짜 종목별 비중 변화 API. date 파라미터 없으면 최신 수집일 사용."""
    date_param = request.args.get("date", None)
    return jsonify(get_daily_snapshot(target_date=date_param))


@app.route("/api/stock-etf-detail")
def api_stock_etf_detail():
    """특정 날짜 특정 종목의 ETF별 상세 API."""
    stock_name = request.args.get("stock_name", "")
    date_param = request.args.get("date", None)
    if not stock_name:
        return jsonify({"error": "stock_name 파라미터가 필요합니다."}), 400
    if not date_param:
        return jsonify({"error": "date 파라미터가 필요합니다."}), 400
    return jsonify(get_stock_etf_detail(stock_name, date_param))


@app.route("/api/last-update")
def api_last_update():
    """마지막 수집 일시 조회 API."""
    return jsonify(get_last_update_info())


# --- 관리 API ---

@app.route("/api/collect", methods=["POST"])
def api_collect():
    """수동 데이터 수집 실행 API."""
    global _collect_running
    with _collect_lock:
        if _collect_running:
            return jsonify({"status": "already_running"})

    thread = threading.Thread(target=run_collection, daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/api/collect-status")
def api_collect_status():
    """수집 상태 조회 API."""
    return jsonify({
        "running": _collect_running,
        "progress": _collect_progress,
    })


# --- 앱 시작 ---

if __name__ == "__main__":
    # DB 초기화
    os.makedirs(os.path.join(os.path.dirname(__file__), "db"), exist_ok=True)
    init_db()
    seed_etf_master()

    # APScheduler 설정 (매일 지정 시간에 자동 수집)
    scheduler = BackgroundScheduler()
    for hour in SCHEDULE_HOURS:
        scheduler.add_job(
            func=run_collection,
            trigger="cron",
            day_of_week="mon-fri",
            hour=hour,
            minute=SCHEDULE_MINUTE,
            id=f"daily_etf_collection_{hour}",
            replace_existing=True,
        )
    scheduler.start()
    hours_str = ", ".join(f"{h:02d}:{SCHEDULE_MINUTE:02d}" for h in SCHEDULE_HOURS)
    logger.info("스케줄러 시작: 매일 %s 자동 수집", hours_str)

    # Flask 앱 실행
    logger.info("서버 시작: http://%s:%d", HOST, PORT)
    app.run(host=HOST, port=PORT, debug=False)
