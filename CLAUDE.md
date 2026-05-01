## Team Operations — MiMo TTS 集成团队

> 由 CCteam-creator 自动生成，可按需修改。
> 此文件让 team-lead 的团队知识在上下文压缩后仍然保持。

### Team-Lead 控制平面

- team-lead = 主对话，不是生成的 agent
- team-lead 负责用户对齐、范围控制、任务分解和阶段推进
- team-lead 维护项目全局真相：主 `task_plan.md`、`decisions.md` 和此 `CLAUDE.md`
- **禁用独立子智能体**：团队存在后，所有工作通过 SendMessage 交给队友

### 团队花名册

| 名称 | 角色 | 模型 | 核心能力 |
|------|------|------|---------|
| backend-dev | 后端开发 | sonnet | MiMo TTS 集成 + fallback 链 + 风格标签 |
| frontend-dev | 前端开发 | sonnet | GitHub Pages 站点适配 + 音频播放器 |
| researcher-technical | 技术调研 | sonnet | prosody-MiMo 映射调研（只读） |
| researcher-product | 产品/市场调研 | sonnet | 市场分析 + 变现路径（只读） |
| reviewer | 代码审查 | sonnet | 安全/质量/性能/音频质量审查（只读） |
| architect | 架构师 | sonnet | 代码库审计 + 重构方案设计 |

### 任务下发协议

#### 消息送达时序（关键）
`SendMessage` 只在接收方 idle 时送达——无法打断进行中的任务。初始派单必须前置上下文。

#### 大任务下发检查（4 项）
1. 范围和目标 + 验收标准
2. 文档提醒："请创建 `<前缀>-<任务名>/` 任务文件夹"
3. 依赖说明：关键文件路径和行号
4. 审查预期：完成后是否需要代码审查

#### 任务文件夹前缀
- backend-dev / frontend-dev: `task-<名称>/`
- researcher-technical / researcher-product: `research-<主题>/`
- reviewer: `review-<目标>/`

### 通信速查

| 操作 | 命令 |
|------|------|
| 给单个智能体分配任务 | `SendMessage(to: "<名称>", message: "...")` |
| 广播给所有人 | `SendMessage(to: "*", message: "...")` |
| dev 请求代码审查 | dev 直接联系 reviewer（不经过 team-lead） |

### 状态检查

| 要检查什么 | 怎么做 |
|-----------|--------|
| 全局概览 | `TaskList` — 所有任务、负责人、阻塞情况一览 |
| 快速扫描 | 并行读取各 agent 的 `progress.md` |
| 深入了解 | 读 agent 的 `findings.md`（索引）→ 再看具体任务文件夹 |
| 方向检查 | 读 `.plans/mimo-tts-integration/task_plan.md` |

读取顺序：**progress**（到哪了）→ **findings**（遇到什么）→ **task_plan**（目标是什么）

### 文档索引

| 文档 | 位置 | 维护者 |
|------|------|--------|
| 导航地图 | .plans/mimo-tts-integration/docs/index.md | team-lead |
| 架构 | .plans/mimo-tts-integration/docs/architecture.md | team-lead, backend-dev |
| API 契约 | .plans/mimo-tts-integration/docs/api-contracts.md | backend-dev |
| 不变量 | .plans/mimo-tts-integration/docs/invariants.md | team-lead, reviewer |

### 审查维度

| # | 维度 | 权重 | STRONG 表现 | WEAK 表现 |
|---|------|------|-----------|---------|
| RD-1 | 音频质量 | 高 | 合成音频自然流畅，风格标签与 prosody curve 协同，无杂音/断句 | 音频生硬、风格标签失效、降级后质量断崖 |
| RD-2 | 容错与降级 | 高 | MiMo 失败时无感降级，fallback 链清晰，错误日志充分 | 静默失败、降级后音频质量不可用 |
| RD-3 | 代码可测试性 | 中 | TTS 模块可 mock、有集成测试、音色配置可离线验证 | 硬编码 API 调用、无法单测 |
| RD-4 | 商业可行性 | 中 | 产品方向有市场调研支撑、变现路径清晰 | 功能做完了但不知道怎么卖 |

### 核心协议

| 协议 | 触发时机 | 操作 |
|------|---------|------|
| 3-Strike 上报 | 智能体报告 3 次失败 | 读其 progress.md，给新方向或重新分配 |
| 代码审查 | 大功能/新模块完成 | dev 在 findings.md 写改动摘要，发给 reviewer |
| 阶段推进 | 阶段完成 | 调研完：读 findings 更新主计划。开发完：等 reviewer [OK]/[WARN] |
| Doc-Code Sync | API/架构变更 | 对应 docs/ 文件必须在同一任务中同步更新 |
| CI 门禁 | 代码变更后 | 运行 `python3 scripts/run_ci.py`，PASS 后才能提交审查 |

### Known Pitfalls

> 当识别到反复出现的失败模式时追加到这里。

（初始为空）
