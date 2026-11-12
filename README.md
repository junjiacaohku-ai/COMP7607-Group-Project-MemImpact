# COMP7607 Group Project — MemImpact

MemImpact 研究规划器级反事实记忆审计：逐条移除检索到的 Memory，重新运行 Planner，观察候选动作是否改变，并据此分配在线验证预算。

核心问题不是“MemImpact 是否一定优于所有方法”，而是：**Planner 重运行相对静态或候选动作条件信号有何增量价值，以及这种收益是否值得额外计算成本。**

## 当前状态

项目目前处于研究原型与开发集 pilot 阶段：

- 已跑通 Qwen × ToolSandbox 官方场景；
- 已实现 Memory 移除、配对规划、动作规范化、噪声校正、验证、重规划和隔离执行；
- 已实现 MemImpact、flip-only 消融、Always Proceed、Always Verify、Static 和 AMV-Guard-style 适配基线；
- 已生成 40 个带元数据的合成开发 episodes，并完成小规模真实模型对照；
- 已保留正向、负向、失败与调试记录；
- 已完成 Reminder Creation 的真实 Qwen pilot，并实现 Reminder Deletion validation pilot；
- 尚未完成正式 held-out 测试、统计置信区间、最终报告和展示。

详细过程和实验路径见 [WORKLOG.md](WORKLOG.md)。

## 仓库结构

```text
memimpact/          核心数据结构、Planner、评分、验证、策略和 ToolSandbox 执行
scripts/            环境 smoke test、实验、数据生成和分析入口
scenarios/pilot/    早期手工调试场景，保留用于追溯
benchmark/dev/      40 个合成开发 episodes 与 manifest
benchmark/reminder_pilot/  Reminder Creation 有效／过期时间场景
benchmark/deletion_pilot/  Reminder Deletion validation 场景
results/            原始轨迹、结果汇总、表格和图
proposal/           中英文 LaTeX proposal、PDF 和参考文献
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

生成分析表和可靠性—成本图：

```bash
python scripts/analyze_comparison.py path/to/comparison_summary.json
```

## 结果口径

- `verification_calls` 包含显式 Memory 验证和作为权威证据使用的只读查询。
- 共享缓存用于保证公平比较；每个策略仍记录独立部署时的逻辑成本，不代表整批实验的实际 API 支出。
- `similarity` 是 ToolSandbox 连续评价分数，不是任务成功率。
- 当前场景和结果均为合成 pilot，不构成普遍有效性或通用安全保证。

## Proposal

- [English proposal](proposal/memimpact_proposal.pdf)
- [中文 Proposal](proposal/memimpact_proposal_zh.pdf)
