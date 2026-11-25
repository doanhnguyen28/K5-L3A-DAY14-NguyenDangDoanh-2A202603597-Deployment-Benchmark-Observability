# Day 14 Lab - Mission Answers

> Output thô của mọi lệnh đã chạy nằm trong `evidence/` (index: `evidence/README.md`).
> Trên máy làm bài, cổng 8000 đã bị một dự án khác chiếm, nên các app develop/production của Part 1, 4, 5 chạy ở cổng **8010**.

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

Trong `01-localhost-vs-production/develop/app.py`:

1. **Hardcode secret** (dòng 17–18): `OPENAI_API_KEY = "sk-hardcoded-..."` và `DATABASE_URL` có cả user/password. Push lên GitHub là lộ ngay, và muốn đổi key thì phải sửa code.
2. **Log ra secret** (dòng 34): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`. Khi chạy thật, log server đã in nguyên key `sk-hardcoded-fake-key-never-do-this` (`evidence/part1-5/part1_outputs.txt`).
3. **Dùng `print()` thay vì logging có cấu trúc** (dòng 33–38): không có level, timestamp hay định dạng JSON, nên khó lọc và tìm kiếm trong log aggregator.
4. **Config cứng, không qua biến môi trường** (dòng 21–22): `DEBUG = True`, `MAX_TOKENS = 500` cố định trong code.
5. **Không có health check** (dòng 42): gọi `GET /health` thì nhận **404**. Platform không biết khi nào agent chết để restart.
6. **Port và host cố định** (dòng 51–52): `host="localhost"` nên không nhận kết nối từ ngoài container; `port=8000` không đọc biến `PORT` mà Railway/Render cấp.
7. **`reload=True` trong production** (dòng 53): bật chế độ debug, tốn tài nguyên để theo dõi file thay đổi.
8. **Không xử lý shutdown:** không bắt SIGTERM, không đợi request đang chạy xong.
9. **Input qua query string** (`/ask?question=...`), không có model validate: câu hỏi nằm trong URL nên bị ghi vào access log, và không giới hạn độ dài.

### Exercise 1.2: Chạy bản develop

```
$ curl -i -X POST "http://localhost:8010/ask?question=Hello"
HTTP/1.1 200 OK
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
$ curl -i http://localhost:8010/health
HTTP/1.1 404 Not Found
```

App chạy được, nhưng chưa production-ready: không có health check và in secret ra log.

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hardcode trong code (`OPENAI_API_KEY`, `DEBUG`, port) | Đọc từ env (`config.py`, `.env.example`) | Cùng một code chạy được ở dev, staging và prod. Secret không nằm trong git. Đổi key không cần sửa code |
| Secret trong log | In nguyên key ra stdout | Không log secret | Log thường được gửi sang hệ thống khác và nhiều người đọc được |
| Health check | Không có (`/health` trả 404) | `/health` (liveness) + `/ready` (readiness) đều 200 | Platform restart container khi liveness fail; load balancer chỉ gửi traffic khi ready |
| Logging | `print()` | JSON qua `logging` (`json.dumps({...})`) | Dễ parse và lọc trong Loki/Datadog, có level và timestamp |
| Shutdown | Đột ngột | Graceful: bắt SIGTERM, `lifespan` dọn dẹp | Không cắt ngang request của người dùng khi deploy hoặc scale down |
| Host / Port | `localhost:8000` cố định | `0.0.0.0` + `PORT` từ env | Nhận kết nối từ ngoài container; chạy được trên cloud nơi PORT do platform cấp |
| Debug / reload | `reload=True`, `DEBUG=True` | Theo `ENVIRONMENT` / `DEBUG` từ env | Không bật debug trong production (tốn tài nguyên, lộ thông tin) |

Kết quả chạy bản production: `/health` trả 200 `{"status":"ok","uptime_seconds":0.6,...}`, `/ready` trả 200 `{"ready":true}`, `POST /ask` với JSON body trả 200.

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. **Base image:** `python:3.11`, bản Python đầy đủ (~1 GB, có cả compiler và công cụ build).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Tại sao COPY requirements.txt trước:** để tận dụng layer cache. Docker cache từng layer; layer `pip install` chỉ build lại khi `requirements.txt` đổi. Sửa code (`app.py`) chỉ làm build lại các layer phía sau, nên không phải cài lại toàn bộ dependency mỗi lần build.
4. **CMD vs ENTRYPOINT:**
   - `CMD` là lệnh mặc định, bị thay hoàn toàn khi chạy `docker run image <lệnh khác>`.
   - `ENTRYPOINT` là chương trình cố định; tham số của `docker run` (hoặc CMD) được nối vào sau làm argument.
   - Cách dùng phổ biến: `ENTRYPOINT ["uvicorn"]` + `CMD ["app:app", "--port", "8000"]`.

### Exercise 2.2: Build và run

```
$ docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
$ docker run -d -p 8010:8000 my-agent:develop
$ curl -X POST "http://localhost:8010/ask?question=What%20is%20Docker"
HTTP/1.1 200 OK
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: Image size comparison

