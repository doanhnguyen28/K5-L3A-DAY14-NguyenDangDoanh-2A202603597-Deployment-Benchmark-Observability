# Benchmark & Observability Report — Day 14

**Họ tên:** Nguyen Dang Doanh
**Ngày chạy:** 2026-11-25
**Môi trường:** Laptop Windows 11, Docker Desktop (12 CPU / 11.4 GB RAM cấp cho Docker), Python 3.13 (venv) cho phần develop; stack production chạy bằng Docker Compose.

> Mọi con số dưới đây lấy từ `reports/*.json`, `benchmark-results/*.csv` và các file trong `evidence/part7/`. Bảng tổng hợp tự động: `evidence/NUMBERS_SUMMARY.md`.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | LLM mock mất ~120–180 ms + retrieval ~20 ms, nên request bình thường ~200 ms. 500 ms cho dư hơn 2 lần cho jitter và hàng đợi, nhưng vẫn bắt được tail latency (request chậm thêm 1500 ms). |
| Error rate `/ask` | < 2 % | Upstream LLM mặc định lỗi ~1 % (`MOCK_ERROR_RATE=0.01`). 2 % là gấp đôi mức nền, nên error budget đủ để không báo động vì nhiễu ngẫu nhiên. |
| Accuracy trên golden dataset | ≥ 95 % | Golden dataset có 23 câu, nên 95 % nghĩa là sai tối đa 1 câu. CI quality gate còn chặt hơn: `--min-accuracy 1.0` và không được có regression so với baseline `eval_v2_fixed.json`. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

300 request mỗi lần chạy, agent v2 ở cổng 8002, `MOCK_SLOW_RATE` mặc định (0.03). File: `reports/load_v2_c{1,10,50,100}.json`.

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.95 | 201.9 | 234.4 | 1718.2 | 0.67 % | PASS |
| 10 | 33.59 | 205.1 | 473.3 | 1693.8 | 1.67 % | PASS |
| 50 | 95.28 | 208.1 | 521.6 | 1713.1 | 0.67 % | FAIL (p95 > 500) |
| 100 | 52.35 | 640.0 | 3417.3 | 3852.6 | 1.67 % | FAIL |

**Nhận xét:** RPS không tăng tuyến tính.
- Từ 1 lên 10 lên 50, RPS tăng gần tuyến tính (3.95 → 33.59 → 95.28), vì mỗi request chủ yếu là `await asyncio.sleep` (chờ LLM). Một process uvicorn async có thể chờ song song rất nhiều request, nên p50 gần như giữ nguyên ~200 ms.
- Đến 100, RPS **giảm** còn 52.35 và p50 nhảy lên 640 ms. Lúc này chỉ còn 1 process Python làm tất cả việc tốn CPU: parse JSON, middleware, đo metric, ghi log. Tôi suy luận rằng process này đã bão hoà, request bắt đầu xếp hàng trong event loop, và thời gian chờ hàng đợi cộng vào mọi request, kể cả request nhanh.
- Ở mức 50, p50 vẫn ổn nhưng p95 đã vượt SLO. Đây là điểm bắt đầu bão hoà.
- Muốn tăng throughput phải scale ngang (nhiều process hoặc container), không tăng concurrency trên 1 instance.

### 2.2 Tail latency

