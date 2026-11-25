# Deployment Information

## Public URL

https://production-ai-agent-bss8.onrender.com

Service này là agent Part 6 (`06-lab-complete/`), không phải app mẫu của `03-cloud-deployment/`.

## Platform

**Render**: Blueprint `06-lab-complete/render.yaml`, gói free, region Singapore.

| Tài nguyên | Loại | Ghi chú |
|---|---|---|
| `production-ai-agent` | Web service, runtime Docker | Build từ `06-lab-complete/Dockerfile` (`rootDir: 06-lab-complete`), health check `/health` |
| `agent-redis` | Key Value (Redis), gói free | Chỉ cho kết nối nội bộ (`ipAllowList: []`). Lưu state của rate limit và cost guard |

Ban đầu tôi thử deploy lên Railway (`railway init`), nhưng tài khoản Railway đã hết trial ("Your trial has expired"). Vì vậy chuyển sang Render, dùng file `render.yaml` đã viết ở Part 6.

Cách deploy: push repo lên GitHub, rồi trên Render chọn New → Blueprint, chọn repo, điền Blueprint Path `06-lab-complete/render.yaml` và bấm Apply.

Lưu ý gói free: service "ngủ" sau 15 phút không có request. Request đầu tiên sau đó mất khoảng 30–60 giây để khởi động lại.

## Test Commands

Đặt biến trong shell (Git Bash). Key lấy từ tab Environment của service trên Render, không ghi vào repo:

```bash
export BASE="https://production-ai-agent-bss8.onrender.com"   # không có dấu / ở cuối
export AGENT_API_KEY="<key trên Render>"
```

### 4 lệnh tự kiểm (CP6)

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Kết quả chạy lúc 2026-11-25 11:08Z: `200`, `200`, `401`, `200` (`evidence/part3_render_selftest.txt`).

### Health check

```bash
curl "$BASE/health"
# {"status":"ok","environment":"production"}

curl "$BASE/ready"
# {"status":"ready","redis":"ok"}      ← đã kết nối được Redis trên Render
```

### API test (with authentication)

```bash
curl -X POST "$BASE/ask" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
# {"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","cost_usd":1.035e-05}
```

### Rate limit (10 request / 60 giây cho mỗi API key)

```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "req $i -> %{http_code}\n" -X POST "$BASE/ask" \
    -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"test"}'
done
```

Kết quả: request 1–8 trả 200, từ request 9 trả 429. Hai request `/ask` chạy ngay trước đó đã nằm trong cùng cửa sổ 60 giây, nên request thứ 9 là request thứ 11 trong cửa sổ.

## Environment Variables Set

Tất cả đặt trên Render qua `render.yaml`, không ghi trong code:

| Biến | Giá trị / nguồn |
|---|---|
| `AGENT_API_KEY` | `generateValue: true`: Render tự sinh chuỗi ngẫu nhiên, chỉ xem được trong tab Environment |
| `REDIS_URL` | `fromService` → `connectionString` của Key Value `agent-redis` (URL nội bộ) |
| `ENVIRONMENT` | `production` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |
| `MONTHLY_BUDGET_USD` | `10.0` |
| `PORT` | Render tự cấp. `CMD` trong Dockerfile lắng nghe `${PORT:-8000}` |
| `LOG_LEVEL` | Không đặt, dùng mặc định `INFO` trong `app/config.py` |

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