- **Stage 1 (builder):** từ `python:3.11-slim`, cài `gcc`, `libpq-dev`, rồi `pip install --user` các dependency vào `/root/.local`. Stage này không được deploy.
- **Stage 2 (runtime):** từ `python:3.11-slim` sạch. Chỉ copy `/root/.local` (package đã cài) và code. Tạo user non-root `appuser`, có `HEALTHCHECK`, `CMD uvicorn ... --workers 2`.
- **Tại sao nhỏ hơn:**
  - Base `slim` thay cho bản full.
  - Compiler, header và cache của apt/pip nằm ở stage builder và bị bỏ lại.
  - Image cuối chỉ chứa thứ cần để **chạy**.

Đo bằng `docker images` và `docker image inspect --format {{.Size}}` (`evidence/part1-5/part2_image_sizes.txt`):

- Develop: **1667.8 MB** (1 667 808 589 bytes, `docker images` hiển thị 1.67GB)
- Production: **239.8 MB** (239 815 330 bytes, hiển thị 240MB)
- Difference: nhỏ hơn **85.6 %** (khoảng 7 lần)

### Exercise 2.4: Docker Compose stack

```
                 ┌────────────────────────────┐
  Client ──:80──▶│  nginx (nginx:alpine)       │  reverse proxy / load balancer,
                 │  upstream agent_backend     │  thêm security headers
                 └──────────────┬─────────────┘
                                │ http://agent:8000  (network nội bộ)
                 ┌──────────────▼─────────────┐
                 │  agent (build Dockerfile)   │  FastAPI, healthcheck
                 └───────┬──────────────┬─────┘
                         │              │
              redis://redis:6379   http://qdrant:6333
                 ┌───────▼──────┐  ┌────▼─────────┐
                 │ redis:7-alpine│  │ qdrant v1.9.0│
                 │ session/cache │  │ vector DB    │
                 └──────────────┘  └──────────────┘
```

- **Services được start:** `redis`, `qdrant` (đều healthy trước), rồi `agent` (`depends_on` với điều kiện healthy), rồi `nginx`.
- **Cách giao tiếp:** các service nói chuyện qua network nội bộ của compose, gọi nhau bằng tên service (DNS: `agent`, `redis`, `qdrant`). Chỉ Nginx publish cổng 80/443 ra host. Agent, Redis và Qdrant không lộ ra ngoài.

Test qua Nginx:

