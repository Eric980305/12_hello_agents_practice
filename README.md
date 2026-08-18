# 智能专家平台

这是一个基于本地 HelloAgents 实践框架构建的多用户智能专家平台。当前主项目位于
`expert_platform/`：Vue 3 + TypeScript 提供浏览器界面，FastAPI 提供认证、专家、文档、问答、报告和管理后台 API，并复用本项目的 `hello_agents_framework` 与 `PDFLearningAssistant` 业务能力。

当前版本：`0.3.0`
项目定位：学习与定制实现，不是生产级身份系统或企业智能专家管理平台。

历史 Gradio 入口 `python -m apps.pdf_learning_assistant` 继续保留，但不再是默认产品入口。

## 主要功能

### 账号、登录与会话

![登录页面](./expert_platform/images/截屏2026-08-18%2011.13.13.png)

- 支持本地注册、登录、退出登录和浏览器刷新后的会话恢复。
- 用户名长度为 2–64 个字符，密码长度为 6–256 个字符。
- 密码使用带随机盐的 PBKDF2-HMAC-SHA256 派生值保存，不保存明文密码。
- 浏览器端只保存不透明的会话 token；账号和服务端会话仍由 SQLite 与进程内会话表负责。
- 登录后默认进入“智能问答”；刷新页面可以恢复当前模块，退出登录会清除当前会话。
- 界面支持简体中文和英文切换，语言选择保存在浏览器本地，不依赖登录状态。

### 智能专家平台权限模型

应用把对于专家的选择作为每次读写和检索的权限边界。SQLite 中的专家管理目录是权限与发现的权威来源，RAG namespace 负责隔离文档和向量检索结果。

| 范围 | 可见对象 | 当前版本允许的操作 |
| --- | --- | --- |
| `共享专家库` | 所有已登录用户 | 读取、上传文档、删除文档、问答和学习回顾 |
| 用户的专属专家 | 仅专属专家的所有者 | 创建、读取、上传、删除文档、问答、学习回顾和删除整个专家库 |
| `所有专家` | 当前用户可访问的通用专家库和专属专家库 | 只读聚合视图，用于汇总浏览文档；不能直接上传，问答必须选择一个具体专家库 |

重要边界：

- 每个用户默认都能看到一个系统拥有的 `共享专家库`。
- 个人专属专家库按用户隔离，其他用户不会在目录、文档列表或检索结果中看到它。
- 共享专家库本身不能删除；个人专属专家库删除前必须确认。
- 当前只有普通用户和管理员两级角色，没有协作者、细粒度共享、SSO 或账号找回机制。
- 共享专家库的内容写入权限目前对所有已登录用户开放，这是学习版本的明确取舍。

### 专家库管理

![专家库管理](./expert_platform/images/截屏2026-08-18%2011.09.56.png)

在“专家团”模块中可以：

- 创建个人专属专家库；名称按不区分大小写的方式检查重复。
- 查看共享专家库和当前用户拥有的个人专属专家库。
- 在专家库管理器中按库查看文档。
- 删除个人专家库。删除会级联清理其中的源文件、SQLite 文档与分块记录，以及 Qdrant 检索向量；共享专家库不可删除。
- 删除后，如果当前问答或管理页面仍选中了被删除的专家库，界面会回退到共享专家库或所有专家库视图。

### 文档管理与索引

- 上传时必须先选择一个具体专家库，不能把文件上传到“所有专家库”。
- 支持 PDF、Markdown、纯文本、CSV、JSON、XML、DOCX、PPTX、XLS/XLSX、HTML 和常见图片格式。
- 单个文件必须非空且不超过 50 MB。
- 上传后立即完成文件保留、解析、分块、Embedding 和 Qdrant 索引，成功返回即表示文档已经可以被检索。
- 使用源文件 SHA-256 做内容级幂等判断；重复上传不会重复复制文件、调用 Embedding 或写入索引。
- 支持按文件名搜索文档，并显示文件名、类型、所属专家库、添加时间和删除操作。
- 专家文档按搜索与专家范围过滤后分页展示，每页 10 条。
- 删除文档需要二次确认，并清理源文件、SQLite 权威记录、分块记录和对应的向量索引。

### 管理后台

