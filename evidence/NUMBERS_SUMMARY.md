# Số liệu trích tự động từ reports/ và benchmark-results/ (dùng để điền BENCHMARK_REPORT.md)

## Load test v2 theo concurrency (300 request)

| Concurrency | RPS | Error rate | avg | p50 | p95 | p99 | SLO p95≤500ms & err≤2% |
|---|---|---|---|---|---|---|---|
| 1 | 3.95 | 0.67% | 253.8 | 201.9 | 234.4 | 1718.2 | PASS |
| 10 | 33.59 | 1.67% | 262.1 | 205.1 | 473.3 | 1693.8 | PASS |
| 50 | 95.28 | 0.67% | 299.1 | 208.1 | 521.6 | 1713.1 | FAIL |
| 100 | 52.35 | 1.67% | 1247.9 | 640.0 | 3417.3 | 3852.6 | FAIL |

## MOCK_SLOW_RATE (300 request, concurrency 20)

| MOCK_SLOW_RATE | RPS | Error rate | avg | p50 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|
| 0 | 90.01 | 1.00% | 216.8 | 201.7 | 464.2 | 494.7 | 501.6 |
| 0.03 | 81.54 | 0.67% | 238.9 | 202.9 | 469.0 | 1693.1 | 1972.7 |
| 0.1 | 44.34 | 0.67% | 384.4 | 207.8 | 1705.8 | 1729.2 | 1955.1 |

## Eval

| Report | Version | Accuracy | Đúng/Tổng | Avg tokens | Total cost USD | Cost / câu đúng | p95 ms | Gate |
|---|---|---|---|---|---|---|---|---|
| eval_v1 | v1 | 4.3% | 1/23 | 56.7 | 0.000399 | 0.00039915 | 1498.6 | {'min_accuracy': 0.8, 'regressions': [], 'passed': False} |
| eval_v2 | v2 | 91.3% | 21/23 | 109.0 | 0.00076 | 3.619e-05 | 234.0 | {'min_accuracy': 0.8, 'regressions': [], 'passed': True} |
| eval_v2_fixed | v2 | 100.0% | 23/23 | 116.0 | 0.000811 | 3.527e-05 | 236.2 | {'min_accuracy': 1.0, 'regressions': [], 'passed': True} |

## Locust (100 user, ramp 10/s, 2 phút) — dòng /ask và Aggregated

| Run | Name | Requests | Failures | Fail % | RPS | Avg ms | p50 | p95 | p99 | Max |
|---|---|---|---|---|---|---|---|---|---|---|
| scale_1 | /ask | 7188 | 83 | 1.15% | 60.20 | 237.5 | 190 | 230 | 1700 | 1738 |
| scale_1 | Aggregated | 7907 | 83 | 1.05% | 66.22 | 216.2 | 190 | 230 | 1700 | 1738 |
| scale_3 | /ask | 7186 | 79 | 1.10% | 60.16 | 232.8 | 190 | 230 | 1700 | 1762 |
| scale_3 | Aggregated | 7912 | 79 | 1.00% | 66.24 | 211.7 | 190 | 220 | 1700 | 1762 |
