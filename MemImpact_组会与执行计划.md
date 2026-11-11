# MemImpact 组会与执行计划

> 目标：在 11 月 30 日展示前，完成一个可运行、可复现、有对照实验的 MemImpact 原型，而不只是演示 Agent 流程。
>
> 核心研究问题：**逐条移除 Memory 并重新运行 Planner 所产生的 action-flip 信号，能否比不重新规划的策略更好地权衡可靠性与验证成本？**

## 1. 明天开会需要先定下来的事情

建议会议控制在 60 分钟，结束时必须形成明确决定，而不是只讨论概念。

### 1.1 会议议程

1. **统一研究问题（5 分钟）**  
   项目不是自动清理记忆，也不是判断记忆文本是否“看起来可靠”；核心是测量移除记忆后，Planner 的候选动作是否改变，再决定是否验证。

2. **确认核心范围和展示产出（10 分钟）**  
   确认本文第 2、8 节。核心未完成前，不增加天气、路线、旅游规划等新工具，不承诺多模型、多步长任务或自动记忆形成。

3. **确定技术环境和模型（10 分钟）**  
   确认 Python 3.11、LangGraph、ToolSandbox、模型提供商及 API 可用性。指定一个确切的模型 ID、温度等解码参数和实验费用上限；先做 ToolSandbox 依赖 smoke test。

4. **确认五人分工与接口（15 分钟）**  
   按第 4 节认领工作流。共同确认 Memory、Action、VerificationResult、EpisodeTrace 的字段；之后跨模块修改接口必须同步通知。

5. **确认实验规则和里程碑（10 分钟）**  
   确认开发集、测试集、基线、指标、调用预算以及第 6 节日期。阈值只能在开发集上调节，看完测试结果后不能回头调参再把它当作 held-out 结果。

6. **确定协作方式（10 分钟）**  
   确定代码仓库、任务看板、共享文档和固定同步时间；约定每人交付代码时附最小运行命令，实验结果必须能追溯到配置和 trace。

### 1.2 会后应立即记录的决议

- 五位成员的真实姓名及 A–E 工作流分工。
- 模型 ID、API 负责人、费用上限、密钥的本地管理方式。
- 最终演示设备与备用录屏方案。
- 每周两次短同步的具体时间；阻塞超过半天就在群内提出。
- 代码、数据、实验结果和幻灯片的存放位置。

## 2. 核心范围：做到什么才算完成

### 2.1 必须完成（P0）

- 一个基于 **Python + LangGraph** 的 memory-augmented tool agent。
- 一个适配 **Apple ToolSandbox** 的执行与评测接口；使用其模拟工具和世界状态，不另造一套独立环境。
- 最多 3 条固定检索记忆的逐条移除、配对重规划和 action-flip 计算。
- `Proceed / Verify / Abstain` 决策、验证预算，以及 refuted 后的重新规划。
- **5 个主要策略**：MemImpact、Always Proceed、Always Verify、Static Policy、AMV-Guard-style Candidate-conditioned Policy。
- 一个 **action-flip-only** 消融版本，用来检验完整评分公式是否真的有必要。
- 约 **40 个开发 episodes + 120 个测试 episodes**；最终测试覆盖 messaging 和 reminder deletion 两类任务。
- 本地 JSONL/CSV trace、结果表、可靠性—成本图、成功与失败案例。
- 可运行的代码、版本化数据、复现实验命令、报告、幻灯片及短演示。

### 2.2 暂缓（P1/P2）

- **P1：核心结果完整后再做**：LangSmith 可视化、额外重复试验、对抗性记忆、relevance baseline。
- **P2：有充裕时间才做**：第二个模型、更多记忆数量、不完整验证、oracle 参考。
- **不在本次核心范围**：自动记忆抽取与巩固、真实用户数据、长程多步任务、多个新任务领域。

同学提出的“换不同 AI model”有价值，但应作为扩展。单模型 matched comparison 没完成前加入多模型，会让数据、调用费用和分析量同时增加，且不能回答核心研究问题。

## 3. 系统到底怎么运行

### 3.1 统一执行流程

