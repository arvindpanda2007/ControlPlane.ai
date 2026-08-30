ControlPlane.ai
AI Application Observability, Evaluation and Safety Control Plane
ControlPlane.ai is a lightweight observability and evaluation layer for LLM applications. It sits between an AI application and its model/runtime layer to capture application runs and model traces, measure latency and estimated cost, record safety interventions, and evaluate response factuality asynchronously through a shadow-evaluation pipeline.
The project is designed around a practical production constraint: expensive or slow evaluation should not block the user-facing response. ControlPlane.ai therefore separates runtime telemetry and safety controls from asynchronous evaluation, giving engineering teams a single place to understand reliability, quality, latency, cost, and safety signals.
Repository: https://github.com/arvindpanda2007/ControlPlane.ai
---
Table of contents
Problem statement
Solution overview
Key objectives
Core features
Architecture
End-to-end workflow
Technology stack
Repository structure
Data model
API design
SDK design
Dashboard and analytics
Installation and setup
Running the system
Example integration
Testing
Design decisions and trade-offs
Security and responsible AI
Limitations
Future roadmap
Competition impact
Team contribution
Conclusion
---
1. Problem statement
Teams building LLM-powered applications often have visibility into infrastructure metrics but limited visibility into the quality and safety of individual AI responses.
A production response can fail in several ways:
It can be factually unsupported or partially supported.
It can be slow even when the application appears healthy.
It can consume more tokens and cost more than expected.
It can trigger a safety intervention.
A workflow can fail while the underlying model traces contain the information needed to diagnose the failure.
Traditional logging can tell a team what happened, but not necessarily whether the model response was well supported.
The project's product requirements describe this gap as the need for a lightweight layer that watches production responses and provides fast visibility into correctness/quality, efficiency, and responsibility/safety.
---
2. Solution overview
ControlPlane.ai provides three connected layers:
A. Instrumentation and SDK
The Python SDK provides reusable building blocks for:
application/run tracking
model tracing
cost estimation
prompt-injection checks
safety handling
OpenAI integration
shadow evaluation
The SDK is intended to be integrated into an existing AI application rather than forcing the application to be rebuilt around ControlPlane.ai.
B. ControlPlane API and persistence
A Python API service exposes resources for:
applications
runs
traces
trace insights
health checks
The API persists operational telemetry in PostgreSQL. Runs contain the workflow-level lifecycle, while traces capture individual model/runtime events and can form parent-child relationships.
C. Web dashboard
The React/Vite frontend aggregates the stored telemetry into application-level views. It calculates and displays operational signals such as:
reliability
quality
p95 latency
average latency
total estimated cost
safety flags
shadow-evaluation results
This gives engineers a response-level investigation path as well as an application-level health view.
---
3. Key objectives
ControlPlane.ai is built around the following objectives:
Observe every important AI workflow
Capture application runs and model traces.
Preserve input, output, context and runtime metadata.
Measure operational efficiency
Track token usage.
Track latency.
Estimate model cost.
Surface safety events
Record safety flags, safety type and safety action.
Keep safety interventions visible even when they cause the owning workflow to fail.
Evaluate quality asynchronously
Run factuality evaluation after the main application execution.
Store supported/partial/unsupported evaluation outcomes.
Provide actionable visibility
Move from aggregate health signals to individual traces and their child events.
Expose the evidence required to investigate a response.
---
4. Core features
4.1 Application and run tracking
Applications are first-class resources in the API. Each application can have multiple runs.
A run stores workflow-level information such as:
input
context
output
status
start/end timestamps
latency
application association
Supported lifecycle statuses include:
`pending`
`running`
`success`
`error`
`blocked`
4.2 Hierarchical tracing
A run can contain multiple traces. Traces support `parent_trace_id`, allowing ControlPlane.ai to represent nested model calls, evaluation calls and safety interventions.
This makes it possible to reconstruct a workflow rather than treating every model call as an isolated log line.
4.3 Token and cost tracking
Trace records include:
input tokens
output tokens
estimated cost in USD
provider
model
latency
The dashboard aggregates child traces so that application-level cost and token metrics can still be displayed when the root trace does not contain the complete values.
4.4 Safety intervention tracking
Trace records can persist:
safety flag
safety type
safety action
The frontend explicitly distinguishes safety-intervention traces from ordinary application errors. This prevents a blocked/safety-affected workflow from being interpreted simply as a generic application failure.
4.5 Shadow evaluation
ControlPlane.ai includes a shadow evaluation path designed to avoid blocking the main user response.
Shadow evaluation results include:
evaluation status
factuality score
factuality status
evaluation timestamp
evaluation error
model/provider metadata
token and cost metadata
The current evaluation model supports factuality states such as:
supported
partially supported
unsupported
The dashboard uses these results to calculate aggregate shadow-evaluation counts and quality signals.
4.6 Trace insights
The API provides a trace-insights endpoint that combines:
trace metadata
span timing information
shadow-evaluation results
This creates a single investigation surface for a trace.
4.7 Application health model
The frontend derives an application health state from observed signals. The current implementation uses reliability, quality and safety flags to classify an application as:
healthy
warning
critical
The health calculation is intentionally derived from observable application telemetry rather than being a manually assigned status.
---
5. Architecture
High-level architecture
```text
                   ┌──────────────────────────────┐
                   │        AI Application         │
                   │  Chatbot / Agent / Copilot   │
                   └──────────────┬───────────────┘
                                  │
                                  ▼
                   ┌──────────────────────────────┐
                   │     ControlPlane.ai SDK       │
                   │                              │
                   │ Trace │ Cost │ Safety        │
                   │ Injection │ OpenAI │ Shadow  │
                   └──────────────┬───────────────┘
                                  │
                                  ▼
                   ┌──────────────────────────────┐
                   │       ControlPlane API        │
                   │           FastAPI             │
                   │                              │
                   │ Applications │ Runs │ Traces │
                   │ Trace Insights │ Health      │
                   └──────────────┬───────────────┘
                                  │
                                  ▼
                   ┌──────────────────────────────┐
                   │          PostgreSQL           │
                   │                              │
                   │ applications │ runs          │
                   │ traces │ spans │ evaluations │
                   └──────────────┬───────────────┘
                                  │
                     ┌────────────┴─────────────┐
                     │                          │
                     ▼                          ▼
          ┌─────────────────────┐     ┌────────────────────┐
          │ Shadow Worker /     │     │ React + Vite        │
          │ Evaluator           │     │ Dashboard            │
          │                     │     │                     │
          │ Async factuality    │     │ Health / Cost /     │
          │ evaluation          │     │ Latency / Safety    │
          └─────────────────────┘     └────────────────────┘
```
Architecture principles
Separation of concerns: instrumentation, API persistence, evaluation and visualization are separate components.
Asynchronous evaluation: expensive factuality evaluation is persisted as a shadow result instead of becoming part of the critical response path.
Trace hierarchy: parent-child traces preserve workflow structure.
Evidence-first debugging: application health is backed by stored runs/traces/evaluations that can be inspected individually.
---
6. End-to-end workflow
A typical request flows through the system as follows:
An AI application starts a workflow.
ControlPlane.ai creates or associates the workflow with an application.
A run is created and begins in a lifecycle state such as `pending`.
The SDK captures model/runtime information as traces.
Each trace can record provider, model, input/output, tokens, latency, cost and safety metadata.
Child traces can represent nested model calls or evaluation/safety activity.
The API persists the records in PostgreSQL.
After a successful application run, the shadow worker can evaluate the response.
Shadow results are stored separately from the main trace.
The dashboard retrieves applications, runs and traces and derives application-level health.
Engineers can move from an aggregate application view into individual traces and shadow-evaluation evidence.
---
7. Technology stack
Layer	Technology
Frontend	React 18 + TypeScript
Frontend tooling	Vite
UI	Tailwind CSS, shadcn-style components, Lucide icons
Charts	Recharts
Backend API	Python / FastAPI
Database	PostgreSQL 16
Database driver	psycopg
SDK	Python
Model integration	OpenAI integration module
Containerization	Docker Compose
Testing	Python test scripts
The frontend dependencies also include React Router, React Hook Form, Motion, Sonner and other UI utilities.
---
8. Repository structure
```text
ControlPlane.ai/
│
├── api/
│   ├── api.py
│   ├── database.py
│   └── __init__.py
│
├── sdk/
│   ├── pyproject.toml
│   └── controlplane/
│       ├── client.py
│       ├── cost.py
│       ├── injection.py
│       ├── openai.py
│       ├── safety.py
│       ├── trace.py
│       └── shadow/
│           ├── evaluator.py
│           └── worker.py
│
├── src/
│   ├── app/
│   │   └── App.tsx
│   ├── imports/
│   ├── styles/
│   ├── index.ts
│   └── main.tsx
│
├── tables/
│   └── traces.sql
│
├── guidelines/
│   ├── Guidelines.md
│   ├── components.md
│   ├── setup.md
│   ├── styles.md
│   └── tokens.md
│
├── prd
├── docker-compose.yml
├── package.json
├── package-lock.json
├── requirements.txt
├── test_workflow.py
├── test_complex_workflow.py
└── test_weather_agent.py
```
---
9. Data model
The core persistence model is organized around an application → run → trace hierarchy.
Applications
Represents an AI application being monitored.
Key fields include:
id
name
created_at
Runs
Represents an execution/workflow under an application.
Key fields include:
id
application_id
input
context
output
status
created_at
started_at
ended_at
latency_ms
Traces
Represents an individual operation within a run.
Key fields include:
id
run_id
parent_trace_id
provider
model
input
output
input_tokens
output_tokens
latency_ms
estimated_cost_usd
context
status
safety_flag
safety_type
safety_action
started_at
ended_at
created_at
Shadow evaluations
Stores asynchronous quality/factuality evaluation results associated with traces.
Key fields exposed by the API include:
trace_id
status
factuality_score
factuality_status
evaluated_at
error
provider
model
token metadata
latency
estimated cost
---
10. API design
The API exposes a small resource-oriented surface.
Health
```http
GET /health
```
Returns the service health status.
Applications
```http
POST /applications
GET  /applications
GET  /applications/{application_id}
```
Runs
```http
POST  /applications/{application_id}/runs
GET   /applications/{application_id}/runs
GET   /runs/{run_id}
PATCH /runs/{run_id}
```
Traces
```http
POST /runs/{run_id}/traces
GET  /runs/{run_id}/traces
GET  /traces/{trace_id}
```
Trace insights
```http
GET /traces/{trace_id}/insights
```
The insights endpoint is particularly important because it combines runtime information with persisted shadow-evaluation evidence.
---
11. SDK design
The SDK is intentionally modular.
`client.py`
Provides the client-side communication layer used to interact with the ControlPlane API.
`trace.py`
Provides tracing functionality and trace lifecycle handling.
`cost.py`
Provides cost-related functionality and model usage accounting.
`injection.py`
Provides prompt-injection-related checks.
`safety.py`
Provides safety handling and intervention-related functionality.
`openai.py`
Provides OpenAI-oriented integration.
`shadow/`
Contains the asynchronous evaluation components:
`evaluator.py` — evaluation logic
`worker.py` — shadow evaluation execution
This structure keeps model-provider integration and evaluation logic separate from the core API.
---
12. Dashboard and analytics
The dashboard converts raw telemetry into application-level operational intelligence.
For each application, the frontend aggregates:
root workflow traces
child traces
safety intervention traces
shadow evaluation results
latency
token usage
estimated cost
Reliability
Reliability is derived from observed run/trace outcomes and is used as one of the main application-health signals.
Quality
Quality incorporates the available shadow-evaluation results. The dashboard distinguishes evaluated results from pending or unavailable results rather than treating missing evaluation data as a successful score.
Latency
The dashboard computes:
average latency
p95 latency
Cost
The dashboard aggregates estimated cost across child traces and uses the most reliable available cost source when constructing a resolved run cost.
Safety
Safety intervention traces are counted separately and can influence application health.
---
13. Installation and setup
Prerequisites
Install:
Git
Node.js
npm
Python 3
Docker Desktop with Docker Compose
Clone the repository
```bash
git clone https://github.com/arvindpanda2007/ControlPlane.ai.git
cd ControlPlane.ai
```
Start PostgreSQL
The repository contains a Docker Compose configuration that starts PostgreSQL 16 and initializes the trace schema from `tables/traces.sql`.
```bash
docker compose up -d
```
The default database configuration in the project is:
```text
Database: controlplane
User:     controlplane
Password: controlplane
Host:     localhost
Port:     5433
```
If a different database configuration is required, set:
```text
DATABASE_URL
```
before starting the API.
Install Python dependencies
```bash
python -m venv .venv
```
Windows:
```bash
.venv\Scripts\activate
```
Linux/macOS:
```bash
source .venv/bin/activate
```
Then:
```bash
pip install -r requirements.txt
```
Install frontend dependencies
```bash
npm install
```
---
14. Running the system
Start the API
The backend is implemented as a FastAPI service in `api/api.py`.
Run it using the project's Python environment and your preferred ASGI server configuration.
Example:
```bash
uvicorn api.api:app --reload
```
Start the frontend
```bash
npm run dev
```
The Vite development server will provide the dashboard locally.
Production frontend build
```bash
npm run build
```
Preview the production build
```bash
npm run preview
```
---
15. Example integration
A simplified integration pattern is:
```python
from controlplane import ControlPlane

cp = ControlPlane(
    api_url="http://localhost:8000"
)

# Register/identify the application,
# create a run, and capture model traces
# through the SDK integration.
```
The exact SDK integration should follow the public interfaces implemented in `sdk/controlplane/`, especially `client.py`, `trace.py`, and the OpenAI integration module.
---
16. Testing
The repository contains workflow-oriented test scripts, including:
```text
test_workflow.py
test_complex_workflow.py
test_weather_agent.py
```
These tests are intended to exercise application workflows and the ControlPlane tracing/evaluation path.
A typical Python test invocation is:
```bash
python test_workflow.py
```
For the full development environment, run the database and API first so that integration-style tests can communicate with the ControlPlane backend.
---
17. Design decisions and trade-offs
Why PostgreSQL?
PostgreSQL provides a simple, queryable relational store for applications, runs, traces and evaluation records. It is appropriate for an MVP where the main requirement is reliable persistence and investigation rather than massive distributed telemetry ingestion.
Why separate runs and traces?
A run represents the business/workflow execution. Traces represent the individual operations inside that workflow. This separation makes it possible to show a user-friendly workflow view while preserving detailed model-level evidence.
Why parent-child traces?
LLM applications frequently make multiple calls. Parent-child relationships preserve the causal structure of those calls and allow the dashboard to aggregate token usage, cost and safety events back to the owning workflow.
Why asynchronous shadow evaluation?
Factuality evaluation can require additional model computation and therefore should not automatically become part of the critical user-facing path. The shadow design allows ControlPlane.ai to provide quality signals without forcing every evaluation to block the original response.
Why treat safety interventions separately?
A safety block is semantically different from an infrastructure failure. The frontend therefore tracks safety intervention traces independently and can classify the owning workflow as safety-affected instead of simply hiding it inside generic errors.
---
18. Security and responsible AI
ControlPlane.ai is designed with responsible AI observability in mind.
The current architecture provides explicit places to record:
safety flags
safety type
safety action
prompt-injection-related checks
response context
evaluation status
factuality results
The system also makes an important distinction between:
blocking/intervention signals, which can affect a workflow, and
shadow evaluation signals, which are primarily diagnostic and arrive asynchronously.
This distinction is important for enterprise use because teams should know whether a signal prevented an action or merely identified a potential problem after execution.
Sensitive production data should be handled according to the deploying organization's data-retention, access-control and privacy requirements.
---
19. Limitations
The current MVP has several deliberate boundaries:
It is not a full RAG/retrieval system.
It does not provide open-domain web fact-checking.
It does not automatically retrain or fine-tune models from flagged data.
Shadow evaluation is not intended to block the original response.
Large-scale production deployment would require additional authentication, authorization, secret management, horizontal scaling, queue durability and observability.
The current PostgreSQL-based persistence layer is appropriate for the MVP but may need a dedicated telemetry architecture at very high volume.
These constraints are intentional and keep the first version focused on useful production visibility.
---
20. Future roadmap
Potential next-stage improvements include:
Webhook/Slack alerting for threshold breaches.
Risk-weighted sampling for shadow evaluations.
Custom evaluation rubrics.
Multi-model comparison and A/B evaluation.
Auto-remediation and safe retry flows.
Open-domain fact-checking where appropriate.
Enterprise authentication and role-based access control.
Distributed background queues for high-volume evaluation.
Advanced PII/secret redaction and retention policies.
Deployment-ready monitoring with metrics, logs and distributed tracing.
Cloud-native scaling and managed database support.
---
21. Competition impact
For the Accenture Reinvent competition, ControlPlane.ai demonstrates a practical approach to making enterprise AI more observable, measurable and governable.
The key value proposition is:
> **Do not just deploy an AI application. Know what it is doing, what it costs, how it performs, when it is unsafe, and whether its responses are supported.**
The solution brings these signals together instead of forcing engineering teams to inspect separate logs, application metrics and evaluation tools.
Enterprise value
Faster incident investigation: traces connect workflow failures to individual operations.
Better AI quality visibility: shadow evaluation surfaces factuality evidence.
Cost awareness: token and estimated-cost telemetry exposes expensive workflows.
Safety awareness: safety interventions are visible as first-class events.
Operational decision-making: application health combines reliability, quality, latency and safety signals.
Low integration friction: the SDK is designed as a layer around an existing AI application.
---
22. Team contribution
ControlPlane.ai is a team-built competition project. Contributions span:
product/problem framing
PRD and solution design
backend/API development
SDK and model integration
tracing and evaluation pipeline
PostgreSQL data layer
frontend/dashboard development
testing and integration
competition presentation and documentation
---
23. Conclusion
ControlPlane.ai provides a focused control plane for production LLM applications.
Its architecture combines:
SDK instrumentation → API persistence → PostgreSQL → shadow evaluation → analytics dashboard
The result is a single operational view of AI application behavior across reliability, quality, latency, cost and safety.
The project deliberately separates fast-path operational controls from slower evaluation workloads, making the architecture practical for real-world AI systems where user-facing latency, evaluation cost and responsible AI requirements must all be considered together.
Repository: https://github.com/arvindpanda2007/ControlPlane.ai