```
$ curl -i http://localhost/health
HTTP/1.1 200 OK
Server: nginx
X-Frame-Options: DENY
{"status":"ok","uptime_seconds":7.6,"version":"2.0.0",...}
$ curl -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deployment

- **URL:** https://production-ai-agent-bss8.onrender.com. Đây là agent Part 6 (`06-lab-complete/`).
- **Platform:** **Render**, Blueprint `06-lab-complete/render.yaml`, gồm web service Docker và Key Value Redis, gói free, region Singapore.
- **Vì sao không dùng Railway:** đã thử `railway init`, nhưng tài khoản báo "Your trial has expired". `railway.toml` vẫn được viết đầy đủ và đạt tiêu chí "Public URL ready" của script chấm.
- **4 lệnh tự kiểm CP6:** `/health` 200, `/ready` 200, `/ask` không key 401, `/ask` có key 200 (`evidence/part3_render_selftest.txt`). Chi tiết ở [DEPLOYMENT.md](DEPLOYMENT.md).
- **Screenshot:** [dashboard](screenshots/dashboard.png), [running](screenshots/running.png), [test](screenshots/test.png).

### So sánh `railway.toml` với `render.yaml`

| Khía cạnh | `railway.toml` | `render.yaml` |
|---|---|---|
| Phạm vi | Cấu hình **1 service** (cách build và deploy) | **Blueprint cả hạ tầng**: khai báo nhiều service, gồm web và Key Value (Redis) |
| Build | `builder = "DOCKERFILE"`, `dockerfilePath` | `runtime: docker`, `rootDir: 06-lab-complete`, `dockerfilePath` |
| Health check | `healthcheckPath = "/health"`, `healthcheckTimeout` | `healthCheckPath: /health` |
| Restart | `restartPolicyType = "ON_FAILURE"`, số lần retry | Render tự quản lý, không cấu hình trong file |
| Biến môi trường / secret | **Không** khai báo trong file. Đặt bằng `railway variables --set` hoặc dashboard; `REDIS_URL=${{Redis.REDIS_URL}}` tham chiếu service Redis tạo riêng | Khai báo ngay trong file: giá trị thường (`value`), secret tự sinh (`generateValue: true`), hoặc tham chiếu service khác (`fromService` → `connectionString` của `agent-redis`) |
| Redis | Tạo riêng (`railway add --database redis`) | Khai báo trong cùng file (`type: keyvalue`, `plan: free`, `ipAllowList: []`) |
| Gói / region | Chọn trên dashboard | `plan: free`, `region: singapore` ghi trong file |
| Cách deploy | CLI `railway up` upload thư mục local | Kết nối GitHub repo; push code là deploy (GitOps) |

**Vì sao khác nhau:**
- Railway thiên về CLI và làm nhanh: file chỉ mô tả build/deploy, còn tài nguyên khác và secret quản lý ngoài file.
- Render theo hướng Infrastructure-as-Code: một file Blueprint dựng lại được toàn bộ stack (web + Redis + nối biến) từ repo, và secret vẫn không nằm trong git nhờ `generateValue` / `sync: false`.

### Exercise 3.3: Cloud Run CI/CD pipeline

Đọc `03-cloud-deployment/production-cloud-run/cloudbuild.yaml` và `service.yaml`. Pipeline Cloud Build gồm 4 bước nối tiếp nhau (`waitFor`):

1. **test**: chạy `pytest` trong `python:3.11-slim`. Fail thì dừng pipeline.
2. **build**: build image, gắn tag `$COMMIT_SHA` và `latest`, dùng `--cache-from` image `latest` để tận dụng layer cache.
3. **push**: đẩy image lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **deploy**: `gcloud run deploy` với đúng image theo commit SHA, region `asia-southeast1`, `min-instances=1` (tránh cold start), `max-instances=10`, 512Mi/1 CPU. Secret lấy từ **Secret Manager** (`--set-secrets`), không ghi trong file.

`service.yaml` mô tả cùng service dạng Knative:
- autoscaling `minScale 1` / `maxScale 10`;
- `containerConcurrency: 80`;
- liveness/readiness probe;
- secret `OPENAI_API_KEY` và `AGENT_API_KEY` qua `secretKeyRef`.

Mỗi commit đi qua test → build → push → deploy một cách tự động, và có thể rollback về image của SHA cũ.

## Part 4: API Security

### Exercise 4.1-4.3: Test results

Đầy đủ trong `evidence/part1-5/part4_outputs.txt`; token đã che.

**4.1 API key (`04-api-gateway/develop`)**
- Key được check trong dependency `verify_api_key` (dòng 39–50), gắn vào `/ask` bằng `Depends`. Key đúng lấy từ env `AGENT_API_KEY` (dòng 35).
- Thiếu header thì trả **401**. Có header nhưng sai key thì trả **403**.
- **Rotate key:** đổi biến `AGENT_API_KEY` trên platform rồi restart hoặc redeploy. Code chỉ hỗ trợ 1 key. Muốn rotate không downtime thì cần chấp nhận 2 key (cũ + mới) trong một khoảng thời gian.

```
$ curl -i -X POST http://localhost:8010/ask            (không có key)
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
$ curl -i -X POST http://localhost:8010/ask -H "X-API-Key: wrong"
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}
$ curl -i -X POST http://localhost:8010/ask -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 200 OK
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

