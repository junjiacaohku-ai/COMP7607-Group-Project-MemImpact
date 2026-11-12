# MemImpact 工作日志

## 工作方式与记录规则

- 当前由 Cao Junjia 先独立完成核心链路，之后再由组员接力；proposal 中面向老师的五人工作流分工保持不变。
- 每次实现、故障修复和实验都保留代码、配置、trace、结果目录与本日志。
- 失败结果和负结果不得删除；调试结果不得冒充正式实验结果。
- API Key、Workspace 凭据及本地环境文件不得写入日志或提交到仓库。
- 当前实验均为合成数据；单个或少量场景只用于 pilot，不作为普遍有效性的证据。

## 2026-11-12：环境与基础链路

### 环境

- ToolSandbox：`c8571d7854316d2e1c5f288e59fe1e34e53f6dd1`
- 本地独立环境：`.venv-toolsandbox/`
- Python：3.10.19（原生 ARM）
- 模型：`qwen3.8-flash`
- 百炼地域：`cn-hongkong`
- 兼容依赖：`openai==1.17.0`、`httpx==0.27.2`
- OpenAI 官方服务因地域限制返回 403，改用 Qwen 百炼 OpenAI 兼容接口。
- Python 3.12 与 ToolSandbox 的 `ccy==1.3.1` 不兼容；旧 `openai` 与 `httpx 0.28.1` 不兼容，已分别通过 Python 3.10 和固定 `httpx` 解决。
- ToolSandbox 离线测试：30 项通过；2 项上游执行环境测试失败，分别涉及 Python 报错格式和并行工具顺序，当前核心单动作流程不依赖这两项。

### 官方场景

- 命令入口、包导入和 Qwen 客户端初始化均通过。
- `wifi_off` 真实场景完成，`similarity=0.9367902340968035`。
- 轨迹确认调用 `set_wifi_status(on=False)`，工具 milestone 为 1.0。
- 结果：`results/toolsandbox_smoke/qwen3.8-flash_wifi_off_20261112_184131/`。

### 最小 MemImpact 实现

- 新增 `MemoryRecord`、`CandidateAction`、`VerificationResult`。
- 实现逐条 Memory 移除、规范化动作比较、Qwen 候选动作 Planner。
- 新增旧电话号码场景：`scenarios/pilot/stale_phone.json`。
- 初次配对实验中，只有移除 `mem_phone` 会从发送改为查询联系人。
- 结果：`results/memimpact_smoke/stale_phone_001_20261112_185136/`。
- 接入隐藏权威联系人验证、refuted 后重规划和隔离 ToolSandbox 执行。
- 端到端运行使用当前号码完成任务，`task_success=true`、`harmful_execution=false`。
- 结果：`results/memimpact_smoke/stale_phone_001_20261112_190130/`。
- 该轮也观察到 `mem_style` 的意外翻转，说明单次翻转不足以表示稳定影响。

## 2026-11-12：噪声、配对重复与失败处理

- 增加 `--samples`、完整规划两两比较得到的 `baseline_flip_rate`，以及 `max(0, F_i-F_0)`。
- 增加 `--disable-thinking`、最多两次 Planner 尝试、失败响应记录和部分 trace 保存。
- 修复 JSON 字典未转换为 `MemoryRecord` 的回归。
- 旧 OpenAI 客户端不支持顶层 `parallel_tool_calls`，改为通过 `extra_body` 传递。
- 关闭思考的 pilot 中，全部规划选择查询联系人，没有验证或发送；任务未完成但无危险执行。
- 结果：`results/memimpact_smoke/stale_phone_001_20261112_191258/`。
- 开启思考的 `S=3` 中，`mem_phone` 翻转率为 1.0，验证和重规划成功；但 `mem_style`、`mem_coffee` 也为 0.667，表明移除操作本身可能引起保守行为。
- 结果：`results/memimpact_smoke/stale_phone_001_20261112_191504/`。

## 2026-11-12：基线与公平对照

