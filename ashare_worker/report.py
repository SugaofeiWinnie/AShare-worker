from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
import re
import subprocess
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


QUOTE_URL = "https://push2delay.eastmoney.com/api/qt/stock/get"
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
FUND_FLOW_URL = "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"
TREND_URL = "https://push2delay.eastmoney.com/api/qt/stock/trends2/get"
DISCLAIMER = "本报告由系统基于公开行情、历史K线和资金流数据生成，仅供研究参考，不构成投资建议。"


@dataclass(frozen=True)
class QuoteSnapshot:
    code: str
    name: str
    price: float
    pct: float
    amount: float
    pe: float
    pb: float
    total_market_value: float
    float_market_value: float


@dataclass(frozen=True)
class KlineStats:
    days: int = 0
    close: float = 0.0
    ma20: float = 0.0
    ma60: float = 0.0
    return20: float = 0.0
    return60: float = 0.0
    high60: float = 0.0
    low60: float = 0.0
    volatility20: float = 0.0
    amount20_avg: float = 0.0


@dataclass(frozen=True)
class FundFlow:
    date: str = ""
    main_net: float = 0.0
    super_net: float = 0.0
    big_net: float = 0.0
    mid_net: float = 0.0
    small_net: float = 0.0
    main_pct: float = 0.0
    close: float = 0.0
    pct: float = 0.0


@dataclass(frozen=True)
class IntradayStats:
    points: int = 0
    high: float = 0.0
    low: float = 0.0
    last: float = 0.0
    average: float = 0.0
    amplitude: float = 0.0
    average_gap: float = 0.0


def generate_report(code: str) -> dict[str, Any]:
    normalized = normalize_code(code)
    quote = fetch_quote(normalized)
    kline = fetch_kline_stats(normalized)
    fund = fetch_fund_flow(normalized)
    intraday = fetch_intraday_stats(normalized)
    score = score_report(quote, kline, fund, intraday)
    verdict = verdict_for(score)
    content = build_content(quote, kline, fund, intraday, score, verdict)
    return {
        "stockCode": quote.code,
        "stockName": quote.name,
        "reportDate": date.today().isoformat(),
        "price": quote.price,
        "pct": quote.pct,
        "verdict": verdict,
        "score": score,
        "aiGenerated": False,
        "model": "python-worker",
        "content": content,
    }


def fetch_quote(code: str) -> QuoteSnapshot:
    data = get_json(
        QUOTE_URL,
        {
            "secid": secid(code),
            "fields": "f57,f58,f43,f170,f135,f162,f167,f116,f117",
        },
    ).get("data") or {}
    if not data:
        raise ValueError(f"未找到股票行情：{code}")
    return QuoteSnapshot(
        code=str(data.get("f57") or code),
        name=str(data.get("f58") or code),
        price=number(data.get("f43")) / 100.0,
        pct=number(data.get("f170")) / 100.0,
        amount=number(data.get("f135")),
        pe=number(data.get("f162")) / 100.0,
        pb=number(data.get("f167")) / 100.0,
        total_market_value=number(data.get("f116")),
        float_market_value=number(data.get("f117")),
    )


def fetch_kline_stats(code: str) -> KlineStats:
    try:
        data = get_json_by_curl(
            KLINE_URL,
            {
                "secid": secid(code),
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": "101",
                "fqt": "1",
                "beg": "0",
                "end": "20500101",
                "lmt": "80",
            },
        ).get("data") or {}
    except OSError:
        return KlineStats()
    rows = [parse_kline(row) for row in data.get("klines") or []]
    rows = [row for row in rows if row]
    if not rows:
        return KlineStats()
    rows = rows[-60:]
    closes = [row["close"] for row in rows]
    amounts = [row["amount"] for row in rows]
    pct_changes = [row["pct"] for row in rows[-20:]]
    close = closes[-1]
    ma20 = average(closes[-20:])
    ma60 = average(closes)
    return20 = percent_change(closes[-20], close) if len(closes) >= 20 else 0.0
    return60 = percent_change(closes[0], close) if len(closes) >= 2 else 0.0
    high60 = max(row["high"] for row in rows)
    low60 = min(row["low"] for row in rows)
    volatility20 = math.sqrt(average([(pct - average(pct_changes)) ** 2 for pct in pct_changes])) if pct_changes else 0.0
    return KlineStats(
        days=len(rows),
        close=close,
        ma20=round2(ma20),
        ma60=round2(ma60),
        return20=round2(return20),
        return60=round2(return60),
        high60=round2(high60),
        low60=round2(low60),
        volatility20=round2(volatility20),
        amount20_avg=round2(average(amounts[-20:])),
    )


