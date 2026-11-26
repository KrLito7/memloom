# 加一个新来源

一个来源 = 一个类。放在 `memloom/adapters/`，实现四个东西，然后去 `adapters/__init__.py` 的 `ADAPTERS` 里登记一行。主流程（聚类、抽取、渲染）不需要改。

```python
from .base import Adapter
from ..model import Session, Turn

class MyTool(Adapter):
    name = "my-tool"              # 内部 id，也用于 --adapter 取值
    label = "My Tool"             # 给人看的名字，出现在页面里
    suffixes = (".jsonl",)        # 只按后缀初筛
    default_roots = ["~/.mytool/sessions"]

    def match(self, path):        # 便宜的路径判断：在 defaults roots 里就认
        return "/.mytool/" in path.replace("\\", "/")

    def sniff(self, head: str):   # 路径判断不出来时看前 16 KB 内容
        return '"mytool_version"' in head

    def load(self, path):         # 真正解析，返回 Session 或 None
        ...
```

`load` 的契约：

- **返回 `Session`，或者 `None`**（认不出内容就老实返回 None，别抛异常 —— `load_all` 会把异常记进 `problems`，但静默返回 None 更干净）。
- `Session.source` 放**档案的绝对路径**（不是目录）。
- `Session.started_at` 是 **epoch 毫秒**。拿不到就留 `None`，页面会显示 `未知`。
- `Session.turns` 里，`Turn.prompt` 是用户说的，`Turn.reply` 是模型说的，`Turn.tools` 是这次会话跑过的工具。`ToolUse.ok` 用三态：`True` / `False` / `None`（不知道）。
- **不要把 `reasoning` / `thinking` 块放进 `reply`。** 这是硬要求：抽取阶段会全文搜错误行，思考过程里的「如果失败就……」会污染成假踩坑页。`base._NOISE_BLOCKS` 就是干这个的。
- 工具调用只统计一次。如果同一次调用在事件流里出现两遍（DSH 有 `tool/call` 事件，也有 `tool-call` 内容块），只取一处。

## 各来源的坑（都是踩过的）

### DSH

`.zstd` 不是单帧，是**多 frame 拼接**：每个事件一个 frame。标准库 `zstandard` 只能读第一帧，所以必须先按 magic `28 b5 2f fd` 切帧（`zstd_frames.split_frames`），再逐帧解。

四种解码后端按顺序尝试，这是为了「用户什么都没装也能跑」：

1. `pyzstd`（可选依赖，最快）
2. 标准库 `compression.zstd`（Python 3.14+）
3. 本机 `node`：`node -e` + `zlib.zstdDecompressSync`，从 stdout 读结果（**不要落临时文件** —— 在沙箱里写系统临时目录会被拒）
4. `zstd` 命令行

事件是**紧凑 JSON，一行一个**。判断来源时不要 `json.loads` 整个文件：先用 `_head(path, 16384)` 取头部，把空白压掉再匹配特征串。

### Claude Code

`~/.claude/projects/<path-slug>/<uuid>.jsonl`，一行一个 JSON 对象，行类型有 15+ 种（`user` / `assistant` / `ai-title` / `cost-state` / `system` / `file-history-*` / `queue-operation` …）。只认自己认识的，其余忽略 —— Anthropic 加新行类型不该让适配器崩。

- 标题优先取 `ai-title`（Claude 自己起的），没有就退到第一条 prompt 的前 40 字。
- `isSidechain: true` 的行是子 agent 的旁支对话，**跳过**，否则一次会话里会混进好几条不相关的时间线。
- 目录名 `C--Users-you` 是路径分隔符被压成 `-` 的结果，`group._cwd_name` 会取最后一段当名字。

### Codex

`~/.codex/sessions/**/*.jsonl`，事件在 `payload` 里：

- `session_meta` → id / cwd / model
- `event_msg` 里的 `user_message` / `agent_message` → 一问一答
- `response_item` 里的 `function_call` / `function_call_output` → 工具调用

⚠️ 本机没有 Codex 档案，这个适配器**只用合成 fixture 验证过**。真跑出问题请开 issue 贴一段脱敏后的 rollout。

### Antigravity

`~/.gemini/antigravity/brain/<对话 id>/.system_generated/logs/transcript.jsonl`，一行一步，按 `step_index` 排序：

- `USER_INPUT` → 用户的话（去掉 `<USER_REQUEST>` 包装和 `ADDITIONAL_METADATA` 等附加块）
- `PLANNER_RESPONSE` → 模型回复，`tool_calls` 里是工具调用
- `GENERIC` → 工具输出；档案里**没有 call id**，所以按顺序和尚未回应的调用配对
- `SYSTEM_MESSAGE` → 框架提醒，跳过

同目录的 `transcript_full.jsonl` 是同一份内容的未截断版本，**不读**，否则每个对话都会算两次；因此这个适配器只按路径识别，不做内容嗅探。没有标题字段，标题取第一条像样的提问。工作目录档案里没有，显示「未知」。

## 测试怎么加

`tests/fixtures/` 里的样本是从**真实档案裁剪**出来的（按事件类型采样 + 截断长文本），不是手编的假数据。加新适配器时配一个 `<name>-session.jsonl` fixture，然后在 `tests/test_adapters.py` 里加两件事：能被 `detect_adapter` 认出来，以及 `load` 出来的轮数/工具数对得上。
