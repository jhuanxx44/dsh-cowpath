# cowpath

独立的后台会话观察者（DSH 插件，立项前设计阶段）：旁听**用户指定工作区**里的所有 agent 会话，只收弯路沉淀 skill，早期不做 memory。

> 名字即机制：取自软件成语 *pave the cowpath*（把人实际走出来的路铺成正式路）。牛不规划路线，靠反复试走找出路——**留下来的那条就是走通了的那条**。
>
> 形态即策略：cowpath 是**独立旁观者**，不是主 agent 的 turn 后 fork——通过 `session/event` 流旁听**用户指定工作区**（范围由用户配置，不是全局），所以只能看到执行轨迹（tool 名 / 参数 / 结果 / 报错 / 退出码），看不到推理。因此「只收弯路」不是额外约定，而是形态的必然：轨迹里只有「失败→修正→成功」的成败转换可识别。弯路错因与解法**成对存**；执行轨迹作一等输入，lint 作确定性验证门，交付物是三臂对比报告；memory 早期不做（刻意排除 Hermes 式 memory+skill 双写）。

设计权威源：me-wiki 项目页 `wiki/projects/cowpath.md`（本仓库的 `docs/design.md` 是摘要与指针，不是替代）。

## 当前状态

| 阶段 | 状态 |
|---|---|
| 立项前设计 | ✅ 已收敛（2026-08-26；定义精化 2026-08-27） |
| 存量轨迹普查（第一轮手工闭环） | 🔄 进行中 |
| 插件实现 | ⛔ 未开工（设计决定：先验前提再写代码） |

## 交付物：三臂对比报告

cowpath 的交付物**不是插件，是一份实验报告**——拿同一批真实任务，在三种配置下各跑一遍，回答「自动沉淀的 skill 到底值不值」：

| 臂 | 配置 | 回答的问题 |
|---|---|---|
| A | 裸跑，无 skill | 基线——任务本身有多难 |
| B | 人工手写 skill | 人写的上限在哪 |
| C | cowpath 自动沉淀的 skill | 自动蒸馏能接近或超过 B 吗 |

**B 臂是关键，不是陪衬。** 市面上大多数同类项目只比 A 和 C：自动蒸馏赢了「无 skill 裸跑」就宣布成功，但这赢得很廉价——C 只要有 skill 就大概率赢 A，说明不了任何事。真正要回答的问题是：**自动蒸馏出来的 skill，比得上人认真手写的吗？** 如果 C 打不过 B，诚实的结论就是「skill 手写就够了，自动沉淀不划算」——这个实验必须允许自己被推翻。

指标不是「看起来好不好」，是可数的：任务成功率（lint 通过 + 人工抽检）、tool 报错数、返工轮数、cost、latency。同一任务多跑几次报 `pass@k`，不用单次采样定生死（n=1 是自进化竞品最普遍的硬伤）。

为什么交付物是报告而不是插件：市场普查证明装机量给不出有效信号（92.4% 零装机），cowpath 不追求「做出插件有人用」。这份报告同时是 me-wiki 里 career 目标 Milestone 1（可点开的 Harness 作品）与 Milestone 3（评测/benchmark 作品）的交集产物——价值与装机量无关。

## 工作区结构

```
dsh-cowpath/
├── progress.md        # 进度记录：普查数据、发现、B 结论、下一步
├── docs/design.md     # 设计摘要 + wiki 指针
├── tools/             # 分析脚本（Python 3，零依赖）
│   ├── trail_scan.py  # 轨迹扫描器：会话 JSONL → 弯路统计 + 报错模板聚类
│   ├── extract_errors.py # 提取全部 isError 报错（模板 + 配对信息）
│   └── classify.py    # 报错自解释性五分类（噪声/自带指令/需推断/不明/环境）
└── data/              # 会话清单等过程数据（gitignored，含绝对路径）
```

## 快速开始

```bash
# 生成某项目（或全部）的会话清单：每行一个 session.jsonl.zstd 绝对路径
ls -d ~/.dsh/sessions/--Users-jinghuan-code-pptgenaiserver--/*/ \
  | sed 's|/$||;s|$|/session.jsonl.zstd|' > data/ppt_all.txt

# 扫描一批会话，输出弯路统计 + 报错模板聚类（JSON）
python3 tools/trail_scan.py data/ppt_all.txt

# 提取全部报错 + 配对信息（默认读 data/ppt_all.txt，写 data/all_errors.json）
python3 tools/extract_errors.py
# 也可以显式指定输入清单和输出路径
python3 tools/extract_errors.py data/all_sessions.txt -o data/all_errors.json

# 按自解释性分类（默认读 data/all_errors.json）
python3 tools/classify.py
# 或指定另一个提取结果
python3 tools/classify.py data/current_errors.json
```

## 关键数据（截至 2026-08-27）

- 全仓：14 项目 / 189 会话 / 18,641 tool 调用 / 352 报错 / 147 llm 重试
- 深挖：pptgenaiserver 127 会话 / 11,685 tool 调用 / 447 报错
- 报错结构：57.7% 会话上下文噪声（sandbox 空转）、28.0% 自带修复指令、7.8% 原因明确需推断、6.0% 现象不明、0.4% 环境
- 核心发现：**85.8% 报错不需要沉淀技能**；候选池只有 62 条（13.9%）

详见 `progress.md`。

## 相关

- me-wiki 项目页：[[cowpath]]（`wiki/projects/cowpath.md`）
- 模式来源：[[agent-self-evolution-patterns]]
- 宿主：[[deepseek-harness]]

## MVP：弯路候选报告器

`tools/cowpath_mvp.py` 是当前阶段的离线 MVP。它不调用 LLM、不写入 skill，只生成待人工审核的候选：

```bash
python3 tools/cowpath_mvp.py data/all_sessions.txt \
  -o data/mvp.json --markdown data/mvp.md
```

输入清单每行一个 `session.jsonl.zstd` 绝对路径。MVP 会隔离每个 session 的状态，读取权限/sandbox/approval 元数据，过滤会话噪声、环境错误和自带修复指令，并按文件路径或其他操作对象寻找后续成功动作。输出包含错误签名、失败/修正工具、独立会话数和原始示例；不会自动生成或覆盖 `SKILL.md`。

## 可安装的离线工作区审阅器

安装为本地命令：

```bash
./install.sh
cowpath --workspace /absolute/path/to/workspace
```

Cowpath 会自动定位该工作区的历史 DSH 会话，生成候选并逐项询问：`n` 新建 Skill、`f` 融合到建议的现有 Skill、`s` 忽略、`q` 退出。写入前必须选择 `n` 或 `f`；融合前会创建 `.cowpath.bak` 备份。只查看候选可使用 `--proposals-only`。
