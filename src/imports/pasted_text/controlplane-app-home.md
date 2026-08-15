Refine the existing ControlPlane.ai frontend, but change the information architecture so there is a PRIMARY APPLICATION HOME before entering an individual LLM application.

DO NOT rebuild the visual design from scratch.
Preserve the current dark developer-tool aesthetic, typography, navigation language, workflow graph, node styling, metrics, and inspection panel.

The major change is the hierarchy:

CONTROLPLANE HOME
        ↓
SELECT AN LLM APPLICATION
        ↓
APPLICATION WORKSPACE
        ↓
SELECT A TRACE / RUN
        ↓
INSPECT WORKFLOW GRAPH
        ↓
INSPECT NODE
        ↓
INPUT / OUTPUT / CONTEXT / QUALITY / EVIDENCE

==================================================
1. PRIMARY SCREEN — LLM APPLICATIONS
==================================================

When the user first opens ControlPlane, DO NOT immediately open
Customer Support Agent.

The primary screen should show ALL of the user's LLM applications.

Think of this as the ControlPlane application command center.

Header:

ControlPlane.ai

Applications

[Search applications...]

[Last 24h ▼]

[+ Add Application]

Then show an application grid/list.

Example:

┌─────────────────────────────────────────────────────────────┐
│ Customer Support Agent                         ● Healthy    │
│ Production                                                  │
│                                                             │
│ Reliability       98.7%                                     │
│ Quality           92%                                       │
│ P95 Latency       2.49s                                     │
│ Traces            12.4k                                     │
│                                                             │
│ Last activity: 2 min ago                         [Open →]   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ RAG Knowledge Assistant                       ● Warning     │
│ Production                                                  │
│                                                             │
│ Reliability       94.2%                                     │
│ Quality           84%                                       │
│ P95 Latency       3.81s                                     │
│ Traces            8.2k                                      │
│                                                             │
│ Last activity: 5 min ago                         [Open →]   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Sales Copilot                                  ● Healthy    │
│ Staging                                                     │
│                                                             │
│ Reliability       99.1%                                     │
│ Quality           96%                                       │
│ P95 Latency       1.72s                                     │
│ Traces            3.1k                                      │
│                                                             │
│ Last activity: 8 min ago                         [Open →]   │
└─────────────────────────────────────────────────────────────┘

The user should be able to scan ALL applications and immediately
understand which applications are healthy and which need attention.

==================================================
2. APPLICATION CARDS
==================================================

Each LLM application should communicate health at a glance.

Show:

Application name
Environment
Health status
Reliability
Quality
Latency
Trace volume
Open recommendations
Last activity

For example:

Customer Support Agent
Production

● Healthy

Reliability     98.7%
Quality         92%
P95             2.49s
Open Issues     0
12.4k traces

Do not make the cards excessively large.

The page should support many applications.

For 20+ applications, the UI should remain usable.

Provide:

Search
Sort
Filter
Grid/List toggle

Filters:

All
Healthy
Warning
Critical
Production
Staging

==================================================
3. APPLICATION HEALTH
==================================================

The application home should immediately answer:

"Which of my AI applications need attention?"

Use subtle status indicators.

Healthy
Warning
Critical

Do NOT make everything colorful.

Use color primarily for status.

Example:

● Healthy
● Warning
● Critical

The primary visual signal should be reliability and quality.

==================================================
4. APPLICATION CLICK
==================================================

When the user clicks:

Customer Support Agent

transition into that application's workspace.

The application workspace should feel like entering a dedicated
observability environment for that AI application.

Header:

← Applications

Customer Support Agent
Production

Health ● 98.7%

[Last 24h ▼]
[Refresh]

==================================================
5. APPLICATION WORKSPACE
==================================================

Inside the selected application, show:

Overview
Traces
Analytics
Reliability
Quality
Cost
Safety

These views are scoped ONLY to the selected application.

Do not lose the selected application context.

The header should always make it obvious:

Customer Support Agent
Production