Lần thử đầu tiên gửi câu hỏi qua query string (theo mẫu cũ) thì server trả 500, vì app đọc JSON body. Gửi đúng JSON body thì nhận 200.

**4.2 JWT (`04-api-gateway/production`)**

JWT flow:
1. `POST /auth/token` với username/password.
2. Server ký JWT (HS256) chứa `sub`, `role` và `exp` (60 phút).
3. Client gửi `Authorization: Bearer <token>`.
4. Server chỉ verify chữ ký và hạn, không phải tra database mỗi request.

```
$ curl -i -X POST http://localhost:8010/auth/token -H "Content-Type: application/json" -d '{"username":"student","password":"demo123"}'
HTTP/1.1 200 OK
{"access_token":"eyJ***REDACTED***","token_type":"bearer","expires_in_minutes":60,...}
$ curl -i -X POST http://localhost:8010/ask            (không token)
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
$ curl -i -X POST http://localhost:8010/ask -H "Authorization: Bearer $TOKEN" -d '{"question":"Explain JWT"}'
HTTP/1.1 200 OK
{"question":"Explain JWT","answer":"...","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
```

**4.3 Rate limiting**
- **Algorithm:** sliding window log. Mỗi user có một `deque` timestamp; xoá timestamp cũ hơn 60 giây rồi đếm.
- **Limit:** user **10 req/phút**; admin **100 req/phút** (`rate_limiter_user` / `rate_limiter_admin`).
- **Bypass cho admin:** `app.py` chọn limiter theo `role` trong JWT (`limiter = rate_limiter_admin if role == "admin" else rate_limiter_user`). Admin không bypass hoàn toàn mà dùng limit cao hơn.

Vòng lặp 20 request (token của user `student`). Request ở 4.2 đã dùng 1 lượt trong cửa sổ, nên request thứ 10 là lượt thứ 11:

```
req  1 -> 200
...
req  9 -> 200
req 10 -> 429 retry-after: 58 {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":58}}
...
req 20 -> 429 retry-after: 57
```

**Agent Part 6 trên Render** cũng chặn đúng: 12 request liên tiếp thì từ request 9 trả **429**. 2 request trước đó nằm cùng cửa sổ, `RATE_LIMIT_PER_MINUTE=10`.

### Exercise 4.4: Cost guard implementation

Đã làm trong `06-lab-complete/app/cost_guard.py`, state lưu trong **Redis**:

