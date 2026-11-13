# COMP7607 Group Project — MemImpact

MemImpact 研究规划器级反事实记忆审计：逐条移除检索到的 Memory，重新运行 Planner，观察候选动作是否改变，并据此分配在线验证预算。

核心问题不是“MemImpact 是否一定优于所有方法”，而是：**Planner 重运行相对静态或候选动作条件信号有何增量价值，以及这种收益是否值得额外计算成本。**

## 当前状态

项目目前处于正式 held-out 评价阶段：

- 已跑通 Qwen × ToolSandbox 官方场景；
- 已实现 Memory 移除、配对规划、动作规范化、噪声校正、验证、重规划和隔离执行；
- 已实现 MemImpact、flip-only 消融、Always Proceed、Always Verify、Static 和 AMV-Guard-style 适配基线；
- 已生成 40 个带元数据的合成开发 episodes，并完成小规模真实模型对照；
- 已保留正向、负向、失败与调试记录；
- 已完成 Reminder Creation 的真实 Qwen pilot，并实现 Reminder Deletion validation pilot；
- 已实现显式 LangGraph 状态图和跨进程 ToolSandbox worker，并完成跨 runtime 语义检查；
- 已完成 120 个 held-out 场景、六种策略的预算 1 与预算 3 正式运行，以及离线标签、识别指标和 paired bootstrap 分析；
- 已完成按 scenario × policy 对齐的跨预算比较和按基础场景聚类的 bootstrap；两轮独立模型调用不被解释为严格的因果预算效应；
- 已完成英文 LaTeX 报告初稿、三个典型案例和 claim-to-artifact 附录；尚需完成展示、短演示和团队确认的贡献记录；
- 当前结论仅适用于该合成基准，不构成普遍安全保证。

详细过程和实验路径见 [WORKLOG.md](WORKLOG.md)。

## 仓库结构

```text
memimpact/          核心数据结构、Planner、评分、验证、策略和 ToolSandbox 执行
scripts/            环境 smoke test、实验、数据生成和分析入口
scenarios/pilot/    早期手工调试场景，保留用于追溯
benchmark/dev/      40 个合成开发 episodes 与 manifest
benchmark/reminder_pilot/  Reminder Creation 有效／过期时间场景
benchmark/deletion_pilot/  Reminder Deletion validation 场景
benchmark/deletion_validation/  四组独立删除验证场景
benchmark/heldout/  120 个正式 held-out episodes 与 manifest（budget 1/3 已完成）
configs/            开发、validation 与冻结 held-out YAML 配置
results/            原始轨迹、结果汇总、表格和图
proposal/           中英文 LaTeX proposal、PDF 和参考文献
report/             英文 LaTeX 项目报告与 PDF
docs/               实施计划、组会材料和评审意见
WORKLOG.md          持续工作日志
third_party/        本地 ToolSandbox checkout，不提交到本仓库
```

## 环境安装

需要 macOS 上可用的原生 Python 3.10。ToolSandbox 使用独立环境，避免旧依赖与后续 LangGraph 环境冲突。

```bash
git clone https://github.com/apple-aiml-research/ToolSandbox.git third_party/ToolSandbox
python3.10 -m venv .venv-toolsandbox
source .venv-toolsandbox/bin/activate

cd third_party/ToolSandbox
python -m pip install '.[dev]'
python -m pip install 'httpx==0.27.2'
cd ../..

python -m pip install -e . --no-deps
```

当前固定 ToolSandbox commit：

```text
c8571d7854316d2e1c5f288e59fe1e34e53f6dd1
```

LangGraph 使用另一个独立环境，不要与 ToolSandbox 环境混装：

```bash
python3.10 -m venv .venv
.venv/bin/python -m pip install -e . 'langgraph==1.2.20' 'PyYAML==6.0.1'
```

`configs/toolsandbox_tools.json` 已包含真实工具 schema。只有工具注册表变化时才需重新导出：

```bash
.venv-toolsandbox/bin/python scripts/export_tool_schemas.py
```

## 模型配置

当前使用百炼 `qwen3.8-flash` 和中国香港地域。请在本地终端设置环境变量，不要将凭据提交到仓库：

```zsh
read -s "DASHSCOPE_API_KEY?DashScope API Key: "
echo
read "DASHSCOPE_WORKSPACE_ID?Workspace ID: "
export DASHSCOPE_API_KEY
export DASHSCOPE_WORKSPACE_ID
export DASHSCOPE_REGION="cn-hongkong"
```