==================================================
6. APPLICATION OVERVIEW
==================================================

The overview should show:

Reliability
Quality
Latency
Usage
Cost
Safety

Then:

Recent Traces

and:

Workflow / Architecture

But distinguish between the APPLICATION workflow and an individual
TRACE.

The application workflow is the general structure.

A trace is one actual execution.

==================================================
7. TRACE SELECTION
==================================================

Show recent executions:

Recent Runs

● 2 min ago
Trace 6144cfc0...
Success
Quality 90%
2.49s

● 5 min ago
Trace 34120a22...
Success
Quality 86%
2.31s

● 8 min ago
Trace b873ca78...
Warning
Quality 72%
4.81s

Clicking a trace opens the trace investigation view.

==================================================
8. TRACE INVESTIGATION VIEW
==================================================

This is where the existing design becomes the main experience.

Layout:

LEFT
Trace/run list

CENTER
Interactive workflow graph

RIGHT
Node inspector

The graph is the visual hero.

Example:

                    Agent
                      │
                      ▼
                  Retrieval
                      │
                      ▼
                    OpenAI
                      │
                      ▼
                 Post Process

The graph represents the ACTUAL execution trace.

==================================================
9. GRAPH — INFORMATION BEFORE CLICKING
==================================================

Before selecting any node, the user should already see:

Node name
Node type
Status
Latency
Warnings
Errors

Example:

┌───────────────────────┐
│ OpenAI           ●    │
│ LLM                   │
│ gpt-4.1-mini          │
│ 2.488s                │
└───────────────────────┘

If the node has a quality problem:

┌───────────────────────┐
│ OpenAI           ⚠    │
│ LLM                   │
│ gpt-4.1-mini          │
│ 2.488s                │
│ Grounding 75%         │
└───────────────────────┘

The user should NOT need to click every node to understand
the workflow's health.

==================================================
10. NODE INSPECTION
==================================================

Clicking a node opens the right inspector.

Do NOT hide the graph.

The right panel should show:

OPENAI

✓ Success

Model
gpt-4.1-mini

Latency
2,488 ms

Input
"What is artificial intelligence?"

Context
"Artificial intelligence is..."

Output
"Artificial intelligence refers to..."

Then:

Quality

Grounding 75%
Relevance 100%
Safety 100%

Tabs:

Overview
Input
Context
Output
Quality
Metadata

==================================================
11. TRACE-LEVEL RELIABILITY
==================================================

At the trace level show:

Overall Quality
90%

Reliability
98.7%

Latency
2.49s

P95
...

Safety
100%

Grounding
90%

Relevance
100%

Hallucination Risk
Low

These should be visible WITHOUT requiring node selection.

==================================================
12. SHADOW
==================================================

Shadow is the AI quality/control layer.

Show:

SHADOW QUALITY

Overall
90% Excellent

Grounding
75% Good

Relevance
100% Excellent

Completeness
85% Good

Flow Accuracy
100% Excellent

Safety
100% Safe

Hallucination Risk
Medium

If there are recommendations:

⚠ Grounding
Medium

Avoid unsupported claims beyond supplied context

Problem
...

Evidence
...

Recommendation
...

Confidence
90%

==================================================
13. EVIDENCE → GRAPH CONNECTION
==================================================

This interaction is extremely important.

If a recommendation references a span/node:

clicking the evidence should:

1. Highlight the relevant graph node.
2. Focus the graph on that node if necessary.
3. Open the node inspector.
4. Open the relevant Input / Output / Context section.
5. Highlight the relevant evidence.

The user should be able to go:

Problem
↓
Evidence
↓
Node
↓
Input / Context / Output
↓
Fix

==================================================
14. APPLICATION-LEVEL ANALYTICS
==================================================

At the application level provide:

Reliability
- success rate
- error rate
- failed traces

Latency
- average
- P50
- P95
- P99

Quality
- Shadow overall
- grounding
- relevance
- completeness
- safety
- hallucination risk

Usage
- traces
- LLM calls
- tokens
- estimated cost

