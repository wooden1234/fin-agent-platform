# fin-agent-platform 本地安装与联调

> W1 范围：PostgreSQL + Redis + JWT 鉴权 + 会话 CRUD。  
> Agent / LlamaIndex 从 W2/W3 开始，本文暂不涉及。

---

## 1. 环境要求

| 工具 | 版本建议 |
|------|----------|
| Python | 3.11+（项目当前用 3.12） |
| Docker + Docker Compose | 用于 PostgreSQL(pgvector) 与 Redis |
| Node.js | 18+（仅在前端联调时需要） |
| Git | 克隆仓库 |

---

## 2. 获取代码

```bash
git clone <你的仓库地址>
cd fin-agent-platform
```

---

## 3. 启动基础设施（PostgreSQL + Redis）

```bash
docker compose up -d
docker compose ps          # 两个服务应为 healthy
```

默认连接信息（与 `.env.example` 一致）：

| 服务 | 地址 | 账号/库 |
|------|------|---------|
| PostgreSQL | `localhost:5432` | 用户 `fin` / 密码 `fin` / 库 `fin_agent` |
| Redis | `localhost:6379` | 无密码，DB `0` |

验证 Postgres：

```bash
docker exec fin-agent-postgres pg_isready -U fin -d fin_agent
```

---

## 4. Python 依赖

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 5. 环境变量

```bash
cp .env.example .env
```

按需修改 `.env`（本地开发可先保持默认）：

| 变量 | 说明 |
|------|------|
| `APP_ENV` | 如 `development` |
| `SECRET_KEY` | JWT 签名密钥，**生产必须改** |
| `DATABASE_URL` | 异步 PG 连接串，格式 `postgresql+asyncpg://...` |
| `REDIS_URL` | W1 可先不配业务逻辑，容器需启动 |
| `ALGORITHM` | 默认 `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token 有效期（分钟） |

> `.env` 已在 `.gitignore` 中，勿提交仓库。

---

## 6. 初始化数据库表

```bash
python scripts/init_db.py
```

成功后会创建：`users`、`conversations`、`messages`。

验证：

```bash
docker exec fin-agent-postgres psql -U fin -d fin_agent -c "\dt"
```

开发环境需**清空重建**时（会删数据）：

```bash
python scripts/init_db.py --reset
```

---

## 7. 启动后端

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

| 地址 | 用途 |
|------|------|
| http://127.0.0.1:8000/health | 健康检查 |
| http://127.0.0.1:8000/docs | Swagger 交互文档 |

若报 `Address already in use`，说明 8000 已被占用：

```bash
pkill -f "uvicorn app.main:app"
# 或换端口：--port 8001
```

---

## 8. （可选）启动前端

W1 计划以 API 测试为主；若需 UI 联调：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173（Vite 会把 `/api` 代理到 `8000`）。

---

## 9. W1 端到端验收（Day 6）

以下命令假设后端运行在 `8000`，将 `EMAIL` 换成未注册邮箱。

```bash
BASE=http://127.0.0.1:8000
EMAIL=test@example.com

# 1. 注册
curl -s -X POST "$BASE/api/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"'"$EMAIL"'","password":"123456"}'

# 2. 登录拿 Token
TOKEN=$(curl -s -X POST "$BASE/api/token" \
  -H "Content-Type: application/json" \
  -d '{"email":"'"$EMAIL"'","password":"123456"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 3. 当前用户
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/users/me"

# 4. 创建会话
CONV=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" "$BASE/api/conversations")
echo "$CONV"
CONV_ID=$(echo "$CONV" | python3 -c "import sys,json; print(json.load(sys.stdin)['conversation_id'])")

# 5. 消息历史（新会话为空列表 [] 属正常，W3 Agent 才会写入 message）
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/conversations/$CONV_ID/messages"
```

预期：各步 HTTP 200；`/users/me` 返回用户信息；`/messages` 返回 `[]`。

---

## 10. API 一览（W1）

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/api/register` | 否 | 注册 |
| POST | `/api/token` | 否 | 登录，返回 JWT |
| GET | `/api/users/me` | Bearer | 当前用户 |
| POST | `/api/conversations` | Bearer | 新建会话 |
| GET | `/api/conversations` | Bearer | 会话列表 |
| GET | `/api/conversations/{id}/messages` | Bearer | 消息历史 |
| DELETE | `/api/conversations/{id}` | Bearer | 删除会话 |
| PUT | `/api/conversations/{id}/name` | Bearer | 改标题 |
| GET | `/api/agent/health` | Bearer | Agent 占位（W3 实现 query/resume） |

---

## 11. 常见问题

### `ModuleNotFoundError: No module named 'app.xxx'`

在项目根目录执行，并已 `source .venv/bin/activate`：

```bash
pip install -r requirements.txt
```

### `asyncpg` / 数据库连接失败

1. `docker compose ps` 确认 Postgres 为 healthy  
2. 检查 `.env` 中 `DATABASE_URL` 与 compose 端口、账号一致  

### 注册报邮箱已存在

换一个新邮箱，或 `python scripts/init_db.py --reset` 清空开发库（仅开发环境）。

### 新建会话在列表里看不到

当前 Service 会过滤标题为「新会话」的记录，有第一条聊天消息改标题后才会出现在列表（已知行为，后续可优化）。

### 端口 8000 被占用

```bash
pgrep -af uvicorn
pkill -f "uvicorn app.main:app"
```

---

## 12. 目录结构（W1 相关）

```
fin-agent-platform/
├── app/
│   ├── api/           # auth、conversations、agent(占位)
│   ├── core/          # config、database、security
│   ├── models/        # User、Conversation、Message
│   ├── schemas/       # Pydantic 请求/响应
│   ├── services/      # 业务逻辑
│   └── main.py        # FastAPI 入口
├── scripts/init_db.py # 建表
├── docker-compose.yml
├── .env.example
└── frontend/          # 可选 UI
```

---

## 13. 下一步（W2 预告）

- [ ] LlamaIndex ingest + pgvector 向量索引  
- [ ] FAQ 检索调试 API  

详见 `fin-agent/plan/week-02-LlamaIndex检索层.md`。