- 管理后台与用户站点共用同一 FastAPI 服务和端口，入口为 `/admin`；只有 SQLite 中拥有管理员角色的账号可以访问。
- 用户、专家和文档列表支持搜索、关联过滤和分页，并按其可归属的原始文档磁盘占用降序展示。
- 删除用户、专家或文档前先展示 SQLite、Qdrant 和文件系统影响范围，再要求输入准确目标 ID 确认。
- 管理员账号、共享专家库和管理员本人受删除保护；成功删除会写入不含正文、凭据和向量内容的审计事件。
- 创建、授权、撤销和列出管理员使用 `python -m expert_platform.cli.manage_admin`；注册用户名为 `admin` 不会自动获得权限。

### 基于来源的智能问答

问答流程固定在当前选中的具体专家库内：

1. 从当前 namespace 检索最多 5 个达到最低相似度的候选分块。
2. 将候选分块重新解析到 SQLite 权威记录，避免直接信任孤立向量。
3. 把来源内容交给 OpenAI-compatible Chat Completions 接口生成答案。
4. 在回答末尾附上 `[S1]`、`[S2]` 等来源标签、文档名、分块编号和相似度。

基础检索默认开启；“高级检索”可选启用 MQE 和 HyDE。没有检索到足够相关的原文时，应用会明确返回暂时无法回答，不使用未引用的模型记忆补答案。文档中的指令被当作资料内容，不会获得改变系统任务或权限的能力。

如果问题包含“之前”“学过”“回顾”“历史”或“记得”等回顾意图，应用会优先检索当前专家库范围内的学习记忆，而不是直接走文档问答路径。

### 回顾与个人月度报告
- 每次完成的真实问答都作为当前用户的 `qa_interaction` episodic memory 持久化，记录问题、最终回答、专家和来源标识，因此退出登录或后端重启后仍可回顾。
- “月度总结”读取当前用户最近 30 天的完整问答，按专家分组，并将每位专家最近 30 次重点问答交给对话模型总结。
- 旧版只保存问题的 `qa_interaction` 记录不会参与总结，因为缺少回答；已有 `learning_reports/` 文件不迁移也不删除。
- 每个用户每个生成月份保存一份 JSON 到 `monthly_personal_reports/<user_scope>/`；同月重新生成会原子覆盖当月快照。

## 运行前提

- Python 3.12
- 项目工作区的 `.venv`
- Docker 或 OrbStack
- 一个 OpenAI-compatible 对话模型服务
- 一个 OpenAI-compatible Embedding 服务
- 本地 Qdrant；前后端分离版本不会隐式启动或停止容器

本项目当前沿用工作区布局：虚拟环境和 `.env` 位于仓库上层工作区根目录，依赖定义位于工作区根目录的 `pyproject.toml` 和 `requirements.txt`。

## 配置

从工作区根目录创建配置文件：

```bash
cd /Users/eric/Documents/Codex/Hello-agent-v0.0.1
cp .env.example .env
```

至少配置以下变量：

```bash
LLM_API_KEY="your-chat-api-key"
LLM_BASE_URL="https://your-provider.example/v1"
LLM_MODEL_ID="your-chat-model"

# EMBED_API_KEY 也可以使用 DASHSCOPE_API_KEY 提供
EMBED_API_KEY="your-embedding-api-key"
EMBED_BASE_URL="https://your-provider.example/compatible-mode/v1"
EMBED_MODEL_NAME="text-embedding-v4"
QDRANT_VECTOR_SIZE="1024"

QDRANT_URL="http://localhost:6333"
QDRANT_TIMEOUT="30"

# compose.chapter8.yml 启动 Neo4j 时需要
NEO4J_PASSWORD="your-local-neo4j-password"
```

不要把真实密钥写入 Git、README、测试或日志。`.env` 已被 Git 忽略。

## 安装与启动

在工作区根目录安装依赖：

```bash
cd /Users/eric/Documents/Codex/Hello-agent-v0.0.1
.venv/bin/python -m pip install -r requirements.txt

cd projects/12_hello_agents_practice/expert_platform/frontend
pnpm install
```

从本项目目录启动 FastAPI 后端：

```bash
cd projects/12_hello_agents_practice
../../.venv/bin/python -m uvicorn expert_platform.backend.app.main:app \
  --host 127.0.0.1 --port 8000 --reload
```

在另一个终端启动 Vue 前端：

```bash
cd projects/12_hello_agents_practice/expert_platform/frontend
pnpm dev
```

访问 <http://127.0.0.1:5173/>。Vite 将 `/api` 转发到 FastAPI。详细架构、管理员命令、删除命令和生产构建方式见 [`expert_platform/README.md`](expert_platform/README.md)。