Recommendations
- total
- critical
- high
- medium
- low

Charts should be compact and useful.

==================================================
15. APPLICATION COMPARISON
==================================================

The PRIMARY applications page should make comparison easy.

The user should be able to visually compare:

Application
Health
Reliability
Quality
P95 latency
Cost
Open issues
Last activity

Example:

Application             Reliability   Quality   P95     Issues

Customer Support        98.7%         92%       2.49s   0
RAG Assistant            94.2%         84%       3.81s   4
Sales Copilot            99.1%         96%       1.72s   0
Document Analyzer        91.8%         79%       4.21s   7

This is one of the most important screens in ControlPlane.

The user should immediately know:

"Which AI application needs my attention?"

==================================================
16. NAVIGATION HIERARCHY
==================================================

The navigation should communicate:

ControlPlane
│
├── Applications
│
│   ├── Customer Support Agent
│   │   ├── Overview
│   │   ├── Traces
│   │   ├── Analytics
│   │   ├── Reliability
│   │   ├── Quality
│   │   ├── Cost
│   │   └── Safety
│   │
│   ├── RAG Knowledge Assistant
│   │   ├── Overview
│   │   ├── Traces
│   │   └── ...
│   │
│   └── Sales Copilot
│       └── ...
│
└── Settings

The user should never lose track of which application they are
currently investigating.

==================================================
17. BACKEND
==================================================

The existing backend is:

http://127.0.0.1:8000

Do NOT create a fake backend.

Use the existing API.

Important endpoints:

GET /traces
GET /traces/{trace_id}
GET /traces/{trace_id}/detail
GET /traces/{trace_id}/insights
GET /analytics/overview
GET /analytics
GET /analytics/bottlenecks

The application/project selection should be implemented as a
frontend concept using the trace/application information available
from the backend.

Do NOT fabricate metrics when the API does not provide them.

If data is unavailable, display:

N/A

rather than fake values.

==================================================
18. DESIGN PRINCIPLE
==================================================

The PRIMARY SCREEN is NOT the workflow graph.

The PRIMARY SCREEN is:

"Here are all of my AI applications.
Which ones are healthy?
Which ones need attention?"

Then:

"I selected an application.
Show me everything about it."

Then:

"I selected a trace.
Show me exactly how it executed."

Then:

"I selected a node.
Show me exactly what went into it and what came out."

Then:

"Something is wrong.
Show me the evidence and tell me what to fix."

This hierarchy is the central product experience.

==================================================
19. FINAL USER JOURNEY
==================================================

User opens ControlPlane

↓

APPLICATIONS

Customer Support Agent       98.7%   Healthy
RAG Assistant                 94.2%   Warning
Sales Copilot                 99.1%   Healthy
Document Analyzer             91.8%   Critical

↓

User clicks:

RAG Knowledge Assistant

↓

APPLICATION WORKSPACE

RAG Knowledge Assistant
Production

Reliability 94.2%
Quality 84%
P95 3.81s
7 open issues

↓

User selects a trace

↓

TRACE INVESTIGATION

LEFT
Recent runs

CENTER
Workflow graph

RIGHT
Node inspector

↓

User clicks OpenAI

↓

Input
Context
Output
Latency
Model
Quality

↓

Shadow says:

⚠ Grounding
Medium

↓

User opens evidence

↓

Relevant output is highlighted

↓

Graph highlights OpenAI node

↓

User understands exactly what happened.

==================================================
FINAL INSTRUCTION
==================================================

Refine the current design to support this TWO-LEVEL experience:

LEVEL 1:
ControlPlane Applications — choose between multiple LLM applications.

LEVEL 2:
Selected Application — inspect reliability, traces, workflow,
nodes, quality, evidence, and recommendations.

Do NOT flatten these into one screen.

The application selection screen and the trace investigation screen
should feel like two distinct but connected experiences.

Preserve the existing design language and workflow graph.

Make the result feel like a serious production control plane for
teams operating multiple AI applications.