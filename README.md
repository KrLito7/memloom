<p align="center">
  <img src="docs/banner.svg" alt="memloom" width="100%">
</p>

<p align="center">
  <b>把本地的 AI 编程会话，织成一本能翻、能链、能搜索的 Obsidian 记忆库。</b><br>
  <sub>Turn your AI coding sessions into a navigable Obsidian memory vault — local, offline, no LLM required.</sub>
</p>

<p align="center">
  <code>python -m memloom build</code> &nbsp;→&nbsp; 打开 <code>vault/</code> 就是一本库
</p>

---

## 这是什么

你每天都在跟 AI 写代码。DSH、Claude Code、Codex、Antigravity 把每次对话都存成了本地档案 —— 但它们是一堆 `.zstd`、`.jsonl`，散在若干个隐藏目录里。**这些档案里装着你解决问题的全部过程，却几乎不可能被再次读到。**

memloom 把这些档案读成一本 Obsidian 库：

```
vault/
├── 00-总索引.md          项目地图 + 主题分类 + 时间线
├── 10-项目/              按工作目录 + 共享文件聚类出的项目页
├── 20-会话/              一次会话一页：你问的、它答的、跑了什么、错在哪
├── 30-主题/              踩坑 / 代码 / 工具 —— 同类问题跨会话归到一起
├── 90-原文归档/          原始档案的位置（不复制、只索引）
└── 99-使用说明.md        这本库是怎么生成的、哪些字是机器写的
```

页面之间全部用 `[[双链]]` 连着 —— 打开一篇会话，可以直接跳回它所属的项目、它踩过的坑、它碰过的文件。

不想先跑一遍？[`examples/sample-vault/`](examples/README.md) 里有五页真实生成的输出（索引、一页会话、一页主题、归档表、说明书），可以先看看这本库长什么样。

## 长什么样

<p align="center">
  <img src="docs/hero.png" alt="散落在隐藏目录里的会话档案 → memloom → 一本 Obsidian 库" width="100%">
</p>

左边是你硬盘上真实存在的东西：一个 120 MB 的单行 JSONL、一堆 zstd 帧、藏在 `.` 开头的目录里。它们打不开、搜不到，下次想问「上次那个报错怎么解的」只能从头再问一遍。

右边是同一条命令跑出来的库。打开其中一页会话，正文大概是这样（真实输出，来自 [`examples/sample-vault/`](examples/sample-vault/20-会话/2026-10-29-3f395ff1-obsidian-agent.md)）：

```markdown
---
类型: 会话记录
日期: 2026-10-29
轮次: 6
工具调用: 151
工作目录: ~workspace
---

# Obsidian Agent记忆库搭建与知识图谱生成

← 返回 [[00-总索引]]

**项目**：[[default-workspace · memloom]]

**相关主题**：[[踩坑-grep search failed (exit N)： rg： … IO error for…]] · [[工具-find]] · [[工具-present]]

## 工具用量

| 工具 | 次数 |
|---|---|
| `pwsh` | 57 |
| `write` | 31 |
| `subagent` | 21 |
```

那几个 `[[...]]` 在 Obsidian 里是真的能点的：点「工具-find」跳到**所有**用过 find 的会话，点「踩坑-…」跳到这个错误跨会话的全部现场。库不是把聊天记录存成 text，是把它编成了能走的网。

## 设计上的三条硬规矩

| 规矩 | 意味着什么 |
|---|---|
| **零第三方运行时依赖** | 纯 Python 标准库，3.9+ 能跑。没有 `pip install` 失败、没有依赖冲突、没有供应链风险。 |
| **不用 LLM** | 路径、命令、错误、工具统计、标题全部由规则抽取。同一批档案跑两次，结果逐字节一致 —— 可以进 git、可以 diff。 |
| **只读你的档案** | 不修改、不移动、不在档案目录里写任何东西；不上传任何内容。唯一写的地方是你指定的 `--out`。 |

> LLM 增强（给主题起更像人话的名字、跨会话总结）留在 v0.2，且永远是**可选的开关**，不是前置条件。

## 不想要输出？

`--dry-run` 只算不写盘；`memloom scan` 连页面都不生成，只报每条来源有多少档案。想先确认自己的档案能不能读：`memloom doctor`。

## 快速开始

> [!WARNING]
> **PyPI 上那个叫 `memloom` 的包不是本项目。**（那边是另一个无关项目，v0.9.0）
> 装它请认准这条命令，或者直接用下面的 `git clone`：
>
> ```bash
> pip install "memloom @ git+https://github.com/KrLito7/memloom"
> ```
>
> 直接 `pip install memloom` 会装到别人的包，命令行为完全不同 —— 这不是你能修的问题，是名字撞了。

**需要 Python 3.9+**，不需要别的依赖。

```bash
# 1) 拿到代码
git clone https://github.com/KrLito7/memloom.git
cd memloom

# 2) 先体检：这台机器上到底有没有可读的档案
python -m memloom doctor

# 3) 看看会读哪些文件（只列，不解析、不写盘）
python -m memloom scan

# 4) 生成
python -m memloom build --out vault
```