def fetch_fund_flow(code: str) -> FundFlow:
    try:
        data = get_json_by_curl(
            FUND_FLOW_URL,
            {
                "secid": secid(code),
                "lmt": "1",
                "klt": "101",
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63",
            },
        ).get("data") or {}
    except OSError:
        return FundFlow()
    rows = data.get("klines") or []
    if not rows:
        return FundFlow()
    parts = rows[-1].split(",")
    if len(parts) < 13:
        return FundFlow()
    return FundFlow(
        date=parts[0],
        main_net=number(parts[1]),
        super_net=number(parts[2]),
        big_net=number(parts[3]),
        mid_net=number(parts[4]),
        small_net=number(parts[5]),
        main_pct=number(parts[6]),
        close=number(parts[11]),
        pct=number(parts[12]),
    )


def fetch_intraday_stats(code: str) -> IntradayStats:
    try:
        data = get_json(
            TREND_URL,
            {
                "secid": secid(code),
                "fields1": "f1,f2,f3,f4,f5,f6,f7,f8",
                "fields2": "f51,f53,f56,f58",
                "iscr": "0",
                "ndays": "1",
            },
        ).get("data") or {}
    except OSError:
        return IntradayStats()
    rows = [parse_trend(row) for row in data.get("trends") or []]
    rows = [row for row in rows if row and row["price"] > 0]
    if not rows:
        return IntradayStats()
    prices = [row["price"] for row in rows]
    averages = [row["average"] for row in rows if row["average"] > 0]
    high = max(prices)
    low = min(prices)
    last = prices[-1]
    average_price = averages[-1] if averages else average(prices)
    return IntradayStats(
        points=len(rows),
        high=round2(high),
        low=round2(low),
        last=round2(last),
        average=round2(average_price),
        amplitude=round2(percent_change(low, high)),
        average_gap=round2(percent_change(average_price, last)),
    )


def build_content(quote: QuoteSnapshot, kline: KlineStats, fund: FundFlow, intraday: IntradayStats, score: int, verdict: str) -> dict[str, Any]:
    bear = round2(quote.price * 0.82)
    base = round2(quote.price * 1.03)
    bull = round2(quote.price * 1.22)
    trend = trend_label(quote, kline, intraday)
    value_tone = value_label(quote)
    fund_tone = fund_label(fund)

    return {
        "summary": (
            f"{quote.name} 当前评分 {score} 分，结论为“{verdict}”。"
            f"报告已综合行情估值、当日分时走势、资金流和历史K线四类公开数据源。"
            f"趋势为“{trend}”，资金为“{fund_tone}”，估值判断为“{value_tone}”。"
        ),
        "metrics": [
            metric("最新价", format_price(quote.price), "down" if quote.pct < 0 else "up"),
            metric("涨跌幅", f"{quote.pct:+.2f}%", "down" if quote.pct < 0 else "up"),
            metric("日内振幅", f"{intraday.amplitude:.2f}%", "warn" if intraday.amplitude > 6 else "neutral"),
            metric("主力净流入", format_amount(fund.main_net), "down" if fund.main_net < 0 else "up" if fund.main_net > 0 else "neutral"),
            metric("市盈率", format_number(quote.pe), "warn" if quote.pe > 80 else "neutral"),
            metric("市净率", format_number(quote.pb), "warn" if quote.pb > 8 else "neutral"),
        ],
        "coreConclusions": [
            f"趋势信号：{trend}。日内高低区间 ¥{intraday.low:.2f} - ¥{intraday.high:.2f}，现价相对分时均价 {intraday.average_gap:+.2f}%。",
            f"资金信号：{fund_tone}。最近交易日主力净流入 {format_amount(fund.main_net)}，占比 {fund.main_pct:+.2f}%。",
            f"估值信号：{value_tone}。当前 PE {format_number(quote.pe)}，PB {format_number(quote.pb)}，仍需结合利润增速和现金流验证。",
        ],
        "investorViews": investor_views(quote, kline, fund, score),
        "deepScan": [
            scan("趋势", trend_score(quote, kline, intraday), trend, "综合日内分时位置、价格相对均价、历史K线和当日涨跌幅。"),
            scan("资金", fund_score(fund), fund_tone, "来自东方财富个股资金流，观察主力、超大单和大单方向。"),
            scan("估值", value_score(quote), value_tone, "基于 PE/PB 的估值温度，后续可接入财报预测和同业估值。"),
            scan("波动", volatility_score(kline, intraday), "波动观察", f"日内振幅约 {intraday.amplitude:.2f}%，近20日波动约 {kline.volatility20:.2f}%。"),
        ],
        "valuation": {
            "bearPrice": bear,
            "basePrice": base,
            "bullPrice": bull,
            "method": "当前采用行情锚定区间法，并用趋势、资金、估值信号校验区间可信度；后续升级为 DCF / PE Band / 同业估值。",
            "assumptions": [
                f"趋势假设：20日涨跌幅 {kline.return20:+.2f}%，60日涨跌幅 {kline.return60:+.2f}%。",
                f"资金假设：最近交易日主力净流入 {format_amount(fund.main_net)}。",
                "估值假设：高 PE/PB 股票需要更强的业绩兑现来支撑估值。",
            ],
        },
        "risks": [
            "公开接口数据可能存在延迟、缺失或字段口径差异。",
            "高估值股票对业绩兑现和市场风险偏好更敏感。",
            "短期趋势和资金信号不能替代财报、订单、公告和行业景气度验证。",
        ],
        "catalysts": [
            "价格重新站上20日和60日均线并伴随成交额放大。",
            "主力资金从净流出转为连续净流入。",
            "财报、业绩预告、订单公告或机构调研验证增长逻辑。",
        ],
        "buyZones": [
            {"name": "防守观察区", "low": bear, "high": round2(quote.price * 0.92), "note": "适合等待风险释放，不追求立刻买入。"},
            {"name": "合理跟踪区", "low": round2(quote.price * 0.92), "high": base, "note": "适合结合基本面和板块强度分批观察。"},
            {"name": "强势确认区", "low": base, "high": bull, "note": "需要成交量、趋势和业绩预期同步确认。"},
        ],
        "disclaimer": DISCLAIMER,
    }