300 request, concurrency 20, khởi động lại agent v2 với từng giá trị `MOCK_SLOW_RATE`. File: `reports/load_v2_slow_{0,0.03,0.1}.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 216.8 | 464.2 | 494.7 |
| 0.03 (mặc định) | 238.9 | 469.0 | 1693.1 |
| 0.1 | 384.4 | 1705.8 | 1729.2 |

**Nhận xét:** **p99 nhạy nhất**.
- Từ 0 lên 0.03: p99 tăng từ 495 lên 1693 ms (×3.4), trong khi avg chỉ tăng 22 ms (+10 %) và p95 gần như không đổi. 3 % request chậm nằm hết trong 1 % cuối, nên chỉ p99 thấy được.
- Từ 0.03 lên 0.1: 10 % request chậm vượt qua ngưỡng 5 %, nên đến lượt p95 nhảy từ 469 lên 1706 ms. avg vẫn chỉ tăng lên 384 ms.
- avg là trung bình cộng, nên vài request chậm 1.7 s bị hàng trăm request 200 ms "pha loãng". Nhìn avg 239 ms thì tưởng hệ thống ổn, trong khi cứ 100 người dùng có 3 người phải chờ gần 2 giây.
- Vì vậy SLO nên đặt theo p95 hoặc p99, là trải nghiệm của nhóm người dùng tệ nhất, chứ không theo average.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Golden dataset 23 câu. File: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3 % (1/23) | 91.3 % (21/23) | 100 % (23/23) |
| Avg tokens / câu | 56.7 | 109.0 | 116.0 |
| Tổng cost (USD) | 0.000399 | 0.000760 | 0.000811 |
| Cost / câu đúng (USD) | 0.00039915 | 0.00003619 | 0.00003527 |
| Quality gate | FAIL (`min_accuracy` 0.8) | PASS (`min_accuracy` 0.8) | PASS (`min_accuracy` 1.0, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 | `token`, `hết hạn`, `chữ ký` | Thêm vào `KNOWLEDGE_BASE` 1 tài liệu với từ khoá `["jwt", "api key", "xác thực"]`. Nội dung: JWT là token có chữ ký số, chứa claims và thời điểm hết hạn (exp). API key là chuỗi cố định, không tự hết hạn. |
| scaling-03 | `cpu`, `memory`, `custom metrics` | Thêm tài liệu với từ khoá `["kubernetes", "hpa", "autoscal"]`. Nội dung: HPA tự scale số pod theo CPU utilization, memory hoặc custom metrics. |

Sửa ở cả `develop/utils/mock_llm.py` và `production/utils/mock_llm.py`. Không sửa `golden_dataset.jsonl`. Sau khi sửa, chạy lại eval với `--baseline reports/eval_v2.json`: 23/23, 0 câu regression.

**Quality gate trong CI:** file `.github/workflows/eval-quality-gate.yml` chạy khi có PR sửa `develop/`. Job bật agent v2, sau đó chạy:

```
run_eval.py --min-accuracy 1.0 --baseline reports/eval_v2_fixed.json
```

`run_eval.py` trả **exit code 1** khi accuracy dưới ngưỡng hoặc có câu regression. Step fail kéo theo job fail. Khi bật "Require status checks to pass" cho nhánh `main`, PR không merge được. Đã kiểm thử bằng cách chạy eval v1 với baseline v2: gate báo ❌ FAIL, 20 câu regression, exit code 1 (`evidence/part7/gate_v1_vs_v2_console.txt`).

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- v2 thêm bước retrieval nên prompt dài gấp đôi (109 so với 57 token/câu). Tổng cost tăng khoảng 1.9 lần, latency tăng thêm khoảng 20 ms cho bước tìm tài liệu.
- Đổi lại, accuracy tăng từ 4 % lên 91 %, rồi 100 %.
- Chỉ số đúng để so sánh là **cost / câu đúng**: v2 rẻ hơn v1 khoảng **11 lần** ($0.000036 so với $0.000399), vì v1 tốn tiền cho 22 câu trả lời vô dụng.
- p95 của v1 trong eval (1498.6 ms) cao hơn v2 (234 ms) chỉ là do ngẫu nhiên: 2/23 câu của v1 dính tail latency của mock. Không phải v1 chậm hơn về bản chất.
- Kết luận: thêm token để có ngữ cảnh đáng giá khi đo theo chi phí trên kết quả đúng, không theo chi phí trên request.

---

## 4. Observability stack (production)

Stack: 3 instance agent sau Nginx, Prometheus, Grafana (map ra cổng **3001** vì cổng 3000 trên máy đã bận), Jaeger, Locust.

### 4.1 Screenshot

Các ảnh chụp lúc 2026-11-25 ~11:02Z, khi Locust chạy 30 users và đang bật chaos (`MOCK_SLOW_RATE=0.3`, `MOCK_ERROR_RATE=0.2`):

- [x] Dashboard Grafana khi đang có tải: [screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png). Traffic 15.4 req/s, Error rate 21.39 %, Latency p95 1.89 s, Saturation 10 in-flight, 3 instance up.
- [x] Một trace chậm trong Jaeger: [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png). Span `chat mock-llm-small` chiếm 1.7 s trên tổng 1.7 s.
- [x] Một trace lỗi trong Jaeger: [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png). HTTP 503, event `exception` kèm `exception.type = utils.mock_llm.LLMError`.
- [x] Trang Alerts của Prometheus: [screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png). `AgentHighErrorRate` và `AgentHighLatencyP95` đều đang **FIRING**.

### 4.1b Trả lời Exercise 7.1 và 7.4

**Exercise 7.1**

Output: `evidence/part7/ex71_metrics.txt`.
- Counter: `http_requests_total{method="POST",route="/ask",status="200"} 1.0` (chỉ tăng).
- Gauge: `agent_in_flight_requests 0.0` (lên xuống theo số request đang xử lý).
- Histogram: `http_request_duration_seconds_bucket / _count / _sum{route="/ask"}`.

Nếu dùng `request.url.path` làm label, mỗi URL lạ mà bot quét (`/wp-admin`, `/.env`, `/a1b2c3`…) tạo ra một time series mới. Hậu quả:
- Cardinality tăng không giới hạn, Prometheus tốn RAM và ổ đĩa đến mức có thể sập.
- Các query `sum by (route)` trở nên vô nghĩa.

Dùng `route.path` (template route) hoặc gán `unmatched` thì số giá trị label luôn cố định.

Đã thêm `agent_question_length_chars` dạng Histogram (bucket 20 … 2000 ký tự) vào `develop/app.py`. Kiểm tra: một câu 40 ký tự rơi vào bucket `le="50"`, `_sum = 40`.

**Exercise 7.4**

Truy vấn Prometheus lúc 11:01:03Z: `evidence/part7/ex74_prometheus_queries.txt`. Điều kiện: 30 users, 3 instance, đang chaos.

1. **p95 và avg:** p95 `/ask` = **1.90 s**, avg = **0.58 s**. p95 gấp 3.3 lần avg, nghĩa là phân bố latency lệch rất mạnh về đuôi. Phần lớn request nhanh (~200 ms), nhưng một nhóm đáng kể (30 % slow rate) chậm thêm 1.5 s. avg không cho thấy nhóm này.
2. **Requests/s theo instance:** 5.80, 5.82 và 5.76 req/s. Nginx chia gần như **đều tuyệt đối** cho 3 instance (lệch dưới 1 %), đúng với round-robin. Stack mặc định có 2 instance; khi chụp tôi đang chạy `--scale agent=3`.
3. **Input tokens/s lớn hơn output tokens/s** (974 so với 515 tok/s): input gồm system prompt, tài liệu retrieve được và câu hỏi. Output chỉ là câu trả lời ngắn. Với RAG, prompt luôn dài hơn câu trả lời. Giá output đắt hơn giá input 4 lần, nên vẫn phải theo dõi cả hai.
4. **`curl http://localhost:8080/metrics` trả `404 Not Found` từ Nginx:** cấu hình Nginx có `location = /metrics { return 404; }`. `/metrics` chỉ dành cho Prometheus scrape trực tiếp từng agent trong mạng nội bộ Docker. Không public ra ngoài vì metric lộ route, lưu lượng và thông tin hệ thống. Hơn nữa, qua load balancer thì mỗi lần scrape trúng một instance khác nhau, số liệu sẽ sai.