> **`git clone` 一直连不上？**（国内网络访问 github.com 不稳定，有时能通有时完全没响应）
> 去 [Releases](https://github.com/KrLito7/memloom/releases/latest) 下那个 **Source code (zip)** —— 164 KB，秒下。
> 解压后 `cd` 进目录，从上面第 2 步开始跑一模一样的命令。**不需要 git。**

然后用 Obsidian 的「打开文件夹作为仓库」指到 `vault/`。

**跑起来大概是这样**（真实运行录的，不是示意图 —— 136 个会话跑完 14 秒）：

<p align="center">
  <img src="docs/quickstart.gif" alt="doctor 体检 → build 生成整本库的真实终端画面" width="100%">
</p>

<p align="center"><sub>中间那段空白不是卡住了：它在解 111 个 zstd 存档。</sub></p>

<details>
<summary><b>Windows 上 <code>python</code> 敲了没反应？</b></summary>

多半是 Microsoft Store 的占位别名。用 `py -3` 或 `python3`，或者装完 Python 后关掉「设置 → 应用 → 应用执行别名」里的 `python.exe` / `python3.exe`。

本项目的输出是 UTF-8。老版终端（cmd / PowerShell 5.1）可能把中文显示成乱码，先 `chcp 65001` 或直接用 Windows Terminal。
</details>

<details>
<summary><b>不想先装，只想看看生成出来长什么样？</b></summary>

[`examples/sample-vault/`](examples/README.md) 里有五页真实输出，直接拿 Obsidian 打开那个目录就能看到双链跳转的效果。
</details>

装成命令（可选）：

```bash
pip install -e .              # 之后可以直接 memloom build
pip install -e ".[zstd]"      # 顺手装 pyzstd，解压更快（不是必需）
```

## 命令

| 命令 | 作用 |
|---|---|
| `memloom doctor` | 体检：默认档案目录在不在、zstd 后端走的哪条路、能不能写盘 |
| `memloom scan [--root NAME=PATH]` | 只扫描，打印每条来源的档案数、总量、后端 |
| `memloom build --out DIR` | 生成整本库（默认扫所有已知来源） |
| `memloom build --root dsh=~/.dsh/sessions` | 只扫指定来源；可重复传 `--root` |
| `memloom build --since 30 --min-turns 3` | 只收最近 30 天、且轮次 ≥ 3 的会话 |
| `memloom build --dry-run` | 只算不写，看看会生成多少页 |
| `memloom build --full` | 忽略增量缓存，全部重新解析 |
| `memloom build --verbose` | 连命中缓存的文件也回显（默认只回显本次真正解析的那几个） |
| `memloom build --quiet` | 一个文件都不回显，只留汇总 |

`--adapter auto|dsh|claude-code|codex|antigravity` 强制指定某个适配器（默认按文件特征自动判断）。

### 第二次跑为什么快

每次 `build` 都在输出目录里留一份 `<out>/.memloom/`：一个 `state.json`（每条档案的 size + mtime_ns + 适配器名）和一份解析结果的缓存。下次跑只有**真的变过的档案**才会被重新解析，其余直接读缓存。缓存只写在你指定的输出目录里，**绝不写进你的档案目录**（那些目录本来就是只读的）。

```
$ memloom build --out vault        # 第一次：138 个存档，全部解析
会话     136
主题    58
页面   206（本次改动 206）
项目     9
缓存   复用 0 / 新解析 136
耗时   14.2s

$ memloom build --out vault        # 再跑一次，其中一份还在长
页面   206（本次改动 3）
缓存   复用 135 / 新解析 1
耗时   2.34s
```

（数字取自作者机器 2026-11-20 在**刚解压的发布包**上的一次实测 —— 就是上面那张 GIF。这些数字每天都在长，你自己跑出来的数量和耗时当然不会一样，看**比例**就行：第二次只剩读缓存和比对的成本。

注意那个 `新解析 1`：作者当时正开着编辑器写东西，所以**恰好有一份档案还在增长**，只有它被重新解析，其余 135 份照旧命中。这正是设计意图 —— 不是「全有或全无」。）

写盘也是增量的：内容没变就不碰文件、只删带生成标记的旧页 —— 所以重复跑是零写入，Obsidian 不会因为一次重建把你看的页面刷掉。缓存坏了、换了版本、想强制重来：`--full` 或直接删掉 `<out>/.memloom/`。

## 支持哪些档案

| 来源 | 路径 | 状态 |
|---|---|---|
| **DSH** | `~/.dsh/sessions/**/*.zstd` | ✅ 已验证（本机 111 个真实档案 / 106 MB） |
| **Claude Code** | `~/.claude/projects/<project>/*.jsonl` | ✅ 已验证（本机 27 个真实文件 / 220 MB，最大一个 120 MB） |
| **Codex** | `~/.codex/sessions/**/*.jsonl` | ⚠️ beta：适配器按已知格式写好；本机现有 29 个 Codex 档案，但尚未逐个核对解析结果 |
| **Google Antigravity** | `~/.gemini/antigravity/brain/<对话 id>/.system_generated/logs/transcript.jsonl` | ✅ 已在本机真实对话上验证（只读 `transcript.jsonl`，`transcript_full.jsonl` 是同一份的未截断副本，会被忽略） |

DSH 的 `.zstd` 是多 frame 拼接的老格式，标准库解不开。memloom 按顺序尝试：`pyzstd` → Python 3.14+ 的 `compression.zstd` → 本机 `node` 的 `zlib.zstdDecompressSync` → `zstd` 命令行；四条路都不通时给一句能照做的报错，而不是 traceback。

适配器是插件式的：一个来源 = 一个类（`memloom/adapters/*.py`），实现 `match` / `sniff` / `load`。加一个新来源不需要动主流程，见 [docs/adapters.md](docs/adapters.md)。

## 它是怎么把会话变成项目的

大多数人的问题是**所有会话都跑在同一个工作目录里**（比如同一个 workspace），所以「一个目录 = 一个项目」会把一百次会话塌成一个没用的页面。

memloom 的做法：

1. 先按规范化后的 `cwd` 分桶；
2. 用**碰过的文件**做并查集，把明显属于同一件事的桶合并；
3. 桶太大（默认 > 12 个会话）时，按共享文件重新切分，并用主要目录给它命名；
4. 主题不是「关键词」而是三件可验证的事：同一错误指纹出现在 ≥ 2 个会话里（`踩坑`）、同一二级路径出现在 ≥ 3 个会话里（`代码`）、同一个非通用命令出现在 ≥ 3 个会话里（`工具`）。

细节和取舍写在 [docs/architecture.md](docs/architecture.md)。

## 已知局限（写在这里，不藏在代码里）

- **主题名是规则拼出来的**，可能不好听（`踩坑-Error- ECONNREFUSED`）。要更像人话的名字得等 v0.2 的可选 LLM 步骤。
- **页面不含 LLM 撰写的内容**。所有正文都来自你的 prompt、模型的回复、工具输出，和规则抽取 —— `99-使用说明.md` 里也这么写。
- **Codex 适配器未验证**（见上表）。
- **不做语义搜索**。链接和分类是结构化的；找关键词请用 Obsidian 自带搜索。

## 常见问题

**跑完只有几个页面 / 一个页面都没有？**
先跑 `memloom doctor`，看采集路径那三行有几个 `✓`。全是不存在，说明你还没用那些工具，或者档案在别的地方 —— 用 `memloom build --root 名字=路径` 手动指过去。

**`页面 0`，但 doctor 说找到档案了？**
大概率是会话太短被过滤了。默认 `--min-turns` 会丢掉空对话，加 `--min-turns 0` 再看。

**zstd 解不开？**
DSH 的 `.zstd` 是多 frame 拼接的，标准库解不了。memloom 会依次试 `pyzstd` → Python 3.14 内置 → 本机 `node` → `zstd` 命令行。四条都不通时报错会告诉你缺哪条。最省事的修法是 `pip install pyzstd`。

**页面名不好听（`踩坑-Error- ECONNREFUSED`）？**
是的，规则拼出来的。v0.2 会加可选的 LLM 命名，但那永远是开关不是前置条件 —— 不想用模型的人不该被挡住。

**我删了会话档案，库里还有？**
`build` 只增不删老页面（带生成标记的会重写）。删了源档案后重新 `build --full` 会重新结账；想彻底清空就换个 `--out` 目录重来。

**它会读我的档案目录吗？会改吗？**
只读。不写、不移动、不复制原始档案（`90-原文归档/` 只记位置）。唯一写入的地方是你 `--out` 指的目录。全程无网络请求，可以断网跑。

**能支持 XXX 吗？**
一个来源 = 一个类，实现 `match` / `sniff` / `load` 三个方法，见 [docs/adapters.md](docs/adapters.md)。想加哪个开个 issue，附一段（脱敏后的）样本文件结构就行。

## 测试

```bash
python -m unittest discover -s tests -t .
```

59 个测试，跑 0.4 秒。fixture 是从真实档案里裁剪出来的（DSH 的紧凑事件流、Claude 的 `.jsonl`、Codex 的 rollout），不是手编的假数据 —— 格式变了测试会先红。

改完代码想确认没把「第二次构建是 no-op」这条核心承诺弄坏，跑一条命令就够：

```bash
python tools/preflight.py
```

它会检查编码与换行是否干净、仓库里有没有混进你本机的绝对路径、元数据是否齐全、测试是否全绿、以及**第二次 build 是否真的 0 改动**。零依赖，退出码即结论。

## 路线图

- **v0.1**（本仓库）：四种适配器（DSH / Claude Code / Codex / Antigravity）、规则抽取、项目/主题聚类、vault 渲染、增量解析（`.memloom/` 状态 + 解析缓存）、`doctor` / `scan` / `build`。
- **v0.2**：`--enrich` 可选的 LLM 主题命名、更多来源（Cursor、Gemini CLI、Copilot）、跨机器共享缓存。
- **v0.3**：把「同一个 bug 在三个项目里复发过」这类跨项目线索自动挖出来。

## 许可

MIT。归档格式属于各自工具的作者，memloom 只读你自己机器上的文件。