1. 从场景文件初始化隔离的 ToolSandbox 世界，并载入固定的 Memory 集合。
2. Planner 根据 User Prompt、Memory 和已验证证据生成结构化候选动作。
3. 非关键动作直接经过普通门控；关键动作进入 MemImpact 审计。
4. 对每条记忆分别构造 `R \ {m_i}`，从相同输入重新运行 Planner；这些分支**只能提议动作，不能执行工具**。
5. 将完整记忆与移除记忆后的动作规范化，比较工具名及参数，计算每条记忆的 action-flip rate。
6. 综合 action flip、可观察的不确定性、动作后果和验证成本，对验证候选排序。
7. 策略输出：
   - **Proceed**：执行获批动作；
   - **Verify**：通过只读权威接口验证一条记忆，消耗一次预算；
   - **Abstain**：高后果关键前提仍无法解决时不执行。
8. 验证为 confirmed 或 unknown 时返回策略门；refuted 时废弃旧动作，用纠正后的证据重新规划。
9. 执行最多一个状态改变动作，最多两次 replan；记录 ToolSandbox 原生评价和项目指标。
10. 导出完整 trace，包括提示配置、提议动作、每次验证、token、延迟、费用、最终状态和隐藏评价结果。

### 3.2 核心算法定义

对第 `i` 条记忆进行 `S` 次配对运行：

`F_i = (1/S) * Σ_s 1[canonical_action(a_full^(s)) != canonical_action(a_without_i^(s))]`

主实验暂按 `S=3`。3 条记忆意味着一次审计至少需要 **12 次 Planner 调用**：3 次完整规划 + 3 条记忆 × 3 次移除规划，尚不包括验证和 replan。必须在 pilot 后根据实测费用确定总预算。

验证排序可使用：

`V_i = consequence(a) * uncertainty_i * (λ1 * F_i + λ2 * normalized_outcome_shift_i) / (verification_cost_i + ε)`

核心实现优先完成不含 outcome-shift 的版本。所有权重、阈值只在开发集选择；另跑仅使用 `F_i` 的 action-flip-only 版本。

### 3.3 两条安全实现红线

- 反事实分支不得修改共享 Memory、ToolSandbox 世界或真实外部服务。
- 隐藏 ground truth、记忆类别标签和正确动作不得进入模型 prompt 或在线策略输入；它们只供离线 evaluator 使用。

## 4. 五个人如何分工

每人对一个工作流负责，但需要指定一名备份 reviewer，避免某人生病或受阻时整个项目停摆。

| 负责人 | 主要工作 | 必须交付的实物 | 关键协作 |
|---|---|---|---|
| **A：Runtime / Agent** | LangGraph 状态图、Planner/Executor 分离、模型接入、ToolSandbox adapter、Memory Store 载入、场景重置、动作规范化、统一 trace | 可运行 Agent、adapter、共享 schema、配置、集成测试、最小运行命令 | 给 C/D 提供统一策略入口；给 E 提供完整 trace |
| **B：Benchmark / Environment** | 选择并适配 ToolSandbox 场景；生成 synthetic users/memories/current records；定义验证接口、隐藏期望和正确/有害结果；划分开发/测试集 | 场景 fixtures、生成脚本、40+120 数据、authoritative verifier、数据说明和人工检查记录 | 给 A 环境接口；给 C 验证结果；给 E 固定评价规则 |
| **C：MemImpact Method** | 逐条移除、配对规划、action-flip 计算、评分排序、Proceed/Verify/Abstain、预算与 replan 控制、action-flip-only 变体 | MemImpact 策略代码、单元测试、参数说明、方法章节、代表性运行案例 | 使用 A 的 runtime 和 B 的 verifier；不得自行修改环境标签 |
| **D：Baselines / Related Work** | Always Proceed、Always Verify、Static、AMV-Guard-style；确保共享相同动作和预算接口；维护文献对比 | 4 个基线、比较测试、baseline 配置、introduction/related work、对比表 | 与 C 共用 observable features 和决策处理规则；不修改 MemImpact |
| **E：Evaluation / Delivery** | 批量实验 runner、指标聚合、bootstrap CI、图表、失败分析、结果追溯、报告与幻灯片整合、演示和排练 | 一键复现实验命令、CSV/图/表、结果分析、最终报告、slides、demo、贡献记录 | 使用 B 的评价规则和 A 的 trace；组织集成与交付 |

### 并行启动方式

- A 第一天先发布 schema 和 fake planner，避免所有人等完整 Agent。
- B 先交付 5–10 个手工检查过的小场景，再自动生成完整数据。
- C、D 先基于 fixtures 实现策略，不等 ToolSandbox 全量接入。
- E 先用人工构造的 example traces 做统计和画图脚本。
- 每人实现时同步写自己的 methods 小节，E 最后统一语言和结果叙述。

