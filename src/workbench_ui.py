"""Read-only Streamlit views for the customer-support workbench."""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import PurePath
from typing import Any

import streamlit as st

from client import AgentClient, AgentClientError

STYLE = """
<style>
  :root { --ink:#17253b; --muted:#68788e; --line:#e3e9f1; --blue:#315fad; }
  .stApp { background:#f7f9fc; color:var(--ink); font-family:Inter,"Segoe UI",sans-serif; }
  [data-testid="stHeader"] { background:transparent; }
  .block-container { max-width:1260px; padding:2.2rem 3rem 4rem; }
  h1,h2,h3 { color:var(--ink); letter-spacing:-.035em; }
  h1 { font-size:2rem !important; font-weight:700 !important; margin-bottom:.2rem !important; }
  p,label,[data-testid="stCaptionContainer"] { color:var(--muted); }
  [data-testid="stSidebar"] { background:#fff; border-right:1px solid var(--line); width:272px !important; }
  [data-testid="stSidebar"] .block-container { padding:1.8rem 1.15rem; }
  [data-testid="stSidebar"] .stButton button { width:100%; height:44px; justify-content:flex-start;
    border:0; border-radius:10px; background:transparent; color:#40526a; font-weight:550;
    box-shadow:none; padding:0 .9rem; transition:background .15s ease,color .15s ease; }
  [data-testid="stSidebar"] .stButton button:hover { background:#f1f5fa; color:#244e91; }
  [data-testid="stSidebar"] .stButton button[kind="primary"] { background:#edf4ff;
    color:var(--blue); font-weight:700; box-shadow:inset 3px 0 0 var(--blue); }
  .brand-lockup { display:flex; align-items:center; gap:.75rem; margin:.1rem 0 2.25rem; }
  .brand-mark { display:grid; place-items:center; width:38px; height:38px; border-radius:10px;
    background:var(--blue); color:#fff; font-weight:800; font-size:1.1rem; }
  .brand-name { color:#15253c; font-weight:750; font-size:1.12rem; line-height:1.25; }
  .brand-subtitle { color:#7c8ba0; font-size:.72rem; margin-top:.2rem; }
  .page-subtitle { color:#6a798d; font-size:.94rem; margin:.1rem 0 1.75rem; }
  .model-badge { display:inline-flex; align-items:center; gap:.4rem; border:1px solid #dbe7f6;
    border-radius:999px; background:#f5f9ff; color:#315f9e; font-size:.78rem;
    font-weight:600; padding:.38rem .75rem; white-space:nowrap; }
  .model-badge::before { content:""; width:6px; height:6px; border-radius:50%; background:#3d83bd; }
  [data-testid="stVerticalBlockBorderWrapper"] { background:#fff; border:1px solid var(--line);
    border-radius:14px; box-shadow:0 5px 20px rgba(27,46,76,.035); }
  .stButton button[kind="secondary"],.stFormSubmitButton button[kind="secondary"] {
    border:1px solid #d9e2ed; border-radius:10px; background:#fff; color:#344862;
    font-weight:600; box-shadow:none; transition:background .15s ease,border-color .15s ease; }
  .stButton button[kind="secondary"]:hover,.stFormSubmitButton button[kind="secondary"]:hover {
    background:#f5f8fc; border-color:#b9cce4; color:#234e89; }
  .stButton button[kind="primary"],.stFormSubmitButton button[kind="primary"] {
    border:1px solid var(--blue); border-radius:10px; background:var(--blue); color:#fff;
    font-weight:650; box-shadow:0 3px 9px rgba(49,95,173,.16); }
  .stButton button[kind="primary"]:hover,.stFormSubmitButton button[kind="primary"]:hover {
    background:#254f98; border-color:#254f98; }
  [data-testid="stChatMessage"] { border:1px solid var(--line); border-radius:16px;
    background:#fff; padding:.85rem 1rem; margin:.75rem 0; box-shadow:0 3px 12px rgba(27,46,76,.025); }
  [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background:#edf4ff; border-color:#dce9fb; margin-left:3rem; }
  [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) { margin-right:3rem; }
  [data-testid="stChatInput"] { border:1px solid #cbd9ea; border-radius:16px;
    background:#fff; box-shadow:0 6px 22px rgba(31,60,104,.07); }
  [data-testid="stChatInput"]:focus-within { border-color:#7ea5df; box-shadow:0 0 0 3px #e8f1ff; }
  [data-testid="stChatInputSubmitButton"] button { border-radius:10px; background:var(--blue); color:#fff; }
  [data-testid="stChatInputSubmitButton"] button:hover { background:#254f98; }
  .welcome-card { border:1px solid var(--line); background:#fff; border-radius:18px;
    padding:2rem 2.2rem; box-shadow:0 6px 24px rgba(27,46,76,.035); margin:1.2rem 0; }
  .welcome-icon { width:36px; height:36px; border-radius:10px; background:#eaf2ff;
    display:grid; place-items:center; color:var(--blue); font-weight:800; margin-bottom:1rem; }
  .welcome-card h2 { margin:0 0 .55rem; font-size:1.35rem; }
  .welcome-card p { margin:0; max-width:520px; line-height:1.7; }
  .section-label { color:#344964; font-size:.88rem; font-weight:700; margin:1.8rem 0 .65rem; }
  .status-badge { display:inline-flex; align-items:center; border-radius:999px;
    padding:.25rem .62rem; font-size:.75rem; font-weight:700; background:#e8f5ef; color:#17714b; }
  .status-badge.failed { background:#fff0ee; color:#b34237; }
  .status-badge.pending { background:#fff5df; color:#916217; }
  [data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:12px; overflow:hidden; }
  [data-testid="stAlert"] { border-radius:10px; }
  [data-testid="stForm"] { border:1px solid var(--line); border-radius:14px; background:#fff; }
  @media (max-width:900px) { .block-container { padding:1.4rem 1.2rem 3rem; }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
      margin-left:0; margin-right:0; } }
</style>
"""


