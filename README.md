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

在后端 `.env` 中将 `AI_MODEL` 改为 `ollama list` 显示的完整名称，并确认 `DATABASE_URL` 与本地 PostgreSQL 配置一致。本机问答使用 `qwen3:4b-instruct-2507-q4_K_M`；其他已安装模型保留，项目不会自动下载或切换模型。

Ollama 可配置 `AI_PROVIDER=ollama`、`AI_BASE_URL=http://127.0.0.1:11434/v1`，每次请求显式传入 `AI_OLLAMA_CONTEXT_TOKENS=16384`。上下文字符预算 `AI_MAX_CONTEXT_CHARS=4000` 包含问题、规则和完整证据，输出上限由 `AI_MAX_OUTPUT_TOKENS=4096` 控制；字符数不等于模型 token 数。接入兼容在线服务时使用 `AI_PROVIDER=openai-compatible`，再设置 `AI_BASE_URL`、`AI_MODEL` 和 `AI_API_KEY`，无需修改业务代码。

数据库启动后，在后端目录执行迁移，再启动前后端：

```bash
cd apps/backend/server
uv run alembic upgrade head
cd ../../..
pnpm dev:check
pnpm dev:all
```

`dev:check` 只读检查配置、前端代理地址、装备资料、数据库连接与迁移版本、模型是否存在；不会执行迁移、下载模型或发起推理。任一检查失败时会返回非零状态并给出处理方式。修改环境变量后，需要重启已经运行的前后端。

当前开放 2R 0.99 的 457 条装备参考资料：人类武器 55 条、主炮 95 条、副炮 50 条、S-E 89 条、C 装置 48 条、引擎型号 120 条。人类武器与主炮为汉化兼容候选；副炮、S-E、C 装置和引擎为日版参考，中文名采用单独标注的参考译名，尚未逐项核对 0.99 实机。游客可浏览、筛选和搜索；邮箱注册后自动登录，AI 问答需要登录，回答附带实际引用的条目及章节链接。首版采用单轮检索问答，未收录的信息不作为已知事实回答；没有账号邮件验证、找回密码和历史会话功能。

赏金首收录 30 次悬赏、31 名敌人及 93 个分别记录的掉落槽，提供位置、触发条件、各槽物品概率和 89 种掉落物的作用与属性表。皮奇兄弟分别列出两人的掉落，同名重复槽不合并；来源楼层、物品类别与作用的差异明确保留。各槽记录不代表统计独立，不能据此推算联合概率。

战车收录 16 种车型、355 个配置、19 个租赁购买选项和 20 项底盘特性。支持按车型、型号、特性及双引擎／双 C 条件查找；配置按来源阶段展示，巴特设计预设单独标注，不推测升级连线。底盘特性数值保留孔位、生效方式和证据适用对象，双部件改造的互斥、开放阶段与不可逆条件明确列出。全站搜索同时覆盖车辆。

职业收录 7 类职业、65 项技能、28 组成长观测与主副职业规则。技能按学习等级、Lv99 次数、对象、作用和使用条件分别展示，保留 28 处来源差异；同一技能的不同来源原值可展开核对。技能名称与作用纳入职业列表及全站搜索，不推算来源未提供的成长公式。

道具收录 274 条记录，包括 81 组 LOVE 配方与 12 处芯片位置；用途、地点、消耗性和不同来源条件分别保留。任务收录 101 项，其中 25 项特别委托、21 项有明确失败或错过条件；其余条目明确标注来源未说明，不能据此认定不会失败。两类均支持类型筛选、中文用途检索、分页和返回列表。

主线攻略分 6 个阶段、23 章，包含 100 个操作步骤、208 条带出处的事实，以及 3 张项目原创流程示意图。支持按阶段、地点、道具和机关查找，区分主线必需、准备、可选与剧情必败；原值和短证据可展开核对。流程图可在手机内阅读并打开大图，不冒充实机地图或截图。

资料使用可追溯 JSON，账号与可撤销会话使用 PostgreSQL。密码通过 Argon2 哈希保存，登录令牌仅保存在 HttpOnly Cookie，数据库保存令牌摘要。生产环境需设置 `ENVIRONMENT=production`、HTTPS 的 `CLIENT_ORIGIN` 并使用 HTTPS；登录与问答限流当前适用于单进程部署。

