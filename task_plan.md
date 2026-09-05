# Cowpath MVP 执行计划

## 目标
实现一个零依赖、可离线复跑的弯路候选报告器：从 DSH `session.jsonl.zstd` 清单中提取会话上下文、按操作对象配对失败→修正→成功链，确定性过滤噪声，并输出 JSON/Markdown 候选报告。

## 阶段
- [complete] 1. 规划 MVP 接口与数据边界
- [complete] 2. 实现会话解析、对象提取、过滤与配对
- [complete] 3. 用合成样本和真实会话回放验证
- [complete] 4. 更新文档与记录限制

## 验收标准
- 不同 session 的 turn/step 绝不互相配对
- 支持 `.zstd` 清单和单条路径；只使用 Python 标准库与系统 zstd
- 输出可机器消费的 JSON，并可选 Markdown
- 候选包含失败签名、修正动作、对象、session 证据和过滤原因
- 对真实当前数据可运行并报告统计

## 错误
暂无
