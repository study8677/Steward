"""Prometheus 指标定义与记录工具。"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

EVENT_INGESTED_TOTAL = Counter(
    "steward_event_ingested_total",
    "事件入库总数",
    ["source"],
)

GATE_RESULT_TOTAL = Counter(
    "steward_gate_result_total",
    "门禁判定计数",
    ["result"],
)

ACTION_EXECUTION_TOTAL = Counter(
    "steward_action_execution_total",
    "动作执行计数",
    ["outcome"],
)

WAITING_QUEUE_SIZE = Gauge(
    "steward_waiting_queue_size",
    "WAITING 队列规模",
)

LLM_ROUTE_LATENCY_SECONDS = Histogram(
    "steward_llm_route_latency_seconds",
    "LLM 路由耗时",
    buckets=(0.05, 0.1, 0.2, 0.5, 1, 2, 3, 5),
)


def render_metrics() -> tuple[bytes, str]:
    """返回 Prometheus 文本格式输出。"""
    return generate_latest(), CONTENT_TYPE_LATEST