def investor_views(quote: QuoteSnapshot, kline: KlineStats, fund: FundFlow, score: int) -> list[dict[str, Any]]:
    return [
        view("价值派", "巴菲特视角", "关注" if value_score(quote) >= 65 else "观望", clamp(value_score(quote) - 8), "先看护城河、现金流和估值安全边际。", "当前先用 PE/PB 代理估值，后续应接财报和自由现金流。"),
        view("成长派", "彼得林奇视角", "关注" if score >= 65 else "观望", clamp(score + 2), "如果增长逻辑被财报验证，可以进入跟踪名单。", "高估值必须用更高的增长和订单兑现来解释。"),
        view("趋势派", "欧奈尔视角", "偏多" if score >= 65 else "等待", clamp(score + (8 if quote.pct > 0 else -8)), "趋势派更重视均线、相对强度和成交确认。", "当前已纳入日内分时、均价位置和历史K线。"),
        view("资金派", "主力资金视角", "偏多" if fund.main_net > 0 else "谨慎", fund_score(fund), "资金方向能影响短线弹性。", f"最近交易日主力净流入 {format_amount(fund.main_net)}。"),
    ]


def score_report(quote: QuoteSnapshot, kline: KlineStats, fund: FundFlow, intraday: IntradayStats) -> int:
    score = 45
    score += int((trend_score(quote, kline, intraday) - 50) * 0.35)
    score += int((fund_score(fund) - 50) * 0.25)
    score += int((value_score(quote) - 50) * 0.25)
    score += int((volatility_score(kline, intraday) - 50) * 0.15)
    return clamp(score)


def trend_score(quote: QuoteSnapshot, kline: KlineStats, intraday: IntradayStats) -> int:
    score = 50
    if kline.days:
        score += 10 if quote.price > kline.ma20 > 0 else -8
        score += 8 if quote.price > kline.ma60 > 0 else -6
        score += clamp_delta(kline.return20, 15)
    if intraday.points:
        score += 8 if intraday.average_gap > 0 else -8 if intraday.average_gap < -1 else 0
    score += clamp_delta(quote.pct, 8)
    return clamp(score)


def fund_score(fund: FundFlow) -> int:
    score = 50
    score += clamp_delta(fund.main_pct * 2, 20)
    score += 8 if fund.main_net > 0 else -8 if fund.main_net < 0 else 0
    return clamp(score)


def value_score(quote: QuoteSnapshot) -> int:
    score = 58
    if 0 < quote.pe < 35:
        score += 14
    elif quote.pe > 90:
        score -= 18
    if 0 < quote.pb < 5:
        score += 8
    elif quote.pb > 10:
        score -= 10
    return clamp(score)


def volatility_score(kline: KlineStats, intraday: IntradayStats) -> int:
    base = kline.volatility20 if kline.volatility20 > 0 else intraday.amplitude
    return clamp(78 - int(base * 5))


