# django-pyturso performance report

| Case | Median ms | Mean ms | Rounds | Queries | Query cap | Correctness | Timing budget | Timing |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |
| `cursor_insert_1000` | 38.578 | 48.977 | 8 | 1 | 1 | pass | — | observation-only |
| `orm_active_page_500` | 0.463 | 0.464 | 12 | 1 | 1 | pass | 1.000 ms | pass |
