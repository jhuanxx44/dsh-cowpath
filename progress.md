# cowpath 存量轨迹普查 — 进度记录

> 工作区文件（gitignored）。正式结论沉淀到 wiki 前，这里保存过程数据与原始证据。
> 最后更新：2026-08-27

## 背景

cowpath（wiki/projects/cowpath.md）设计里「第一步」是手工跑 3–5 轮闭环，验证「真实工作里到底有多少可识别的弯路」。本普查直接对存量 DSH 会话做静态分析，是该前提的第一轮验证。

## 数据源与方法

- 存储：`~/.dsh/sessions/<project>/session-*/session.jsonl.zstd`（zstd 压缩 JSONL 事件流）
- 关键事件：`tool/call`（name+arguments）、`tool/result`（输出+`isError`）、`llm/retry`（provider 层重试）、`turn/step` 边界
- 扫描脚本：`local/cowpath/trail_scan.py`（用法：`python3 trail_scan.py <list_file>`）
- 全仓普查（第一轮）：14 项目 / 189 会话 / 18,641 tool 调用 / 352 isError / 147 llm 重试
- 深挖对象：pptgenaiserver（127 会话，8 批并行 subagent 扫描 + 1 批补扫）

## pptgenaiserver 深挖结果（2026-08-27）

| 指标 | 值 |
|---|---|
| 会话 | 127 |
| tool 调用 | 11,685 |
| 报错（isError） | 443 |
| llm/retry | 118（大头是 429 网关限流） |
| 配对率（报错后同 turn 同名成功） | 批次间 0.116–0.588，均值 ~0.35 |

### 报错按根因归类（估算）

| 类别 | 次数 | 占比 | 说明 |
|---|---|---|---|
| sandbox 升级空转 | ~260 | 58% | 「not strictly wider」~139 + 「invalid justification」~106；会话已处 danger-full-access 且审批禁用，agent 反复做必然被拒的事 |
| 文件工具协议 | ~150 | 34% | edit 前未 read（70+）、file changed 并发编辑（跨 13+ 文件）、old_string 不匹配、write 覆盖前未 read |
| 零星协议 | ~30 | 7% | grep 超限/超时、read 路径/offset、subagent 深度、job_kill 跨会话、goal stale ref |
| 业务领域 | ~2 | <1% | pilot-02 的 llm_calls 依赖 B0 extract 前置（pptgenaiserver 域） |

### 三个核心发现

1. **58% 报错是「空转」不是「弯路」**：同一根因（sandbox 升级协议），同会话内永远不可能成功。cowpath 噪声过滤必须前置「会话上下文感知」（读当前权限态/审批策略）。
2. **真弯路集中在 edit 协议，且错误信息几乎全部自解释**（"read the file, then retry" 之类）。agent 当场可自我修正——沉淀成技能的价值是预防不是解锁。
3. **频次 ≠ 价值**（对设计页「频次是优先级」的实质挑战）：最高频的是零价值空转；唯一不可自解释的领域知识（pilot 依赖）只出现 1–2 次。候选优先级信号：**报错自解释性**——自解释的当场能过不需要技能；不自解释的才值得蒸馏。

### 方法论备注

- batch 划分踩坑：split 生成的文件无 `.txt` 后缀，subagent prompt 里写错后缀导致 batch_1 重复扫了 batch_0，已补扫真实 batch_1（16 会话 / 951 calls / 97 errors / pair 0.577）
- 脚本 bug（subagent 发现）：env 关键词 `timeout` 匹配不到 `timed out`，grep 超时未计入 env_like

## B：报错自解释性量化（2026-08-27 完成）

方法：447 条 isError 报错（提取自 `local/cowpath/trail_scan.py` 的严格配对逻辑 + 模板化）按确定性关键词五分类。

| 类别 | 数量 | 占比 | 配对率 | 含义 |
|---|---|---|---|---|
| 会话上下文噪声 | 258 | 57.7% | 0.0% | sandbox 升级空转（escalation/justification） |
| 自带修复指令 | 125 | 28.0% | 6.4% | 报错文本含 "read the file, then retry" 等 |
| 原因明确需推断 | 35 | 7.8% | 11.4% | old_string not found、read not found、offset 超界等 |
| 现象不明/中断 | 27 | 6.0% | 0.0% | interrupted/aborted/partial output |
| 环境类 | 2 | 0.4% | 50.0% | 30s 超时 |

### B 的四个结论