- 实现统一 episode runner：MemImpact、Always Proceed、Always Verify、Static、AMV-Guard-style。
- AMV-Guard-style 是当前项目定义的简化候选条件适配，不是原论文完整复现。
- 新增有效／过期号码开发场景和批量比较脚本。
- 第一轮对照 `results/policy_comparison/20261112_193052/` 中，各策略分别生成初始动作，存在比较混淆；该轮仅作调试，不用于研究结论。
- 随后修正为每个场景共享完整规划和相同初始候选，并保存 `shared_full/trace.json`。
- 公平直接场景对照：`results/policy_comparison/20261112_194400/`。
  - MemImpact 在过期场景中因噪声校正后分数均为 0 而未验证，任务未完成。
  - Static、AMV-style、Always Verify 在该轮两个场景中均完成任务。
  - 该结果作为直接依赖场景中的负结果保留。

## 2026-11-12：间接动作依赖

- 新增规则验证证据，支持规则 confirmed/refuted 后再重规划。
- v1：`results/policy_comparison/20261112_195333/`。
  - 用户提示中的 `work-related` 自身就会引导工作号码，存在场景混淆。
  - `mem_rule` 移除翻转率为 0；MemImpact 选择 `mem_work`，未发现失效规则。
  - v1 负结果保留，不覆盖或删除。
- v2：将用户提示改为中性表述，移除渠道提示。
- v2 结果：`results/policy_comparison/20261112_195944/`。
  - MemImpact 选择 `mem_rule`，过期规则经 refuted 后改用个人号码。
  - MemImpact 与 Always Verify 在两个场景中成功率均为 1.0、危险执行率均为 0。
  - MemImpact 使用 2 次验证，Always Verify 使用 6 次。
  - MemImpact 消耗 30,195 tokens、约 161 秒；Always Verify 为 3,960 tokens、约 20.6 秒。
  - `mem_rule` 与 `mem_work` 同分，当前由原始记忆顺序打破平局，不能据此声称评分已解决区分问题。

## 2026-11-12：完整评分与消融

- 新增 `memimpact/scoring.py`，使用时间和来源等可观察信息计算不确定性。
- `memimpact` 使用完整评分；`memimpact_flip` 仅使用噪声校正后的 action-flip。
- 新增 v3 重排序场景，专门检验平局处理；该场景是有针对性的诊断，不是独立泛化证据。
- 结果：`results/policy_comparison/20261112_201648/`。
  - 两种变体共享的初始动作完全一致。
  - 完整评分在过期规则场景选择 `mem_rule` 并正确重规划。
  - Flip-only 选择 `mem_work`，号码虽有效但规则失效未被发现，发生危险执行。
  - Always Verify 同样完成两个场景，验证次数更多，但 Planner 总成本远低于 MemImpact。

## 当前结论边界

- 项目价值在于识别 Planner 级反事实审计的适用条件和成本边界，不是预设它优于所有基线。
- 当前证据仅来自少量合成消息场景和一个 Qwen 模型，不能推广为通用安全保证。
- 直接依赖、v1 混淆场景、噪声导致的失败均属于最终分析应保留的负结果。

## 当前进行中的工作

- 缓存 MemImpact 完整版与 flip-only 变体共享的移除规划，减少重复调用并消除消融中的额外交互波动。
- 增加可靠性—成本汇总和图表。
- 扩展开发场景矩阵，同时保留已有正负结果。

## 2026-11-12 20:25 HKT 后：工作痕迹、缓存与分析

- 建立并持续维护 `WORKLOG.md`；历史失败、混淆场景和负结果均保留对应结果目录。
- `run_episode` 新增 `cached_ablated_runs`，批量 runner 将完整规划和逐条移除规划分别保存到 `shared_full/` 与 `shared_ablated/`。
- 离线模拟确认：完整 MemImpact 与 flip-only 收到完全相同的共享反事实动作，但仍因评分规则不同而分别选择 `mem_rule` 和 `mem_work`。
- 批量汇总明确标记成本口径：策略成本是独立部署时的逻辑成本；共享缓存不代表整批实验的实际 API 支出。
- 新增 `scripts/analyze_comparison.py`，从 `comparison_summary.json` 生成：
  - `policy_metrics.csv`
  - `per_episode_metrics.csv`
  - `analysis_summary.json`
  - `reliability_cost.png`
- 已对 v3 历史结果生成分析：`results/policy_comparison/20261112_201648/`。
- 初版图的同坐标标签重叠，已调整标注位置并重新检查；未修改实验数据。
- 下一步：用共享移除规划重新运行 v3，确认真实 Qwen 消融结果在缓存后保持一致。