## 5. Evaluation Test Case 具体怎么设计

### 5.1 每个 episode 的固定字段

- `scenario_id / base_scenario_id / split`
- `user_prompt`
- `initial_world_state`
- `available_tools`
- `retrieved_memories`：稳定 ID、claim、entity/scope、timestamp、provenance
- `candidate_consequence_level`
- `verification_evidence`：权威当前记录及 confirmed/refuted/unknown 规则
- `hidden_expected_outcome`：正确完成条件、有害执行条件
- `memory_condition` 和生成参数：仅 evaluator 可见

### 5.2 Memory 条件与同学建议的对应

核心统一为五类，避免不同模块使用不同标签：

| 条件 | 含义 | 与初步想法的关系 |
|---|---|---|
| Valid | 当前正确，包括“旧但仍有效”的记忆 | 准确 + 旧但仍有效 |
| Stale | 曾经正确，但当前世界状态已改变 | 过时失效 |
| Conflicting | 与另一条可见信息或证据冲突，需验证才能解决 | 错误/冲突情形 |
| Misattributed | 内容本身可能成立，但归错用户、联系人或实体 | 错误记忆的一种重要形式 |
| Irrelevant | 与当前决策无关，作为不应触发额外验证的负对照 | 新增的必要对照 |

“旧”不能直接等于“该验证”，“文本有冲突”也不能直接等于“验证后一定改变结果”。后果高低要独立于记忆正误变化，防止策略靠一个浅层特征完成全部判断。

### 5.3 数据矩阵与划分

- 开发任务：contact updates、reminder creation，约 40 episodes，用于调试与选阈值。
- 最终测试：messaging、reminder deletion。
- 测试矩阵：2 个任务族 × 5 个记忆条件 × 2 个后果等级 × 6 个场景变体 = **120 episodes**。
- 同一基础场景的变体放在同一 split，防止仅替换名字造成泄漏。
- 每个场景保存可重建的初始状态；相关变体在 bootstrap 时按 base scenario 分组。
- 天气、通勤路线、旅游行程可作为未来扩展，但当前不要为了这些例子另建工具和世界模型。

### 5.4 Critical-memory 标签

“移除后动作改变”不等于“这条记忆值得验证”。关键记忆标签由单独的离线验证—重规划试验生成，根据最终模拟结果判断验证是否改善决策；离线生成标签的成本与在线部署成本分开报告。

## 6. 从现在到 11 月 30 日的逐阶段计划

| 时间 | 主要任务 | 当日/阶段退出标准 |
|---|---|---|
| **11/10–11/11** | 阅读方案、开会、认领分工、确定模型/API/预算、建立仓库和接口文档 | 五人职责明确；schema、P0 范围和模型决议写进共享文档 |
| **11/12–11/13** | A 做依赖 smoke test；B 交付小场景；C/D 写策略骨架；E 准备 example trace 和分析脚本 | 明确 ToolSandbox 与 LangGraph/LangChain 能否共环境；若冲突，采用独立进程/环境 + adapter，并验证消息传递 |
| **11/14–11/16** | 接通 Planner → Gate → ToolSandbox execution → evaluator → trace；实现场景隔离和动作规范化 | **第一个完整 episode 跑通**；counterfactual 不执行工具；结果能保存并重建 |
| **11/17–11/18** | C 完成 MemImpact 与 action-flip-only；D 完成四个基线；B 扩展开发数据；E 完成批量 runner | 同一批小场景可运行全部策略；所有验证和 replan 都进入统一 trace |
| **11/19–11/20** | 跑 20 个开发 episodes pilot；检查数据质量、泄漏、状态污染、异常调用和实测费用 | 修复阻塞问题；冻结模型、prompt、阈值、预算、split 和正式配置 |
| **11/21–11/23** | 跑 held-out 测试矩阵；保存原始输出；按需补跑失败调用但保留错误记录 | 五种主要策略及 action-flip-only 均有完整 matched 结果；主实验费用未超上限 |
| **11/24–11/25** | 统计 task success、harm、coverage、safe-proceed recall、验证次数和总成本；生成 CI 与图表；人工分析案例 | 结果表和可靠性—成本图冻结；每个数字都能定位到配置和 trace |
| **11/26–11/27** | 完成报告、slides 和 demo；只在核心结果完整后选择一个 P1 扩展 | 展示故事完整；扩展失败也不影响已冻结的核心结果 |
| **11/28–11/29** | 全流程复现、试讲、计时、修复展示问题、准备离线录屏和备份图 | 从干净命令可重建关键结果；演示不依赖临场修改代码；最终版本冻结 |
| **11/30** | 展示与问答 | 讲清研究问题、方法差异、实验结果、成本、失败案例和局限 |

