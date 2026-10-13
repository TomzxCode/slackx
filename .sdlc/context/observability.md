<!-- session_link: http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ -->
# Observability

<!--
This file inventories the project's existing observability infrastructure: metrics,
logging, tracing, and alerting. It gives create-observability, audit-observability, and
audit-reliability the context they need without grepping the codebase each time.
Service-level targets (SLOs, SLIs, error budgets) live in service-levels.md.
Update this file when the monitoring stack changes.
-->

## Monitoring Pillars

| Pillar | System | Status |
|---|---|---|
| Metrics | None | Not configured |
| Logging | structlog writing to stderr | In use |
| Tracing | None | Not configured |
| Profiling | None | Not configured |

## Instrumentation Libraries

| Library | Pillar | Configuration |
|---|---|---|
| structlog | Logging | Processors are add_log_level, TimeStamper with iso format, and ConsoleRenderer with colors disabled. Logger factory is PrintLoggerFactory writing to stderr. The bound logger filters by the level from the --log-level flag, which accepts debug, info, warning, error, or critical and defaults to info. |

No metrics library is present: there is no prometheus-client, no OpenMetrics endpoint, and no statsd client.
No tracing library is present: there is no opentelemetry-sdk and no APM agent.
No error reporting library is present: there is no sentry-sdk.
The fake Slack server configures structlog the same way, at an effective info level.

Debug log level adds per-query SQL timings and per-phase timings, which is useful for local performance work.
Storage logs each SQL statement with its duration_ms through the _LoggingCursor and _LoggingConnection wrappers and the _log_sql helper.
The CLI logs each phase duration_ms through the _timed context manager.

## Log Aggregation

There is no central log destination and no retention policy.
structlog emits structured key=value lines to stderr only, so logs are read from the terminal or captured by whatever runs the process.
The one web component, the FastAPI server started by serve, uses the same structlog configuration and writes to the same stderr stream.
No sampling and no filtering beyond the level threshold are applied.

## Tracing

Tracing is not configured.
There is no tracing backend, no sampler, no propagation format, and no service that emits spans.

## Alerting

Alerting is not configured.
There are no alert rules, no alert sources, and no routing to on-call or any other destination.

## Dashboards

Dashboards are not configured.
There is no dashboard and no visualization backend.

## SLO Reference

No `service-levels.md` exists yet, so there are no service-level objectives, indicators, or error budgets to reference.
When that file is added, link it here and use it when creating feature-level observability plans.