1. **Trước khi gọi LLM**, `check_budget()` đọc 2 key `cost:daily:YYYY-MM-DD` và `cost:monthly:YYYY-MM` bằng một lệnh `MGET`. Nếu tổng ngày ≥ `DAILY_BUDGET_USD` hoặc tổng tháng ≥ `MONTHLY_BUDGET_USD` thì trả **HTTP 402 Payment Required**. Redis lỗi thì trả 503, không cho gọi LLM "mù".
2. **Sau khi gọi LLM**, `record_cost()` tính chi phí theo token (`input/1000 × 0.00015 + output/1000 × 0.0006`), rồi `INCRBYFLOAT` vào cả 2 key trong một pipeline. Key ngày có `EXPIRE` 2 ngày, key tháng 32 ngày.
3. **Reset đầu tháng/ngày** không cần cron: tên key chứa ngày hoặc tháng, nên sang kỳ mới là key mới, bắt đầu từ 0. Key cũ tự hết hạn.
4. **Vì sao dùng Redis:** Dockerfile chạy 2 worker và có thể scale nhiều container. Nếu lưu trong RAM thì mỗi process có một tổng riêng và vượt budget mà không biết. `INCRBYFLOAT` là atomic nên nhiều instance cùng cộng vẫn đúng. Script chấm đặt budget gần 0 và nhận **402**.

Phiên bản theo user, đúng chữ ký hàm của bài tập ($10/tháng mỗi user):

```python
def check_budget(user_id: str, estimated_cost: float) -> bool:
    key = f"budget:{user_id}:{datetime.now(timezone.utc):%Y-%m}"   # key mới mỗi tháng → tự reset
    new_total = r.incrbyfloat(key, estimated_cost)                   # cộng atomic trước
    r.expire(key, 32 * 24 * 3600)
    if new_total > 10:
        r.incrbyfloat(key, -estimated_cost)                          # hoàn lại nếu vượt
        return False
    return True
```

Cộng trước rồi mới so sánh, thay vì `GET` rồi mới cộng, để tránh race condition khi 2 request cùng lúc thấy "còn tiền".

Phân biệt: **rate limit bảo vệ tốc độ** (chống spam/DoS, theo số request/phút), **cost guard bảo vệ tiền** (một lượng request vừa phải nhưng prompt dài vẫn có thể đốt hết ngân sách). Cần cả hai.

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes

Output: `evidence/part1-5/part5_outputs.txt`.

**5.1 Health checks**
- `/health` (liveness) chỉ kiểm tra process còn chạy, kèm uptime và mức dùng memory. Không phụ thuộc DB/Redis, để Redis chập chờn không làm platform restart container vô ích.
- `/ready` (readiness) kiểm tra dependency và trạng thái shutdown; chưa sẵn sàng thì trả 503 để load balancer ngừng gửi traffic.

```
$ curl -i http://localhost:8010/health
HTTP/1.1 200 OK
{"status":"degraded",...,"checks":{"memory":{"status":"degraded","used_percent":93.3}}}
$ curl -i http://localhost:8010/ready
HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```

Lúc test, RAM máy đang dùng 93 %, nên `/health` báo `degraded` nhưng vẫn trả 200: process còn sống, chỉ cảnh báo.

**5.2 Graceful shutdown**
- Handler SIGTERM chỉ ghi log. uvicorn tự ngừng nhận kết nối mới, chờ request đang chạy xong, rồi chạy phần shutdown của `lifespan` (đợi `_in_flight_requests` về 0, tối đa 30 giây).
- Windows không gửi được SIGTERM thật, nên tôi test trong container Linux `python:3.11-slim`:

```
[shell]  kill -TERM 7          (gửi khi request "Long task" đang chạy)
INFO:     Shutting down
INFO:     127.0.0.1:58576 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
[client] in-flight request -> HTTP 200 sau 3.01s
INFO:     Application shutdown complete.
[shell]  app exit code: 0
```

Request đang chạy vẫn hoàn thành (200) và process thoát với code 0.

**5.3 Stateless design**
- Bản production không giữ `conversation_history = {}` trong RAM nữa. Session và history lưu ở Redis: `session:{id}` qua `setex`, TTL 1 giờ, giữ 20 message gần nhất.
- Lý do: khi scale ra nhiều instance, mỗi instance có RAM riêng. Request sau của cùng user có thể rơi vào instance khác và mất history. Instance bị kill hoặc restart cũng mất state.

