# AGENTS.md — dsh-cowpath

本仓库是 **cowpath：弯路驱动的技能沉淀器**（DSH 插件）的开发工作区，处于立项前设计 + 手工闭环验证阶段。

## 这是什么

- 设计权威源是 me-wiki 的 `wiki/projects/cowpath.md`；本仓库的 `docs/design.md` 只是摘要与指针，**有歧义以 wiki 为准**
- 当前阶段铁律：**先验前提，再写代码**。设计页「第一步」要求手工跑 3–5 轮闭环（真实工作里到底有多少可识别的弯路）验证通过前，不写插件骨架
- 所有结论必须能回指到证据：会话轨迹（`~/.dsh/sessions/`）、`progress.md` 里的数据、me-wiki 的 raw 快照

## 行为规则

- 进度、数据、脚本改动优先记录到本仓库（`progress.md`、`tools/`）
- `data/` 下的清单含绝对路径与本地会话元数据，**gitignored**，不进 git
- 分析脚本保持 Python 3 零依赖（只用标准库 + 系统 `zstd`），便于在任何机器复跑
- 改脚本时保持确定性：分类/聚类用规则与关键词，不引入 LLM 判断（这是 cowpath 自身的哲学：判定必须可复现）
- 涉及会话数据时注意隐私：只在本机处理，不写入日志或提交

## 与 me-wiki 的关系

- me-wiki 的 `wiki/projects/cowpath.md` 是本项目页（项目 1:1 对应）
- 本仓库的正式结论（普查结果、设计修正）需用户确认后沉淀回 me-wiki
- 本仓库不反向依赖 me-wiki 的文件内容来运行；脚本只依赖 `~/.dsh/sessions/`
