"""自然语言 → SQL（NL2SQL）→ 只读查询 SQLite。

调用 OpenAI 兼容的 ChatCompletions 端点（默认 DeepSeek：https://api.deepseek.com/v1，
key 从环境变量 DEEPSEEK_API_KEY 读取；模型/Base URL 可分别用 DEEPSEEK_MODEL / DEEPSEEK_BASE_URL 覆盖）。

安全：生成的 SQL 一律 clean → 只允许单条 SELECT/WITH/EXPLAIN → 在「只读 + query_only」连接上执行。
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-v4-flash"
_KEY_ENV = "DEEPSEEK_API_KEY"
_MODEL_ENV = "DEEPSEEK_MODEL"
_BASE_ENV = "DEEPSEEK_BASE_URL"

_TABLES = ("bank_flow", "ledger", "unmatched")

# 直接拒绝的写/危险关键字（不区分大小写、按词边界）
_FORBIDDEN = (
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|"
    r"pragma|vacuum|reindex|load_extension)\b"
)


class QueryError(ValueError):
    """中文面向用户的查询错误。"""


@dataclass(frozen=True)
class LlmConfig:
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    model: str = DEFAULT_MODEL
    timeout: float = 60.0

    @classmethod
    def from_env(cls) -> "LlmConfig":
        return cls(
            base_url=os.getenv(_BASE_ENV, DEFAULT_BASE_URL).rstrip("/"),
            api_key=os.getenv(_KEY_ENV, ""),
            model=os.getenv(_MODEL_ENV, DEFAULT_MODEL),
        )

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


@dataclass
class QueryResult:
    text: str = ""
    sql: str = ""
    note: str = ""
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    row_count: int = 0
    elapsed_ms: float = 0.0
    error: str | None = None


# ---------------------------------------------------------------------------
# SQL 清洗与只读校验
# ---------------------------------------------------------------------------

def clean_sql(sql: str) -> str:
    """去掉 #/--/块注释、库名前缀(ledger_system.ledger→ledger)与收尾分号。

    SQLite 不支持 # 注释，但模型可能照抄用户/旧 MySQL 写法，故先剥掉。
    """
    s = str(sql)
    # 行注释
    s = re.sub(r"(?m)^\s*#.*$", "", s)          # 整行 #
    s = re.sub(r"#[^\n]*", " ", s)               # 行内 # 之后（视同注释）
    s = re.sub(r"--[^\n]*", " ", s)              # -- 注释
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)  # /* */ 块注释
    # 去掉“库名.”前缀，如 ledger_system.ledger / main.ledger
    s = re.sub(r"(?i)\b[a-zA-Z_][\w$]*\.(%s)\b" % "|".join(_TABLES), r"\1", s)
    s = s.strip()
    # 只去掉收尾的 ;（多个空语句则全剥）
    while s.endswith(";"):
        s = s[:-1].rstrip()
    return s.strip()


def check_readonly(sql: str) -> str:
    """返回清洗后 SQL；若不满足只读安全则抛 QueryError（中文）。"""
    s = clean_sql(sql)
    if not s:
        raise QueryError("生成的 SQL 为空。")
    if ";" in s:
        raise QueryError("只允许单条查询语句，不支持多条 SQL（请去掉分号分隔的语句）。")
    if not re.match(r"(?is)^\s*(SELECT|WITH|EXPLAIN)\b", s):
        raise QueryError("只允许只读查询（SELECT / WITH / EXPLAIN）。")
    if re.search(_FORBIDDEN, s, flags=re.I):
        raise QueryError("检测到写/危险操作（INSERT/UPDATE/DELETE/DROP 等），已拒绝执行。")
    return s


def execute_readonly(db_path: str | Path, sql: str) -> QueryResult:
    """清洗 + 校验 + 在只读连接上执行查询。"""
    db = Path(db_path).resolve()
    if not db.exists():
        raise QueryError(f"数据库不存在：{db}；请先 `ledger init` 建库。")
    s = check_readonly(sql)
    start = time.perf_counter()
    # mode=ro 只读 + PRAGMA query_only 双保险；即使校验有漏洞也无法写库
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
    try:
        conn.execute("PRAGMA query_only=ON")
        cur = conn.execute(s)
        columns = [d[0] for d in (cur.description or [])]
        rows = [list(r) for r in cur.fetchall()]
        conn.commit()  # 只读连接上 commit 无害；确保无残留事务
    except sqlite3.Error as e:
        raise QueryError(f"SQL 执行失败：{e}")
    finally:
        conn.close()
    elapsed = round((time.perf_counter() - start) * 1000, 1)
    return QueryResult(sql=s, columns=columns, rows=rows, row_count=len(rows), elapsed_ms=elapsed)


# ---------------------------------------------------------------------------
# LLM 调用（OpenAI 兼容 ChatCompletions）
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """从模型返回文本里稳健地取出 JSON 对象。"""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t).strip()
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # 退回抓取第一个 {...}
    m = re.search(r"\{.*\}", t, flags=re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    raise QueryError("大模型返回不是有效 JSON，请重试或换一种问法。")


def llm_chat_json(cfg: LlmConfig, system: str, user: str) -> dict:
    """POST {base}/chat/completions，要求 JSON 对象返回。网络/状态错误转中文。"""
    import httpx

    if not cfg.has_key:
        raise QueryError(f"缺少环境变量 {_KEY_ENV}，请在配置后重启服务再查询。")
    url = f"{cfg.base_url}/chat/completions"
    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=cfg.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise QueryError(f"调用大模型失败：{e.__class__.__name__}。请检查网络/Base URL。")
    if resp.status_code >= 400:
        detail = resp.text[:300]
        raise QueryError(f"大模型接口返回 {resp.status_code}：{detail}")
    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        raise QueryError("大模型响应格式异常。")
    return _extract_json(content)


# ---------------------------------------------------------------------------
# Schema 上下文 + few-shot
# ---------------------------------------------------------------------------

def schema_text(settings) -> str:
    """从真实库取三表结构 + 行数 + 首行样例，供模型参考。"""
    from . import db

    if not Path(settings.db_path).exists():
        return "（数据库尚未创建：请先执行 ledger init）"
    conn = db.connect(settings.db_path)
    try:
        parts = []
        for table in _TABLES:
            df = db.read_table(conn, table)
            cols = []
            for c in df.columns:
                cols.append(str(c))
            head = ""
            if not df.empty:
                sample = {str(k): v for k, v in df.iloc[0].items()}
                head = "，示例首行 " + json.dumps(sample, ensure_ascii=False, default=str)
            parts.append(f"- {table}：列 {', '.join(cols)}；行数 {len(df)}{head}")
    finally:
        conn.close()
    return "\n".join(parts)


SYSTEM_HEAD = """你是资金台账数据库的 SQL 专家。把中文问题转成在 SQLite 上可执行的只读查询。