def heading(title: str, subtitle: str) -> None:
    st.title(title)
    st.html(f'<div class="page-subtitle">{escape(subtitle)}</div>')


def model_badge(provider: str, model: str) -> None:
    st.html(f'<span class="model-badge">{escape(provider)} · {escape(model)}</span>')


def status_badge(status: str) -> None:
    label = {"completed": "已完成", "failed": "失败", "approval_required": "待确认"}.get(status, status)
    style = "failed" if status == "failed" else "pending" if status == "approval_required" else ""
    st.html(f'<span class="status-badge {style}">{escape(label)}</span>')


def render_welcome() -> None:
    st.html("""<div class="welcome-card"><div class="welcome-icon">O</div>
      <h2>你好，我是 OrderCare</h2><p>可以帮你查询订单物流、了解退换货与维修政策、判断退款资格，
      并在你确认后创建售后工单。</p></div>""")
    st.html('<div class="section-label">你可以这样提问</div>')


def render_privacy() -> None:
    st.markdown("""#### 会话与数据

会话凭证保存在当前浏览器会话中。历史记录和执行记录按凭证隔离；仅分享会话编号不能让他人读取内容。

#### 业务操作

查询订单和退款资格前需提供订单号及手机号后四位。创建售后工单前会请求明确确认；取消或未确认时不执行写入。

#### 模型与记录

模型由服务端环境变量配置。执行记录只保存筛选、脱敏后的字段，不展示原始模型思考、API Key 或完整手机号。商城政策为项目演示规则，并非真实商家承诺。""")


def _get(client: AgentClient, path: str, **params: Any) -> dict[str, Any] | None:
    try:
        result = client.workbench_get(path, params=params or None)
    except (AgentClientError, AttributeError):
        st.warning("暂时无法读取后端工作台数据。")
        return None
    return result if isinstance(result, dict) else None


def _timestamp(value: str | None) -> str:
    if not value:
        return "未知"
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value[:16]


