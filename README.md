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

首次开发先初始化本地配置：

```bash
pnpm dev:setup
```

该命令从 Ollama 的已安装模型中选择问答模型，创建缺失的前后端及数据库配置，并生成本地数据库密码。已有配置保持原样，配置内容不会打印到终端。

若后端配置已存在、数据库配置却缺失，命令会在写入前停止；请先按原 `DATABASE_URL` 补齐数据库配置，避免使用不同的凭据。

如果默认 8000 端口被其他项目占用，可在首次初始化时指定端口：

```bash
pnpm dev:setup --port 8001
```

也可以通过 `--model 模型名` 明确指定模型。后端使用 `API_PORT`，用户端使用 `API_BASE_URL`；两者由初始化命令同步设置。已有配置需要手动调整，重新运行不会覆盖。

启动 Docker 后运行：

```bash
docker compose --env-file infra/env/.env -f infra/compose.yaml up -d --wait db
```

Compose 项目名固定为 `metalmax-wiki`，使用独立的 `metalmax-wiki_postgres_data` 数据卷，数据库端口仅监听本机。旧的 `infra_*` 数据卷不会被删除或自动迁移。

停止数据库但保留数据卷：

```bash
docker compose --env-file infra/env/.env -f infra/compose.yaml down
```

## 本地 MVP 配置

`pnpm dev:setup` 已自动创建缺失的配置。若手动配置，可参考各应用的 `.env.example`；使用下面的命令查看本机模型：

```bash
ollama list
```

在后端 `.env` 中将 `AI_MODEL` 改为 `ollama list` 显示的完整名称，并确认 `DATABASE_URL` 与本地 PostgreSQL 配置一致。Ollama 默认通过 `http://127.0.0.1:11434/v1` 调用；`AI_BASE_URL`、`AI_MODEL` 和 `AI_API_KEY` 可用于接入其他兼容模型服务。

数据库启动后，在后端目录执行迁移，再启动前后端：

```bash
cd apps/backend/server
uv run alembic upgrade head
cd ../../..
pnpm dev:check
pnpm dev:all
```

`dev:check` 只读检查配置、前端代理地址、装备资料、数据库连接与迁移版本、模型是否存在；不会执行迁移、下载模型或发起推理。任一检查失败时会返回非零状态并给出处理方式。修改环境变量后，需要重启已经运行的前后端。

当前开放 2R 0.99 的 407 条装备参考资料：人类武器 55 条、主炮 95 条、S-E 89 条、C 装置 48 条、引擎型号 120 条。人类武器与主炮为汉化兼容候选；S-E、C 装置和引擎为日版参考，中文名采用单独标注的参考译名，尚未逐项核对 0.99 实机。游客可浏览、筛选和搜索；邮箱注册后自动登录，AI 问答需要登录，回答附带装备详情引用。首版采用单轮检索问答，未收录的信息不作为已知事实回答；没有账号邮件验证、找回密码和历史会话功能。

资料使用可追溯 JSON，账号与可撤销会话使用 PostgreSQL。密码通过 Argon2 哈希保存，登录令牌仅保存在 HttpOnly Cookie，数据库保存令牌摘要。生产环境需设置 `ENVIRONMENT=production`、HTTPS 的 `CLIENT_ORIGIN` 并使用 HTTPS；登录与问答限流当前适用于单进程部署。

前端默认连接 `http://127.0.0.1:8000`，可通过前端环境变量 `API_BASE_URL` 修改。浏览器只访问同源 `/api`，不直接访问 Ollama 或持有模型密钥。

主要业务接口均位于 `/api/v1`：

- `GET /game-versions`：游戏版本。
- `GET /versions/{version}/equipment`：装备筛选、排序与分页。
- `GET /versions/{version}/equipment/{id}`：装备详情与来源。
- `GET /versions/{version}/search?q=...`：真实装备搜索。
- `POST /auth/register`、`POST /auth/login`、`GET /auth/me`、`POST /auth/logout`：账号与会话。
- `POST /versions/{version}/ask`：登录后的带引用问答。

列表、搜索与账号请求由 FastAPI 处理；装备详情保留静态生成，使用与接口相同的数据文件。修改资料后重新构建前端并重启后端，使静态详情与接口同步。

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

后端端口以本机 `.env` 的 `API_PORT` 为准；例如初始化时使用 `--port 8001`，接口文档位于 `http://localhost:8001/docs`。

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

数据管线从 17 份候选快照与 S-E、C 装置、引擎事实快照生成 761 条记录：装备 407 条、道具 274 条、任务 8 条、职业 7 条、技能 65 条。输出保留 1235 个来源引用、37 个跨列原始范围、256 组 S-E 星级改造数值、114 组 C 装置星级改造数值和 346 组引擎星级数值。总表与独立详情的同星级数值差异单独标记，原始值均保留。

初次运行先同步数据工具依赖：

```bash
cd tools/data-pipeline && uv sync --locked && cd ../..
```

完整的可重建顺序如下：

```bash
pnpm data:collect
pnpm data:collect:se
pnpm data:collect:c-units
pnpm data:collect:engines
pnpm data:normalize
pnpm data:audit
pnpm assets:fetch
pnpm assets:audit
```

`data:collect` 会访问清单中的公开资料页；`data:collect:se`、`data:collect:c-units`、`data:collect:engines` 分别采集 S-E、C 装置、引擎总表与独立详情中的数值、星级、特性和获取地点事实，引擎同时保留马力强化型号与费用；`data:normalize` 根据显式映射重建 `interim` 数据；`data:audit` 离线执行候选快照、部件事实与图片资产审计，`assets:audit` 可单独执行后者。网络采集不会被 `test`、`lint`、`build` 或默认启动命令触发。

S-E 的普通改造数值按星级分别保存，不包含超改造。来源未给出的值不推算；固定星级装备的其他星级仅作图鉴参考。LOVE 机器在总表中的配方合并行尚不足以建立可靠独立条目，本次未收入 S-E。

C 装置的主动指令与被动特性分别标注，保留耗弹变化、适用孔位和效果疑点。命中与回避只显示来源面板值，不能当作实际概率；通信转送品注明 MM3 条件，RENTA 系统注明无法获得。LOVE 机器的 C 装置配方行尚未独立收录。

引擎将型号升级与星级数值分开，支持基础载重排序、特性筛选和强化路径跳转。载重不含特性加成及自重扣除；同名加成与辅助加成以一号引擎为基数，租赁装备专属星级单独标明。加成计算补充参考 METAL MAX 大辞典的资料快照，原词典链接当前不能直接访问。LOVE 机器的引擎配方尚未独立收录。

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

AI 问答只使用当前已收录的装备资料。检索、模型 Provider 与业务接口分开组织，后续可以替换检索策略或模型服务。

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