前端默认连接 `http://127.0.0.1:8000`，可通过前端环境变量 `API_BASE_URL` 修改。浏览器只访问同源 `/api`，不直接访问 Ollama 或持有模型密钥。

主要业务接口均位于 `/api/v1`：

- `GET /game-versions`：游戏版本。
- `GET /versions/{version}/equipment`：装备筛选、排序与分页。
- `GET /versions/{version}/equipment/{id}`：装备详情与来源。
- `GET /versions/{version}/wiki/wanted-monsters`：赏金首搜索、赏金排序与分页摘要。
- `GET /versions/{version}/wiki/wanted-monsters/{id}`：赏金首位置、出现条件、独立掉落槽与物品属性。
- `GET /versions/{version}/wiki/vehicles`：车型搜索与 `mount=double-engine|double-c-unit|all` 筛选。
- `GET /versions/{version}/wiki/vehicles/{id}`：底盘配置、获取方式、特性、改造限制与来源。
- `GET /versions/{version}/wiki/jobs`、`/wiki/jobs/{id}`：职业检索、成长观测、技能与来源差异。
- `GET /versions/{version}/wiki/items`、`/wiki/items/{id}`：道具类型、用途、LOVE 配方及芯片位置。
- `GET /versions/{version}/wiki/quests`、`/wiki/quests/{id}`：任务类型、步骤、奖励与错过条件。两类列表支持 `tag` 筛选。
- `GET /versions/{version}/search?q=...`：装备、战车、赏金首、职业、道具、任务与攻略搜索，返回统一摘要及详情链接。
- `GET /versions/{version}/guides`、`/guides/{slug}`：按 `q`、`phase` 筛选攻略及读取章节正文。
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

## 生产部署

生产编排独立于本地数据库，包含 PostgreSQL、FastAPI、Next.js 和 Caddy。仅 Caddy 发布 80／443 端口，API 与数据库通过容器网络连接；生产数据卷使用 `metalmax-wiki-production_*` 前缀，不复用本地数据卷。

在目标 Linux 主机的项目根目录准备配置：

```bash
cp infra/production/.env.example infra/production/.env
chmod 600 infra/production/.env
```

填写域名、证书邮箱、数据库用户名与库名、数据库密码及模型配置。数据库密码使用 `openssl rand -hex 32` 生成，避免数据库 URL 中的保留字符；真实配置不提交到 Git。域名须解析到目标主机，80／443 端口须可访问。

`AI_BASE_URL` 必须是 API 容器可访问的地址，容器内的 `127.0.0.1` 不代表开发用 Mac。4GB 云服务器只运行网站和数据库，本机 Ollama 通过私有网络或另行配置的 SSH 反向隧道接入；不要公开 11434 端口。也可填写在线兼容接口。编排不会部署模型、创建隧道或修改 DNS。

配置完成后，使用同一份配置构建和启动：

```bash
compose_prod() {
  docker compose --env-file infra/production/.env -f infra/compose.production.yaml "$@"
}

compose_prod config --quiet
compose_prod build server
compose_prod build client
compose_prod up -d --wait db
compose_prod run --rm server alembic upgrade head
compose_prod up -d --wait
```

业务迁移由显式命令执行，不随 API 启动自动运行。后端使用单 worker，与当前进程内限流一致；资料目录只读挂载，前后端以非 root 用户运行，镜像不包含真实 `.env`、本地代理规则或原始采集资料。

数据库备份使用 Linux 脚本：

```bash
bash infra/scripts/backup-postgres.sh infra/production/.env /srv/backups/metalmax-wiki
```

备份目录须由执行用户拥有，权限为 `700`。脚本以 `600` 权限写入带 UTC 时间的 PostgreSQL 自定义格式备份；失败时保留 `.partial` 文件，不覆盖旧备份，也不自动清理或恢复数据。需要定期将备份保存到独立存储。

本次镜像构建和容器联测在本机 Linux/arm64 环境完成，尚未部署到远端。目标主机的 CPU 架构、4GB 内存下的构建与负载、域名证书及私有模型连通性仍需上线前核对。

## 质量检查

