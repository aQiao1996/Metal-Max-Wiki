# Metal Max Wiki

重装机兵资料百科与 AI 问答项目。

项目采用前后端分离架构：站点使用 Next.js，后端使用 FastAPI，数据库使用 PostgreSQL。固定游戏资料通过结构化数据文件和导入流程维护，不单独建设管理端，并为后续的向量检索和在线模型接入预留扩展能力。

## 环境要求

- Node.js 22.18.0
- npm 与 pnpm 12.4.2
- uv
- Python 3.14.6（由 uv 自动安装和管理）
- Docker Desktop 或兼容的 Docker Engine

## 安装

```bash
npm install --global pnpm@12.4.2
pnpm install --frozen-lockfile
(cd apps/backend/server && uv sync --locked)
(cd tools/data-pipeline && uv sync --locked)
```

## 本地数据库

```bash
cp infra/env/.env.example infra/env/.env
docker compose --env-file infra/env/.env -f infra/compose.yaml up -d --wait db
```

停止数据库但保留数据卷：

```bash
docker compose --env-file infra/env/.env -f infra/compose.yaml down
```

## 启动

```bash
pnpm dev
```

该命令会打开交互式菜单，可选择启动用户端、后端或全部应用。直接启动全部应用：

```bash
pnpm dev:all
```

- Client：<http://localhost:3000>
- API：<http://localhost:8000>
- API 文档：<http://localhost:8000/docs>

也可以分别执行：

```bash
pnpm dev:client
pnpm dev:server
```

## 质量检查

