"""OpenTelemetry tracing for the underwriting workflow (lesson 7).

    OTEL_EXPORTER=none (default)   spans are created but go nowhere; near-zero cost
    OTEL_EXPORTER=console          print each finished span as JSON
    OTEL_EXPORTER=otlp             send to OTEL_EXPORTER_OTLP_ENDPOINT (Jaeger, Tempo, …);
                                   needs `uv sync --extra otel`
    `underwriter trace <app>`      an in-memory exporter, printed as a tree

The span tree for one application:

    underwrite APP-002                       application, decision, reason codes
    ├── node income / checks / analyze / …   attempts, outcome (ok, retried, failed)
    │   ├── check credit_bureau              status, required, latency
    │   ├── retrieve                         k, results, abstained
    │   └── chat mock-underwriter-v1         gen_ai.* model and token attributes
    │       └── tool check_policy            outcome
    └── node engine                          recommendation, overridden

Two rules:

1. **No personal data in spans.** Applicant names, ids, emails and addresses never
   become attributes. Traces go to more systems and more people than the audit trail.
2. **Traces aren't the audit.** The audit trail is the business record, kept with the
   decision. Traces are operational telemetry: sampled, short-lived, for engineers.

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/07-observability/SPEC.md; the tests are the answer key.
"""
