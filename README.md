# Metal Max Wiki

重装机兵资料百科与 AI 问答项目。

项目采用前后端分离架构：用户端使用 Next.js，管理端使用 Vite + React，后端使用 FastAPI，数据库使用 PostgreSQL，并为后续的向量检索和在线模型接入预留扩展能力。

## 环境要求

- Node.js 22.18.0
- npm 与 pnpm 12.4.2
- uv
- Python 3.14.6（由 uv 自动安装和管理）
- Docker Desktop 或兼容的 Docker Engine

## 安装

```bash
npm install --global pnpm@12.4.2
pnpm install
cd apps/backend/server && uv sync
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

- Client：<http://localhost:3000>
- Admin：<http://localhost:5173>
- API：<http://localhost:8000>
- API 文档：<http://localhost:8000/docs>

也可以分别执行：

```bash
pnpm dev:client
pnpm dev:admin
pnpm dev:api
```

## 质量检查

```bash
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

## 项目结构

```text
metalmax-wiki/
├── apps/
│   ├── frontend/
│   │   ├── client/                 # 用户端：Next.js + shadcn/ui
│   │   │   ├── public/             # 图片、字体等静态资源
│   │   │   └── src/
│   │   │       ├── app/            # App Router页面、布局及就近业务组件
│   │   │       ├── api/            # 按业务划分的API文件
│   │   │       ├── components/ui/  # shadcn/ui基础组件
│   │   │       ├── hooks/          # 通用Hooks
│   │   │       ├── lib/            # 请求、鉴权和工具函数
│   │   │       ├── stores/         # 客户端全局状态
│   │   │       └── types/          # 当前应用的类型补充
│   │   │
│   │   └── admin/                  # 管理端：Vite + React + Ant Design
│   │       ├── public/
│   │       ├── src/
│   │       │   ├── api/            # 按业务划分的API文件
│   │       │   ├── assets/         # 图片和全局样式
│   │       │   ├── components/     # 跨页面通用组件
│   │       │   ├── hooks/          # 通用Hooks
│   │       │   ├── layouts/        # 管理后台整体布局
│   │       │   ├── lib/            # 请求、鉴权和工具函数
│   │       │   ├── pages/          # 管理页面
│   │       │   ├── router/         # React Router配置
│   │       │   ├── stores/         # 客户端全局状态
│   │       │   ├── types/          # 当前应用的类型补充
│   │       │   ├── App.tsx
│   │       │   └── main.tsx
│   │       ├── index.html
│   │       └── vite.config.ts
│   │
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
├── packages/                   # 两个前端应用共享的非 UI 代码
│   ├── api-client/             # 根据 FastAPI OpenAPI 生成的请求代码
│   ├── domain/                 # 游戏版本、装备类型、稀有度等领域定义
│   └── config/                 # TypeScript、ESLint 等共享配置
│
├── data/
│   ├── raw/                    # 原始攻略、截图、表格等资料
│   └── processed/              # 清洗和结构化后的数据
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

| 模块                   | 技术                                                              | 主要职责                              |
| ---------------------- | ----------------------------------------------------------------- | ------------------------------------- |
| `apps/frontend/client` | Next.js、TypeScript、shadcn/ui                                    | 百科浏览、搜索、用户登录和 AI 问答    |
| `apps/frontend/admin`  | Vite、React、TypeScript、Ant Design、React Router、TanStack Query | 表格管理、资料录入、审核和知识库维护  |
| `apps/backend/server`  | FastAPI、Pydantic、SQLAlchemy、Alembic                            | API、鉴权、业务逻辑和数据访问         |
| 数据库                 | PostgreSQL、pgvector                                              | 结构化数据、全文检索和向量数据        |
| 本地 AI                | Ollama                                                            | 本地开发阶段的问答和知识库验证        |
| `infra`                | Docker Compose、Caddy                                             | 容器运行、HTTPS、反向代理、部署与备份 |

## 计划域名

- `mm.yangyunqiao.top`：用户端
- `admin.mm.yangyunqiao.top`：管理端
- 两个站点通过各自的 `/api` 路径反向代理到 FastAPI，减少跨域和鉴权复杂度。