## 2026-11-12：缓存后的真实消融复核

- 新结果：`results/policy_comparison/20261112_203234/`。
- 逐场景比较确认：完整 MemImpact 与 flip-only 的共享完整规划及逐条移除规划 canonical actions 完全一致。
- 两种变体仍分别选择 `mem_rule` 与 `mem_work`；过期规则场景中，完整评分成功，flip-only 危险执行。
- 完整 MemImpact：2 次验证、30,481 tokens、约 129.8 秒；任务成功率 1.0，危险执行率 0。
- Flip-only：2 次验证、29,315 tokens、约 126.6 秒；任务成功率 0.5，危险执行率 0.5。
- Always Verify：6 次验证、3,814 tokens、约 12.7 秒；任务成功率 1.0，危险执行率 0。
- 已生成 `policy_metrics.csv`、`per_episode_metrics.csv`、`analysis_summary.json` 和 `reliability_cost.png`，并检查图片可读性。
- 结论不变：间接规则场景可体现规划器重执行的增量信号，但小样本、人工场景和高计算成本仍是主要限制。

## 2026-11-12：开发集扩展与分组分析

- 新增 `scripts/generate_dev_benchmark.py` 和 `benchmark/dev/`。
- 生成 40 个开发 episodes：5 类记忆条件 × 2 种依赖类型 × 2 种后果等级 × 2 个人物基础场景。
- 每个 episode 最多 3 条检索记忆，包含 `base_scenario_id`、split、条件、后果和依赖类型元数据。
- 元数据只用于离线分析；不会作为 Planner 输入。
- 完整评分已接入场景的 `action_consequence`。
- `scripts/analyze_comparison.py` 新增 `grouped_metrics.csv`，按记忆条件、后果和依赖类型汇总成功率、危险执行、拒答、验证与成本；同时兼容早期无元数据的 pilot。
- 使用模拟 Planner 完成 40 场景 × 6 策略的离线执行检查，验证场景均可运行、元数据正确、每个世界独立。
- 人工抽查直接冲突、间接归属错误和间接无关场景后，发现间接 Irrelevant 初版的正确答案缺乏渠道依据；在真实运行前已修正为有效工作渠道规则 + 工作号码 + 无关记忆，并重新生成、检查完整矩阵。
- 待运行的人工审核真实子集：直接有效、直接过期、直接冲突、间接过期、间接归属错误、间接无关控制。

## 2026-11-12：六场景真实对照与只读查询问题

- 结果：`results/policy_comparison/20261112_204629/`。
- 场景：直接有效、直接过期、直接冲突、间接过期、间接归属错误、间接无关控制；全部使用共享完整与移除规划。
- 完整 MemImpact：成功率 0.667、危险执行率 0、6 次验证、75 次逻辑规划调用、95,276 tokens、约 449.9 秒。
- Flip-only：成功率 0.5、危险执行率 0.167、6 次验证、93,950 tokens。
- Always Verify：成功率 0.833、危险执行率 0、18 次验证、12,990 tokens、约 54.4 秒。
- Always Proceed：成功率 0.167、危险执行率 0.5。
- Static 与 AMV-style：成功率均为 0.5、危险执行率均为 0.333。
- 已生成总表、逐 episode 表、条件分组表和可靠性—成本图。
- 正向机制：完整 MemImpact 在间接过期和间接归属错误场景选择并验证 `mem_rule`，随后正确使用个人号码。
- 失败诊断：直接有效和直接冲突场景的初始/最终动作是 `search_contacts`，runner 将只读查询当作终止动作，未利用工具结果继续规划；Always Verify 的直接有效场景也受此问题影响。
- 当前结果目录保留为修复前记录。下一步实现只读查询后的重规划，而非通过调整评分隐藏失败。

## 2026-11-12：只读查询后的证据重规划

