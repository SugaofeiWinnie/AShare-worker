from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
import re
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


QUOTE_URL = "https://push2delay.eastmoney.com/api/qt/stock/get"
DISCLAIMER = "本报告由系统基于公开行情和 Python 规则模型生成，仅供研究参考，不构成投资建议。"


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
    inflow: float = 0.0


def generate_report(code: str) -> dict[str, Any]:
    quote = fetch_quote(normalize_code(code))
    score = score_quote(quote)
    verdict = verdict_for(score)
    content = build_content(quote, score, verdict)
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
    secid = f"{market_prefix(code)}.{code}"
    params = urlencode(
        {
            "secid": secid,
            "fields": "f57,f58,f43,f170,f135,f162,f167,f116,f117",
        }
    )
    request = Request(f"{QUOTE_URL}?{params}", headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data") or {}
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


def build_content(quote: QuoteSnapshot, score: int, verdict: str) -> dict[str, Any]:
    bear = round2(quote.price * 0.82)
    base = round2(quote.price * 1.03)
    bull = round2(quote.price * 1.22)
    trend = "短线偏强" if quote.pct >= 3 else "短线承压" if quote.pct <= -3 else "震荡观察"
    value_tone = (
        "估值偏高"
        if quote.pe > 80
        else "估值相对克制"
        if 0 < quote.pe < 25
        else "估值需要结合成长验证"
    )

    return {
        "summary": f"{quote.name} 当前评分 {score} 分，结论为“{verdict}”。Python worker 已接管个股报告生成，当前基于行情、估值和资金占位信号形成 MVP 版结构化报告。",
        "metrics": [
            metric("最新价", format_price(quote.price), "down" if quote.pct < 0 else "up"),
            metric("涨跌幅", f"{quote.pct:+.2f}%", "down" if quote.pct < 0 else "up"),
            metric("市盈率", format_number(quote.pe), "warn" if quote.pe > 80 else "neutral"),
            metric("市净率", format_number(quote.pb), "warn" if quote.pb > 8 else "neutral"),
            metric("成交额", format_amount(quote.amount), "neutral"),
            metric("主力净流入", format_amount(quote.inflow), "neutral"),
        ],
        "coreConclusions": [
            f"{trend}：今日涨跌幅为 {quote.pct:+.2f}%，需要结合板块强弱和成交量确认持续性。",
            f"{value_tone}：PE/PB 只是第一层过滤，真正关键仍是利润增速、现金流和订单兑现。",
            "资金信号：MVP 阶段暂未接入个股主力净流入，资金方向先保持中性观察。",
        ],
        "investorViews": investor_views(quote, score),
        "deepScan": [
            scan("趋势", clamp(score + (8 if quote.pct >= 0 else -8)), trend, "以当日涨跌幅和价格位置作为 MVP 阶段的趋势代理指标。"),
            scan("估值", clamp(55 if quote.pe <= 0 else 38 if quote.pe > 80 else 72 if quote.pe < 30 else 58), value_tone, "后续接入财务预测后，可升级为 PE/PEG/DCF 联合评分。"),
            scan("资金", 50, "资金中性", "当前 Python worker 先保留资金占位，后续接入个股资金流数据源。"),
            scan("波动", clamp(70 - int(abs(quote.pct * 5))), "波动观察", "涨跌幅越大，追高或杀跌的风险越需要单独评估。"),
        ],
        "valuation": {
            "bearPrice": bear,
            "basePrice": base,
            "bullPrice": bull,
            "method": "MVP 阶段采用行情锚定区间法，后续升级为 DCF / PE Band / 同业估值。",
            "assumptions": [
                "熊市情景：当前价格下修约 18%。",
                "基准情景：当前价格上浮约 3%。",
                "乐观情景：当前价格上浮约 22%。",
            ],
        },
        "risks": [
            "行情和财务数据可能存在延迟或缺失，不能只依赖单日信号。",
            "估值处于高位时，对业绩兑现和市场风险偏好更敏感。",
            "后续需要接入公告、新闻、财报和机构预期，降低单一行情数据带来的偏差。",
        ],
        "catalysts": [
            "财报披露、业绩预告或机构调研可能成为重新定价窗口。",
            "板块资金回流、成交额放大和突破关键均线可作为右侧确认信号。",
            "若行业政策或订单验证改善，报告评分应及时刷新。",
        ],
        "buyZones": [
            {"name": "防守观察区", "low": bear, "high": round2(quote.price * 0.92), "note": "适合等待风险释放，不追求立刻买入。"},
            {"name": "合理跟踪区", "low": round2(quote.price * 0.92), "high": base, "note": "适合结合基本面和板块强度分批观察。"},
            {"name": "强势确认区", "low": base, "high": bull, "note": "需要成交量和业绩预期同步确认，避免单纯追高。"},
        ],
        "disclaimer": DISCLAIMER,
    }


def investor_views(quote: QuoteSnapshot, score: int) -> list[dict[str, Any]]:
    return [
        view("价值派", "巴菲特视角", "关注" if score >= 70 else "观望", clamp(score - 8), "先看护城河和现金流，再决定价格是否值得。", "MVP 阶段财务数据不足，价值派会要求更多利润质量证据。"),
        view("成长派", "彼得林奇视角", "关注" if score >= 65 else "观望", clamp(score + 2), "如果增长逻辑能被财报验证，可以进入跟踪名单。", "当前先用估值和行情做代理，后续需要接入营收和利润增速。"),
        view("趋势派", "欧奈尔视角", "偏多" if quote.pct > 0 else "等待", clamp(score + (8 if quote.pct > 0 else -8)), "趋势派更重视价格强度和成交量确认。", "今日涨跌幅是第一层趋势信号。"),
        view("风险控制", "霍华德马克斯视角", "谨慎" if score < 55 else "中性", clamp(100 - abs(score - 55)), "先问下行风险，再谈上行空间。", "估值、波动和数据缺口都需要在仓位上体现。"),
    ]


def score_quote(quote: QuoteSnapshot) -> int:
    score = 55
    score += min(18, round(quote.pct * 3)) if quote.pct >= 0 else max(-18, round(quote.pct * 3))
    if 0 < quote.pe < 35:
        score += 8
    elif quote.pe > 90:
        score -= 12
    if quote.pb > 10:
        score -= 6
    return clamp(score)


def verdict_for(score: int) -> str:
    if score >= 75:
        return "积极跟踪"
    if score >= 60:
        return "谨慎关注"
    if score >= 45:
        return "中性观察"
    return "风险优先"


def normalize_code(raw: str) -> str:
    code = re.sub(r"\D", "", raw or "")
    if len(code) != 6:
        raise ValueError("请输入6位A股股票代码")
    return code


def market_prefix(code: str) -> str:
    return "1" if code.startswith(("6", "9")) else "0"


def metric(label: str, value: str, tone: str) -> dict[str, str]:
    return {"label": label, "value": value, "tone": tone}


def view(school: str, name: str, stance: str, score: int, conclusion: str, reason: str) -> dict[str, Any]:
    return {"school": school, "name": name, "stance": stance, "score": score, "conclusion": conclusion, "reason": reason}


def scan(name: str, score: int, status: str, detail: str) -> dict[str, Any]:
    return {"name": name, "score": score, "status": status, "detail": detail}


def number(value: Any) -> float:
    try:
        if value in (None, "", "-"):
            return 0.0
        result = float(value)
        return 0.0 if math.isnan(result) else result
    except (TypeError, ValueError):
        return 0.0


def clamp(value: int) -> int:
    return max(0, min(100, int(value)))


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
