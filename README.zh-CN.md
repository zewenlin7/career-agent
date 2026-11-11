# Career Agent

[English](README.md)

## 项目定位与当前阶段

Career Agent 是面向个人求职者、单用户私有部署的求职工作区。它将职位管理、可追溯的求职材料与明确授权的模型流程结合起来，不代替用户自动投递或发送消息。

当前处于 **v0.5 Application/Interview 收口**。Profile Workspace 已通过用户人工验收；Application/Interview 整体最终确认和 Internal 最终人工验收仍待完成。用户已通过真实调用观察到 Mock 根据回答选择下一主问或针对性追问，以及 Debrief 失败项重试、独立新建分析成功。这些是有限功能验证，不是广泛模型质量结论。状态详见 [TODO](TODO.md)，历史演进见 [CHANGELOG](CHANGELOG.md)。

## 核心功能与使用流程

**个人资料 → 简历 → 申请 → 研究/匹配 → 投递记录 → 面试 → 复盘**

这是一条导航线索，不是强制依赖链。公司研究、岗位匹配、简历优化和 Mock 都可按需使用；每个生成动作只校验自身必需的输入。生成材料与记录实际投递是两个不同操作。

- **个人资料与简历：** 命名资料、统一编辑会话、手动/AI 创建简历、来源校验、保存版本、显式短表达式及中文 PDF。
- **申请管理：** 原始 JD 输入与修订、六种跟进状态、备注、exact 简历绑定、公司研究、逐项岗位匹配及解释。
- **投递：** 简历优化、招呼语、冻结简历/PDF/招呼语引用的真实投递记录；保留历史和引用保护下的移除能力。
- **面试：** 基于可见简历材料的准备、可继续的文本模拟、真实面试原子新增/编辑及只读历史。Mock 可在服务端配额内跳过、延后或连续追问。
- **复盘：** 指定题组分析和/或整场综合复盘、精确依据、冻结问答、失败项重试、独立历史及可编辑求职笔记。
- **Internal：** 安全运行元数据、有限控制、恢复检查、离线重放、对比及显式执行的评测操作。

## 工程能力与架构

- **结构化输出与来源校验：** 正式采纳前检查 Schema、来源及引用，阻止无效输出。引用提供可追溯性，不等于证明语义真实。
- **请求身份与历史：** 持久化回执避免同请求重发造成重复操作；revision/CAS 和不可变快照分开管理当前编辑与历史输入。
- **有边界的执行与恢复：** 共用 Gateway 记录尝试、预算及结果；具备持久化有效输出的路径可安全恢复，unknown 不盲目重放。
- **评测：** 冻结输入、离线 provider 和生产校验链路区分执行正确性与质量证据；Judge 输出不等于人工真值。

```text
Next.js Product / Internal → 允许列表 BFF → FastAPI 业务服务
    → 模型 Gateway / 策略 / 预算 / 执行日志
    → PostgreSQL + 私有产物 → 结果 / 历史 / PDF / Eval
```

后端使用 Python >=3.12（仓库选择 3.12）、FastAPI、Pydantic、异步 SQLAlchemy/Alembic 和 PostgreSQL；前端使用 Next.js、React、严格 TypeScript 和 Tailwind CSS v4。PDF 使用固定版本 Typst 与 CJK 字体。依赖以 `pyproject.toml`、`uv.lock`、`frontend/package.json` 及其锁文件为准，详细边界见 [架构](docs/architecture.md)。前端不另建直接模型调用通道。

## Quick Start

需要 uv、Python 3.12、Node >=22.13/npm、Docker Compose（仓库服务使用 PostgreSQL 17.6）及 **Typst 0.15.1**。Typst 由用户预先安装，应用不会安装或升级它。使用本地/私有环境，迁移前先确认目标数据库；不要未经授权和迁移计划对已有业务库执行以下流程。

```sh
uv sync --locked
npm ci --prefix frontend
cp .env.example .env
cp frontend/.env.example frontend/.env.local
# Review database, private storage, compiler and server-only configuration before continuing.
uv run python scripts/setup_resume_fonts.py
./cgstart --check
./cgstart
```

字体安装脚本下载并校验 Noto Sans CJK SC 2.004 Regular/Bold 及许可证，保存到外部缓存。`cgstart --check` 是离线依赖检查；**`cgstart` 不是只读操作**：它会启动 PostgreSQL、对配置的数据库执行 Alembic 迁移、按需安装缺少的固定字体，并启动 FastAPI/Next 开发服务；不会下载 Typst。不要在已有开发服务上重复启动。Ctrl+C 停止其应用进程，保留 PostgreSQL 数据。

Product：`http://127.0.0.1:3000`；API 文档：`http://127.0.0.1:8000/docs`。
后端凭据仅放在根目录服务器环境；前端 `.env.local` 配置 `CAREER_AGENT_API_ORIGIN`，Internal 另使用服务器端 Ops token。BFF 不等于登录鉴权。

示例配置的 `CAREER_AGENT_LIVE_ENABLED=false`。Product 生成请求使用 live 模式，需要明确配置和授权；关闭 live 不会把页面变成 fixture 演示。浏览和普通 PDF 渲染不启动付费调用。配置、分开启动服务及详细环境说明见 [开发指南](docs/development.md)。

## 常用验证入口

从仓库根目录执行：

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
npm --prefix frontend run check
npm --prefix frontend run build
git diff --check
```

完整后端测试需要真实 PostgreSQL、Typst 和固定字体。harness 创建随机临时数据库，使用合成数据及离线 provider，不重置业务库。浏览器回归需要 Chromium 和前端 production build。不要让 dev/build 并发共用同一 `.next`。隔离环境、浏览器套件与打包说明见 [验证指南](docs/development.md#verification)。这些是操作说明，不代表文档整理时重新执行过检查。

## 当前限制与安全边界

- 单用户本地/私有部署，不提供多用户登录、公开 SaaS 权限或计费系统。BFF allowlist 和 Ops token 不能保护直接公开的后端。
- 未实现自动投递/发送、无限制自主规划、向量检索、语音面试或围绕复盘的多轮讨论，后续范围见 [TODO](TODO.md#next-function-stage-and-polish)。
- 私人来源、数据库备份、生成产物和 Eval capture 不进入公开材料。普通日志/Ops 使用安全元数据；基础脱敏不等于完整 DLP。
- 不承诺分布式 exactly-once、通用持久化 worker、供应商结果查询或数据库/文件系统全局原子性。恢复能力取决于具体任务及实际保存的证据。
- 软删除保留共享来源和审计，不等于物理擦除；迁移与数据清理需另行决定。代码中的迁移文件不代表业务库已升级。
- Grounding、合成回归和少量真实功能观察不能证明招聘结果、广泛模型质量、实际账单或生产负载能力。

## 深入文档导航

| 需要了解 | 文档 |
| --- | --- |
| 安装、配置、字体、迁移、测试和 Eval CLI | [开发指南](docs/development.md) |
| API 用法、请求示例和历史兼容 | [后端 API 指南](docs/backend-api.md)及本地 OpenAPI |
| 分层、执行、预算、恢复和版本治理 | [架构](docs/architecture.md) |
| Profile/Resume 编辑、渲染和生命周期 | [Profile workspace](docs/profile-workspace.md) |
| 前端路由、交互、BFF、字级及 Internal | [前端 README](frontend/README.md) |
| 模型任务诊断、恢复证据与质量边界 | [执行可靠性](docs/model-reliability.md) |
| 当前验收、后续范围及历史变化 | [TODO](TODO.md)、[CHANGELOG](CHANGELOG.md) |