```bash
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

## MM2R 0.99 资料数据管线

数据管线已将 17 份候选快照标准化为 504 条记录：装备 150 条、道具 274 条、任务 8 条、职业 7 条、技能 65 条。输出保留 527 个来源引用和 37 个跨列原始范围，当前字段冲突为 0。

初次运行先同步数据工具依赖：

```bash
cd tools/data-pipeline && uv sync --locked && cd ../..
```

完整的可重建顺序如下：

```bash
pnpm data:collect
pnpm data:normalize
pnpm data:audit
pnpm assets:fetch
pnpm assets:audit
```

`data:collect` 会访问清单中的公开资料页；`data:normalize` 根据显式映射重建 `interim` 数据；`data:audit` 离线执行候选快照与图片资产审计，`assets:audit` 可单独执行后者。`assets:fetch` 是显式的网络操作，只获取权利清单允许的资产，不会被 `test`、`lint`、`build` 或默认启动命令触发。

数据分层的语义是：

- `data/raw/`：保留候选快照、原始字段、来源与权利结论，不被标准化流程覆盖。
- `data/interim/`：网站准备使用的统一候选记录，但不是 0.99 实机准确性证明。
- `data/processed/`：只接收经本机 0.99 游戏界面、截图、存档观察或可重复提取核验的 `verified_0_99` 数据。

### 图片权利与获取边界

| 权利状态                               | 处理方式                                                       |
| -------------------------------------- | -------------------------------------------------------------- |
| `reusable`                             | 仅在具有明确开放许可或作者授权时下载，保留作者、许可和原始来源 |
| `user_capture`                         | 后续保存用户自有 0.99 版本的必要截图，记录地点、条件和日期     |
| `original_diagram`                     | 后续根据已核对的事实制作原创 SVG，不复制他人图片的像素与排版   |
| `permission_needed` / `reference_only` | 只保留来源索引，不复制未授权文件                               |
| `rejected`                             | 不使用官方攻略书扫描、版本错误或来源不明的图片                 |

当前清单记录 3 个外部候选，均为仅索引或已拒绝，因此本地下载数为 0；这不代表攻略图片已齐全。后续的用户自有截图将放入 `assets/files/user-captures/`，原创 SVG 将放入 `assets/files/original-diagrams/`。

远程图片仅允许 HTTPS 与清单允许的重定向主机；每次请求都检查公网 DNS，并限制重定向次数、文件大小、MIME、实际图片格式、尺寸、帧数和哈希。远程下载只接受 PNG、JPEG 和 WebP，全部合格后才更新 `lock.json`。

AI 问答与 Agent 由用户后续单独实现；本轮数据和图片管线未接入、未修改相关代码。

## 项目结构

```text
metalmax-wiki/
├── apps/
│   ├── frontend/
│   │   └── client/                 # 用户端：Next.js + shadcn/ui
│   │       ├── public/             # 图片、字体等静态资源
│   │       └── src/
│   │           ├── app/            # App Router页面、布局及就近业务组件
│   │           ├── api/            # 按业务划分的API文件
│   │           ├── components/ui/  # shadcn/ui基础组件
│   │           ├── hooks/          # 通用Hooks
│   │           ├── lib/            # 请求、鉴权和工具函数
│   │           ├── stores/         # 客户端全局状态
│   │           └── types/          # 当前应用的类型补充
│   └── backend/
│       └── server/                  # FastAPI 主服务
│           ├── app/
│           │   ├── api/             # API 路由
│           │   ├── models/          # SQLAlchemy 数据模型
│           │   ├── schemas/         # Pydantic 请求与响应模型
│           │   ├── services/        # 业务逻辑
│           │   ├── repositories/    # 数据访问逻辑
│           │   ├── auth/            # 登录、会话和权限
│           │   ├── ai/              # RAG、模型和向量检索
│           │   └── core/            # 配置、数据库连接等基础模块
│           ├── migrations/          # Alembic 数据库迁移
│           └── tests/               # 后端测试
│
├── packages/                   # 生成的 API 客户端、领域定义和工程配置
│   ├── api-client/             # 根据 FastAPI OpenAPI 生成的请求代码
│   ├── domain/                 # 游戏版本、装备类型、稀有度等领域定义
│   └── config/                 # TypeScript、ESLint 等共享配置
│
├── data/
│   ├── raw/                    # 来源快照、人工权利清单与允许保存的原始资产
│   ├── interim/                # 可追溯、尚未经 0.99 实机核验的统一候选数据
│   └── processed/              # 仅保存已核验的 0.99 数据
│
├── tools/
│   └── data-pipeline/          # 资料采集、标准化、权利校验与资产审计工具
│
├── infra/                      # 部署及服务器基础设施配置
│   ├── compose.yaml            # 本地及服务器容器编排
│   ├── caddy/
│   │   └── Caddyfile           # HTTPS、域名和反向代理配置
│   ├── postgres/
│   │   └── init.sql            # PostgreSQL、pgvector 初始化
│   ├── scripts/
│   │   ├── deploy.sh           # 部署脚本
│   │   └── backup.sh           # 数据库备份脚本
│   └── env/
│       └── .env.example        # 环境变量示例，不保存真实密码
│
├── docs/                       # 需求、架构、数据库和接口文档
├── pnpm-workspace.yaml         # 前端 Monorepo 工作区配置
└── README.md
```

## 技术划分

| 模块                   | 技术                                   | 主要职责                              |
| ---------------------- | -------------------------------------- | ------------------------------------- |
| `apps/frontend/client` | Next.js、TypeScript、shadcn/ui         | 百科浏览、搜索、用户登录和 AI 问答    |
| `apps/backend/server`  | FastAPI、Pydantic、SQLAlchemy、Alembic | API、鉴权、业务逻辑和数据访问         |
| 数据库                 | PostgreSQL、pgvector                   | 结构化数据、全文检索和向量数据        |
| 本地 AI                | Ollama                                 | 本地开发阶段的问答和知识库验证        |
| `infra`                | Docker Compose、Caddy                  | 容器运行、HTTPS、反向代理、部署与备份 |

## 计划域名

- `mm.yangyunqiao.top`：用户端
- 站点通过同源 `/api` 路径反向代理到 FastAPI，减少跨域和鉴权复杂度。