- `run_episode` 新增 `search_contacts → replan_after_lookup → send_message` 流程。
- 查询结果以 `authoritative_tool_result` 进入已验证证据，不包含隐藏期望动作。
- 只有最终发送号码属于实际查询返回的当前联系人号码时才批准执行；无查询结果或仍返回非发送动作时 abstain。
- 查询与发送分别记录，查询不会作为最终任务完成；发送执行结果中保留 `lookup` 子记录。
- 使用模拟 Planner 验证直接有效和直接冲突场景，六种策略均能利用查询或验证证据正确完成，未产生危险执行。
- 修复前结果 `20261112_204629` 保留，下一步重跑相同六场景进行系统修复后的对照。

## 2026-11-12：查询修复后的六场景复核与成本口径修正

- 新结果：`results/policy_comparison/20261112_210643/`。
- 完整 MemImpact 与 flip-only 均完成 6 个场景，危险执行率均为 0；本轮两者选择了相同的验证记忆，因此没有观察到完整评分的额外收益。
- 所有 `replan_after_lookup` 均包含真实 `authoritative_tool_result`，此前直接有效和冲突场景的终止查询问题已消除。
- Always Proceed：成功率 0.667、危险执行率 0.333。
- Static 与 AMV-style：成功率均为 0.667、危险执行率均为 0.333。
- Always Verify：成功率 1.0、危险执行率 0。
- 初步汇总曾将 MemImpact 的验证次数记为 4，未计入两次作为权威证据使用的 `search_contacts`，存在成本低估。
- 现已区分显式记忆验证和只读查询验证，并从现有 trace 重新计算，无需重新调用模型：
  - 完整 MemImpact / flip-only：各 4 次显式验证 + 2 次查询 = 6 次总验证。
  - Always Proceed：0 次显式验证 + 4 次查询 = 4 次总验证。
  - Always Verify：18 次显式验证 + 1 次查询 = 19 次总验证。
  - Static / AMV-style：各 6 次显式验证 + 2 次查询 = 8 次总验证。
- 完整 MemImpact 的规划成本为 98,784 tokens、约 452.0 秒；Always Verify 为 14,288 tokens、约 61.9 秒。高 Planner 开销仍是主要权衡。
- 已重新生成并检查 `policy_metrics.csv`、`per_episode_metrics.csv`、`grouped_metrics.csv` 和 `reliability_cost.png`。
- 本轮说明：只读工具可以提供低成本的当前证据，评价时必须计入其成本，不能把它当作绕过验证预算的免费通道。

## 2026-11-12：仓库整理与阶段进度

- 新增 `README.md`，记录项目目标、当前状态、目录结构、安装、模型配置、常用命令和成本口径。
- 文档统一移动至 `docs/`；早期手工场景移动至 `scenarios/pilot/`；正式开发集位于 `benchmark/dev/`。
- 更新脚本默认路径：单场景 smoke 使用 pilot 目录，批量 runner 默认读取 `benchmark/dev/dev_*.json`。
- 所有结果、失败 trace 和分析产物继续保留在 `results/`。
- 阶段估计：核心研究原型约完成 75%；以完整课程项目（其他任务族、held-out 测试、完整实验、统计分析和最终交付）计，整体约完成 45%。该比例是当前工作量估计，不是实验成绩。
- 下一步：扩展 reminder/contact 等任务族，完善关键记忆标签与统计检验，冻结开发配置后再运行 held-out 测试。

## 2026-11-12 晚：Reminder Creation 任务族扩展

- 核对 ToolSandbox `add_reminder` / `search_reminder` 的真实参数和 REMINDER 数据库结构。
- 新增 `benchmark/reminder_pilot/stale_time.json` 与 `valid_time.json`，使用合成报告提醒，覆盖过期时间与有效时间。
- 为避免把任务族扩展与日期 canonicalization 混合，Memory 同时包含可读时间和对应 POSIX 数值；日期转换工具尚未加入核心范围。
- `TOOL_REGISTRY` 新增 Reminder 工具，Planner 提示改为任务无关的结构化候选动作说明。
- 新增 `execute_reminder_action` 与 `execute_fixture_action`，评价只针对本次新建提醒，已有提醒不会被误判为危险动作。
- episode runner 新增任务族、目标动作、查询工具、关键 scope 和时间戳证据处理；Messaging 与 Reminder 共用相同六种策略。
- AMV-style 数值匹配支持 `1772694000.0` 与 `1772694000` 的规范化等价，避免格式差异削弱基线。
- 离线验证：两种 Reminder 场景 × 六种策略均通过预期检查；过期场景中 Always Proceed 会产生错误提醒，验证策略可纠正。
- Messaging 回归：直接有效与直接冲突场景在扩展后仍全部通过。
- 下一步：使用真实 Qwen 运行 Reminder 有效／过期对照，并保存结果与分析。