def verdict_for(score: int) -> str:
    if score >= 75:
        return "积极跟踪"
    if score >= 60:
        return "谨慎关注"
    if score >= 45:
        return "中性观察"
    return "风险优先"


def trend_label(quote: QuoteSnapshot, kline: KlineStats, intraday: IntradayStats) -> str:
    if kline.days and quote.price > kline.ma20 > 0 and kline.return20 > 5:
        return "趋势偏强"
    if kline.days and quote.price < kline.ma20 and kline.return20 < -5:
        return "趋势承压"
    if intraday.points and intraday.average_gap > 1 and quote.pct > 0:
        return "日内偏强"
    if intraday.points and intraday.average_gap < -1 and quote.pct < 0:
        return "趋势承压"
    return "震荡观察"


def fund_label(fund: FundFlow) -> str:
    if fund.main_net > 0 and fund.main_pct > 2:
        return "资金偏暖"
    if fund.main_net < 0 and fund.main_pct < -2:
        return "资金偏弱"
    return "资金中性"


def value_label(quote: QuoteSnapshot) -> str:
    if quote.pe > 80 or quote.pb > 10:
        return "估值偏高"
    if 0 < quote.pe < 30 and 0 < quote.pb < 5:
        return "估值相对克制"
    return "估值需要结合成长验证"


def parse_kline(row: str) -> dict[str, float] | None:
    parts = row.split(",")
    if len(parts) < 11:
        return None
    return {
        "open": number(parts[1]),
        "close": number(parts[2]),
        "high": number(parts[3]),
        "low": number(parts[4]),
        "volume": number(parts[5]),
        "amount": number(parts[6]),
        "pct": number(parts[8]),
    }


def parse_trend(row: str) -> dict[str, float] | None:
    parts = row.split(",")
    if len(parts) < 4:
        return None
    return {"price": number(parts[1]), "average": number(parts[3])}


def get_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    full_url = f"{url}?{urlencode(params, safe=',')}"
    request = Request(
        full_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://quote.eastmoney.com/",
        },
    )
    try:
        with urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except OSError:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", "12", "-A", "Mozilla/5.0", full_url],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise
        return json.loads(result.stdout)


def get_json_by_curl(url: str, params: dict[str, str]) -> dict[str, Any]:
    full_url = f"{url}?{urlencode(params, safe=',')}"
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "12", "-A", "Mozilla/5.0", full_url],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise OSError("curl request failed")
    return json.loads(result.stdout)


def normalize_code(raw: str) -> str:
    code = re.sub(r"\D", "", raw or "")
    if len(code) != 6:
        raise ValueError("请输入6位A股股票代码")
    return code


def secid(code: str) -> str:
    return f"{market_prefix(code)}.{code}"


def market_prefix(code: str) -> str:
    return "1" if code.startswith(("6", "9")) else "0"


def metric(label: str, value: str, tone: str) -> dict[str, str]:
    return {"label": label, "value": value, "tone": tone}


def view(school: str, name: str, stance: str, score: int, conclusion: str, reason: str) -> dict[str, Any]:
    return {"school": school, "name": name, "stance": stance, "score": score, "conclusion": conclusion, "reason": reason}


def scan(name: str, score: int, status: str, detail: str) -> dict[str, Any]:
    return {"name": name, "score": score, "status": status, "detail": detail}


def distance_text(price: float, baseline: float) -> str:
    if baseline <= 0:
        return "暂无均线参考"
    return f"{percent_change(baseline, price):+.2f}%"


def percent_change(start: float, end: float) -> float:
    return 0.0 if start <= 0 else (end / start - 1) * 100


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def number(value: Any) -> float:
    try:
        if value in (None, "", "-"):
            return 0.0
        result = float(value)
        return 0.0 if math.isnan(result) else result
    except (TypeError, ValueError):
        return 0.0


def clamp(value: int | float) -> int:
    return max(0, min(100, int(round(value))))


def clamp_delta(value: float, limit: int) -> int:
    return int(max(-limit, min(limit, round(value))))


def round2(value: float) -> float:
    return round(value + 1e-9, 2)


def format_price(value: float) -> str:
    return "--" if value <= 0 else f"¥{value:.2f}"


def format_number(value: float) -> str:
    return "--" if value <= 0 else f"{value:.2f}"


def format_amount(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 100_000_000:
        return f"{value / 100_000_000:+.2f}亿"
    if abs_value >= 10_000:
        return f"{value / 10_000:+.2f}万"
    return f"{value:+.0f}"