库表（均为 TEXT 日期 'YYYY-MM-DD'，金额 REAL 两位小数）：
{schema}

铁律：
1. 只输出 JSON：{{"sql": "……", "note": "一句中文说明"}}，不要输出其它文字或代码块。
2. SQL 只读；单条语句；不得使用 INSERT/UPDATE/DELETE/DROP/PRAGMA 等。
3. 表名直接用 ledger / bank_flow / unmatched，不要带库名或模式前缀（如不要 ledger_system.ledger）。
4. 字符串统一用单引号，例如 date <= '2026-02-28'。
5. ledger.balance 是“全局逐行滚动”的余额，不是按项目切的。若问“某日期每个项目的资金净额/余额”，必须用窗口函数按项目累计后取截止日前的最后一行（见示例 1）。

示例问答（仅作参考，勿照抄进答案）：
示例1 Q: 获取 2026-02-28 各项目的资金净额（取截至该日每项目最后一笔净额）
示例1 SQL:
WITH t AS (
  SELECT *, SUM(income - expense) OVER (PARTITION BY project ORDER BY date, id) AS project_balance
  FROM ledger
),
ranked AS (
  SELECT project, date, project_balance,
         ROW_NUMBER() OVER (PARTITION BY project ORDER BY id DESC) AS rn
  FROM t
  WHERE date <= '2026-02-28'
)
SELECT project, date, project_balance FROM ranked WHERE rn = 1 ORDER BY project;