首次创建管理员：

```bash
cd projects/12_hello_agents_practice
../../.venv/bin/python -m expert_platform.cli.manage_admin create admin
```

### 历史 Gradio 入口

原 Gradio 应用继续保留，用于对照和学习：

```bash
cd projects/12_hello_agents_practice
../../.venv/bin/python -m apps.pdf_learning_assistant
```

默认访问 <http://127.0.0.1:7860/>，也可以覆盖监听地址和端口：

```bash
../../.venv/bin/python -m apps.pdf_learning_assistant --host 127.0.0.1 --port 7861
```

Gradio 入口启动时会：

1. 加载工作区根目录的 `.env`。
2. 检查目标端口是否被占用。
3. 通过 [`infra/compose.chapter8.yml`](infra/compose.chapter8.yml) 启动 Qdrant 和 Neo4j。
4. 创建 Gradio 应用并监听本地端口。
5. 应用退出时停止容器，但保留 Docker volume 中的数据。

## 数据位置与存储边界

运行数据默认保存在本项目目录，且不纳入 Git：

| 路径 | 内容 |
| --- | --- |
| `memory_data/practice_memory.db` | 用户账号、专家库目录、文档与分块记录、episodic memory |
| `knowledge_base/` | 按用户和专家库隔离保存的原始文件 |
| `monthly_personal_reports/` | 按用户和生成月份保存的最近 30 天个人对话总结 JSON |
| `learning_reports/` | 旧版会话报告，仅保留历史文件，不再写入 |
| Docker volume `hello_agents_qdrant_data` | Qdrant 向量数据 |
| Docker volume `hello_agents_neo4j_data` | Neo4j 数据；当前应用主流程主要使用 SQLite 与 Qdrant |

SQLite 保存权威目录和原文分块，Qdrant 保存派生向量与检索载荷。切换 Embedding 模型或向量维度时，不能直接复用旧 collection；应使用新的 collection 或重建索引。

## 项目结构

```text
apps/
  pdf_learning_assistant.py   # Gradio 应用、认证编排、权限边界和业务流程
  user_store.py               # 本地账号注册与认证
hello_agents_framework/
  agents/                     # Simple、ReAct、Reflection、Plan-and-Solve、FunctionCall
  core/                       # Message、Config、LLM 和 Agent 合约
  memory/                     # Working/Episodic Memory、SQLite、Qdrant、RAG
  tools/                      # Tool Registry、RAG、Memory、Search、Chain、Async Executor
expert_platform/
  frontend/                   # Vue 3、TypeScript、Router 和 Pinia 前端
  backend/                    # FastAPI API、会话、管理和业务编排
  cli/                        # 本地管理员授权与跨存储删除命令
  docs/                       # PRD、Tech Spec 和 API Contract
examples/                     # 手动示例和外部服务检查
tests/                        # 离线单元测试与应用流程测试
infra/compose.chapter8.yml    # Qdrant 和 Neo4j 本地服务
```

## 验证

离线测试不需要调用真实模型、Embedding 服务或 Docker：

```bash
cd /Users/eric/Documents/Codex/Hello-agent-v0.0.1/projects/12_hello_agents_practice
../../.venv/bin/python -m unittest discover -s tests -v
```

`examples/` 下的 `local_*` 示例是手动集成检查，可能消耗模型、Embedding、搜索或向量数据库资源；它们不等同于自动化测试。

## 运行限制

- 当前认证是本地学习实现；登录会话可恢复，但当前对话上下文仍是进程内状态。
- 共享专家库的写权限仍然开放给所有已登录用户。
- 当前只有普通用户和管理员两级权限，没有生产级 SSO、账号找回、通用 RBAC、分布式限流或跨进程助手状态。
- 管理删除使用同源校验、准确 ID 确认和审计记录，但生产互联网部署仍应在 HTTPS、反向代理、备份和集中监控下运行。
- Qdrant、Embedding、Chat Completions 和文件解析能力都依赖外部服务或本地容器的可用性。
- 这是来源增强的检索问答实现，不等于对答案事实正确性的独立审核。

## 相关文档

- [`Tech-Spec.md`](Tech-Spec.md)：技术范围、验收标准和变更记录
- [`CHANGELOG.md`](CHANGELOG.md)：版本里程碑与发布边界
- [`design-qa.md`](design-qa.md)：界面视觉验收记录