**5.4 Load balancing:** chạy `docker compose up -d --scale agent=3` được 3 agent, 1 Nginx và 1 Redis, tất cả healthy. Log cho thấy Nginx chia request cho `agent-1`, `agent-2`, `agent-3`. Instance nào chết thì Nginx bỏ qua và gửi sang instance còn lại.

**5.5 Test stateless:** `python test_stateless.py`

```
Request 1: [instance-55fda7]   Request 2: [instance-92ee1c]   Request 3: [instance-f228f1]
Request 4: [instance-55fda7]   Request 5: [instance-92ee1c]
Instances used: {'instance-55fda7', 'instance-92ee1c', 'instance-f228f1'}
✅ All requests served despite different instances!
--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

5 request của cùng một session đi qua cả 3 instance, nhưng history vẫn đủ 10 message (5 user + 5 assistant), vì state nằm ở Redis chứ không ở instance nào.

## Part 6: Final Project

Code trong `06-lab-complete/`. Đã sửa hết TODO trong `app/` (`config.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `redis_client.py`, `main.py`), cùng với `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`.

Tóm tắt cách làm:
- **Rate limit:** sliding window 60 giây bằng Redis sorted set (`ZREMRANGEBYSCORE`, `ZCARD`, `ZADD`, `EXPIRE` trong một pipeline). Bucket theo sha256 của API key, không lưu key thô. Vượt limit trả 429 kèm `Retry-After`.
- **Log:** JSON mỗi dòng.
- **`/ready`:** trả 503 khi mất Redis hoặc đang shutdown.
- **Dockerfile:** multi-stage dùng venv, base slim, user non-root, `HEALTHCHECK`. `exec uvicorn ... --workers 2 --timeout-graceful-shutdown 8` để uvicorn là PID 1 và nhận được SIGTERM.

Script chấm chạy bản đầy đủ có Docker. Vì Windows không gửi được SIGTERM, script chạy trong container Linux, có Docker CLI và mount cả repo; không sửa `check_production_ready.py`. Output đầy đủ: `evidence/check_production_ready_output.txt`.

