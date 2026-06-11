# AShare Worker

Python worker for AShare data collection and stock research report generation.

## Stock Report CLI

```bash
python3 -m ashare_worker.report_cli --code 002837
```

The command prints a UTF-8 JSON payload compatible with the Spring Boot
`StockReportContent` DTO. The Java backend calls this worker and persists the
result in MySQL.