def render_knowledge(client: AgentClient) -> None:
    heading("知识库管理", "查看售后政策文档，并独立测试知识检索效果。")
    data = _get(client, "policies")
    if not data:
        return
    documents = data.get("documents", [])
    chunks = data.get("chunks", [])
    index = data.get("online_index") or {}
    metrics = st.columns(4, gap="small")
    metrics[0].metric("政策文档", len(documents))
    metrics[1].metric("知识切片", len(chunks))
    metrics[2].metric("Embedding", index.get("model") or "未建立")
    metrics[3].metric("线上向量索引", "已建立" if index else "未建立")

    st.subheader("政策文档")
    st.caption("线上政策与实验语料分开展示；下方检索使用线上政策。")
    for document in documents:
        source = str(document.get("source", ""))
        with st.container(border=True):
            info, action = st.columns([5, 1], vertical_alignment="center")
            with info:
                st.markdown(f"**{PurePath(source).name}**")
                collection = "线上政策" if document.get("collection") == "online" else "实验语料"
                st.caption(
                    f"{collection} · Markdown · 更新于 {_timestamp(document.get('updated_at'))}"
                    f" · {document.get('sections', 0)} 个章节"
                )
            with action:
                if st.button("查看详情", key=f"doc_{source}", use_container_width=True):
                    st.session_state.selected_policy_source = source
    selected_source = st.session_state.get("selected_policy_source")
    selected = next((item for item in documents if item.get("source") == selected_source), None)
    if selected:
        st.subheader(f"文档详情 · {PurePath(str(selected_source)).name}")
        with st.container(border=True):
            st.markdown(selected.get("preview", ""))
            related = [item for item in chunks if item.get("source") == selected_source]
            with st.expander(f"查看 {len(related)} 个 Chunk"):
                for item in related:
                    st.markdown(f"**{item['title']}** · Chunk {item['chunk_index'] + 1}")
                    st.caption(f"ID {item['chunk_id']} · 来源 {item['source']}")
                    st.write(item["content"])
                    st.divider()

    st.subheader("RAG 检索调试")
    with st.form("rag_debug"):
        query = st.text_input("检索问题", placeholder="例如：七天无理由退货需要满足什么条件？")
        top_k = st.slider("返回结果数 Top-K", 1, 10, 2)
        rewrite = st.checkbox("同时运行 Rewrite + Hybrid（调用 DeepSeek）")
        submitted = st.form_submit_button("运行检索", type="primary", icon=":material/search:")
    if submitted:
        if not query.strip():
            st.warning("请输入检索问题。")
        else:
            try:
                st.session_state.rag_debug_result = client.workbench_post(
                    "search", {"query": query, "top_k": top_k, "rewrite": rewrite}
                )
            except AgentClientError:
                st.error("检索失败，请检查后端服务和模型配置。")
    result = st.session_state.get("rag_debug_result")
    if isinstance(result, dict):
        rewrite_info = result.get("rewrite")
        if rewrite_info:
            st.caption(f"改写查询：{rewrite_info.get('effective', '')}")
            if rewrite_info.get("validation_issues"):
                st.warning("改写未通过约束校验，已使用原始 Query。")
        runs = result.get("runs", [])
        if runs:
            labels = {"dense": "Direct", "hybrid": "Hybrid", "rewrite_hybrid": "Rewrite + Hybrid"}
            tabs = st.tabs([labels.get(run.get("method"), "检索") for run in runs])
            for tab, run in zip(tabs, runs, strict=True):
                with tab:
                    st.caption(f"Query：{run.get('query', '')} · 检索耗时 {run.get('latency_ms', 0)} ms")
                    if not run.get("hits"):
                        st.info("未找到足够相关的政策内容。")
                    for rank, hit in enumerate(run.get("hits", []), 1):
                        with st.container(border=True):
                            st.markdown(f"**{rank}. {hit.get('title', '未命名章节')}**")
                            st.caption(
                                f"来源 {hit.get('source', '')} · Chunk {hit.get('chunk_id', '')}"
                                f" · 排序分 {hit.get('score', '—')}"
                                f" · 向量相关性 {hit.get('dense_relevance', '—')}"
                            )
                            st.write(hit.get("content", ""))