### 4.2 Thí nghiệm "phá hệ thống"

Locust chạy 30 users (ramp 5) trong suốt các thí nghiệm. Alert rules: `AgentHighErrorRate` (5xx > 5 %, `for: 1m`), `AgentHighLatencyP95` (p95 > 1 s, `for: 2m`), `AgentInstanceDown` (`up == 0`, `for: 30s`), `LLMCostBurnRateHigh` (> $2/giờ, `for: 2m`).

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | Đổi lúc 08:15:22Z, pending lúc 08:15:42 (~20 s), **firing ~80 s** (08:16:42; lần kiểm tra 08:16:49 thấy firing) | Error rate (stat chuyển đỏ ~20 %), Requests/s theo status code (đường 503) |
| B | `MOCK_SLOW_RATE=0.3` (đổi cùng lúc với A) | `AgentHighLatencyP95` | pending ~20 s, **firing ~140 s** (08:17:42) | Latency /ask p50/p95/p99 (p95 và p99 vọt lên ~1.9 s, avg chỉ ~0.6 s) |
| C | `LLM_MODEL=mock-llm-large` | Không thực hiện | — | — |
| D | `docker pause k5-day14-observability-agent-1` | `AgentInstanceDown` (instance 172.19.0.2:8000) | Pause lúc 11:15:15Z, pending sau 15 s, **firing sau ~45 s** (11:16:00) | Instances up (3 → 2). Locust thấy lỗi 504 Gateway Time-out ở Nginx, nhưng Error rate của agent không đổi |
| E | `AGENT_VERSION=v1` | Không thực hiện trên stack (đã đo bằng eval ở mục 3) | — | — |

