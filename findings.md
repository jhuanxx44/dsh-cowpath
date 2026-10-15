# 研究发现

## 项目定位与阶段

- `README.md` 与 `docs/design.md` 都把 cowpath 定位为 DSH 的独立后台会话观察者：监听用户指定工作区的 `session/event`，只从执行轨迹中提取“失败→修正→成功”的弯路，早期不做 memory。
- 设计权威源是 `/Users/jinghuan/code/me-wiki/wiki/projects/cowpath.md`；本仓库文档明确不替代它。
- 当前仍处于“立项前设计/第一轮存量轨迹普查”阶段，插件骨架按设计尚未开工。
- 最终交付物被定义为 A/B/C 三臂对比报告：裸跑、人工 SKILL、自动沉淀 SKILL；需要比较成功率、报错、返工、cost、latency，并用多次运行而非 n=1。

## 设计结论（已写入权威页）

- 验证器优先；结构层用确定性 lint，语义层人工抽检；不能让 LLM 自己给自己打分。
- 监听范围是用户指定工作区，技能落盘应与工作区隔离。
- 竞品/市场装机量不构成立项证据；执行轨迹→弯路配对→验证门是主要差异化空白。
- 第一轮普查建议把“频次优先级”修正为两段式：先过滤会话上下文噪声、自带修复指令、环境类，再对剩余池按频次和领域相关性排序；配对键按操作对象而非工具名。

## 当前机器上的实时数据（2026-09-05）

- `~/.dsh/sessions/` 当前有 538 个 `session.jsonl.zstd`，约 439M；仓库 README/progress 的旧口径是 189 会话、18,641 tool 调用、352 报错，不能当作当前快照。
- 直接运行 `tools/trail_scan.py data/all_sessions.txt` 得到：538 sessions、42,849 tool calls、747 errors、533 `llm/retry`、3 env_like、报告的同名工具配对率 0.728。
- 当前最高频模板仍是 sandbox escalation 空转 159 次、edit 前未 read 130 次、invalid justification 114 次、file changed 后未 re-read 64 次、old_string 不匹配 37 次。这与旧普查的根因方向一致：大量错误是协议/上下文噪声，不是领域知识。
- 样本首个会话的元数据事件明确包含 `permission/preset`、`sandbox/mode`、`approval/policy`；因此设计提出的会话上下文前置过滤在数据层可行。

## 脚本审计

- `tools/*.py` 可通过 `python3 -m py_compile`，均为标准库脚本。
- `trail_scan.py` 的 `turns` 在文件循环外创建、且 key 只有 `(turn, step)`；处理多会话时不同会话的同编号 turn/step 会混在一起，可能产生跨会话错误配对。应把 turns 放入每个文件循环内，或给 key 加 session 标识，再复算结果。
- `trail_scan.py` 的环境关键词包含 `timeout`，但不包含 `timed out`；`classify.py` 已包含 `timed out`。两脚本的环境分类口径不一致。
- `extract_errors.py` 和 `classify.py` 依赖固定的 `/tmp/ppt_all.txt`、`/tmp/all_errors.json`，README 的 `data/...` 用法与脚本实际接口不一致；这降低了可复跑性。
- `extract_errors.py` 使用 shell 拼接 `zstd -d -c "{f}"`，对含特殊字符的路径不稳健；当前 DSH 项目路径通常安全，但应改为 `subprocess.run([...])`。
- `data/` 与 `tools/__pycache__/` 已被忽略；本轮生成的 `data/all_sessions.txt`、`data/current_scan.json` 是本地证据，不应提交。

## 研究判断

1. 项目核心假设“真实工作里存在可识别弯路”已有静态证据支持，但还没有完成设计要求的 3–5 轮人工闭环和 A/B/C 三臂实验。
2. 当前数据规模扩大后，旧结论需要用修正后的扫描器重新计算；尤其不能直接引用 0.728 配对率，因为现有扫描器存在跨会话 key 污染风险。
3. 下一步最有价值的是先修复/验证扫描口径，再按操作对象重算配对率，并挑 1 个高频但非自解释候选写人工 SKILL、跑 lint 和三臂小实验；在此之前不应写插件骨架。

## 操作对象模型（2026-09-14）