def _render_trace_details(detail: dict[str, Any]) -> None:
    status_badge(detail.get("status", ""))
    st.caption(
        f"{_timestamp(detail.get('created_at'))} · {detail.get('provider', '')} / "
        f"{detail.get('model', '')} · {detail.get('duration_ms', 0):.0f} ms"
    )
    if detail.get("question"):
        st.markdown(f"**用户问题**　{detail['question']}")
    if detail.get("answer"):
        st.markdown(f"**执行结果**　{detail['answer']}")
    events = detail.get("events", [])
    router = [item for item in events if item.get("kind") == "router"]
    planner = [item for item in events if item.get("kind") == "planner"]
    tools = [item for item in events if item.get("kind") in {"tool", "mcp"}]
    llms = [item for item in events if item.get("kind") == "llm"]
    if router:
        with st.expander("Router · 意图识别", expanded=True):
            for event in router:
                route = event.get("result") or {}
                st.write("意图：" + "、".join(route.get("intents", [])))
                entities = route.get("entities") or {}
                if entities:
                    st.caption("已提取参数：" + " · ".join(f"{key}: {value}" for key, value in entities.items()))
                if event.get("missing_fields"):
                    st.warning("需要补充：" + "、".join(event["missing_fields"]))
    if planner:
        with st.expander("Planner · 任务摘要"):
            for event in planner:
                if not event.get("invoked"):
                    st.caption("单意图请求：直接执行，无独立 Planner 调用。")
                for index, step in enumerate(event.get("steps", []), 1):
                    condition = step.get("when", "always")
                    st.write(f"{index}. {step.get('action', '')}" + (f" · 条件 {condition}" if condition != "always" else ""))
    if tools:
        with st.expander("工具调用与 RAG 证据"):
            for event in tools:
                name = event.get("name") or event.get("tool") or "工具"
                st.markdown(f"**{name}** · {event.get('status', '未知')} · {event.get('duration_ms', 0):.0f} ms")
                args = event.get("arguments") or {}
                if args:
                    st.caption("参数：" + " · ".join(f"{key}: {value}" for key, value in args.items()))
                result = event.get("result") or {}
                if event.get("error_type"):
                    st.error("异常类型：" + str(event["error_type"]))
                elif result and name != "search_policy":
                    st.caption("结果：" + " · ".join(f"{key}: {value}" for key, value in result.items() if key != "query_results"))
                for hit in result.get("query_results", []):
                    st.caption(f"证据：{hit.get('title', '')} · {hit.get('source', '')} · Chunk {hit.get('chunk_id', '')} · 分数 {hit.get('score', '—')}")
                st.divider()
    if llms:
        with st.expander("模型调用"):
            for event in llms:
                tokens = event.get("tokens") or {}
                st.caption(
                    f"{event.get('status', '未知')} · {event.get('duration_ms', 0):.0f} ms"
                    f" · 输入 {tokens.get('input_tokens', '—')} / 输出 {tokens.get('output_tokens', '—')} Token"
                )
                if event.get("error_type"):
                    st.error("异常类型：" + str(event["error_type"]))


def render_records(client: AgentClient) -> None:
    heading("执行记录", "查看历史客服请求及 Agent 执行结果。")
    data = _get(client, "traces", limit=50)
    rows = data.get("traces", []) if data else []
    if not rows:
        st.info("当前会话暂无执行记录。")
        return
    display = [{
        "请求时间": _timestamp(row.get("created_at")),
        "用户问题": row.get("question") or "历史记录（未保存问题摘要）",
        "模型": row.get("model", ""),
        "执行状态": {"completed": "已完成", "failed": "失败", "approval_required": "待确认"}.get(row.get("status"), "未知"),
        "总耗时": f"{row.get('duration_ms', 0):.0f} ms",
    } for row in rows]
    st.caption("点击表格中的一行查看详情；仅显示当前会话凭证可访问的记录。")
    selection = st.dataframe(
        display, hide_index=True, use_container_width=True,
        on_select="rerun", selection_mode="single-row",
    )
    selected_rows = selection.get("selection", {}).get("rows", [])
    if selected_rows:
        detail = _get(client, "traces/" + rows[selected_rows[0]]["trace_id"])
        if detail:
            st.subheader("执行详情")
            with st.container(border=True):
                _render_trace_details(detail)