Ghi chú:
- A và B được áp dụng cùng lúc: sửa `.env`, rồi `docker compose up -d --scale agent=3`. Timeline: `evidence/part7/alert_timeline.txt`.
- Lần chụp ảnh lúc 11:00 lặp lại đúng hành vi này: `AgentHighErrorRate` active lúc 10:59:57 và firing trong khoảng 11:01; `AgentHighLatencyP95` firing lúc 11:02:09.
- Thời gian tới lúc firing = thời gian để rate trong cửa sổ `[1m]` vượt ngưỡng (~20 s) + khoảng `for:` của rule (1 phút cho error, 2 phút cho latency). Đặt `for:` để tránh báo động vì spike ngắn, đổi lại là chậm phát hiện hơn.
- D: timeline ở `evidence/part7/experiment_D_timeline.txt`. Request tới instance bị pause bị Nginx giữ đến timeout. Lỗi chỉ hiện ở phía Nginx/Locust, còn metric của agent không thấy vì agent bị pause không nhận được request. Đây là lý do cần alert `up == 0` riêng.
- `LLMCostBurnRateHigh` cũng firing trong lúc chạy tải: lần 100 users từ 08:11; lần 30 users đo được $2.37/giờ, vượt ngưỡng $2/giờ. Nguyên nhân là tải liên tục, không phải do thí nghiệm. Ngưỡng $2/giờ hợp với lưu lượng thật hơn là với load test.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Lỗi chất lượng không làm hạ tầng "đỏ": v1 vẫn trả 200, vẫn nhanh, thậm chí còn rẻ hơn. Phải đo trực tiếp **chất lượng**:
1. **Trước deploy:** chạy eval golden dataset làm quality gate trong CI, có baseline và exit code. v1 so với baseline v2 bị chặn với 20 câu regression (mục 3).
2. **Sau deploy:** chạy eval định kỳ (canary eval) vào production và alert khi accuracy giảm.
3. **Proxy metric có thể alert:** retrieval hit ratio giảm về 0, tokens/câu giảm đột ngột, `agent_info{version}` đổi ngoài lịch deploy.
4. **Tín hiệu từ người dùng:** tỉ lệ 👍/👎, hỏi lại, hoặc LLM-as-judge chấm mẫu ngẫu nhiên từ traffic thật.

### 4.3 Debug bằng trace

Trace chậm nhất trong lúc chụp ảnh. Dữ liệu: `evidence/part7/screenshot_traces.txt`.