```bash
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

## MM2R 0.99 资料数据管线

数据管线从 17 份候选快照与战车底盘及部件、赏金首和掉落物事实快照生成 973 条记录：装备 457 条、道具 274 条、任务 101 条、职业 7 条、技能 65 条、赏金首 30 条、战车 16 条、攻略 23 章。输出保留 4686 个来源引用、37 个跨列原始范围、137 组副炮星级改造数值、256 组 S-E 星级改造数值、114 组 C 装置星级改造数值和 346 组引擎星级数值。总表与独立详情的同星级数值差异单独标记，原始值均保留。

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
pnpm data:collect:sub-guns
pnpm data:collect:wanted
pnpm data:collect:wanted-items
pnpm data:collect:vehicles
pnpm data:collect:vehicle-traits
pnpm data:collect:job-skills
pnpm data:collect:items
pnpm data:collect:quests
pnpm data:collect:guides
pnpm data:normalize
pnpm assets:fetch
pnpm assets:publish:guides
pnpm data:audit
pnpm assets:audit
```

`data:collect` 会访问清单中的公开资料页；`data:collect:se`、`data:collect:c-units`、`data:collect:engines`、`data:collect:sub-guns` 分别采集 S-E、C 装置、引擎、副炮总表与独立详情中的数值、星级、特性和获取地点事实，引擎同时保留马力强化型号与费用；`data:normalize` 根据显式映射重建 `interim` 数据；`data:audit` 离线执行候选快照、部件事实与图片资产审计，`assets:audit` 可单独执行后者。网络采集不会被 `test`、`lint`、`build` 或默认启动命令触发。

S-E 的普通改造数值按星级分别保存，不包含超改造。来源未给出的值不推算；固定星级装备的其他星级仅作图鉴参考。LOVE 机器在总表中的配方合并行尚不足以建立可靠独立条目，本次未收入 S-E。

副炮保留有限与无限弹仓的区别，迎击兵装化标记表示适用性，不等于装备后自动迎击。转送品和固定星级单独注明；副炮与 S-E 共用星级表采集和展示规则。

`data:collect:wanted` 采集悬赏总表、出现条件和カエル研究室的逐槽掉落率；`data:collect:wanted-items` 随后采集全部 89 种掉落物的事实表。依赖哈希按已校验快照的规范 JSON 计算，排版变化不会误报，事实变化需要重新采集。掉落率来源未说明统计或解析方法，不推算联合概率、难度加成或星级概率；不同星级与不同来源的数值分开显示。

`data:collect:vehicles` 采集底盘配置、初始装备、单孔改造、获取条件及租赁购买事实；`data:collect:vehicle-traits` 随后采集同作特性与双部件改造证据，依赖车辆规范内容哈希。来源空重量不补零；猎豹 GSE 的两个阶段不按同名去重；C 装置验证值不冒充底盘固定参数。

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

AI 问答检索装备、赏金首、战车、职业、道具、任务和攻略，保留星级、孔位、职业、触发条件及来源差异。缺少输入、完整证据超出预算或没有相关资料时，返回 `insufficient_evidence`；模型超时、输出截断、引用无效，以及检测到的资料外数字或来源冲突误述会明确报错。数字校验不等于完整语义证明，仍需通过引用核对。

输入名称、星级与槽位完整，且资料包含对应公式时，引擎载重由业务代码计算并引用输入来源；不让模型补齐缺失条件或计算未知净载重。检索、计算、模型 Provider 与问答业务分开组织，后续可替换检索策略或模型服务。

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
│   ├── compose.yaml            # 本地 PostgreSQL
│   ├── compose.production.yaml # 生产数据库、API、用户端与 HTTPS
│   ├── production/
│   │   ├── client.Dockerfile   # Next.js standalone 镜像
│   │   ├── server.Dockerfile   # FastAPI 镜像
│   │   ├── Caddyfile           # HTTPS 与反向代理
│   │   └── .env.example        # 生产配置占位符
│   ├── postgres/
│   │   └── init.sql            # PostgreSQL、pgvector 初始化
│   ├── scripts/
│   │   └── backup-postgres.sh  # Linux 数据库备份
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

`assets:publish:guides` 离线核对攻略事实、原创资产清单、锁文件和 SHA-256 后，将三张 SVG 发布至用户端 public。原图或清单变化时先同步原创资产与锁文件；路径、权限、哈希或许可声明不符会拒绝发布，不自动删除旧图。`guide-routes.json` 为章节提供独立轻量索引，未知地址和未开放版本返回 HTTP 404。