```
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

Image 273 MB; `docker stop` thoát với code 0 sau 0.7 giây.

## Part 7: Benchmark & Observability

Xem [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md). Tóm tắt:
- Load test 4 mức concurrency: SLO p95 < 500 ms vỡ từ concurrency 50.
- Eval: v1 4.3 %, v2 91.3 %, sau khi sửa `KNOWLEDGE_BASE` là 100 %, 0 regression. CI quality gate dựa trên exit code.
- Grafana, Jaeger (trace chậm và trace lỗi khớp `trace_id` với log), 3 alert firing trong các thí nghiệm A, B, D.

Hai thay đổi code trong Part 7:
- Thêm metric `agent_question_length_chars` (Exercise 7.1).
- Sửa Dockerfile của stack production: thêm `ENV PYTHONUSERBASE=/home/agent/.local`. User `agent` có HOME là `/app`, nên Python không tìm thấy package đã copy sang `/home/agent/.local` và container crash vì không thấy uvicorn.

---

## AI log

Công cụ: **Claude Code** (model Claude Opus 5.5), chạy trong VS Code với quyền đọc/ghi file và chạy lệnh trên máy tôi. Tôi giao việc bằng tiếng Việt; AI đọc đề, viết code, chạy lệnh và báo lại.

| # | Tôi hỏi / giao việc | AI đã làm | Tôi tự kiểm tra / tự làm |
|---|---|---|---|
| 1 | "Đọc bài lab day14 và làm cho tôi" (Part 1–7, trừ report và git) | Đọc `CODE_LAB.md`, `RUBRIC.md`, `06-lab-complete/README.md`. Viết toàn bộ TODO Part 6 (`app/*.py`, Dockerfile, compose, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`). | Chạy lại các lệnh curl, đọc code để giải thích được từng phần: sliding window bằng sorted set, `compare_digest`, `/health` khác `/ready`, `exec` để uvicorn là PID 1. |
| 2 | Chạy script chấm Part 6 | Lần đầu trên Windows được 11/12 (⚠️ graceful shutdown vì Windows không có SIGTERM). AI dựng container Linux có Docker CLI, mount repo và socket Docker để chạy bản đầy đủ: **PASS 12/12**. Không sửa `check_production_ready.py`. | Đọc output 43/43 checks trong `evidence/check_production_ready_output.txt`. |
| 3 | Chạy Part 1, 2, 4, 5 và lưu output | Chạy các app ở cổng 8010, build 2 image Part 2, chạy compose Part 2/5, test SIGTERM trong container Linux. Ghi output vào `evidence/part1-5/`. | Đối chiếu số MB và mã HTTP trong report với file evidence. |
| 4 | Part 7: load test, eval, sửa knowledge base, CI gate | Chạy `load_test.py` (4 mức concurrency, 3 mức `MOCK_SLOW_RATE`) và `run_eval.py`. Thêm 2 tài liệu vào `KNOWLEDGE_BASE` theo `missing_keywords`. Viết `.github/workflows/eval-quality-gate.yml`. | Kiểm tra eval v2 đạt 23/23, 0 regression; v1 so với baseline v2 cho exit code 1. Không sửa `golden_dataset.jsonl`. |
| 5 | Part 7: observability stack, trace, alert | Sửa lỗi `PYTHONUSERBASE` trong Dockerfile stack production. Map Grafana sang cổng 3001 bằng file override tạm (cổng 3000 bận). Chạy Locust (scale 1 và 3), bơm lỗi A+B và D, ghi timeline alert. Tìm trace chậm/lỗi qua Jaeger API v3, grep log theo `trace_id`. Chụp 4 ảnh Part 7 bằng trình duyệt Edge headless (Playwright). | Xem lại 4 ảnh, đối chiếu `trace_id` trong ảnh, report và dòng log. |
| 6 | Hướng dẫn deploy Railway | Hướng dẫn từng bước. Railway báo trial hết hạn nên AI đề xuất Render với `render.yaml` có sẵn. | **Tự tạo tài khoản và deploy trên Render** (Blueprint). Tự chạy 4 lệnh CP6. Lần đầu sai URL (dán nhầm URL mẫu, rồi thừa dấu `/` cuối nên ra 404), AI chỉ ra lỗi. |
| 7 | Viết report (`MISSION_ANSWERS.md`, `DEPLOYMENT.md`, `BENCHMARK_REPORT.md`) | Soạn 3 file từ số liệu trong `reports/`, `benchmark-results/`, `evidence/`. Thêm metric `agent_question_length_chars` và chạy thí nghiệm D để bổ sung. | Đọc lại toàn bộ, kiểm tra mọi số khớp file JSON/CSV. Tự chụp 2 ảnh trên dashboard Render (`dashboard.png`, `running.png`). Tự commit. |
| 8 | Dọn image Docker, chụp `test.png` | Xoá 3 image lab (`my-agent:*`, `day14-checker`). Mở một cửa sổ Git Bash, chạy 4 lệnh CP6 vào URL Render (ra 200/200/401/200), rồi chụp cửa sổ đó thành `test.png`. | Xem lại ảnh: đúng URL, đúng mã HTTP, không lộ giá trị key. |

Ghi chú về sự cố trong lúc AI làm: khi dọn cổng 8000, AI đã kill nhầm tiến trình giữ cổng của Docker Desktop (cổng đó thuộc một dự án khác trên máy tôi), làm Docker tắt khoảng 1 phút. AI đã khởi động lại Docker Desktop, các container tự chạy lại, và sau đó chuyển app lab sang cổng 8010.

Không có số liệu nào do AI ước lượng. Mọi con số đều lấy từ lệnh đã chạy trên máy và file report nộp kèm.