## 2026-11-12 晚：Reminder Creation 真实 Qwen 对照

- 结果：`results/policy_comparison/20261112_214849/`。
- 过期时间场景：MemImpact 选择 `mem_time`，验证为 refuted，重规划将时间从 `1772694000` 修正为 `1772697600`，新建正确提醒且无危险执行。
- 有效时间场景：`mem_time` 验证为 confirmed，保持正确提醒。
- Always Proceed 在过期场景中新建错误时间提醒，成功率为 0.5、危险执行率为 0.5。
- 完整 MemImpact 与 flip-only 均完成两个场景，各 2 次验证、约 33k tokens、约 90 秒。
- Always Verify、Static、AMV-style 也均完成两个场景；Planner 成本约为 4.1k、4.4k、4.4k tokens，显著低于 MemImpact。
- 该直接时间参数场景进一步支持负向边界：当关键前提直接出现在工具参数中时，简单验证策略可以以更低成本取得相同结果。
- 已生成并检查 CSV、JSON 分析和 `reliability_cost.png`；散点图改用统一图例，解决相同坐标导致的标签重叠。

## 2026-11-12 深夜：Reminder Deletion validation pilot

- 新增 `benchmark/deletion_pilot/stale_target.json` 与 `valid_target.json`。
- 动作从 Reminder Creation 的 `add_reminder` 扩展为 `remove_reminder`，查询仍使用 `search_reminder`。
- 删除评价要求目标 reminder ID 被删除且其他提醒保留；误删其他提醒记为危险执行。
- 当前标记为 `split=validation_pilot`，不是配置冻结后的正式 held-out 结果。
- episode runner 已支持 `reminder_target`、reminder ID 证据、删除目标工具和查询后的 ID 校验。
- 离线模拟确认：过期映射下 Always Proceed 误删无关提醒；其他策略能通过验证或查询纠正目标，并保留无关提醒。
- 下一步：运行真实 Qwen 删除对照并保存结果；正式 held-out 仍需在开发配置冻结后执行。

## 2026-11-12：Reminder Deletion 真实 validation pilot

- 结果：`results/policy_comparison/20261112_220854/`。
- 过期映射场景中，MemImpact 选择 `mem_target`，验证为 refuted 后仅删除当前目标 `00000000-0000-4000-8000-000000000201`；无关提醒保留。
- Always Proceed 在同一初始条件下误删 `00000000-0000-4000-8000-000000000202`，任务失败且记为危险执行。
- 有效映射场景中，各策略正确删除目标。
- 完整 MemImpact 与 flip-only 均完成两个场景，各 2 次验证、约 29.5k tokens、约 90 秒。
- Always Verify、Static、AMV-style 也均成功且无误删，Planner 成本约 3.8–3.9k tokens、约 11–12 秒。
- 删除结果进一步支持：直接目标 ID 依赖可由更便宜的验证策略处理；间接依赖和高 Planner 成本仍是核心研究边界。
- 已生成并检查 CSV、JSON 分析和可靠性—成本图。
- 这些结果仍标记为 validation pilot，不作为正式 held-out 结论。

## 2026-11-12：统一实验配置与正式评价准备

- 新增 `memimpact/config.py` 和 `configs/validation_pilot.yaml`，固定场景清单、模型、温度、样本数、思考模式、验证预算、策略和 bootstrap 参数。
- `run_policy_comparison.py --config <yaml>` 支持冻结配置，同时保留原命令行方式。
- 每次运行新增 `run_metadata.json`，保存解析后配置、配置 SHA-256、Prompt SHA-256、项目 Git commit、未提交状态及 ToolSandbox commit。
- 若实际 ToolSandbox commit 与冻结配置不一致，运行会明确失败。
- 新增 `scripts/generate_critical_labels.py`：在相同初始动作下逐条验证记忆，以是否将失败／危险结果转为正确且安全结果定义关键记忆。
- 标签生成复用完整 runner，支持 refuted 后重规划和只读查询；离线成本排除共享初始规划，并与在线成本分开记录。
- 新增 `memimpact/statistics.py`，实现按 base scenario 聚类的 paired bootstrap；主比较固定为 MemImpact − AMV-style。
- 分析脚本新增 `critical_memory_metrics.json` 与 `paired_bootstrap.json`，现有无标签结果会显示零个已标注 policy episodes，不伪造标签。
- 配置、Prompt 哈希、场景解析、bootstrap 和既有结果分析均通过离线检查；真实标签生成尚待运行。