最后三天不再加入新算法。若进度落后，先砍扩展和场景美化，不砍基线、trace、结果追溯或核心测试。

## 7. Evaluation 怎么比较，才不只是在“演示 Agent”

### 7.1 必须回答的比较

1. **Always Proceed vs 所有验证策略**：验证是否真正降低错误和有害执行？
2. **Always Verify vs 选择性验证**：能否以更少验证获得接近的安全性？
3. **Static vs MemImpact**：planner re-execution 是否优于可观察的静态特征？
4. **AMV-Guard-style vs MemImpact**：这是最关键的对照，检验“重新规划”相对“只审计固定候选动作”的增量价值。
5. **Full score vs action-flip-only**：额外的不确定性、后果和成本项是否必要？

所有方法使用相同场景、固定检索记忆、模型、解码参数和可比预算。选择性方法分别测试 1 次和 3 次验证预算；Always Verify 验证完整检索集合。

### 7.2 指标及口径

- **Task success**：最终隐藏任务条件是否满足。
- **Harmful execution rate**：实际执行有害动作的 episodes / 全部评价 episodes。
- **Proceed coverage / Abstention rate**：避免靠大量拒答获得表面安全。
- **Safe-proceed recall**：原始候选安全的 episodes 中，获批执行的比例。
- **Critical-memory precision / recall**：在线选中的验证记忆是否对应离线关键记忆标签。
- **Verification calls**：实际检查次数。
- **Total calls / tokens / latency / monetary cost**：包含规划、反事实审计、验证、重试和 replan，不能只计算最后一次执行。
- 分任务族、记忆条件和后果等级报告结果；用 paired bootstrap confidence intervals，按基础场景分组重采样。
- 在预定义子集上做“不移除记忆”的重复运行，估计普通 Planner 波动。

### 7.3 LangSmith 的定位

LangSmith 可用于查看 trace、管理 dataset experiment 和自定义 evaluator，但它不是模拟环境，也不是核心评价真值来源。核心评分和 trace export 必须先能完全离线运行；LangSmith 只作为 P1 可观测性增强，不能成为展示能否完成的前置条件。

## 8. 11 月 30 日最终展示建议

建议控制在约 10–12 分钟，具体按老师后续要求调整：

1. **问题（1 分钟）**：旧电话号码导致发错人的例子；为什么“所有记忆都验证”太贵。
2. **研究缺口（1 分钟）**：已有工作有反事实记忆审计和固定候选动作验证；我们专测 Planner 重运行的增量价值。
3. **方法（2 分钟）**：一张 LangGraph 流程图 + 一次逐条移除示例 + action-flip 定义。
4. **Benchmark 与对照（1.5 分钟）**：ToolSandbox、五类记忆、四个基线、预算控制。
5. **核心结果（3 分钟）**：可靠性—成本图、主结果表、分记忆类型结果；即使结果为负也如实解释。
6. **Demo / Trace（1.5 分钟）**：展示一个验证后避免有害动作的案例，以及一个不必要验证或错误翻转的失败案例。
7. **结论与局限（1 分钟）**：合成任务、少量任务族、单模型、反事实调用开销；不把结论推广到所有 Agent。

展示当天必须准备：可运行代码、固定数据、结果表、图、成功/失败/不必要验证案例、报告、贡献记录，以及关键 demo 的录屏或完整 trace 备份。

## 9. 明天会后第一周的实际任务清单

- [ ] A：发布共享 schema、fake planner、依赖检查和 ToolSandbox smoke test。
- [ ] B：提交 5–10 个手工场景及对应 authoritative evidence / hidden outcome。
- [ ] C：在 fixtures 上实现单条移除、动作规范比较和最小 Verify gate。
- [ ] D：提交 Always Proceed、Always Verify、Static、AMV-Guard-style 的统一策略接口。
- [ ] E：定义 trace 字段、指标分母、结果表模板和批量运行配置。
- [ ] 全员：确认一次完整 episode 的成功标准，不把“模型返回了一段合理文字”当作任务成功。

**项目完成标准不是 MemImpact 一定优于所有基线，而是能复现地回答：Planner 级反事实审计带来的可靠性和安全性提升，是否值得它增加的调用、token 与延迟。**
