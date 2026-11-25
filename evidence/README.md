# Evidence — output thô của các lệnh đã chạy (nguồn số liệu để viết report)

| File | Dùng cho |
|---|---|
| `check_production_ready_output.txt` | Part 6 — output đầy đủ `PASS 12/12` (chạy trong container Linux, có Docker). Dán phần "📋 Checklist Deliverable" vào MISSION_ANSWERS |
| `part1-5/part1_outputs.txt` | Exercise 1.2, 1.3 — curl bản develop/production, log develop in lộ secret |
| `part1-5/part2_image_sizes.txt` | Exercise 2.2, 2.3 — kích thước image develop vs advanced |
| `part1-5/part2_run_outputs.txt` | Exercise 2.2, 2.4 — gọi container, stack compose qua Nginx |
| `part1-5/part4_outputs.txt` | Exercise 4.1–4.3 — 401 / 403 / 200 / 429 (token đã che) |
| `part1-5/part5_outputs.txt` | Exercise 5.1–5.5 — health/ready, graceful shutdown (SIGTERM), 3 instance + test_stateless |
| `NUMBERS_SUMMARY.md` | Part 7 — bảng số trích tự động từ `reports/*.json` và `benchmark-results/*.csv` |
| `part7/eval_*_console.txt`, `gate_v1_vs_v2_console.txt` | Exercise 7.3 — output eval, quality gate (exit code 1 khi v1 so với baseline v2) |
| `part7/locust_scale_*_console.txt` | Mục 2.7 — output Locust headless |
| `part7/jaeger_traces_summary.txt` | Exercise 7.5 — span của 1 trace chậm và 1 trace lỗi |
| `part7/trace_log_lines.txt` | Dòng log JSON có cùng `trace_id` với 2 trace trên |
| `part7/alert_timeline.txt`, `prometheus_alerts_api.json` | Exercise 7.6 — mốc thời gian inactive → pending → firing |
| `part7/promtool_test_rules.txt` | Unit test alert rules (SUCCESS) |
| `part3_render_selftest.txt` | Part 3: 4 lệnh CP6 trên URL Render (200/200/401/200) và rate limit 429 (key không in ra) |
| `part7/ex71_metrics.txt` | Exercise 7.1: Counter/Gauge/Histogram và metric mới `agent_question_length_chars` |
| `part7/ex74_prometheus_queries.txt` | Exercise 7.4: p95/avg, req/s theo instance, tokens/s, `curl :8080/metrics` → 404 |
| `part7/screenshot_traces.txt` | Span và log của trace chậm `e3ab584e…` và trace lỗi `58ed196e…` trong ảnh Jaeger |
| `part7/prometheus_alerts_api_screenshot.json` | Trạng thái alert lúc chụp `prometheus-alert-firing.png` |
| `part7/experiment_D_timeline.txt` | Thí nghiệm D: `docker pause` 1 instance → `AgentInstanceDown` firing sau ~45 s |

Ghi chú môi trường:
- Cổng 8000 trên máy đang bận nên app Part 1/4/5 develop chạy ở cổng 8010.
- Grafana của stack Part 7 map ra cổng **3001** (cổng 3000 bận), bằng file override tạm, không sửa `docker-compose.yml`.