示例2 Q: 2026年4月各项目支出合计
示例2 SQL: SELECT project, ROUND(SUM(expense), 2) AS expense_total FROM ledger
WHERE date BETWEEN '2026-04-01' AND '2026-04-30' GROUP BY project ORDER BY expense_total DESC;

示例3 Q: 现在还有几条未识别项目记录
示例3 SQL: SELECT COUNT(*) AS unmatched_count FROM unmatched WHERE status != 'resolved';

示例4 Q: 主表最近 10 笔流水
示例4 SQL: SELECT * FROM ledger ORDER BY date DESC, id DESC LIMIT 10;
"""


def build_system_prompt(settings) -> str:
    return SYSTEM_HEAD.format(schema=schema_text(settings))


def query_nl(text: str, settings, llm=None) -> QueryResult:
    """NL2SQL 主流程：生成 → 校验 → 只读执行。

    llm: 可选注入函数 llm(cfg, system, user) -> dict，测试用假模型。
    """
    from .config import Settings  # noqa: F401  (type hint 用)

    if not text or not text.strip():
        raise QueryError("请输入查询问题。")
    cfg = LlmConfig.from_env()
    system = build_system_prompt(settings)
    caller = llm if llm is not None else llm_chat_json
    resp = caller(cfg, system, text.strip())
    if not isinstance(resp, dict) or "sql" not in resp:
        raise QueryError("大模型未返回 sql 字段。")
    sql = clean_sql(resp["sql"])
    note = str(resp.get("note", "")).strip()
    res = execute_readonly(settings.db_path, sql)
    res.text = text.strip()
    res.note = note
    res.sql = check_readonly(sql)
    return res


def _demo_offline(cfg: LlmConfig):
    """离线演示（未配 key 或未加 --ask）：只演示清洗与只读执行，不调大模型。"""
    print("  已配 key =", cfg.has_key, "；未加 --ask → 离线演示（不调大模型），交互问答请用：ledger query \"问题\"")
    print("  clean_sql('ledger_system.ledger\\n#注释') →", repr(clean_sql("ledger_system.ledger\n#注释\nSELECT 1;")))
    demo_sql = "SELECT project, COUNT(*) AS n FROM ledger GROUP BY project ORDER BY n DESC LIMIT 5;"
    try:
        r = execute_readonly(default_settings().db_path, demo_sql)
        print("  只读执行示例结果（行数", r.row_count, "）：", r.rows[:5])
    except QueryError as e:
        print("  只读执行示例被跳过：", e)


if __name__ == "__main__":
    # 自测：python -m ledger_etl.nl2sql [--ask]
    # 默认离线演示（不调大模型）；显式加 --ask 且已配 key 时进入交互问答。
    import sys

    from .config import default_settings

    print("## nl2sql：自然语言 → SQL → 只读执行（DeepSeek，env: DEEPSEEK_API_KEY）")
    cfg = LlmConfig.from_env()
    print("配置：model =", cfg.model, "| base_url =", cfg.base_url, "| 已配 key =", cfg.has_key)
    if not cfg.has_key:
        _demo_offline(cfg)
    elif "--ask" not in sys.argv:
        _demo_offline(cfg)
    else:
        question = input("请输入查询问题（回车用示例）：").strip() or "各项目总支出排名前5"
        try:
            r = query_nl(question, default_settings())
        except (QueryError, EOFError) as e:
            print("  查询失败/中断：", e)
            sys.exit(1)
        print("问题：", r.text)
        print("SQL：", r.sql)
        print("说明：", r.note)
        print("耗时：", r.elapsed_ms, "ms | 行数：", r.row_count)
        print("结果：", r.rows[:20])
