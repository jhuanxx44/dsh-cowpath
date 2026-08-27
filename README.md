# cowpath

弯路驱动的技能沉淀器（DSH 插件，立项前设计阶段）。

> 名字即机制：取自软件成语 *pave the cowpath*（把人实际走出来的路铺成正式路）。牛不规划路线，靠反复试走找出路——**留下来的那条就是走通了的那条**。cowpath 只收「失败→修正→成功」的弯路，执行轨迹作一等输入，lint 作确定性验证门，交付物是三臂对比报告。

设计权威源：me-wiki 项目页 `wiki/projects/dsh-shortcut.md`（本仓库的 `docs/design.md` 是摘要与指针，不是替代）。

## 当前状态

| 阶段 | 状态 |
|---|---|
| 立项前设计 | ✅ 已收敛（2026-08-26） |
| 存量轨迹普查（第一轮手工闭环） | 🔄 进行中 |
| 插件实现 | ⛔ 未开工（设计决定：先验前提再写代码） |

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

# 提取全部报错 + 配对信息
python3 tools/extract_errors.py   # 读 data/ppt_all.txt，写 data/all_errors.json

# 按自解释性分类（读 data/all_errors.json）
python3 tools/classify.py
```

## 关键数据（截至 2026-08-27）

- 全仓：14 项目 / 189 会话 / 18,641 tool 调用 / 352 报错 / 147 llm 重试
- 深挖：pptgenaiserver 127 会话 / 11,685 tool 调用 / 447 报错
- 报错结构：57.7% 会话上下文噪声（sandbox 空转）、28.0% 自带修复指令、7.8% 原因明确需推断、6.0% 现象不明、0.4% 环境
- 核心发现：**85.8% 报错不需要沉淀技能**；候选池只有 62 条（13.9%）

详见 `progress.md`。

## 相关

- me-wiki 项目页：[[cowpath]]（`wiki/projects/dsh-shortcut.md`）
- 模式来源：[[agent-self-evolution-patterns]]
- 宿主：[[deepseek-harness]]