1. **85.8% 报错不需要沉淀技能**（57.7% 噪声 + 28.0% 自带指令 + 0.4% 环境）。自带修复指令的错误文本本身就是最好的技能，蒸馏是重复劳动。**真正的蒸馏候选池只有 62 条（13.9%）= diagnosable 35 + opaque 27**。
2. **「自解释性」是有效的负向过滤器，但不是正向优先级信号**。它能把 85.8% 确定性排除，但剩下的 62 条里无法排序（diagnosable vs opaque 无明确优先级）。优先级排序仍要回到频次 + 领域相关性——但只在过滤后的小池子里有效。
3. **配对检测键要改**：严格口径（同 turn 同名 tool 重试）下所有类别配对率都低（0–11%），含自带修复指令的也只有 6.4%——因为 agent 修正时**换工具**（edit 失败 → read 成功 → edit 成功，跨工具跨 step）。cowpath 的「弯路配对」应按**操作对象**（文件路径/目标）配对，不是按 tool 名。
4. **上下文噪声可被会话元数据前置识别**：session.jsonl 开头就有 `permission/preset`、`sandbox/mode`、`approval/policy` 事件——258 条 sandbox 空转本来就能据此前置标记。cowpath 观察层要把会话元数据带进特征，噪声过滤第一层就是它。

### 对 cowpath 设计的修正建议（待用户确认后写进 wiki）

- 优先级信号改为**两段式**：先确定性过滤（会话上下文噪声 → 自带修复指令 → 环境），剩余小池子再按频次+领域相关性排序
- 弯路配对按操作对象配对，不按 tool 名
- 噪声过滤第一层 = 会话上下文感知（读 permission/sandbox/approval 元数据）
- 自带修复指令类报错：错误文本即技能，无需蒸馏（可考虑直接旁路为 harness 级规则注入，而非 SKILL.md）

## 下一步（按建议顺序）

- [x] 深挖 pptgenaiserver（完成）
- [x] B：量化「报错自解释性」（完成，结论见上）
- [ ] 可选验证：按操作对象重算配对率（检验「修正链跨工具」假设，数据现成）
- [ ] A：写第一份 SKILL.md 草稿（DSH 工具协议纪律，B 臂人手写版本）
- [ ] C：结论收敛后沉淀进 wiki（需用户确认；含对「频次=优先级」设计的修正）
- [ ] 脚本归档为可复用工具（增量扫描能力）

## 2026-09-05 本轮研究（实时复核）

- 当前扫描 `~/.dsh/sessions/`：538 个会话、42,849 tool calls、747 errors、533 llm/retry（由 `data/all_sessions.txt` 与 `data/current_scan.json` 生成，均 gitignored）。
- 实时最高频错误：sandbox escalation 159、edit 未先 read 130、invalid justification 114、file changed 未 re-read 64、old_string 不匹配 37。
- 发现脚本口径问题：`trail_scan.py` 的 `turns` 在跨文件循环外，key 只有 `(turn, step)`，可能跨会话配对；环境关键词漏 `timed out`；`extract_errors.py`/`classify.py` 使用 `/tmp` 固定输入，与 README 不一致。
- 首个真实 session 元数据含 `permission/preset`、`sandbox/mode`、`approval/policy`，支持上下文前置过滤设计。
- 本轮未写插件代码；结论与证据已记录于 `findings.md`。
- 临时修正版将 `turns` 每会话隔离后，同口径配对率从脚本的 72.8% 降为 3.2%（24/747），确认跨会话状态污染是实质性问题；此数仍只是同名工具配对，不是最终操作对象配对率。

## 2026-09-05 MVP 实现

- 新增 `tools/cowpath_mvp.py`，实现离线候选报告器：session 隔离、元数据读取、确定性过滤、对象提取、跨工具失败→成功配对、JSON/Markdown 输出。
- 合成样本通过：`edit` 失败 → `read` → `edit` 成功可识别。
- 当前 538 会话回放结果：756 errors、617 filtered、166 paired、153 candidate groups；结果仅作候选发现，不是质量结论。
- README 增加 MVP 用法；未实现自动写 SKILL、后台监听、语义判定和行为验证门。

## 2026-09-06 可安装离线审阅器

- `tools/cowpath_mvp.py` 新增 `--workspace` 模式：自动发现工作区历史 session，扫描现有 `.agents/skills/*/SKILL.md`，确定性计算融合建议。
- 交互选项：`n` 新建、`f` 融合、`s` 跳过、`q` 退出；只有明确选择 n/f 才写入，融合前生成 `.cowpath.bak`。
- 新增 `install.sh`，安装本地 `cowpath` 命令；新增可被 skills 工具安装的 `skill/cowpath/SKILL.md`。
- `--proposals-only` 提供完全只读模式。