## 常用命令

运行 ToolSandbox 官方场景：

```bash
python scripts/run_qwen_toolsandbox.py --scenario wifi_off
```

运行单个 MemImpact 场景：

```bash
python scripts/run_memimpact_smoke.py \
  --scenario scenarios/pilot/stale_phone.json \
  --samples 3
```

运行真实 Qwen × LangGraph × ToolSandbox 删除场景：

```bash
.venv/bin/python scripts/run_langgraph_smoke.py \
  --scenario benchmark/deletion_pilot/stale_target.json \
  --policy memimpact \
  --model qwen3.8-flash \
  --temperature 0 \
  --samples 3 \
  --max-planner-attempts 2
```

使用冻结配置运行 LangGraph 批量对照；输出目录带 `langgraph` 标记，并额外记录工具 schema 哈希：

```bash
.venv/bin/python scripts/run_langgraph_comparison.py \
  --config configs/validation_matrix_v1.yaml
```

运行分层 20-episode 开发 pilot（不是正式 held-out 配置）：

```bash
.venv/bin/python scripts/run_langgraph_comparison.py \
  --config configs/dev_pilot_v1.yaml
```

正式 held-out 数据与配置已冻结；预算 1 和 3 均已完成。以下命令用于复现独立运行；新运行应保存为独立目录：

```bash
.venv/bin/python scripts/run_langgraph_comparison.py \
  --config configs/heldout_budget1_v1.yaml

.venv/bin/python scripts/run_langgraph_comparison.py \
  --config configs/heldout_budget3_v1.yaml
```

若批量运行中断，使用同一配置和原运行目录续跑。已完成的 policy 结果和共享规划样本会被复用，不会从头重跑：

```bash
.venv/bin/python scripts/run_langgraph_comparison.py \
  --config configs/heldout_budget1_v1.yaml \
  --resume results/heldout/heldout_budget1_v1_langgraph_20261113_013824
```

为原 runner 或 LangGraph 运行生成独立离线关键记忆标签；runtime 默认从结果元数据识别：

```bash
.venv/bin/python scripts/generate_critical_labels.py path/to/langgraph_run
```

生成开发集：

```bash
python scripts/generate_dev_benchmark.py
```

默认比较全部开发集；实际运行时建议先明确选择少量审核过的场景：

```bash
python scripts/run_policy_comparison.py \
  --scenarios \
    benchmark/dev/dev_direct_sam_valid_low.json \
    benchmark/dev/dev_direct_ava_stale_high.json \
    benchmark/dev/dev_indirect_sam_stale_high.json \
  --policies memimpact memimpact_flip always_proceed always_verify static amv_guard \
  --samples 3 \
  --verification-budget 1
```

比较两套 runtime 的决策与结果语义。`--strict` 适用于共享确定性 Planner 输入的回归；独立真实模型调用可能合理产生差异：

```bash
.venv/bin/python scripts/compare_runtime_results.py \
  path/to/original_run path/to/langgraph_run --strict
```

生成分析表和可靠性—成本图：

```bash
.venv-toolsandbox/bin/python scripts/analyze_comparison.py \
  path/to/comparison_summary.json
```

对两轮冻结实验做 matched 预算比较；默认将 JSON 和 CSV 保存到 candidate 运行目录：

```bash
.venv/bin/python scripts/compare_verification_budgets.py \
  results/heldout/heldout_budget1_v1_langgraph_20261113_013824 \
  results/heldout/heldout_budget3_v1_langgraph_20261113_141753
```

## 结果口径

- `verification_calls` 包含显式 Memory 验证和作为权威证据使用的只读查询。
- 共享缓存用于保证公平比较；每个策略仍记录独立部署时的逻辑成本，不代表整批实验的实际 API 支出。
- `similarity` 是 ToolSandbox 连续评价分数，不是任务成功率。
- ToolSandbox 的 `NoDataError` 会保存在 `execution.tool_result.error`；任务是否成功及是否有害仍按实际数据库变化计算。
- 当前场景和结果均为合成基准，不构成普遍有效性或通用安全保证。

## Proposal and Report

- [English proposal](proposal/memimpact_proposal.pdf)
- [中文 Proposal](proposal/memimpact_proposal_zh.pdf)
- [English project report](report/memimpact_report.pdf)

重新编译报告：

```bash
cd report
tectonic memimpact_report.tex
```