- 当前采用两层模型：**Agent 工作区目录是观察、隔离和跨会话聚合边界；文件路径/URL/目标是工作区内判断失败→修正因果关系的证据键**。
- 完全只按工作区配对会把同一目录下互不相关的动作误连；完全只按绝对文件路径又无法表达“工作区级协议”候选。因此候选键为 `(workspace, target, failure_signature)`，报告同时保留 `workspace` 和 `object` 字段。
- DSH session 路径中的编码工作区目录作为稳定 `workspace` 标识，不尝试把连字符反解为绝对路径；`--workspace` 模式仍提供用户给定的绝对路径。
- 当前 538 个 session 重算：17 个工作区、764 errors、623 filtered、167 次按目标配对、155 个候选。该数字用于候选发现，仍不是技能价值结论。

## 配对率校验

- 用不改仓库的临时修正版（每个 session 单独重置 `turns`）重算，同样 538/42,849/747 数据得到 24 个同名工具后续成功，配对率 **3.2%**；现有 `trail_scan.py` 报出的 72.8% 明显受跨会话 `(turn, step)` 污染，不能使用。
- 这也强化了设计页已有判断：按工具名配对本身不足以识别跨工具修正链；下一步应按操作对象重算，而不是把 3.2% 当最终弯路比例。

## MVP 实现结果

- 新增 `tools/cowpath_mvp.py`：零依赖、无 LLM、使用系统 `zstd`，输入路径清单，输出 `cowpath-mvp/v1` JSON 和可选 Markdown。
- 对当前 538 个会话回放：756 errors，617 条被确定性过滤，166 次按操作对象配对，153 个候选分组。该结果用于发现候选，不代表技能价值或最终配对率；因为目前对象提取仍以路径和少量字段规则为主。
- 合成 JSONL/zstd 样本验证了失败 edit → read → 成功 edit 的跨工具链能被识别，且 session 状态不会串联。

## DSH 扩展点（2026-10-15，DSH 0.1.7-rc.2，只读调研）

- 用户插件：放 `~/.dsh/profiles/<p>/node_modules`（可 `link:`），`dsh plugin --profile <p> add link:/abs/path`；包内 `dsh.bundle.patch` 自动插行（不要再手工插，重复 id 会崩）。
- 改工具描述：`system-prompt/assemble` waterfall 可改 `assembly.tools`（直接发给模型，`dsh-agent-loop/lib/index.js:907,1048`）；改 description 安全，改 schema 有风险（执行端仍用原 schema 校验）。另可用 `ctx.systemPrompt.section` 加指导文本。
- 调用前：`tools/pre-execute` 只能 allow/deny/cancel/ask，**不能改参数**；`ctx.tools.guard` 为同步最终 deny。
- 调用后：`tools/post-execute` 可对失败结果替换 `content`、追加 `additionalContexts`、或 `block` 带纠正文本。参考实现 `dsh-repeat-tool-reminder`。
- 观察：`ctx.on('session/event')`、`tools/result` 可实时旁听全部 agent。
- 报错出处：old_string 未找到 `dsh-fs-local:703`；offset 越界 `dsh-tool-fs:53`；escalation/justification `dsh-sandbox:53`（参数说明 `sandboxPermissionsDescription()` `:86`）；edit 前未读 `dsh-fs-observation-policy:67`；读后文件变更 `dsh-fs-local:870-888`；subagent maxDepth `dsh-subagent:384`（可配置）。
- `dsh-memory-evolve` 是 Hermes 式 memory+skill 插件，未安装、不碰工具错误，与本方向不重叠。

## 错误头部（data/current_scan.json，538 sessions / 42,849 calls）

- bash sandbox 参数类：escalation 不比当前更宽 159 + justification 为空 114 = 273（约 36%）
- edit 协议类：edit 前未读 130 + 读后变更 64(+12 截断变体) + write 文件已不存在 8 ≈ 214（约 28%）
- old_string 不匹配 37、read 不存在 18、grep 输出超限 13、offset 越界 11
- 注意：这些在 cowpath 里被判为“自带修复指令”而过滤，但每条仍消耗一次往返；对 harness 改进而言它们恰恰是主要收益池。