- `trace_id`: `e3ab584e8953383136ccf531f47aee73`
- Tổng thời gian: 1724.4 ms (span `POST /ask`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (1698.6 ms, **98.5 %**). `agent.retrieve_context` chỉ 23.3 ms (1.4 %).
- Kết luận: chậm là do LLM upstream (request rơi vào nhánh tail latency +1500 ms của mock), không phải do retrieval hay code agent. Muốn giảm thì cần timeout + retry, hedged request, hoặc stream sớm, không cần tối ưu retrieval.
- Dòng log tương ứng (grep theo `trace_id` trong `docker compose logs agent`):

```json
{"ts": "2026-11-25T11:01:40.647561+00:00", "level": "INFO", "service": "observable-agent", "instance": "99d126011515", "event": "llm_call", "trace_id": "e3ab584e8953383136ccf531f47aee73", "span_id": "c7c3aab9fe055193", "request_id": "822073e7836c", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1697.6}
{"ts": "2026-11-25T11:01:40.648125+00:00", "level": "INFO", "service": "observable-agent", "instance": "99d126011515", "event": "http_request", "trace_id": "e3ab584e8953383136ccf531f47aee73", "span_id": "c7c3aab9fe055193", "request_id": "822073e7836c", "method": "POST", "route": "/ask", "status": 200, "ms": 1723.6}
```

Trace lỗi trong ảnh: `58ed196ea62227c1bc23fbcb9b36cf52`, HTTP 503, 847.6 ms. Span `chat mock-llm-small` có status error và event `exception`: `Upstream LLM error: 503 Service Unavailable (mock)`. Log khớp:

```json
{"ts": "2026-11-25T11:02:09.941843+00:00", "level": "INFO", "service": "observable-agent", "instance": "306f41915981", "event": "llm_error", "trace_id": "58ed196ea62227c1bc23fbcb9b36cf52", "span_id": "41552234f999c02a", "request_id": "734420a56604", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Dòng `/ask` trong `benchmark-results/scale_{1,3}_stats.csv`. Chạy với `MOCK_*` mặc định.

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 60.20 | 190 | 230 | 1700 | 83 / 7188 (1.15 %) |
| 3 | 60.16 | 190 | 230 | 1700 | 79 / 7186 (1.10 %) |

**Giải thích kết quả:** Scale lên 3 instance **không cải thiện** p95 hay RPS; hai lần chạy gần như trùng nhau.
- **Throughput do Locust quyết định, không do server.** Mỗi user Locust chờ response rồi nghỉ `wait_time = between(0.5, 2)` (trung bình 1.25 s) mới gửi tiếp. Mỗi vòng ~1.25 s + ~0.24 s response ≈ 1.5 s, nên 100 users chỉ tạo được ~66 req/s tổng (khớp cột Aggregated 66.2 RPS, trong đó 60 RPS là `/ask`). Một instance async vẫn xử lý dư 60 req/s (ở mục 2.1, 1 process đạt 95 RPS ở concurrency 50), nên thêm instance không có việc gì để làm.
- **Latency do LLM upstream quyết định.** p50 190 ms là latency của mock LLM. p99 1700 ms là tail +1500 ms. Thời gian này nằm ở phía "gọi LLM", thêm agent không làm LLM nhanh hơn.
- **Nút thắt là độ trễ của LLM**, cùng với mô hình tải closed-loop của Locust. Scale ngang chỉ có ích khi CPU hoặc event loop của agent bão hoà (như ở concurrency 100 của mục 2.1). Muốn thấy khác biệt phải tăng users hoặc giảm `wait_time` cho đến khi 1 instance bão hoà.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Đo theo percentile, không theo average.** 3 % request chậm làm p99 tăng 3.4 lần trong khi avg chỉ tăng 10 %. SLO, alert và dashboard đều phải dựa trên p95/p99.
  2. **Hạ tầng xanh không có nghĩa là agent đúng.** Lỗi chất lượng (v1 đúng 4 %) không làm metric nào đỏ. Cần eval golden dataset làm quality gate với exit code trong CI, và so sánh với baseline để bắt regression.
  3. **Ba tín hiệu bổ sung cho nhau.** Metric cho biết *có* vấn đề (error rate 20 %). Trace cho biết vấn đề *ở đâu* (98.5 % thời gian ở span LLM). Log cùng `trace_id` cho biết *chi tiết* (model, token, thông báo lỗi). Alert cần `for:` để tránh nhiễu, nên luôn có độ trễ phát hiện (~1–2 phút).
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  - **Alert theo error budget burn rate** (multi-window, ví dụ 1h và 5m), thay cho ngưỡng tĩnh, để vừa nhanh vừa ít báo nhầm.
  - **Metric chất lượng online:** retrieval hit ratio, tỉ lệ câu trả lời rơi vào "generic response", điểm LLM-as-judge trên mẫu traffic. Alert khi giảm.
  - **Budget theo ngày/tháng và theo user** (giống cost guard ở Part 6), alert khi dùng hết 80 % budget. Hiện chỉ có burn rate.
  - **Saturation:** độ dài hàng đợi / in-flight theo instance, CPU và memory của container, alert trước khi p95 vỡ.
  - **Upstream LLM:** tỉ lệ 429/timeout theo provider, và đếm số lần retry hoặc fallback sang model khác.
  - **Blackbox probe** từ bên ngoài vào URL public (`/health`, `/ready`). Khi instance bị pause như thí nghiệm D, metric bên trong agent không thấy lỗi nhưng người dùng vẫn thấy.