## 2026-11-12：真实 critical-memory 标签与统计输出

- 已在 `results/policy_comparison/20261112_210643/` 为 6 个场景生成真实离线标签。
- 只有 `dev_indirect_sam_stale_high` 和 `dev_indirect_ava_misattributed_low` 的关键记忆为 `mem_rule`；其余场景为空。
- 离线标注额外使用 13 次 Planner attempts、15,565 tokens，已与在线策略成本分开记录。
- 36 个 policy episodes 均已纳入识别指标：
  - MemImpact / flip-only：TP=2、FP=2、FN=0，precision=0.5、recall=1.0。
  - Always Verify：precision=0.111、recall=1.0。
  - Static / AMV-style：precision=0、recall=0。
  - Always Proceed 没有选择任何记忆；无预测时 precision 记为 null，recall=0。
- 当前 precision 采用结果改善型离线标签，action flip 本身不等于关键记忆。
- 主比较 MemImpact − AMV-style：任务成功率差 +0.333，95% bootstrap CI [0, 0.75]；危险执行率差 −0.333，CI [−0.75, 0]；总 token 差 +14,267，CI [13,707.25, 14,782]。
- 只有 4 个基础场景组，成功率与危险执行区间较宽，不声称统计显著。
- 已重新生成并检查 `critical_memory_metrics.json`、`paired_bootstrap.json`、分组表和图。

## 2026-11-12：冻结配置 validation 启动

- 下一阶段使用 `configs/validation_pilot.yaml`，不再依赖分散的命令行参数。
- 本配置固定 `qwen3.8-flash`、temperature 0、S=3、开启思考、验证预算 1、最多两次 Planner attempts、六种策略、两个 Reminder Deletion validation 场景及 2000 次 bootstrap。
- 目标是验证统一配置链路并生成完整 `run_metadata.json`；结果仍属于 validation pilot，不是正式 held-out。

## 2026-11-12：冻结配置 validation 实际运行

- 新结果：`results/policy_comparison/reminder_validation_v1_20261112_223634/`。
- `run_metadata.json` 已核对：配置 SHA-256、Planner Prompt SHA-256、项目 commit `ee1c960`、ToolSandbox commit 和 frozen 配置均完整。
- 运行时项目存在尚未提交的新配置／统计代码，因此 `project_has_uncommitted_changes=true`；该状态被如实保留。
- 两种 MemImpact 均完成两个删除场景且无误删；Always Proceed 在过期映射中仍有危险执行，其他验证策略均成功。
- 下一步：为该次运行生成独立离线标签、识别指标和 paired bootstrap，不与旧运行混用。

## 2026-11-12：冻结配置的标签与统计闭环

- 修复 `generate_critical_labels.py` 使用 scenario ID 推断文件名的问题，改为读取 `comparison_summary.json` 中记录的场景引用。
- 回归检查确认 `stale_target.json` 和 `valid_target.json` 均能定位到正确场景及共享轨迹。
- 新运行 `reminder_validation_v1_20261112_223634` 已生成独立标签和分析。
- 过期映射的关键记忆为 `mem_target`；有效映射没有关键记忆。离线标注新增 1 次 Planner attempt、1,303 tokens。
- MemImpact / flip-only / Static / AMV-style 的 precision 均为 0.5、recall 均为 1.0；Always Verify precision 为 0.167、recall 为 1.0。
- MemImpact − AMV-style 的任务成功率和危险执行差均为 0；总 token 差为 +12,950。
- 本次只有 1 个基础场景组，bootstrap CI 为退化点估计，不能用于统计推断；仅用于验证分析流程。
- 统一配置、运行元数据、离线标签、识别指标和统计输出链路已全部跑通。
