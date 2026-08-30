import { useState, useEffect, useCallback, useRef } from "react";
import {
Search, Settings, Activity, BarChart2, DollarSign, Shield,
AlertTriangle, ChevronRight, ChevronLeft, X, Plus, Minus,
RefreshCw, ArrowRight, Grid3x3, LayoutList, CheckCircle,
Clock, Cpu, TrendingUp, Loader2, AlertCircle, Command,
XCircle, Zap,
} from "lucide-react";
import {
BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
ResponsiveContainer, PieChart, Pie, Cell,
} from "recharts";
// ─── API ──────────────────────────────────────────────────────────────────────
const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
async function apiGet<T>(path: string): Promise<T> {
const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(10000) });
if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
return res.json() as Promise<T>;
}

async function apiGetTraceDetail(traceId: string): Promise<ApiTraceDetail> {
const [trace, spans] = await Promise.all([
  apiGet<ApiTrace>(`/traces/${traceId}`),
  apiGet<ApiSpan[]>(`/traces/${traceId}/spans`),
]);
return { trace, spans };
}

async function apiGetTraceInsights(traceId: string): Promise<ApiInsights | null> {
try {
  return await apiGet<ApiInsights>(`/traces/${traceId}/insights`);
} catch {
  return null;
}
}
// ─── API Types ────────────────────────────────────────────────────────────────
interface ApiTrace {
id: string;
run_id?: string;
created_at: string;
provider: string;
model: string;
input: string;
output: string | null;
input_tokens: number | null;
output_tokens: number | null;
latency_ms: number | null;
estimated_cost_usd: number | null;
context: string | null;
session_id: string | null;
status: string;
safety_flag: boolean;
safety_type: string | null;
safety_action: string | null;
parent_trace_id: string | null;
factuality_score: number | null;
factuality_status: string | null;
evaluated_at: string | null;
}
interface ApiSpan {
id: string;
trace_id: string;
parent_span_id: string | null;
name: string;
span_type: string;
started_at: string | null;
ended_at: string | null;
duration_ms: number | null;
status: string;
metadata: Record<string, unknown>;
input?: string | null;
output?: string | null;
context?: string | null;
children?: ApiSpan[];
}
interface ApiGraphNode {
id: string;
trace_id?: string;
parent_span_id?: string | null;
name: string;
span_type?: string;
started_at?: string | null;
ended_at?: string | null;
duration_ms?: number | null;
status?: string;
metadata?: Record<string, unknown>;
input?: string | null;
output?: string | null;
context?: string | null;
}
interface ApiGraphEdge {
source: string;
target: string;
type?: string;
}
interface ApiApplication {
id: string;
application_id: string;
name: string;
created_at: string;
run_count: number;
}

interface ApiRun {
id: string;
run_id: string;
application_id: string;
created_at: string;
started_at: string | null;
ended_at: string | null;
latency_ms: number | null;
status: string;
input: string | null;
output: string | null;
context: string | null;
}

interface ApiTraceDetail {
trace: ApiTrace;
spans: ApiSpan[];
child_traces?: ApiTrace[];
graph?: {
root_trace_id?: string;
nodes?: ApiGraphNode[];
edges?: ApiGraphEdge[];
};
}
interface ApiInsights {
trace_id: string;
summary: string;
performance?: {
workflow_latency_ms: number | null;
cost_usd: number | null;
bottleneck?: {
span_id: string;
name: string;
span_type: string;
duration_ms: number;
latency_share: number;
status: string;
};
};
shadow?: {
evaluations: number;
evaluated: number;
average_factuality_score: number | null;
supported: number;
partially_supported: number;
unsupported: number;
pending: number;
};
shadow_evaluations?: Array<{
trace_id: string;
provider?: string;
model?: string;
factuality_score: number | null;
factuality_status: string | null;
input: string;
has_output?: boolean;
context: string | null;
input_tokens?: number | null;
output_tokens?: number | null;
latency_ms: number | null;
estimated_cost_usd: number | null;
status?: string;
evaluated_at?: string | null;
}>;
recommendations: string[];
performance_recommendations?: string[];
quality_recommendations?: string[];
}
interface ApiAnalytics {
overview: {
total_requests: number;
average_latency_ms: number;
total_cost_usd: number;
total_input_tokens: number;
total_output_tokens: number;
successful_requests: number;
error_requests: number;
blocked_requests: number;
};
models: Array<{
provider: string;
model: string;
requests: number;
average_latency_ms: number;
total_cost_usd: number;
input_tokens: number;
output_tokens: number;
}>;
spans: Array<{
span_type: string;
count: number;
average_duration_ms: number;
total_duration_ms: number;
}>;
slowest_spans: Array<{
trace_id: string;
name: string;
span_type: string;
duration_ms: number;
status: string;
}>;
most_expensive_requests: Array<{
trace_id: string;
model: string;
estimated_cost_usd: number;
input_tokens: number;
output_tokens: number;
latency_ms: number;
}>;
}
// ─── Canvas Types ─────────────────────────────────────────────────────────────
type NodeKind = "agent" | "llm" | "retrieval" | "tool" | "database" | "postprocess" | "chain";
type RunStatus = "success" | "warning" | "error" | "running" | "blocked" | "pending";
interface WFNode {
id: string;
name: string;
kind: NodeKind;
model?: string;
duration: number;
status: RunStatus;
x: number;
y: number;
inputTokens?: number;
outputTokens?: number;
cost?: number;
childCount?: number;
input?: string | null;
output?: string | null;
context?: string | null;
// Persisted span ID backing this visual graph node. Graph node IDs can be
// generated independently by the backend, so the inspector uses this ID
// to retrieve the exact per-step input/output.
sourceSpanId?: string;
}
interface WFEdge { from: string; to: string; }
// ─── App State ────────────────────────────────────────────────────────────────
type Screen = "home" | "app" | "trace";
interface AppGroup {
applicationId: string;
name: string;
traces: ApiTrace[];           // Root workflow traces (the actual runs).
reliability: number;
quality: number | null;       // Avg factuality from Shadow child traces.
p95Latency: number | null;
avgLatency: number | null;
totalCost: number;
safetyFlags: number;
// Safety interventions can be child traces of an error root. Keep the
// actual flagged/blocked traces available to the Safety tab.
safetyTraces: ApiTrace[];
lastActivity: string | null;
health: "healthy" | "warning" | "critical";
// Shadow evaluation counts (from child traces).
shadowCounts: { supported: number; partial: number; unsupported: number; pending: number; total: number };
  shadowEvaluations: AppShadowEvaluation[];
}
// ─── Constants ────────────────────────────────────────────────────────────────
const NODE_W = 186;
const NODE_H = 94;
const KIND_COLOR: Record<string, string> = {
agent: "#7c3aed",
llm: "#2563eb",
retrieval: "#16a34a",
tool: "#d97706",
database: "#b45309",
postprocess: "#64748b",
chain: "#9333ea",
};
const DRILLABLE = new Set(["agent", "chain"]);
// ─── Helpers ──────────────────────────────────────────────────────────────────
function flattenSpans(spans: ApiSpan[]): ApiSpan[] {
const flat: ApiSpan[] = [];
function walk(s: ApiSpan) {
flat.push(s);
(s.children || []).forEach(walk);
}
spans.forEach(walk);
return flat;
}
function resolveSpanForGraphNode(
graphNode: ApiGraphNode,
flatSpans: ApiSpan[],
): ApiSpan | undefined {
// 1. Exact ID is the safest mapping.
const exact = flatSpans.find(s => s.id === graphNode.id);
if (exact) return exact;
// 2. Some graph builders keep the originating span ID in metadata.
const meta = graphNode.metadata || {};
const possibleIds = [
meta.span_id,
meta.spanId,
meta.source_span_id,
meta.sourceSpanId,
meta.id,
].filter((v): v is string => typeof v === "string");
for (const id of possibleIds) {
const match = flatSpans.find(s => s.id === id);
if (match) return match;
}
// 3. Match by name + start time. This is important when a workflow has
// repeated node names: name-only matching can attach every node to the
// first span with that name.
const sameName = flatSpans.filter(s => s.name === graphNode.name);
if (sameName.length === 0) return undefined;
if (sameName.length === 1) return sameName[0];
const graphTime = graphNode.started_at
? new Date(graphNode.started_at).getTime()
: null;
if (graphTime != null && Number.isFinite(graphTime)) {
return [...sameName].sort((a, b) => {
const at = a.started_at ? new Date(a.started_at).getTime() : Number.MAX_SAFE_INTEGER;
const bt = b.started_at ? new Date(b.started_at).getTime() : Number.MAX_SAFE_INTEGER;
return Math.abs(at - graphTime) - Math.abs(bt - graphTime);
})[0];
}
return sameName[0];
}
function layoutGraph(detail: ApiTraceDetail | null): { nodes: WFNode[]; edges: WFEdge[] } {
if (!detail) return { nodes: [], edges: [] };
const backendNodes = detail.graph?.nodes;
const backendEdges = detail.graph?.edges;
const flatSpans = flattenSpans(detail.spans || []);
const spanMap = new Map(flatSpans.map(s => [s.id, s]));
const sourceNodes: ApiGraphNode[] = backendNodes?.length
? backendNodes
: flatSpans.map(s => ({
id: s.id,
trace_id: s.trace_id,
parent_span_id: s.parent_span_id,
name: s.name,
span_type: s.span_type,
started_at: s.started_at,
ended_at: s.ended_at,
duration_ms: s.duration_ms,
status: s.status,
metadata: s.metadata,
input: s.input,
output: s.output,
context: s.context,
}));
if (!sourceNodes.length) return { nodes: [], edges: [] };
const nodeMap = new Map(sourceNodes.map(n => [n.id, n]));
const childrenOf = new Map<string, string[]>();
const parentsOf = new Map<string, string[]>();
sourceNodes.forEach(n => {
childrenOf.set(n.id, []);
parentsOf.set(n.id, []);
});
const graphEdges: WFEdge[] = [];
const edgeKeys = new Set<string>();
const addEdge = (from: string, to: string) => {
if (!nodeMap.has(from) || !nodeMap.has(to) || from === to) return;
const key = `${from}->${to}`;
if (edgeKeys.has(key)) return;
edgeKeys.add(key);
graphEdges.push({ from, to });
childrenOf.get(from)!.push(to);
parentsOf.get(to)!.push(from);
};
// Preserve the backend's real topology whenever it is available.
for (const e of (backendEdges || [])) addEdge(e.source, e.target);
// Some traces expose topology only through parent_span_id.
if (!graphEdges.length) {
for (const n of sourceNodes) {
if (n.parent_span_id && nodeMap.has(n.parent_span_id)) {
addEdge(n.parent_span_id, n.id);
}
}
}
// Last-resort chain reconstruction for old telemetry that has no relationships.
if (!graphEdges.length && sourceNodes.length > 1) {
const ordered = [...sourceNodes].sort((a, b) => {
const at = a.started_at ? new Date(a.started_at).getTime() : Number.MAX_SAFE_INTEGER;
const bt = b.started_at ? new Date(b.started_at).getTime() : Number.MAX_SAFE_INTEGER;
return at - bt;
});
for (let i = 1; i < ordered.length; i++) addEdge(ordered[i - 1].id, ordered[i].id);
}
/*

- Layered DAG layout.
-
- Unlike the old "index within level" layout, this:
-
  - keeps every branch on its own lane;
-
  - keeps merge nodes below ALL of their parents;
-
  - orders siblings by the barycenter of their parents/children to reduce
- edge crossings;
-
  - handles disconnected roots;
-
  - does not throw away edges when telemetry contains a cycle.
    */
    const indegree = new Map<string, number>();
    sourceNodes.forEach(n => indegree.set(n.id, parentsOf.get(n.id)!.length));

const rank = new Map<string, number>();
const queue: string[] = [];
sourceNodes.forEach(n => {
if ((indegree.get(n.id) || 0) === 0) {
rank.set(n.id, 0);
queue.push(n.id);
}
});
// Normal DAG ranking.
let head = 0;
while (head < queue.length) {
const id = queue[head++];
const nextRank = (rank.get(id) || 0) + 1;
for (const child of childrenOf.get(id) || []) {
rank.set(child, Math.max(rank.get(child) ?? 0, nextRank));
const nextIn = (indegree.get(child) || 0) - 1;
indegree.set(child, nextIn);
if (nextIn === 0) queue.push(child);
}
}
// Cycle/disconnected fallback: assign unresolved nodes to a stable rank
// rather than allowing NaN/overlapping coordinates.
let maxRank = Math.max(0, ...rank.values());
const unresolved = sourceNodes.filter(n => !rank.has(n.id));
for (const n of unresolved) {
const parentRanks = (parentsOf.get(n.id) || [])
.map(id => rank.get(id))
.filter((v): v is number => v != null);
rank.set(n.id, parentRanks.length ? Math.max(...parentRanks) + 1 : 0);
maxRank = Math.max(maxRank, rank.get(n.id)!);
}
const levels = new Map<number, ApiGraphNode[]>();
for (const n of sourceNodes) {
const r = rank.get(n.id) ?? 0;
if (!levels.has(r)) levels.set(r, []);
levels.get(r)!.push(n);
}
// Stable initial ordering.
for (const ids of levels.values()) {
ids.sort((a, b) => {
const at = a.started_at ? new Date(a.started_at).getTime() : Number.MAX_SAFE_INTEGER;
const bt = b.started_at ? new Date(b.started_at).getTime() : Number.MAX_SAFE_INTEGER;
return at - bt || a.name.localeCompare(b.name) || a.id.localeCompare(b.id);
});
}
// Crossing reduction. A few downward/upward barycenter sweeps make
// fan-outs and fan-ins much easier to follow without a graph library.
const position = new Map<string, number>();
const refreshPositions = () => {
for (const ids of levels.values()) ids.forEach((n, i) => position.set(n.id, i));
};
const barycenter = (id: string, neighbors: string[]) => {
const values = neighbors
.map(n => position.get(n))
.filter((v): v is number => v != null);
if (!values.length) return Number.POSITIVE_INFINITY;
return values.reduce((a, b) => a + b, 0) / values.length;
};
for (let sweep = 0; sweep < 4; sweep++) {
refreshPositions();

const ranks = [...levels.keys()].sort((a, b) => a - b);
for (let i = 1; i < ranks.length; i++) {
  const ids = levels.get(ranks[i])!;
  ids.sort((a, b) =>
    barycenter(a.id, parentsOf.get(a.id) || []) -
    barycenter(b.id, parentsOf.get(b.id) || [])
  );
  refreshPositions();
}

for (let i = ranks.length - 2; i >= 0; i--) {
  const ids = levels.get(ranks[i])!;
  ids.sort((a, b) =>
    barycenter(a.id, childrenOf.get(a.id) || []) -
    barycenter(b.id, childrenOf.get(b.id) || [])
  );
  refreshPositions();
}

}
const HGAP = 82;
const VGAP = 105;
const componentGap = 90;
const nodes: WFNode[] = [];
/*

- Keep the workflow vertical. Each rank gets a centered row. Wide branch
- levels are allowed to grow horizontally rather than crushing nodes into
- each other. This is intentionally deterministic so the same trace always
- looks the same.
  */
  [...levels.keys()].sort((a, b) => a - b).forEach(level => {
  const ids = levels.get(level)!;
  const totalW = ids.length * NODE_W + Math.max(0, ids.length - 1) * HGAP;
  const rowOffset = -totalW / 2;

ids.forEach((graphNode, i) => {

  const span = resolveSpanForGraphNode(graphNode, flatSpans);
  const meta = (graphNode.metadata || span?.metadata || {}) as Record<string, unknown>;
  const spanType = graphNode.span_type || span?.span_type || "tool";
  const kind = (KIND_COLOR[spanType] !== undefined ? spanType : "tool") as NodeKind;
  const childCount = (childrenOf.get(graphNode.id) || []).length;

  nodes.push({
    id: graphNode.id,
    name: graphNode.name || span?.name || graphNode.id,
    kind,
    duration: graphNode.duration_ms ?? span?.duration_ms ?? 0,
    status: (['success', 'error', 'warning', 'running', 'blocked', 'pending']
      .includes(graphNode.status || span?.status || 'success')
      ? (graphNode.status || span?.status || 'success')
      : 'success') as RunStatus,
    x: rowOffset + i * (NODE_W + HGAP),
    y: level * (NODE_H + VGAP + componentGap),
    model: meta.model as string | undefined,
    inputTokens: meta.input_tokens as number | undefined,
    outputTokens: meta.output_tokens as number | undefined,
    cost: (meta.cost as number | undefined) ?? (meta.estimated_cost_usd as number | undefined),
    input: graphNode.input ?? span?.input ?? (meta.input as string | null | undefined) ?? null,
    output: graphNode.output ?? span?.output ?? (meta.output as string | null | undefined) ?? null,
    context: graphNode.context ?? span?.context ?? (meta.context as string | null | undefined) ?? null,
    sourceSpanId: span?.id,
    childCount: childCount > 0 ? childCount : undefined,
  });
});

});
return { nodes, edges: graphEdges };
}
function computeP95(values: number[]): number | null {
if (values.length === 0) return null;
const sorted = [...values].sort((a, b) => a - b);
return sorted[Math.max(0, Math.ceil(sorted.length * 0.95) - 1)];
}
type ShadowEvaluation = NonNullable<ApiInsights["shadow_evaluations"]>[number];

type AppShadowEvaluation = ShadowEvaluation & {
  // Shadow evaluations are child traces. Keep the owning workflow trace ID
  // for application-level display and navigation.
  application_trace_id?: string;
};

function buildAppGroup(
application: ApiApplication,
allTraces: ApiTrace[],
shadowEvaluations: ShadowEvaluation[] = [],
): AppGroup {
const sessionTraces = allTraces;
// Root workflow traces correspond to the runs created under this application.
// Child traces are nested LLM/evaluation records owned by those runs.
const rootTraces = sessionTraces.filter(t => t.parent_trace_id === null);
const childTraces = sessionTraces.filter(t => t.parent_trace_id !== null);

// Safety interventions are frequently recorded as child traces. In that
// case the workflow root can legitimately have status="error" because the
// blocked child terminated the workflow. Treat the entire owning workflow as
// safety-blocked rather than as an application failure.
const directSafetyTraces = sessionTraces.filter(isSafetyBlockedTrace);
const parentByTraceId = new Map(
  sessionTraces.map(t => [t.id, t.parent_trace_id])
);
const safetyAffectedTraceIds = new Set<string>();

for (const safetyTrace of directSafetyTraces) {
  let currentId: string | null = safetyTrace.id;
  while (currentId) {
    if (safetyAffectedTraceIds.has(currentId)) break;
    safetyAffectedTraceIds.add(currentId);
    currentId = parentByTraceId.get(currentId) ?? null;
  }
}

const blockedRootTraces = rootTraces.filter(
  t => safetyAffectedTraceIds.has(t.id)
);

const operationalRootTraces = rootTraces.filter(
  t => !safetyAffectedTraceIds.has(t.id)
);
const successful = operationalRootTraces.filter(
  t => t.status === "success"
).length;
const reliability = operationalRootTraces.length > 0
  ? (successful / operationalRootTraces.length) * 100
  : (rootTraces.length > 0 ? 100 : 0);

// Use the canonical Shadow evaluation records returned by
// /traces/:id/insights. This is the same data source used by the Trace
// Investigation quality pane. Raw child-trace factuality is only a
// compatibility fallback for older API responses.
// Shadow evaluation records use the child evaluation trace ID. That ID is
// different from the real application/workflow trace ID shown in the Traces
// and Reliability tabs. Resolve the evaluation back to its owning root trace
// entirely in the frontend; no backend change is required.
const traceById = new Map(sessionTraces.map(t => [t.id, t]));
const rootTraceIdFor = (traceId: string): string | undefined => {
  let currentId: string | null = traceId;
  const visited = new Set<string>();

  while (currentId && !visited.has(currentId)) {
    visited.add(currentId);
    const trace = traceById.get(currentId);
    if (!trace) return undefined;
    if (!trace.parent_trace_id) return trace.id;
    currentId = trace.parent_trace_id;
  }

  return undefined;
};

const shadowByTraceId = new Map<string, AppShadowEvaluation>();
for (const evaluation of shadowEvaluations) {
  if (!evaluation.trace_id) continue;
  shadowByTraceId.set(evaluation.trace_id, {
    ...evaluation,
    application_trace_id: rootTraceIdFor(evaluation.trace_id),
  });
}

const canonicalEvaluations = Array.from(shadowByTraceId.values());
const fallbackEvaluations: AppShadowEvaluation[] = childTraces
  .filter(t => t.factuality_score != null || t.factuality_status != null)
  .map(t => ({
    trace_id: t.id,
    application_trace_id: rootTraceIdFor(t.id),
    provider: t.provider,
    model: t.model,
    factuality_score: t.factuality_score,
    factuality_status: t.factuality_status,
    input: t.input,
    has_output: t.output != null,
    context: t.context,
    input_tokens: t.input_tokens,
    output_tokens: t.output_tokens,
    latency_ms: t.latency_ms,
    estimated_cost_usd: t.estimated_cost_usd,
    status: t.status,
    evaluated_at: t.evaluated_at,
  }));

const evaluations = canonicalEvaluations.length > 0
  ? canonicalEvaluations
  : fallbackEvaluations;

const evaluated = evaluations.filter(e => e.factuality_score != null);
const quality = evaluated.length > 0
  ? (evaluated.reduce((sum, e) => sum + (e.factuality_score ?? 0), 0) / evaluated.length) * 100
  : null;

const latencies = rootTraces.filter(t => t.latency_ms != null).map(t => t.latency_ms!);
const p95Latency = computeP95(latencies);
const avgLatency = latencies.length > 0
  ? latencies.reduce((a, b) => a + b, 0) / latencies.length : null;

const totalCost = childTraces.reduce((s, t) => s + (t.estimated_cost_usd || 0), 0);
// Count the actual safety intervention traces. These may be child traces
// whose root workflow is persisted as status="error".
const safetyInterventionTraces = directSafetyTraces;
const safetyFlags = safetyInterventionTraces.length;

const shadowCounts = {
  supported: evaluations.filter(e => e.factuality_status === "supported").length,
  partial: evaluations.filter(e => e.factuality_status === "partially_supported").length,
  unsupported: evaluations.filter(e => e.factuality_status === "unsupported").length,
  pending: evaluations.filter(e => e.factuality_score == null).length,
  total: evaluations.length,
};

const childTotals = new Map<string, {
  input: number;
  output: number;
  cost: number;
  hasInput: boolean;
  hasOutput: boolean;
  hasCost: boolean;
}>();

for (const child of childTraces) {
  if (!child.parent_trace_id) continue;
  const totals = childTotals.get(child.parent_trace_id) || {
    input: 0,
    output: 0,
    cost: 0,
    hasInput: false,
    hasOutput: false,
    hasCost: false,
  };

  if (child.input_tokens != null && child.input_tokens > 0) {
    totals.input += child.input_tokens;
    totals.hasInput = true;
  }
  if (child.output_tokens != null && child.output_tokens > 0) {
    totals.output += child.output_tokens;
    totals.hasOutput = true;
  }
  if (child.estimated_cost_usd != null && child.estimated_cost_usd > 0) {
    totals.cost += child.estimated_cost_usd;
    totals.hasCost = true;
  }
  childTotals.set(child.parent_trace_id, totals);
}

const enrichedRootTraces = rootTraces.map(trace => {
  const totals = childTotals.get(trace.id);
  if (!totals) return trace;
  return {
    ...trace,
    input_tokens:
      trace.input_tokens != null && trace.input_tokens > 0
        ? trace.input_tokens
        : totals.hasInput ? totals.input : trace.input_tokens,
    output_tokens:
      trace.output_tokens != null && trace.output_tokens > 0
        ? trace.output_tokens
        : totals.hasOutput ? totals.output : trace.output_tokens,
    estimated_cost_usd:
      trace.estimated_cost_usd != null && trace.estimated_cost_usd > 0
        ? trace.estimated_cost_usd
        : totals.hasCost ? totals.cost : trace.estimated_cost_usd,
  };
});

const sorted = [...enrichedRootTraces].sort(
  (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
);
const lastActivity = sorted[0]?.created_at || application.created_at || null;

let health: "healthy" | "warning" | "critical" = "healthy";
if (reliability < 90 || (quality != null && quality < 80)) health = "critical";
else if (reliability < 97 || (quality != null && quality < 90) || safetyFlags > 0) health = "warning";

return {
  applicationId: application.application_id || application.id,
  name: application.name,
  traces: sorted,
  safetyTraces: safetyInterventionTraces,
  reliability,
  quality,
  p95Latency,
  avgLatency,
  totalCost,
  safetyFlags,
  lastActivity,
  health,
  shadowCounts,
  shadowEvaluations: evaluations,
};
}

async function loadApplicationGroups(): Promise<AppGroup[]> {
const applications = await apiGet<ApiApplication[]>("/applications");

const groups = await Promise.all(
  applications.map(async application => {
    const runs = await apiGet<ApiRun[]>(
      `/applications/${application.application_id || application.id}/runs?limit=500`,
    );

    const traceLists = await Promise.all(
      runs.map(run =>
        apiGet<ApiTrace[]>(`/runs/${run.run_id || run.id}/traces?limit=2000`)
          .catch(() => [] as ApiTrace[])
      )
    );

    const traces = traceLists.flatMap((traceList, index) => {
      const run = runs[index];
      return traceList.map(trace => ({
        ...trace,
        run_id: trace.run_id || run?.run_id || run?.id,
      }));
    });

    // The run endpoint is authoritative for lifecycle data. When a root trace
    // does not carry those fields, copy them from its owning run.
    const runById = new Map(runs.map(run => [run.run_id || run.id, run]));
    const normalized = traces.map(trace => {
      const run = trace.run_id ? runById.get(trace.run_id) : undefined;
      if (!run) return trace;
      return {
        ...trace,
        created_at: trace.created_at || run.created_at,
        status: trace.status || run.status,
        latency_ms: trace.latency_ms ?? run.latency_ms,
      };
    });

    // Application Quality must use the same canonical Shadow evaluation
    // endpoint as Trace Investigation. The API exposes this per trace, so
    // collect the evaluations for each root workflow trace.
    const rootTraces = normalized.filter(t => t.parent_trace_id === null);
    const shadowResults = await Promise.all(
      rootTraces.map(async trace => {
        const insights = await apiGetTraceInsights(trace.id);
        return insights?.shadow_evaluations ?? [];
      })
    );
    const shadowEvaluations = shadowResults.flat();

    return buildAppGroup(application, normalized, shadowEvaluations);
  })
);

return groups.sort((a, b) => {
  const ta = a.lastActivity ? new Date(a.lastActivity).getTime() : 0;
  const tb = b.lastActivity ? new Date(b.lastActivity).getTime() : 0;
  return tb - ta;
});
}

function fmtMs(ms: number | null | undefined): string {
if (ms == null) return "N/A";
if (ms < 1000) return `${Math.round(ms)}ms`;
return `${(ms / 1000).toFixed(2)}s`;
}
function getRunDurationMs(spans: ApiSpan[]): number | null {
const flatSpans = flattenSpans(spans);
const starts = flatSpans
.map(span => span.started_at ? new Date(span.started_at).getTime() : NaN)
.filter(Number.isFinite);
const ends = flatSpans
.map(span => span.ended_at ? new Date(span.ended_at).getTime() : NaN)
.filter(Number.isFinite);
if (starts.length > 0 && ends.length > 0) {
const duration = Math.max(...ends) - Math.min(...starts);
if (duration > 0) return duration;
}
// Some Default / All Traces records do not persist span timestamps.
// Their individual span durations are still available.
const durations = flatSpans
.map(span => span.duration_ms)
.filter((duration): duration is number => duration != null && duration > 0);
return durations.length > 0 ? Math.max(...durations) : null;
}
function getResolvedRunDuration(
trace: ApiTrace,
spans: ApiSpan[],
insights: ApiInsights | null = null,
): number | null {
if (trace.latency_ms != null && trace.latency_ms > 0) {
return trace.latency_ms;
}
const workflowLatency = insights?.performance?.workflow_latency_ms;
if (workflowLatency != null && workflowLatency > 0) {
return workflowLatency;
}
const spanDuration = getRunDurationMs(spans);
if (spanDuration != null && spanDuration > 0) {
return spanDuration;
}
const bottleneckDuration = insights?.performance?.bottleneck?.duration_ms;
if (bottleneckDuration != null && bottleneckDuration > 0) {
return bottleneckDuration;
}
return null;
}
function getMetadataCost(value: unknown): number | null {
if (value == null) return null;
if (typeof value === "string") {
const numeric = Number(value);
if (Number.isFinite(numeric) && numeric > 0) return numeric;
try {
return getMetadataCost(JSON.parse(value));
} catch {
return null;
}
}
if (typeof value === "number") {
return Number.isFinite(value) && value > 0 ? value : null;
}
if (typeof value !== "object") return null;
const obj = value as Record<string, unknown>;
const directKeys = [
"cost_usd",
"estimated_cost_usd",
"total_cost_usd",
"total_cost",
"cost",
];
for (const key of directKeys) {
const candidate = obj[key];
const numeric =
typeof candidate === "number"
? candidate
: typeof candidate === "string"
? Number(candidate)
: NaN;

if (Number.isFinite(numeric) && numeric > 0) return numeric;

}
let total = 0;
let found = false;
for (const [key, candidate] of Object.entries(obj)) {
if (key === "input_cost" || key === "output_cost") {
const numeric =
typeof candidate === "number"
? candidate
: typeof candidate === "string"
? Number(candidate)
: NaN;
if (Number.isFinite(numeric) && numeric > 0) {
total += numeric;
found = true;
}
continue;
}

if (candidate && typeof candidate === "object") {
  const nested = getMetadataCost(candidate);
  if (nested != null && nested > 0) {
    total += nested;
    found = true;
  }
}

}
return found ? total : null;
}
function getChildTraceCost(allTraces: ApiTrace[], rootTraceId: string): number | null {
const total = allTraces
.filter(t => t.parent_trace_id === rootTraceId)
.reduce((sum, t) => {
const cost = t.estimated_cost_usd;
return sum + (cost != null && cost > 0 ? cost : 0);
}, 0);
return total > 0 ? total : null;
}
function getChildTraces(allTraces: ApiTrace[], rootTraceId: string): ApiTrace[] {
return allTraces
  .filter(t => t.parent_trace_id === rootTraceId)
  .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
}
function getChildTraceMetrics(
allTraces: ApiTrace[],
rootTraceId: string,
): {
inputTokens: number | null;
outputTokens: number | null;
cost: number | null;
} {
const children = allTraces.filter(t => t.parent_trace_id === rootTraceId);
let inputTokens = 0;
let outputTokens = 0;
let cost = 0;
let hasInput = false;
let hasOutput = false;
let hasCost = false;
for (const child of children) {
if (child.input_tokens != null && child.input_tokens > 0) {
inputTokens += child.input_tokens;
hasInput = true;
}

if (child.output_tokens != null && child.output_tokens > 0) {
  outputTokens += child.output_tokens;
  hasOutput = true;
}

if (child.estimated_cost_usd != null && child.estimated_cost_usd > 0) {
  cost += child.estimated_cost_usd;
  hasCost = true;
}

}
return {
inputTokens: hasInput ? inputTokens : null,
outputTokens: hasOutput ? outputTokens : null,
cost: hasCost ? cost : null,
};
}
function getResolvedRunCost(
trace: ApiTrace | null,
spans: ApiSpan[],
insights: ApiInsights | null = null,
): number | null {
if (trace?.estimated_cost_usd != null && trace.estimated_cost_usd > 0) {
return trace.estimated_cost_usd;
}
const insightCost = insights?.performance?.cost_usd;
if (insightCost != null && insightCost > 0) {
return insightCost;
}
const flatSpans = flattenSpans(spans);
let spanCost = 0;
let foundSpanCost = false;
for (const span of flatSpans) {
const cost = getMetadataCost(span.metadata);
if (cost != null && cost > 0) {
spanCost += cost;
foundSpanCost = true;
}
}
if (foundSpanCost) return spanCost;
const shadowCost = (insights?.shadow_evaluations || []).reduce((sum, evaluation) => {
const cost = evaluation.estimated_cost_usd;
return sum + (cost != null && cost > 0 ? cost : 0);
}, 0);
return shadowCost > 0 ? shadowCost : null;
}
function fmtCost(usd: number | null | undefined): string {
if (usd == null) return "N/A";
if (usd === 0) return "$0.00";
if (usd < 0.0001) return `<$0.0001`;
return `$${usd.toFixed(4)}`;
}
function fmtTime(iso: string | null | undefined): string {
if (!iso) return "N/A";
const diff = Date.now() - new Date(iso).getTime();
if (diff < 60000) return `${Math.floor(diff / 1000)}s ago`;
if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
return new Date(iso).toLocaleDateString();
}
function statusColor(s: string): string {
if (s === "success") return "#16a34a";
if (s === "error") return "#dc2626";
if (s === "blocked") return "#d97706";
if (s === "warning") return "#d97706";
if (s === "running") return "#2563eb";
if (s === "pending") return "#6b6b68";
return "#9e9e9b";
}
// Canonical safety-intervention classifier.
// A blocked request may be represented by status, safety_flag, or safety_action.
function isSafetyBlockedTrace(trace: ApiTrace): boolean {
  return (
    trace.status.trim().toLowerCase() === "blocked" ||
    trace.safety_flag === true ||
    trace.safety_action?.trim().toLowerCase() === "block"
  );
}

function healthColor(h: "healthy" | "warning" | "critical"): string {
return h === "healthy" ? "#16a34a" : h === "warning" ? "#d97706" : "#dc2626";
}
// ─── Canvas Helpers ───────────────────────────────────────────────────────────
function getSubtreeIds(rootId: string, nodes: WFNode[], edges: WFEdge[]): Set<string> {
const visited = new Set<string>();
const queue = [rootId];
while (queue.length > 0) {
const id = queue.shift()!;
if (visited.has(id)) continue;
visited.add(id);
edges.filter(e => e.from === id).forEach(e => queue.push(e.to));
}
return visited;
}
function getHiddenByCollapse(collapsedIds: Set<string>, nodes: WFNode[], edges: WFEdge[]): Set<string> {
const hidden = new Set<string>();
for (const cid of collapsedIds) {
const sub = getSubtreeIds(cid, nodes, edges);
sub.delete(cid);
sub.forEach(nid => hidden.add(nid));
}
return hidden;
}
// ─── WorkflowCanvas ───────────────────────────────────────────────────────────
interface CanvasProps {
nodes: WFNode[];
edges: WFEdge[];
selectedNodeId: string | null;
highlightedNodeId: string | null;
onSelectNode: (id: string | null) => void;
}
function WorkflowCanvas({ nodes, edges, selectedNodeId, highlightedNodeId, onSelectNode }: CanvasProps) {
const svgRef = useRef<SVGSVGElement>(null);
const [tf, setTf] = useState({ x: 0, y: 0, scale: 0.85 });
const [panning, setPanning] = useState(false);
const panStart = useRef({ mx: 0, my: 0, tx: 0, ty: 0 });
const [hoveredId, setHoveredId] = useState<string | null>(null);
const [drillPath, setDrillPath] = useState<string[]>([]);
const [collapsedIds, setCollapsedIds] = useState(new Set<string>());
const drillId = drillPath[drillPath.length - 1] ?? null;
const subtreeIds = drillId ? getSubtreeIds(drillId, nodes, edges) : null;
const hiddenIds = getHiddenByCollapse(collapsedIds, nodes, edges);
const visibleNodes = nodes.filter(n =>
(!subtreeIds || subtreeIds.has(n.id)) && !hiddenIds.has(n.id)
);
const visibleEdges = edges.filter(e =>
visibleNodes.some(n => n.id === e.from) && visibleNodes.some(n => n.id === e.to)
);
const visibleNodesRef = useRef(visibleNodes);
visibleNodesRef.current = visibleNodes;
const fitView = useCallback(() => {
const vn = visibleNodesRef.current;
if (!svgRef.current || vn.length === 0) return;
const { width, height } = svgRef.current.getBoundingClientRect();
const xs = vn.map(n => n.x);
const ys = vn.map(n => n.y);
const pad = 32;
const minX = Math.min(...xs) - pad, minY = Math.min(...ys) - pad;
const maxX = Math.max(...xs) + NODE_W + pad, maxY = Math.max(...ys) + NODE_H + pad;
const scale = Math.min(width / (maxX - minX), height / (maxY - minY), 1.2);
const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
setTf({ x: width / 2 - cx * scale, y: height / 2 - cy * scale, scale });
}, []); // stable — reads visibleNodesRef at call time
// Re-fit only when the set of visible node IDs actually changes.
const visibleNodeIds = visibleNodes.map(n => n.id).join(",");
// eslint-disable-next-line react-hooks/exhaustive-deps
useEffect(() => { fitView(); }, [visibleNodeIds]);
useEffect(() => {
const svg = svgRef.current;
if (!svg) return;
const handler = (e: WheelEvent) => {
e.preventDefault();
const rect = svg.getBoundingClientRect();
const mx = e.clientX - rect.left, my = e.clientY - rect.top;
const d = e.deltaY < 0 ? 1.1 : 0.9;
setTf(t => ({
scale: Math.min(3, Math.max(0.15, t.scale * d)),
x: mx - (mx - t.x) * d,
y: my - (my - t.y) * d,
}));
};
svg.addEventListener("wheel", handler, { passive: false });
return () => svg.removeEventListener("wheel", handler);
}, []);
useEffect(() => {
const handler = (e: KeyboardEvent) => {
if (e.key === "Escape") {
if (drillPath.length > 0) setDrillPath(p => p.slice(0, -1));
else onSelectNode(null);
}
};
window.addEventListener("keydown", handler);
return () => window.removeEventListener("keydown", handler);
}, [drillPath, onSelectNode]);
const onMouseDown = (e: React.MouseEvent) => {
if (e.button !== 0) return;
setPanning(true);
panStart.current = { mx: e.clientX, my: e.clientY, tx: tf.x, ty: tf.y };
};
const onMouseMove = (e: React.MouseEvent) => {
if (!panning) return;
setTf(t => ({
...t,
x: panStart.current.tx + e.clientX - panStart.current.mx,
y: panStart.current.ty + e.clientY - panStart.current.my,
}));
};
const onMouseUp = () => setPanning(false);
const showKindLabel = tf.scale >= 0.55;
const showModel = tf.scale >= 0.65;
const showDuration = tf.scale >= 0.55;
const showChildCount = tf.scale >= 0.65;
const showCostLine = tf.scale >= 1.35;
// Minimap bounds
const allXs = nodes.map(n => n.x), allYs = nodes.map(n => n.y);
const mmMinX = nodes.length ? Math.min(...allXs) - 20 : -200;
const mmMaxX = nodes.length ? Math.max(...allXs) + NODE_W + 20 : 200;
const mmMinY = nodes.length ? Math.min(...allYs) - 20 : -100;
const mmMaxY = nodes.length ? Math.max(...allYs) + NODE_H + 20 : 100;
const mmW = 140, mmH = 80;
const mmScale = Math.min(mmW / (mmMaxX - mmMinX), mmH / (mmMaxY - mmMinY));
if (nodes.length === 0) {
return (
<div className="flex-1 flex items-center justify-center text-cp-secondary text-sm">
No spans recorded for this trace.
</div>
);
}
return (
<div className="relative flex-1 overflow-hidden bg-cp-canvas">
<svg
ref={svgRef}
className="w-full h-full select-none"
style={{ cursor: panning ? "grabbing" : "grab" }}
onMouseDown={onMouseDown}
onMouseMove={onMouseMove}
onMouseUp={onMouseUp}
onMouseLeave={onMouseUp}
onClick={() => onSelectNode(null)}
>
<defs>
<pattern id="dots" patternUnits="userSpaceOnUse" width="24" height="24">
<circle cx="1" cy="1" r="0.8" fill="#2a2826" />
</pattern>
<filter id="node-glow" x="-20%" y="-20%" width="140%" height="140%">
<feGaussianBlur in="SourceAlpha" stdDeviation="4" result="blur" />
<feFlood floodOpacity="0.3" result="flood" />
<feComposite in="flood" in2="blur" operator="in" result="glow" />
<feMerge><feMergeNode in="glow" /><feMergeNode in="SourceGraphic" /></feMerge>
</filter>
<filter id="amber-glow" x="-30%" y="-30%" width="160%" height="160%">
<feGaussianBlur in="SourceAlpha" stdDeviation="6" result="blur" />
<feFlood floodColor="#d97706" floodOpacity="0.5" result="flood" />
<feComposite in="flood" in2="blur" operator="in" result="glow" />
<feMerge><feMergeNode in="glow" /><feMergeNode in="SourceGraphic" /></feMerge>
</filter>
<marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto" markerUnits="userSpaceOnUse">
<path d="M0,0 L10,5 L0,10 Z" fill="#52504d" />
</marker>
<marker id="arrow-active" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto" markerUnits="userSpaceOnUse">
<path d="M0,0 L10,5 L0,10 Z" fill="#f97316" />
</marker>
</defs>

    <rect width="100%" height="100%" fill="url(#dots)" />

    <g transform={`translate(${tf.x},${tf.y}) scale(${tf.scale})`}>
      {/* Edges */}
      {visibleEdges.map(e => {
        const from = visibleNodes.find(n => n.id === e.from);
        const to = visibleNodes.find(n => n.id === e.to);
        if (!from || !to) return null;

        const x1 = from.x + NODE_W / 2;
        const y1 = from.y + NODE_H;
        const x2 = to.x + NODE_W / 2;
        const y2 = to.y;
        const isActive = selectedNodeId === e.from || selectedNodeId === e.to;

        // Normal workflow edge: smooth vertical routing.
        // Back-edges (possible in cyclic telemetry) get a side loop instead
        // of producing an inverted arrow through the middle of the graph.
        const d = y2 > y1
          ? (() => {
              const distance = Math.max(30, y2 - y1);
              const curve = Math.min(70, distance / 2);
              return `M ${x1} ${y1} C ${x1} ${y1 + curve}, ${x2} ${y2 - curve}, ${x2} ${y2}`;
            })()
          : (() => {
              const side = Math.max(x1, x2) + 90;
              return `M ${x1} ${y1} C ${side} ${y1}, ${side} ${y2}, ${x2} ${y2}`;
            })();

        return (
          <path
            key={`${e.from}-${e.to}`}
            d={d}
            fill="none"
            stroke={isActive ? "#f97316" : "#52504d"}
            strokeWidth={isActive ? 2.5 : 2}
            strokeLinecap="round"
            markerEnd={isActive ? "url(#arrow-active)" : "url(#arrow)"}
            pointerEvents="none"
          />
        );
      })}

      {/* Nodes */}
      {visibleNodes.map(node => {
        const isSel = selectedNodeId === node.id;
        const isHov = hoveredId === node.id;
        const isHL = highlightedNodeId === node.id;
        const kc = KIND_COLOR[node.kind] || "#6e7a8a";
        const sc = statusColor(node.status);
        const isDrillable = DRILLABLE.has(node.kind);
        const isCol = collapsedIds.has(node.id);

        return (
          <g
            key={node.id}
            transform={`translate(${node.x},${node.y})`}
            style={{ cursor: "pointer" }}
            onClick={e => { e.stopPropagation(); onSelectNode(node.id); }}
            onDoubleClick={e => {
              e.stopPropagation();
              if (!isDrillable) return;
              setDrillPath(p => [...p, node.id]);
              onSelectNode(null);
            }}
            onMouseEnter={() => setHoveredId(node.id)}
            onMouseLeave={() => setHoveredId(null)}
          >
            {/* Amber highlight ring */}
            {isHL && (
              <rect x={-7} y={-7} width={NODE_W + 14} height={NODE_H + 14} rx={7}
                fill="none" stroke="#d97706" strokeWidth={2} opacity={0.75}
                filter="url(#amber-glow)">
                <animate attributeName="opacity" values="0.75;0.2;0.75" dur="1.8s" repeatCount="indefinite" />
              </rect>
            )}

            {/* Selection / hover ring */}
            {(isSel || isHov) && (
              <rect x={-3} y={-3} width={NODE_W + 6} height={NODE_H + 6} rx={7}
                fill="none" stroke={isSel ? kc : "rgba(255,255,255,0.18)"} strokeWidth={isSel ? 1.5 : 1} />
            )}

            {/* Card — dark surface */}
            <rect x={0} y={0} width={NODE_W} height={NODE_H} rx={6}
              fill={isSel ? "#2e2c2a" : "#262422"} stroke={isSel ? kc + "80" : "#3a3835"} strokeWidth={1} />
            {/* Top accent bar */}
            <rect x={0} y={0} width={NODE_W} height={3} rx={3} fill={kc} opacity={0.9} />
            {/* Header area */}
            <rect x={0} y={3} width={NODE_W} height={19} fill={kc} opacity={0.08} />

            {showKindLabel && (
              <text x={10} y={16} fontSize={8.5} fill={kc} fontFamily="'Geist',sans-serif"
                fontWeight={700} style={{ textTransform: "uppercase", letterSpacing: "0.08em" }}>
                {node.kind}
              </text>
            )}
            <circle cx={NODE_W - 10} cy={12} r={3} fill={sc} />

            <line x1={0} y1={22} x2={NODE_W} y2={22} stroke="rgba(255,255,255,0.06)" />

            <text x={10} y={40} fontSize={12} fill="#f0efed" fontFamily="'Geist',sans-serif" fontWeight={500}>
              {node.name.length > 20 ? node.name.slice(0, 18) + "…" : node.name}
            </text>

            {showModel && node.model && (
              <text x={10} y={55} fontSize={9.5} fill="#7a7875" fontFamily="'Geist Mono',monospace">
                {node.model.length > 22 ? node.model.slice(0, 20) + "…" : node.model}
              </text>
            )}

            {isHov && isDrillable && !node.model && (
              <text x={10} y={55} fontSize={9} fill={kc} fontFamily="'Geist',sans-serif" opacity={0.7}>
                double-click to drill in
              </text>
            )}

            <line x1={0} y1={72} x2={NODE_W} y2={72} stroke="rgba(255,255,255,0.06)" />

            {showDuration && (
              <text x={10} y={86} fontSize={9.5} fill="#5e5c5a"
                fontFamily="'Geist Mono',monospace">
                {showCostLine && node.cost != null ? fmtCost(node.cost) : fmtMs(node.duration)}
              </text>
            )}

            {showChildCount && node.childCount && node.childCount > 0 && (
              <g onClick={e => {
                e.stopPropagation();
                setCollapsedIds(s => {
                  const n = new Set(s);
                  n.has(node.id) ? n.delete(node.id) : n.add(node.id);
                  return n;
                });
              }}>
                <rect x={NODE_W - 38} y={77} width={30} height={12} rx={3}
                  fill={isCol ? kc + "33" : "rgba(255,255,255,0.08)"} stroke="rgba(255,255,255,0.12)" strokeWidth={0.5} />
                <text x={NODE_W - 23} y={87} fontSize={8.5} fill="#7a7875"
                  fontFamily="'Geist',sans-serif" textAnchor="middle">
                  {isCol ? `+${node.childCount}` : `−${node.childCount}`}
                </text>
              </g>
            )}
          </g>
        );
      })}
    </g>
  </svg>

  {/* Minimap */}
  <div className="absolute bottom-14 right-4 rounded border border-white/10 bg-black/40 p-1.5">
    <svg width={mmW} height={mmH}>
      {visibleNodes.map(n => (
        <rect key={n.id}
          x={(n.x - mmMinX) * mmScale} y={(n.y - mmMinY) * mmScale}
          width={NODE_W * mmScale} height={NODE_H * mmScale}
          rx={1} fill={KIND_COLOR[n.kind] || "#6e7a8a"}
          opacity={selectedNodeId === n.id ? 0.9 : 0.4} />
      ))}
    </svg>
  </div>

  {/* Drill breadcrumb */}
  {drillPath.length > 0 && (
    <div className="absolute top-3 left-3 flex items-center gap-1.5 text-xs bg-black/50 border border-white/10 rounded px-2 py-1 text-white/70">
      <button onClick={() => setDrillPath([])} className="text-cp-blue hover:underline">Root</button>
      {drillPath.map((id, i) => {
        const n = nodes.find(n => n.id === id);
        return (
          <span key={id} className="flex items-center gap-1">
            <ChevronRight size={10} className="text-cp-muted" />
            <button onClick={() => setDrillPath(p => p.slice(0, i + 1))}
              className="text-cp-text hover:text-cp-blue">
              {n?.name || id.slice(0, 8)}
            </button>
          </span>
        );
      })}
      <button onClick={() => setDrillPath(p => p.slice(0, -1))} className="ml-1 text-cp-muted hover:text-cp-error">
        <X size={10} />
      </button>
    </div>
  )}

  {/* Zoom controls */}
  <div className="absolute bottom-4 right-4 flex flex-col gap-1">
    {[
      { icon: <Minus size={12} />, action: () => setTf(t => ({ ...t, scale: Math.max(0.15, t.scale * 0.8) })) },
      { icon: <span className="text-xs font-mono">fit</span>, action: fitView },
      { icon: <Plus size={12} />, action: () => setTf(t => ({ ...t, scale: Math.min(3, t.scale * 1.2) })) },
    ].map((btn, i) => (
      <button key={i} onClick={btn.action}
        className="w-7 h-7 flex items-center justify-center bg-black/40 border border-white/10 rounded text-white/50 hover:text-white/90 transition-colors">
        {btn.icon}
      </button>
    ))}
  </div>

  <div className="absolute bottom-4 left-4 text-xs text-white/40 font-mono bg-black/30 border border-white/10 rounded px-1.5 py-0.5">
    {Math.round(tf.scale * 100)}%
  </div>
</div>

);
}
// ─── Node Inspector ───────────────────────────────────────────────────────────
interface InspectorProps {
node: WFNode | null;
trace: ApiTrace | null;
flatSpans: ApiSpan[];
insights: ApiInsights | null;
childTraces?: ApiTrace[];
traceCost?: number | null;
traceInputTokens?: number | null;
traceOutputTokens?: number | null;
onHighlightNode: (id: string | null) => void;
}
function NodeInspector({
node,
trace,
flatSpans,
insights,
childTraces = [],
traceCost,
traceInputTokens,
traceOutputTokens,
onHighlightNode,
}: InspectorProps) {
const [tab, setTab] = useState("overview");
// Shadow output is only a fallback for the ROOT workflow node.
// Never use one trace's Shadow result as the output of an arbitrary child node.
const [childOutput, setChildOutput] = useState<string | null | "loading" | "error">(null);
// Graph nodes and spans normally share the same id. If a backend graph
// implementation only supplies graph nodes, fall back to name/parent matching
// so the inspector still resolves the actual span payload.
const span = node
? (
// The layout stores the exact persisted span behind this visual node.
(node.sourceSpanId
? flatSpans.find(s => s.id === node.sourceSpanId)
: undefined) ??
// Exact graph/span ID remains a valid fallback.
flatSpans.find(s => s.id === node.id) ??
// Last fallback for older traces without sourceSpanId.
flatSpans.find(s => s.name === node.name)
)
: null;
const isRootNode = !span?.parent_span_id;
// Shadow evaluation record for the trace. It is deliberately scoped to the
// root node only; child nodes must display their own recorded output.
const shadowEval = insights?.shadow_evaluations?.[0] ?? null;
useEffect(() => {
if (!isRootNode || tab !== "output" || !shadowEval?.trace_id) return;
if (childOutput !== null) return;
setChildOutput("loading");
apiGet<{ trace: ApiTrace; spans: ApiSpan[] }>(`/traces/${shadowEval.trace_id}`)
.then(d => setChildOutput(d.trace.output || null))
.catch(() => setChildOutput("error"));
}, [tab, shadowEval, childOutput, isRootNode]);
// Reset selected-node Shadow output when the node changes.
useEffect(() => { setChildOutput(null); }, [node?.id]);
if (!node && !trace) {
return (
<div className="flex-1 flex items-center justify-center text-cp-secondary text-sm p-6 text-center">
Click a node to inspect
</div>
);
}
if (!node) {
return (
<div className="flex-1 overflow-y-auto">
  <TraceOverviewPane
    trace={trace}
    insights={insights}
    flatSpans={flatSpans}
    traceCost={traceCost}
    traceInputTokens={traceInputTokens}
    traceOutputTokens={traceOutputTokens}
    onHighlightNode={onHighlightNode}
  />
  {childTraces.length > 0 && (
    <div className="border-t border-cp-border p-4">
      <div className="text-xs text-cp-muted uppercase tracking-wider mb-2">LLM Executions</div>
      <div className="space-y-2">
        {childTraces.map(child => (
          <div key={child.id} className="rounded-lg border border-cp-border bg-cp-surface p-3">
            <div className="flex items-center justify-between mb-2">
              <div>
                <div className="text-sm font-semibold text-cp-text">{child.provider}</div>
                <div className="text-xs font-mono text-cp-muted">{child.model || "Unknown model"}</div>
              </div>
              <span className="text-xs font-mono capitalize" style={{ color: statusColor(child.status) }}>{child.status}</span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div><div className="text-[10px] text-cp-muted">In Tokens</div><div className="text-xs font-mono text-cp-text">{child.input_tokens?.toLocaleString() ?? "N/A"}</div></div>
              <div><div className="text-[10px] text-cp-muted">Out Tokens</div><div className="text-xs font-mono text-cp-text">{child.output_tokens?.toLocaleString() ?? "N/A"}</div></div>
              <div><div className="text-[10px] text-cp-muted">Cost</div><div className="text-xs font-mono text-cp-text">{fmtCost(child.estimated_cost_usd)}</div></div>
            </div>
            {child.latency_ms != null && <div className="mt-2 text-[10px] text-cp-muted font-mono">Latency: {fmtMs(child.latency_ms)}</div>}
            {child.output && <div className="mt-3"><CodeBlock label="Output" value={child.output} /></div>}
          </div>
        ))}
      </div>
    </div>
  )}
</div>
);
}
const rawMetadata = span?.metadata ?? {};
const meta: Record<string, unknown> =
typeof rawMetadata === "string"
? (() => {
try {
const parsed = JSON.parse(rawMetadata);
return parsed && typeof parsed === "object" ? parsed : {};
} catch {
return {};
}
})()
: (rawMetadata as Record<string, unknown>);
const isBottleneck = insights?.performance?.bottleneck?.span_id === node.id;
const shadow = insights?.shadow;
const tabs = isRootNode ? ["overview", "input", "context", "output", "quality"] : ["overview", "input", "context", "output"];
const toDisplayValue = (value: unknown): string | null => {
if (value == null || value === "") return null;
if (typeof value === "string") return value;
try { return JSON.stringify(value, null, 2); }
catch { return String(value); }
};
// Accept the payload names commonly used by SDKs/telemetry producers.
// This is still the selected NODE'S payload; these are only fallbacks for
// spans whose producer put the data inside metadata.
const firstValue = (...values: unknown[]) =>
values.find(v => v !== null && v !== undefined && v !== "") ?? null;
const metadataInput = firstValue(
meta.input,
meta.prompt,
meta.request,
meta.inputs,
meta.messages,
(meta.payload as Record<string, unknown> | undefined)?.input,
(meta.payload as Record<string, unknown> | undefined)?.prompt,
);
const metadataContext = firstValue(
meta.context,
meta.retrieved_context,
meta.retrieved_documents,
meta.documents,
meta.sources,
meta.retrieval,
(meta.payload as Record<string, unknown> | undefined)?.context,
(meta.payload as Record<string, unknown> | undefined)?.documents,
);
const metadataOutput = firstValue(
meta.output,
meta.response,
meta.result,
meta.result_text,
meta.completion,
meta.response_text,
meta.outputs,
(meta.payload as Record<string, unknown> | undefined)?.output,
(meta.payload as Record<string, unknown> | undefined)?.response,
);
/*

- IMPORTANT:
-
  - Root node: the user's prompt is trace.input. Do not show the workflow
- name/agent name as the prompt just because a root span also has metadata.
-
  - Child node: only use that child span's input/context/output (or its
- metadata). Never substitute the root trace payload.
  */
  const realInput =
  toDisplayValue(span?.input) ??
  toDisplayValue(node.input) ??
  toDisplayValue(metadataInput) ??
  (isRootNode ? toDisplayValue(trace?.input) : null) ??
  (isRootNode ? toDisplayValue(shadowEval?.input) : null);

const realContext = isRootNode
? (
toDisplayValue(trace?.context) ??
toDisplayValue(span?.context) ??
toDisplayValue(metadataContext) ??
toDisplayValue(node.context) ??
toDisplayValue(shadowEval?.context)
)
: (
toDisplayValue(span?.context) ??
toDisplayValue(metadataContext) ??
toDisplayValue(node.context)
);
const realOutput =
toDisplayValue(span?.output) ??
toDisplayValue(node.output) ??
toDisplayValue(metadataOutput) ??
(isRootNode ? toDisplayValue(trace?.output) : null);
const inputSource =
span?.input != null ? "span" :
node.input != null ? "graph node" :
metadataInput != null ? "metadata" :
isRootNode && trace?.input != null ? "trace / prompt" :
isRootNode && shadowEval?.input != null ? "shadow prompt" :
null;
const contextSource =
span?.context != null ? "span" :
node.context != null ? "graph node" :
metadataContext != null ? "metadata" :
isRootNode && trace?.context != null ? "trace" :
isRootNode && shadowEval?.context != null ? "shadow" :
null;
return (
<div className="flex flex-col h-full">
<div className="p-4 border-b border-cp-border flex-shrink-0 bg-cp-surface">
<div className="flex items-center justify-between mb-2">
<span className="text-xs px-2 py-0.5 rounded font-semibold uppercase tracking-wide"
style={{ background: KIND_COLOR[node.kind] + "22", color: KIND_COLOR[node.kind] }}>
{node.kind}
</span>
<div className="flex items-center gap-2">
{isBottleneck && (
<span className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded font-medium">Bottleneck</span>
)}
<span className="w-2 h-2 rounded-full" style={{ background: statusColor(node.status) }} />
<span className="text-xs text-cp-secondary capitalize">{node.status}</span>
</div>
</div>

    <div className="flex items-center gap-2">
      <div className="text-base font-semibold text-cp-text truncate">{node.name}</div>
      {isRootNode && <span className="text-[10px] px-1.5 py-0.5 rounded bg-cp-purple/10 text-cp-purple border border-cp-purple/20">ROOT</span>}
    </div>
    {node.model && (
      <div className="text-xs text-cp-secondary font-mono mt-0.5">{node.model}</div>
    )}

    <div className="flex gap-4 mt-3">
      <div>
        <div className="text-xs text-cp-muted">Latency</div>
        <div className="text-sm font-mono text-cp-text">{fmtMs(node.duration)}</div>
      </div>
      {node.cost != null && (
        <div>
          <div className="text-xs text-cp-muted">Cost</div>
          <div className="text-sm font-mono text-cp-text">{fmtCost(node.cost)}</div>
        </div>
      )}
      {node.inputTokens != null && (
        <div>
          <div className="text-xs text-cp-muted">Tokens</div>
          <div className="text-sm font-mono text-cp-text">
            {(node.inputTokens + (node.outputTokens || 0)).toLocaleString()}
          </div>
        </div>
      )}
    </div>
  </div>

  <div className="flex border-b border-cp-border flex-shrink-0 overflow-x-auto">
    {tabs.map(t => (
      <button key={t} onClick={() => setTab(t)}
        className={`shrink-0 px-3 py-2.5 text-xs font-medium capitalize transition-colors ${
          tab === t ? "text-cp-text border-b-2 border-cp-purple -mb-px" : "text-cp-secondary hover:text-cp-text"
        }`}>
        {t}
      </button>
    ))}
  </div>

  <div className="flex-1 overflow-y-auto p-4 space-y-4">
    {(tab === "input" || tab === "context") && (
      <div className="flex items-center justify-between rounded-lg border border-cp-border bg-cp-elevated/50 px-3 py-2">
        <span className="text-[11px] text-cp-muted">Recorded source</span>
        <span className="text-[10px] uppercase tracking-wider font-semibold text-cp-secondary">
          {(tab === "input" ? inputSource : contextSource) || "none"}
        </span>
      </div>
    )}
    {tab === "overview" && (
      <>
        {isBottleneck && insights?.performance?.bottleneck && (
          <div className="rounded-lg border border-cp-border bg-cp-surface p-3">
            <div className="flex items-center gap-1.5 mb-1">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              <div className="text-xs font-semibold text-cp-text">Performance Bottleneck</div>
            </div>
            <div className="text-xs text-cp-secondary">
              {insights.performance.bottleneck.latency_share.toFixed(1)}% of total recorded span time
            </div>
          </div>
        )}

        <div>
          <div className="text-xs text-cp-muted uppercase tracking-wider mb-2">Span Details</div>
          <div className="space-y-1.5">
            {([
              ["Span ID", node.id.slice(0, 16) + "…"],
              ["Type", node.kind],
              ["Status", node.status],
              ["Duration", fmtMs(node.duration)],
              ...(node.model ? [["Model", node.model] as [string, string]] : []),
              ...(node.inputTokens != null ? [["In Tokens", String(node.inputTokens)] as [string, string]] : []),
              ...(node.outputTokens != null ? [["Out Tokens", String(node.outputTokens)] as [string, string]] : []),
              ...(node.cost != null ? [["Cost", fmtCost(node.cost)] as [string, string]] : []),
            ] as [string, string][]).map(([k, v]) => (
              <div key={k} className="flex justify-between text-xs">
                <span className="text-cp-secondary">{k}</span>
                <span className="text-cp-text font-mono">{v}</span>
              </div>
            ))}
          </div>
        </div>

        {insights?.recommendations && insights.recommendations.length > 0 && (
          <div>
            <div className="text-xs text-cp-muted uppercase tracking-wider mb-2">Recommendations</div>
            <div className="space-y-2">
              {insights.recommendations.map((rec, i) => (
                <button key={i} onClick={() => onHighlightNode(node.id)}
                  className="w-full text-left text-xs text-cp-secondary bg-cp-surface border border-cp-border rounded-lg p-2.5 hover:border-cp-border-strong hover:bg-cp-elevated transition-colors">
                  <AlertTriangle size={10} className="inline mr-1.5 text-cp-warning" />
                  {rec}
                </button>
              ))}
            </div>
          </div>
        )}
      </>
    )}

    {tab === "input" && (
      <CodeBlock label="Input" value={realInput} />
    )}

    {tab === "context" && (
      <CodeBlock label="Context / Retrieved Documents" value={realContext} />
    )}

    {tab === "output" && (
      childOutput === "loading" ? (
        <div className="flex items-center gap-2 text-cp-secondary text-xs">
          <Loader2 size={12} className="animate-spin" /> Loading output…
        </div>
      ) : childOutput === "error" ? (
        <div className="text-xs text-cp-error">Failed to load output from backend.</div>
      ) : (
        <CodeBlock label="Output"
          value={realOutput || childOutput || null} />
      )
    )}

    {tab === "quality" && isRootNode && (
      <ShadowQualityPane shadow={shadow} shadowEvals={insights?.shadow_evaluations ?? []} />
    )}
  </div>
</div>

);
}
function CodeBlock({ label, value }: { label: string; value: string | null }) {
const [copied, setCopied] = useState(false);
const copy = async () => {
if (!value) return;
try {
await navigator.clipboard.writeText(value);
setCopied(true);
window.setTimeout(() => setCopied(false), 1200);
} catch { /* clipboard may be unavailable in an embedded browser */ }
};
return (
<div className="space-y-2">
<div className="flex items-center justify-between">
<div className="text-[11px] font-semibold text-cp-muted uppercase tracking-wider">{label}</div>
{value && (
<button onClick={copy} className="text-[11px] text-cp-secondary hover\:text-cp-text px-2 py-1 rounded border border-cp-border hover\:bg-cp-elevated transition-colors">
{copied ? "Copied" : "Copy"}
</button>
)}
</div>
{!value ? (
<div className="rounded-lg border border-dashed border-cp-border bg-cp-elevated/40 p-4 text-xs text-cp-muted">
<div className="font-medium text-cp-secondary mb-1">Not recorded</div>
This span did not persist a {label.toLowerCase()} payload.
</div>
) : (
<div className="rounded-lg border border-[#3a3835] bg-[#111110] overflow-hidden shadow-inner">
<pre className="text-[12px] leading-5 text-[#f3f4f6] font-mono p-4 whitespace-pre-wrap break-words max-h-[520px] overflow-auto">
{value}
</pre>
</div>
)}
</div>
);
}
type ShadowEval = NonNullable<ApiInsights["shadow_evaluations"]>[number];
function ShadowQualityPane({
shadow,
shadowEvals = [],
}: {
shadow: ApiInsights["shadow"];
shadowEvals?: ShadowEval[];
}) {
if (!shadow || shadow.evaluations === 0) {
return <div className="text-xs text-cp-muted italic">No Shadow evaluations for this trace.</div>;
}
const statusLabel: Record<string, string> = {
supported: "Supported",
partially_supported: "Partially Supported",
unsupported: "Unsupported",
};
const statusBg: Record<string, string> = {
supported: "#3fb95022",
partially_supported: "#d2992222",
unsupported: "#f8514922",
};
const statusFg: Record<string, string> = {
supported: "#16a34a",
partially_supported: "#d97706",
unsupported: "#dc2626",
};
return (
<div className="space-y-4">
<div className="text-xs text-cp-muted uppercase tracking-wider">Shadow Quality</div>

  {shadow.average_factuality_score != null && (
    <div>
      <div className="flex justify-between mb-1">
        <span className="text-xs text-cp-secondary">Factuality Score</span>
        <span className="text-xs font-mono text-cp-text">
          {(shadow.average_factuality_score * 100).toFixed(0)}%
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-cp-elevated">
        <div className="h-full rounded-full transition-all" style={{
          width: `${shadow.average_factuality_score * 100}%`,
          background: shadow.average_factuality_score >= 0.8 ? "#16a34a"
            : shadow.average_factuality_score >= 0.6 ? "#d97706" : "#dc2626",
        }} />
      </div>
    </div>
  )}

  <div className="grid grid-cols-3 gap-2 text-center">
    {[
      { label: "Supported", val: shadow.supported, color: "#16a34a" },
      { label: "Partial", val: shadow.partially_supported, color: "#d97706" },
      { label: "Unsupported", val: shadow.unsupported, color: "#dc2626" },
    ].map(item => (
      <div key={item.label} className="bg-cp-elevated rounded p-2 border border-cp-border">
        <div className="text-lg font-bold"
          style={{ color: item.val > 0 ? item.color : "#9e9e9b" }}>{item.val}</div>
        <div className="text-xs text-cp-muted">{item.label}</div>
      </div>
    ))}
  </div>

  {shadow.pending > 0 && (
    <div className="text-xs text-cp-secondary flex items-center gap-1">
      <Loader2 size={10} className="animate-spin" /> {shadow.pending} evaluation(s) pending
    </div>
  )}

  {/* Individual shadow evaluation records */}
  {shadowEvals.length > 0 && (
    <div>
      <div className="text-xs text-cp-muted uppercase tracking-wider mb-2">Evaluation Details</div>
      <div className="space-y-3">
        {shadowEvals.map((ev) => (
          <div key={ev.trace_id} className="bg-cp-elevated border border-cp-border rounded p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono text-cp-muted">{ev.trace_id.slice(0, 12)}…</span>
              {ev.factuality_status && (
                <span className="text-xs px-1.5 py-0.5 rounded font-medium"
                  style={{
                    background: statusBg[ev.factuality_status] || "#42505e22",
                    color: statusFg[ev.factuality_status] || "#6b6b68",
                  }}>
                  {statusLabel[ev.factuality_status] || ev.factuality_status}
                </span>
              )}
            </div>

            {ev.factuality_score != null && (
              <div className="flex items-center gap-2">
                <div className="flex-1 h-1 rounded-full bg-cp-app">
                  <div className="h-full rounded-full" style={{
                    width: `${ev.factuality_score * 100}%`,
                    background: ev.factuality_score >= 0.8 ? "#16a34a"
                      : ev.factuality_score >= 0.6 ? "#d97706" : "#dc2626",
                  }} />
                </div>
                <span className="text-xs font-mono text-cp-text w-8 text-right">
                  {(ev.factuality_score * 100).toFixed(0)}%
                </span>
              </div>
            )}

            <div className="grid grid-cols-3 gap-2 text-xs">
              {ev.input_tokens != null && (
                <div>
                  <div className="text-cp-muted">In tokens</div>
                  <div className="text-cp-text font-mono">{ev.input_tokens}</div>
                </div>
              )}
              {ev.output_tokens != null && (
                <div>
                  <div className="text-cp-muted">Out tokens</div>
                  <div className="text-cp-text font-mono">{ev.output_tokens}</div>
                </div>
              )}
              {ev.estimated_cost_usd != null && (
                <div>
                  <div className="text-cp-muted">Cost</div>
                  <div className="text-cp-text font-mono">{fmtCost(ev.estimated_cost_usd)}</div>
                </div>
              )}
            </div>

            {ev.evaluated_at && (
              <div className="text-xs text-cp-muted">Evaluated {fmtTime(ev.evaluated_at)}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  )}

</div>

);
}
function TraceOverviewPane({
trace,
insights,
flatSpans,
traceCost,
traceInputTokens,
traceOutputTokens,
onHighlightNode,
}: {
trace: ApiTrace | null;
insights: ApiInsights | null;
flatSpans: ApiSpan[];
traceCost?: number | null;
traceInputTokens?: number | null;
traceOutputTokens?: number | null;
onHighlightNode: (id: string | null) => void;
}) {
if (!trace) return null;
const shadow = insights?.shadow;
const bottleneck = insights?.performance?.bottleneck;
const resolvedLatency = getResolvedRunDuration(trace, flatSpans, insights);
const resolvedCost =
traceCost != null && traceCost > 0
? traceCost
: getResolvedRunCost(trace, flatSpans, insights);
const factColor = shadow?.average_factuality_score != null
? shadow.average_factuality_score >= 0.8 ? "#16a34a" : shadow.average_factuality_score >= 0.6 ? "#d97706" : "#dc2626"
: null;
return (
<div className="flex-1 overflow-y-auto">

  {/* Trace identity */}
  <div className="px-4 pt-3 pb-3 border-b border-cp-border">
    <div className="flex items-center gap-2 mb-1.5">
      <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: statusColor(trace.status) }} />
      <span className="text-sm font-semibold text-cp-text capitalize">{trace.status}</span>
      <span className="text-xs text-cp-muted ml-auto">{fmtTime(trace.created_at)}</span>
    </div>
    <div className="flex items-center gap-2">
      <span className="text-xs font-mono text-cp-muted">{trace.id.slice(0, 18)}…</span>
      {trace.model && (
        <span className="ml-auto text-xs font-mono text-cp-muted bg-cp-elevated rounded px-1.5 py-0.5 flex-shrink-0">{trace.model}</span>
      )}
    </div>
  </div>

  <div className="p-4 space-y-3">

    {/* Metrics grid */}
    <div className="grid grid-cols-2 gap-2">
      {[
        { label: "Latency", value: fmtMs(resolvedLatency) },
        { label: "Cost", value: fmtCost(resolvedCost) },
        {
          label: "In Tokens",
          value:
            traceInputTokens != null
              ? traceInputTokens.toLocaleString()
              : "N/A",
        },
        {
          label: "Out Tokens",
          value:
            traceOutputTokens != null
              ? traceOutputTokens.toLocaleString()
              : "N/A",
        },
      ].map(({ label, value }) => (
        <div key={label} className="bg-cp-elevated rounded-lg p-3 border border-cp-border">
          <div className="text-xs text-cp-muted mb-1">{label}</div>
          <div className="text-base font-mono font-semibold text-cp-text">{value}</div>
        </div>
      ))}
    </div>

    {/* Safety flag */}
    {trace.safety_flag && (
      <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs">
        <div className="flex items-center gap-1.5 text-red-600 font-semibold mb-1">
          <Shield size={12} /> Safety Flag
        </div>
        {trace.safety_type && <div className="text-red-500">Type: {trace.safety_type}</div>}
        {trace.safety_action && <div className="text-red-500">Action: {trace.safety_action}</div>}
      </div>
    )}

    {/* Shadow Quality card */}
    {shadow && (
      <div className="rounded-lg border border-cp-border bg-cp-surface overflow-hidden">
        <div className="px-3 py-2 border-b border-cp-border bg-cp-elevated flex items-center justify-between">
          <span className="text-xs font-semibold text-cp-text">Shadow Quality</span>
          {shadow.average_factuality_score != null && (
            <span className="text-xs font-mono font-bold" style={{ color: factColor ?? undefined }}>
              {(shadow.average_factuality_score * 100).toFixed(0)}%
            </span>
          )}
        </div>
        <div className="p-3 space-y-2">
          {shadow.average_factuality_score != null ? (
            <>
              <div className="flex items-center gap-2">
                <span className="text-xs text-cp-secondary flex-1">Factuality</span>
                <div className="w-28 h-1.5 rounded-full bg-cp-elevated overflow-hidden">
                  <div className="h-full rounded-full transition-all" style={{
                    width: `${shadow.average_factuality_score * 100}%`,
                    background: factColor ?? "#6b6b68",
                  }} />
                </div>
              </div>
              <div className="flex gap-3 text-xs pt-1">
                {[
                  { label: "Supported", val: shadow.supported, color: "#16a34a" },
                  { label: "Partial", val: shadow.partially_supported, color: "#d97706" },
                  { label: "Unsupported", val: shadow.unsupported, color: "#dc2626" },
                ].map(item => (
                  <div key={item.label} className="flex flex-col items-center gap-0.5">
                    <span className="font-mono font-semibold" style={{ color: item.val > 0 ? item.color : "#9e9e9b" }}>
                      {item.val}
                    </span>
                    <span className="text-cp-muted" style={{ fontSize: 9 }}>{item.label}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="text-xs text-cp-muted py-1">
              {shadow.pending > 0 ? "Evaluation pending…" : "Not evaluated"}
            </div>
          )}
        </div>
      </div>
    )}

    {/* Performance card */}
    {bottleneck && (
      <div className="rounded-lg border border-cp-border bg-cp-surface overflow-hidden">
        <div className="px-3 py-2 border-b border-cp-border bg-cp-elevated">
          <span className="text-xs font-semibold text-cp-text">Performance</span>
        </div>
        <div className="p-3">
          <div className="text-xs text-cp-muted mb-0.5">Primary bottleneck</div>
          <div className="text-sm font-semibold text-cp-text">{bottleneck.name}</div>
          <div className="text-xs text-cp-muted mt-1">
            {fmtMs(bottleneck.duration_ms)} · {bottleneck.latency_share.toFixed(1)}% of span time
          </div>
        </div>
      </div>
    )}

    {/* Recommendations */}
    {insights?.recommendations && insights.recommendations.length > 0 && (
      <div className="rounded-lg border border-cp-border bg-cp-surface overflow-hidden">
        <div className="px-3 py-2 border-b border-cp-border bg-cp-elevated">
          <span className="text-xs font-semibold text-cp-text">Recommendations</span>
        </div>
        <div className="divide-y divide-cp-border">
          {insights.recommendations.map((rec, i) => (
            <button key={i} onClick={() => onHighlightNode(bottleneck?.span_id || null)}
              className="w-full text-left px-3 py-2.5 text-xs text-cp-secondary hover:bg-cp-elevated transition-colors flex gap-2">
              <AlertTriangle size={11} className="text-amber-500 flex-shrink-0 mt-0.5" />
              <span>{rec}</span>
            </button>
          ))}
        </div>
      </div>
    )}

    {/* Shadow evaluations */}
    {insights?.shadow_evaluations && insights.shadow_evaluations.length > 0 && (
      <div className="rounded-lg border border-cp-border bg-cp-surface overflow-hidden">
        <div className="px-3 py-2 border-b border-cp-border bg-cp-elevated">
          <span className="text-xs font-semibold text-cp-text">Shadow Evaluations</span>
        </div>
        <div className="divide-y divide-cp-border">
          {insights.shadow_evaluations.map(ev => {
            const sc = ev.factuality_status === "supported" ? "#16a34a"
              : ev.factuality_status === "partially_supported" ? "#d97706"
              : ev.factuality_status === "unsupported" ? "#dc2626" : "#6b6b68";
            return (
              <div key={ev.trace_id} className="px-3 py-2.5 space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-cp-muted">{ev.trace_id.slice(0, 10)}…</span>
                  {ev.factuality_score != null && (
                    <span className="text-xs font-mono font-bold" style={{ color: sc }}>
                      {(ev.factuality_score * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                {ev.factuality_status && (
                  <span className="inline-block text-xs px-2 py-0.5 rounded-full font-medium"
                    style={{ background: sc + "18", color: sc }}>
                    {ev.factuality_status.replace(/_/g, " ")}
                  </span>
                )}
                {/* Do not render evaluation input here: it may contain the evaluator/system prompt.
                    The overview should expose evaluation status and quality data, not prompt internals. */}
              </div>
            );
          })}
        </div>
      </div>
    )}

    {insights?.summary && (
      <div className="text-xs text-cp-secondary bg-cp-elevated border border-cp-border rounded p-3">
        {insights.summary}
      </div>
    )}
  </div>
</div>

);
}
// ─── Trace Investigation ──────────────────────────────────────────────────────
interface TraceInvestigationProps {
traceId: string;
sessionTraces: ApiTrace[];
onSelectTrace: (id: string) => void;
onBack: () => void;
}
function TraceInvestigation({ traceId, sessionTraces, onSelectTrace, onBack }: TraceInvestigationProps) {
const [detail, setDetail] = useState<ApiTraceDetail | null>(null);
const [insights, setInsights] = useState<ApiInsights | null>(null);
const [loading, setLoading] = useState(true);
const [error, setError] = useState<string | null>(null);
const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
const [highlightedNodeId, setHighlightedNodeId] = useState<string | null>(null);
const [runDurations, setRunDurations] = useState<Record<string, number | null>>({});
const [allTraces, setAllTraces] = useState<ApiTrace[]>(sessionTraces);
const [childTraces, setChildTraces] = useState<ApiTrace[]>([]);
useEffect(() => { setAllTraces(sessionTraces); }, [sessionTraces]);
useEffect(() => {
const tracesNeedingDuration = sessionTraces.filter(
trace => (trace.latency_ms == null || trace.latency_ms <= 0) && runDurations[trace.id] === undefined
);

if (tracesNeedingDuration.length === 0) return;

Promise.all(
  tracesNeedingDuration.map(async trace => {
    try {
      const data = await apiGetTraceDetail(trace.id);
      return [
        trace.id,
        getResolvedRunDuration(data.trace, data.spans || [], null),
      ] as const;
    } catch {
      return [trace.id, null] as const;
    }
  })
).then(results => {
  setRunDurations(previous => {
    const next = { ...previous };
    for (const [id, duration] of results) next[id] = duration;
    return next;
  });
});

}, [sessionTraces, runDurations]);
useEffect(() => {
let cancelled = false;
let refreshTimer: ReturnType<typeof setInterval> | null = null;

setLoading(true);
setError(null);
setSelectedNodeId(null);
setHighlightedNodeId(null);

const loadTrace = async (showLoading = false) => {
  if (showLoading) setLoading(true);

  try {
    const d = await apiGetTraceDetail(traceId);
    const ins: ApiInsights | null = await apiGet<ApiInsights>(
      `/traces/${traceId}/insights`
    ).catch(() => null);
    const resolvedRunId = d.trace?.run_id || sessionTraces.find(t => t.id === traceId)?.run_id;
    const freshTraces = resolvedRunId
      ? await apiGet<ApiTrace[]>(`/runs/${resolvedRunId}/traces?limit=2000`).catch(() => [])
      : sessionTraces;

    if (cancelled) return;

    // The trace endpoint is the source of truth for the currently selected
    // workflow. Rebuild the graph from the latest persisted spans every
    // refresh so a RUNNING workflow can progressively show new spans.
    const persisted = flattenSpans(d.spans || []);

    const enrichedGraph = d.graph
      ? {
          ...d.graph,
          nodes: (d.graph.nodes || []).map(g => {
            const span = resolveSpanForGraphNode(g, persisted);

            return {
              ...g,
              input: g.input ?? span?.input ?? null,
              output: g.output ?? span?.output ?? null,
              context: g.context ?? span?.context ?? null,
              parent_span_id: g.parent_span_id ?? span?.parent_span_id ?? null,
            };
          }),
        }
      : d.graph;

    const liveChildTraces = getChildTraces(freshTraces, traceId);

    setDetail({
      ...d,
      child_traces: liveChildTraces,
      graph: enrichedGraph,
    });
    setInsights(ins);
    setAllTraces(freshTraces);
    setChildTraces(liveChildTraces);

    // Once the backend says the workflow is no longer running, one final
    // refresh is enough. While it is running, keep polling so child LLM
    // traces and their token/cost data appear without reopening the run.
    if (d.trace?.status !== "running" && refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  } catch (err: any) {
    if (!cancelled) setError(err?.message || "Failed to load trace");
  } finally {
    if (!cancelled && showLoading) setLoading(false);
  }
};

loadTrace(true);

// This is the important live-run fix. Previously this page fetched the
// trace once, so a RUNNING workflow stayed frozen at whatever data existed
// at the moment it was opened. The OpenAI child trace may be created later,
// which is why completed runs showed tokens/cost while running runs showed
// only latency.
refreshTimer = setInterval(() => {
  loadTrace(false);
}, 1000);

return () => {
  cancelled = true;
  if (refreshTimer) clearInterval(refreshTimer);
};

}, [traceId]);
const flatSpans = detail ? flattenSpans(detail.spans) : [];
const { nodes, edges } = layoutGraph(detail);
const selectedNode = selectedNodeId ? nodes.find(n => n.id === selectedNodeId) ?? null : null;
// GET /traces is the live workflow snapshot and already enriches root
// workflow rows with child LLM usage. Prefer that snapshot over the initial
// session list or the detail endpoint for the overview metrics.
const liveRootTrace = allTraces.find(t => t.id === traceId) ?? null;
const currentTrace = liveRootTrace
? {
...(detail?.trace ?? {}),
...liveRootTrace,
} as ApiTrace
: detail?.trace
?? sessionTraces.find(t => t.id === traceId)
?? null;
const factScore = currentTrace?.factuality_score;
const currentRunDuration = currentTrace && detail
? getResolvedRunDuration(currentTrace, detail.spans || [], insights)
: currentTrace?.latency_ms ?? null;
const childTraceMetrics = currentTrace
? getChildTraceMetrics(allTraces, currentTrace.id)
: {
inputTokens: null,
outputTokens: null,
cost: null,
};
const currentRunInputTokens =
currentTrace?.input_tokens != null && currentTrace.input_tokens > 0
? currentTrace.input_tokens
: childTraceMetrics.inputTokens;
const currentRunOutputTokens =
currentTrace?.output_tokens != null && currentTrace.output_tokens > 0
? currentTrace.output_tokens
: childTraceMetrics.outputTokens;
const currentRunCost =
currentTrace?.estimated_cost_usd != null && currentTrace.estimated_cost_usd > 0
? currentTrace.estimated_cost_usd
: childTraceMetrics.cost;
return (
<div className="flex flex-col h-screen bg-cp-app">
{/* Header */}
<div className="flex items-center gap-3 px-4 h-12 border-b border-cp-border flex-shrink-0 bg-cp-surface">
<button onClick={onBack}
       className="flex items-center gap-1.5 text-xs text-cp-secondary hover\:text-cp-text transition-colors">
<ChevronLeft size={14} /> Back
</button>
<div className="w-px h-4 bg-cp-border" />
<span className="text-xs font-medium text-cp-text">
Run #{sessionTraces.length - sessionTraces.findIndex(t => t.id === traceId)}
</span>
<span className="text-xs text-cp-muted font-mono">{traceId.slice(0, 8)}…</span>
{currentTrace && (
<>
<span className="w-1.5 h-1.5 rounded-full" style={{ background: statusColor(currentTrace.status) }} />
<span className="text-xs text-cp-secondary capitalize">{currentTrace.status}</span>
<div className="w-px h-4 bg-cp-border" />
<span className="text-xs text-cp-muted">{fmtMs(currentRunDuration)}</span>
{currentRunCost != null && (
<span className="text-xs text-cp-muted">{fmtCost(currentRunCost)}</span>
)}
</>
)}
<div className="flex-1" />
{factScore != null && (
<div className="flex items-center gap-1.5 text-xs">
<span className="text-cp-muted">Quality</span>
<span className="font-mono" style={{
           color: factScore >= 0.8 ? "#16a34a" : factScore >= 0.6 ? "#d97706" : "#dc2626"
}}>
{(factScore * 100).toFixed(0)}%
</span>
</div>
)}
</div>

  {/* 3-pane layout */}
  <div className="flex flex-1 overflow-hidden">
    {/* Left: trace list */}
    <div className="w-56 border-r border-cp-border flex flex-col flex-shrink-0 bg-cp-surface">
      <div className="px-3 py-2 border-b border-cp-border">
        <div className="text-xs font-medium text-cp-secondary">Recent Traces</div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {sessionTraces.map((t, i) => {
          const runNum = sessionTraces.length - i;
          const d = new Date(t.created_at);
          const dateLabel = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
          const timeLabel = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
          return (
            <button key={t.id} onClick={() => onSelectTrace(t.id)}
              className={`w-full text-left px-3 py-3 border-b border-cp-border/50 transition-colors hover:bg-cp-hover ${
                t.id === traceId ? "bg-cp-active border-l-2 border-l-cp-purple" : ""
              }`}>
              <div className="flex items-center gap-1.5 mb-0.5">
                <span className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                  style={{ background: statusColor(t.status) }} />
                <span className="text-xs font-medium text-cp-text">Run #{runNum}</span>
              </div>
              <div className="text-xs text-cp-muted pl-3">{dateLabel} · {timeLabel}</div>
              <div className="flex gap-2 mt-1 pl-3 text-xs text-cp-muted">
                <span>{fmtMs(
                  t.latency_ms != null && t.latency_ms > 0
                    ? t.latency_ms
                    : runDurations[t.id] ?? t.latency_ms
                )}</span>
                {t.factuality_score != null && (
                  <span style={{
                    color: t.factuality_score >= 0.8 ? "#16a34a"
                      : t.factuality_score >= 0.6 ? "#d97706" : "#dc2626"
                  }}>
                    {(t.factuality_score * 100).toFixed(0)}%
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>

    {/* Center: canvas with grey outer frame */}
    <div className="flex-1 flex flex-col overflow-hidden bg-[#20201f] p-2">
      <div className="flex-1 flex flex-col rounded-xl overflow-hidden border border-cp-border/40 shadow-sm">
        {loading ? (
          <div className="flex-1 flex items-center justify-center text-cp-secondary text-sm gap-2 bg-cp-canvas">
            <Loader2 size={16} className="animate-spin" /> Loading trace…
          </div>
        ) : error ? (
          <div className="flex-1 flex items-center justify-center text-cp-error text-sm bg-cp-canvas">
            Failed to load: {error}
          </div>
        ) : (
          <WorkflowCanvas
            nodes={nodes}
            edges={edges}
            selectedNodeId={selectedNodeId}
            highlightedNodeId={highlightedNodeId}
            onSelectNode={setSelectedNodeId}
          />
        )}
      </div>
    </div>

    {/* Right: inspector */}
    <div className="w-[360px] border-l border-cp-border flex flex-col flex-shrink-0 bg-cp-surface overflow-hidden">
      {loading ? (
        <div className="flex-1 flex items-center justify-center text-cp-muted text-xs gap-2">
          <Loader2 size={14} className="animate-spin" /> Loading…
        </div>
      ) : (
        <NodeInspector
          node={selectedNode}
          trace={currentTrace}
          flatSpans={flatSpans}
          insights={insights}
          childTraces={childTraces}
          traceCost={currentRunCost}
          traceInputTokens={currentRunInputTokens}
          traceOutputTokens={currentRunOutputTokens}
          onHighlightNode={setHighlightedNodeId}
        />
      )}
    </div>
  </div>
</div>

);
}
// ─── Application Workspace ────────────────────────────────────────────────────
type AppTab = "overview" | "traces" | "analytics" | "reliability" | "quality" | "cost" | "safety";
interface AppWorkspaceProps {
app: AppGroup;
onBack: () => void;
onSelectTrace: (id: string) => void;
}
function ApplicationWorkspace({ app, onBack, onSelectTrace }: AppWorkspaceProps) {
const [tab, setTab] = useState<AppTab>("overview");
const [analytics, setAnalytics] = useState<ApiAnalytics | null>(null);
const [search, setSearch] = useState("");
const [runDurations, setRunDurations] = useState<Record<string, number | null>>({});
// The current API exposes application/run/trace/span resources but no
// application-scoped analytics endpoint. Keep this optional so the workspace
// remains usable without making a request that the backend cannot satisfy.
useEffect(() => { setAnalytics(null); }, []);
const filtered = app.traces.filter(t =>
!search ||
t.id.toLowerCase().includes(search.toLowerCase()) ||
(t.model || "").toLowerCase().includes(search.toLowerCase()) ||
t.status.toLowerCase().includes(search.toLowerCase())
);
const totalTokens = app.traces.reduce(
(s, t) => s + (t.input_tokens || 0) + (t.output_tokens || 0), 0
);
// Application errors and safety interventions are separate outcomes.
const blockedTraces = app.safetyTraces;
const blockedTraceIds = new Set(app.safetyTraces.map(t => t.id));
const appTraceById = new Map(app.traces.map(t => [t.id, t]));
const blockedRootIds = new Set<string>();

for (const safetyTrace of app.safetyTraces) {
  let currentId: string | null = safetyTrace.id;
  while (currentId) {
    if (appTraceById.has(currentId)) {
      blockedRootIds.add(currentId);
      break;
    }
    const current = app.safetyTraces.find(t => t.id === currentId);
    currentId = current?.parent_trace_id ?? null;
  }
}

const errorTraces = app.traces.filter(
  t =>
    t.status.trim().toLowerCase() === "error" &&
    !blockedRootIds.has(t.id)
  );
const safetyTraces = app.safetyTraces;
const latencyBuckets = [500, 1000, 2000, 5000, Infinity];
const latencyLabels = ["<0.5s", "0.5–1s", "1–2s", "2–5s", ">5s"];
const latencyData = latencyLabels.map((label, i) => ({
label,
count: app.traces.filter(t => {
const ms = t.latency_ms || 0;
const lo = latencyBuckets[i - 1] || 0;
return ms >= lo && ms < latencyBuckets[i];
}).length,
}));
// Shadow quality is derived from child evaluation traces. Keep this view
// factuality-only; the API does not expose separate grounding/relevance/etc.
const qualityData = [
{ name: "Supported", value: app.shadowCounts.supported, color: "#16a34a" },
{ name: "Partial", value: app.shadowCounts.partial, color: "#d97706" },
{ name: "Unsupported", value: app.shadowCounts.unsupported, color: "#dc2626" },
].filter(d => d.value > 0);
const TABS: { id: AppTab; label: string }[] = [
{ id: "overview", label: "Overview" },
{ id: "traces", label: "Traces" },
{ id: "analytics", label: "Analytics" },
{ id: "reliability", label: "Reliability" },
{ id: "quality", label: "Quality" },
{ id: "cost", label: "Cost" },
{ id: "safety", label: "Safety" },
];
const hc = healthColor(app.health);
useEffect(() => {
const tracesNeedingDuration = app.traces.filter(
trace =>
(trace.latency_ms == null || trace.latency_ms <= 0) &&
runDurations[trace.id] === undefined
);

if (tracesNeedingDuration.length === 0) return;

Promise.all(
  tracesNeedingDuration.map(async trace => {
    try {
      const data = await apiGetTraceDetail(trace.id);
      return [
        trace.id,
        getResolvedRunDuration(data.trace, data.spans || [], null),
      ] as const;
    } catch {
      return [trace.id, null] as const;
    }
  })
).then(results => {
  setRunDurations(previous => {
    const next = { ...previous };
    for (const [id, duration] of results) next[id] = duration;
    return next;
  });
});

}, [app.traces, runDurations]);
return (
<div className="flex flex-col h-screen bg-cp-app">
{/* App header */}
<div className="flex items-center gap-4 px-6 h-14 border-b border-cp-border flex-shrink-0 bg-cp-surface">
<button onClick={onBack}
       className="flex items-center gap-1.5 text-xs text-cp-secondary hover\:text-cp-text transition-colors">
<ChevronLeft size={14} /> Applications
</button>
<div className="w-px h-4 bg-cp-border" />
<div>
<div className="text-sm font-semibold text-cp-text">{app.name}</div>
<div className="text-xs text-cp-muted font-mono">ID {app.applicationId.slice(0, 8)}…</div>
</div>
<div className="flex items-center gap-1.5 ml-1">
<span className="w-2 h-2 rounded-full" style={{ background: hc }} />
<span className="text-xs font-medium capitalize" style={{ color: hc }}>{app.health}</span>
</div>
<div className="flex-1" />
<div className="flex items-center gap-4 text-xs text-cp-secondary">
<span>Reliability <span className="text-cp-text font-mono ml-1">{app.reliability.toFixed(1)}%</span></span>
{app.quality != null && <span>Quality <span className="text-cp-text font-mono ml-1">{app.quality.toFixed(0)}%</span></span>}
{app.p95Latency != null && <span>P95 <span className="text-cp-text font-mono ml-1">{fmtMs(app.p95Latency)}</span></span>}
<span className="text-cp-muted">{app.traces.length} traces</span>
</div>
</div>

  {/* Tabs */}
  <div className="flex border-b border-cp-border bg-cp-surface flex-shrink-0">
    {TABS.map(t => (
      <button key={t.id} onClick={() => setTab(t.id)}
        className={`px-4 py-2.5 text-xs font-medium transition-colors whitespace-nowrap ${
          tab === t.id
            ? "text-cp-text border-b-2 border-cp-purple -mb-px bg-cp-app"
            : "text-cp-secondary hover:text-cp-text"
        }`}>
        {t.label}
      </button>
    ))}
  </div>

  <div className="flex-1 overflow-y-auto p-6">
    {/* OVERVIEW */}
    {tab === "overview" && (
      <div className="space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: "Total Traces", value: String(app.traces.length), icon: Activity },
            { label: "Reliability", value: `${app.reliability.toFixed(1)}%`, icon: CheckCircle,
              color: app.reliability >= 97 ? "#16a34a" : app.reliability >= 90 ? "#d97706" : "#dc2626" },
            { label: "Quality", value: app.quality != null ? `${app.quality.toFixed(0)}%` : "N/A",
              icon: Zap,
              color: app.quality == null ? "#6b6b68" : app.quality >= 90 ? "#16a34a" : app.quality >= 80 ? "#d97706" : "#dc2626" },
            { label: "P95 Latency", value: fmtMs(app.p95Latency), icon: Clock },
            { label: "Avg Latency", value: fmtMs(app.avgLatency), icon: TrendingUp },
            { label: "Total Cost", value: fmtCost(app.totalCost), icon: DollarSign },
            { label: "Total Tokens", value: totalTokens > 0 ? totalTokens.toLocaleString() : "N/A", icon: Cpu },
            { label: "Safety Flags", value: String(app.safetyFlags), icon: Shield,
              color: app.safetyFlags > 0 ? "#dc2626" : "#16a34a" },
          ].map(({ label, value, icon: Icon, color }) => (
            <div key={label} className="bg-cp-surface border border-cp-border rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-cp-muted">{label}</span>
                <Icon size={14} className="text-cp-muted" />
              </div>
              <div className="text-xl font-bold font-mono" style={{ color: color || "#1a1a18" }}>
                {value}
              </div>
            </div>
          ))}
        </div>

        <div>
          <div className="text-sm font-medium text-cp-text mb-3">Recent Traces</div>
          <div className="bg-cp-surface border border-cp-border rounded-lg overflow-hidden">
            {app.traces.slice(0, 8).map((t, i) => (
              <button key={t.id} onClick={() => onSelectTrace(t.id)}
                className={`w-full flex items-center gap-4 px-4 py-3 text-left hover:bg-cp-hover transition-colors ${i > 0 ? "border-t border-cp-border/50" : ""}`}>
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: statusColor(t.status) }} />
                <span className="text-xs font-medium text-cp-secondary flex-1 truncate">Run #{app.traces.length - i}</span>
                <span className="text-xs text-cp-muted">{fmtTime(t.created_at)}</span>
                <span className="text-xs font-mono text-cp-secondary w-16 text-right">{fmtMs(
                  t.latency_ms != null && t.latency_ms > 0
                    ? t.latency_ms
                    : runDurations[t.id] ?? t.latency_ms
                )}</span>
                {t.factuality_score != null && (
                  <span className="text-xs font-mono w-10 text-right" style={{
                    color: t.factuality_score >= 0.8 ? "#16a34a" : t.factuality_score >= 0.6 ? "#d97706" : "#dc2626"
                  }}>
                    {(t.factuality_score * 100).toFixed(0)}%
                  </span>
                )}
                <ArrowRight size={12} className="text-cp-muted" />
              </button>
            ))}
            {app.traces.length === 0 && (
              <div className="px-4 py-8 text-center text-xs text-cp-muted">No traces yet.</div>
            )}
          </div>
        </div>
      </div>
    )}

    {/* TRACES */}
    {tab === "traces" && (
      <div className="space-y-4">
        <div className="relative max-w-sm">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-cp-muted" />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search by ID, model, status…"
            className="w-full bg-cp-elevated border border-cp-border rounded pl-8 pr-3 py-2 text-xs text-cp-text placeholder-cp-muted outline-none focus:border-cp-border-strong" />
        </div>

        <div className="bg-cp-surface border border-cp-border rounded-lg overflow-hidden">
          <div className="flex items-center gap-3 px-4 py-2 border-b border-cp-border text-xs text-cp-muted">
            <span className="w-5" />
            <span className="flex-1">Trace ID</span>
            <span className="w-28">Model</span>
            <span className="w-20 text-right">Latency</span>
            <span className="w-16 text-right">Cost</span>
            <span className="w-14 text-right">Quality</span>
            <span className="w-20 text-right">Time</span>
            <span className="w-4" />
          </div>
          {filtered.map((t, i) => (
            <button key={t.id} onClick={() => onSelectTrace(t.id)}
              className={`w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-cp-hover transition-colors ${i > 0 ? "border-t border-cp-border/50" : ""}`}>
              <span className="w-5 flex justify-center">
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: statusColor(t.status) }} />
              </span>
              <span className="text-xs font-mono text-cp-secondary flex-1 truncate">{t.id}</span>
              <span className="text-xs text-cp-muted w-28 truncate">{t.model || "N/A"}</span>
              <span className="text-xs font-mono text-cp-secondary w-20 text-right">{fmtMs(
                  t.latency_ms != null && t.latency_ms > 0
                    ? t.latency_ms
                    : runDurations[t.id] ?? t.latency_ms
                )}</span>
              <span className="text-xs font-mono text-cp-muted w-16 text-right">{fmtCost(t.estimated_cost_usd)}</span>
              <span className="text-xs font-mono w-14 text-right" style={{
                color: t.factuality_score == null ? "#9e9e9b"
                  : t.factuality_score >= 0.8 ? "#16a34a"
                  : t.factuality_score >= 0.6 ? "#d97706" : "#dc2626"
              }}>
                {t.factuality_score != null ? `${(t.factuality_score * 100).toFixed(0)}%` : "—"}
              </span>
              <span className="text-xs text-cp-muted w-20 text-right">{fmtTime(t.created_at)}</span>
              <ArrowRight size={12} className="text-cp-muted w-4" />
            </button>
          ))}
          {filtered.length === 0 && (
            <div className="px-4 py-8 text-center text-xs text-cp-muted">No traces match.</div>
          )}
        </div>
      </div>
    )}

    {/* ANALYTICS */}
    {tab === "analytics" && (
      <div className="space-y-6">
        <div className="bg-cp-surface border border-cp-border rounded-lg p-4">
          <div className="text-sm font-medium text-cp-text mb-4">Latency Distribution</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={latencyData} barSize={32}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e2" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#6b6b68" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#6b6b68" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid #e4e4e2", borderRadius: 4, fontSize: 11 }} />
              <Bar dataKey="count" name="Traces" fill="#2563eb" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {analytics?.models && analytics.models.length > 0 && (
          <div className="bg-cp-surface border border-cp-border rounded-lg p-4">
            <div className="text-sm font-medium text-cp-text mb-4">Model Breakdown</div>
            <div className="space-y-3">
              {analytics.models.map(m => {
                const maxReqs = Math.max(...analytics.models.map(x => x.requests));
                return (
                  <div key={`${m.provider}:${m.model}`} className="flex items-center gap-3 text-xs">
                    <span className="font-mono text-cp-text w-44 truncate">
                      {m.provider ? `${m.provider} / ${m.model}` : m.model}
                    </span>
                    <div className="flex-1 h-1.5 bg-cp-elevated rounded-full">
                      <div className="h-full rounded-full bg-cp-blue"
                        style={{ width: `${(m.requests / maxReqs) * 100}%` }} />
                    </div>
                    <span className="text-cp-secondary w-14 text-right">{m.requests} req</span>
                    <span className="text-cp-muted w-16 text-right">{fmtMs(m.average_latency_ms)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {analytics?.spans && analytics.spans.length > 0 && (
          <div className="bg-cp-surface border border-cp-border rounded-lg p-4">
            <div className="text-sm font-medium text-cp-text mb-4">Span Types</div>
            <div className="space-y-2">
              {analytics.spans.map(s => {
                const maxCount = Math.max(...analytics.spans.map(x => x.count));
                return (
                  <div key={s.span_type} className="flex items-center gap-3 text-xs">
                    <span className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ background: KIND_COLOR[s.span_type] || "#6e7a8a" }} />
                    <span className="text-cp-text capitalize w-24">{s.span_type}</span>
                    <div className="flex-1 h-1 bg-cp-elevated rounded-full">
                      <div className="h-full rounded-full"
                        style={{ width: `${(s.count / maxCount) * 100}%`, background: KIND_COLOR[s.span_type] || "#6e7a8a" }} />
                    </div>
                    <span className="text-cp-secondary w-10 text-right">{s.count}</span>
                    <span className="text-cp-muted w-16 text-right">{fmtMs(s.average_duration_ms)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {!analytics && (
          <div className="text-xs text-cp-muted text-center py-8">
            Analytics unavailable — backend not connected.
          </div>
        )}
      </div>
    )}

    {/* RELIABILITY */}
    {tab === "reliability" && (
      <div className="space-y-6">
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Success Rate", value: `${app.reliability.toFixed(1)}%`,
              color: app.reliability >= 97 ? "#16a34a" : "#d97706" },
            { label: "Error Traces", value: String(errorTraces.length),
              color: errorTraces.length > 0 ? "#dc2626" : "#16a34a" },
            { label: "Blocked", value: String(blockedRootIds.size),
              color: blockedRootIds.size > 0 ? "#d97706" : "#16a34a" },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-cp-surface border border-cp-border rounded-lg p-4 text-center">
              <div className="text-2xl font-bold font-mono" style={{ color }}>{value}</div>
              <div className="text-xs text-cp-muted mt-1">{label}</div>
            </div>
          ))}
        </div>

        {errorTraces.length > 0 && (
          <div>
            <div className="text-sm font-medium text-cp-text mb-3">Failed Traces</div>
            <div className="bg-cp-surface border border-cp-border rounded-lg overflow-hidden">
              {errorTraces.map((t, i) => (
                <button key={t.id} onClick={() => onSelectTrace(t.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-cp-hover transition-colors ${i > 0 ? "border-t border-cp-border/50" : ""}`}>
                  <XCircle size={12} className="text-cp-error flex-shrink-0" />
                  <span className="text-xs font-mono text-cp-secondary flex-1 truncate">{t.id}</span>
                  <span className="text-xs text-cp-muted">{fmtTime(t.created_at)}</span>
                  <span className="text-xs px-1.5 py-0.5 rounded capitalize"
                    style={{ background: statusColor(t.status) + "22", color: statusColor(t.status) }}>
                    {t.status}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {errorTraces.length === 0 && (
          <div className="flex flex-col items-center py-16 text-cp-secondary">
            <CheckCircle size={32} className="text-cp-success mb-3" />
            <div className="text-sm">All traces succeeded</div>
          </div>
        )}
      </div>
    )}

    {/* QUALITY */}
    {tab === "quality" && (
      <div className="space-y-6">
        {(() => {
          const evaluations = app.shadowEvaluations.filter(
            e => e.factuality_score != null
          );
          const evaluatedCount = evaluations.length;
          const totalCount = app.shadowEvaluations.length;
          const averageScore = evaluatedCount > 0
            ? evaluations.reduce((sum, e) => sum + (e.factuality_score ?? 0), 0) / evaluatedCount
            : null;
          const lostPoints = averageScore != null
            ? Math.max(0, (1 - averageScore) * 100)
            : null;

          const belowPerfect = evaluations
            .filter(e => (e.factuality_score ?? 1) < 1)
            .sort((a, b) => (a.factuality_score ?? 0) - (b.factuality_score ?? 0));

          // The API may not provide factuality_status. In that case, derive
          // display buckets directly from the numerical factuality score:
          // 100% = supported, 1-99% = partially supported, 0% = unsupported.
          const factualityBuckets = evaluations.reduce(
            (counts, e) => {
              const score = e.factuality_score ?? 0;
              if (score >= 1) counts.supported += 1;
              else if (score <= 0) counts.unsupported += 1;
              else counts.partial += 1;
              return counts;
            },
            { supported: 0, partial: 0, unsupported: 0 }
          );

          const scoreLabel =
            averageScore == null ? "Not evaluated" :
            averageScore >= 0.9 ? "Strong factuality" :
            averageScore >= 0.8 ? "Generally reliable" :
            averageScore >= 0.6 ? "Needs review" :
            "Poor factuality";

          return (
            <>
              <div className="bg-cp-surface border border-cp-border rounded-lg p-5">
                <div className="flex items-start justify-between gap-8">
                  <div className="flex-1">
                    <div className="text-xs text-cp-muted uppercase tracking-wider mb-2">
                      Factuality
                    </div>
                    <div className="flex items-baseline gap-3">
                      <div className="text-4xl font-bold font-mono" style={{
                        color: averageScore == null ? "#9e9e9b"
                          : averageScore >= 0.9 ? "#16a34a"
                          : averageScore >= 0.8 ? "#d97706"
                          : "#dc2626"
                      }}>
                        {averageScore != null ? `${(averageScore * 100).toFixed(0)}%` : "N/A"}
                      </div>
                      <span className="text-sm font-medium text-cp-secondary">
                        {scoreLabel}
                      </span>
                    </div>
                    <p className="text-xs text-cp-secondary leading-5 mt-2 max-w-3xl">
                      Shadow evaluated {evaluatedCount} response{evaluatedCount === 1 ? "" : "s"}.
                      The headline score is the average of those individual factuality scores.
                    </p>
                  </div>

                  <div className="w-48 flex-shrink-0">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-cp-muted">Evaluated</span>
                      <span className="font-mono text-cp-text">
                        {evaluatedCount} / {totalCount}
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-cp-elevated overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${totalCount > 0 ? (evaluatedCount / totalCount) * 100 : 0}%`,
                          background: "#2563eb"
                        }}
                      />
                    </div>
                    {app.shadowCounts.pending > 0 && (
                      <div className="text-xs text-cp-muted mt-1">
                        {app.shadowCounts.pending} pending
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="bg-cp-surface border border-cp-border rounded-lg p-5">
                <div className="flex items-center justify-between gap-6">
                  <div>
                    <div className="text-sm font-medium text-cp-text">
                      Why is the score {averageScore != null ? `${(averageScore * 100).toFixed(0)}%` : "N/A"}?
                    </div>
                    <div className="text-xs text-cp-muted mt-1">
                      These rows show the application traces behind the headline average. Each row represents one evaluated agent response, with its application trace ID and factuality result.
                    </div>
                  </div>
                  {lostPoints != null && (
                    <div className="text-right">
                      <div className="text-xs text-cp-muted">Gap from 100%</div>
                      <div className="text-lg font-bold font-mono text-cp-text">
                        {lostPoints.toFixed(0)} pts
                      </div>
                    </div>
                  )}
                </div>

                {evaluations.length === 0 ? (
                  <div className="mt-4 rounded-lg border border-cp-border bg-cp-elevated p-4 text-xs text-cp-secondary">
                    No completed factuality scores are available.
                  </div>
                ) : belowPerfect.length === 0 ? (
                  <div className="mt-4 rounded-lg border border-cp-border bg-cp-elevated p-4 text-xs text-cp-secondary">
                    Every completed evaluation scored 100%, so the average is 100%.
                  </div>
                ) : (
                  <div className="mt-4 space-y-2">
                    {belowPerfect.map((ev, index) => {
                      const score = ev.factuality_score ?? 0;
                      const gap = Math.max(0, (1 - score) * 100);
                      // Keep the displayed bucket consistent with the numerical score.
                      // Shadow status can be absent or use a non-factuality label such as
                      // "not_applicable", so the score remains the source of truth here.
                      const status = score >= 1
                        ? "Supported"
                        : score <= 0
                          ? "Unsupported"
                          : "Partially supported";
                      const shadowTraceId = ev.trace_id;
                      const traceId = ev.application_trace_id || ev.trace_id;
                      const canOpenTrace = Boolean(ev.application_trace_id);

                      return (
                        <button
                          type="button"
                          key={`${ev.trace_id}-${index}`}
                          onClick={() => {
                            if (canOpenTrace) onSelectTrace(traceId);
                          }}
                          disabled={!canOpenTrace}
                          className={`w-full text-left rounded-lg border border-cp-border bg-cp-elevated p-3 ${
                            canOpenTrace ? "hover:bg-cp-hover transition-colors cursor-pointer" : "cursor-default"
                          }`}
                          title={
                            canOpenTrace
                              ? `Open application trace ${traceId}`
                              : `Shadow evaluation ${shadowTraceId}`
                          }
                        >
                          <div className="flex items-center justify-between gap-4">
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-mono text-cp-muted">
                                  Trace ID
                                </span>
                                <span className="text-xs px-1.5 py-0.5 rounded bg-cp-app text-cp-secondary">
                                  {status}
                                </span>
                              </div>
                              <div
                                className="text-xs text-cp-secondary mt-1 font-mono truncate"
                                title={traceId}
                              >
                                {traceId}
                              </div>
                              {!canOpenTrace && (
                                <div className="text-[10px] text-cp-muted mt-1">
                                  Application trace unavailable for this evaluation.
                                </div>
                              )}
                            </div>

                            <div className="flex items-center gap-3 flex-shrink-0">
                              <div className="w-28 h-1.5 rounded-full bg-cp-app overflow-hidden">
                                <div
                                  className="h-full rounded-full"
                                  style={{
                                    width: `${score * 100}%`,
                                    background: score >= 0.8 ? "#16a34a"
                                      : score >= 0.6 ? "#d97706"
                                      : "#dc2626"
                                  }}
                                />
                              </div>
                              <div className="text-right w-16">
                                <div className="text-sm font-bold font-mono text-cp-text">
                                  {(score * 100).toFixed(0)}%
                                </div>
                                <div className="text-[10px] text-cp-muted">
                                  −{gap.toFixed(0)} pts
                                </div>
                              </div>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}

                {belowPerfect.length > 0 && (
                  <div className="mt-4 text-xs text-cp-muted">
                    Lower-scoring evaluations are shown first. Their individual scores
                    are what pull the application average below 100%.
                  </div>
                )}
              </div>

              <div className="bg-cp-surface border border-cp-border rounded-lg p-5">
                <div className="text-sm font-medium text-cp-text mb-1">
                  How to interpret factuality
                </div>
                <div className="text-xs text-cp-secondary leading-5">
                  Factuality is Shadow's assessment of whether an agent response is
                  supported by the information available to the evaluation. It is a
                  quality signal, not a guarantee of correctness.
                </div>

                <div className="grid grid-cols-3 gap-3 mt-4">
                  <div className="rounded-lg border border-cp-border bg-cp-elevated p-3">
                    <div className="text-xs font-medium text-cp-text">Supported</div>
                    <div className="text-lg font-bold font-mono text-cp-text mt-1">
                      {factualityBuckets.supported}
                    </div>
                  </div>
                  <div className="rounded-lg border border-cp-border bg-cp-elevated p-3">
                    <div className="text-xs font-medium text-cp-text">Partially supported</div>
                    <div className="text-lg font-bold font-mono text-cp-text mt-1">
                      {factualityBuckets.partial}
                    </div>
                  </div>
                  <div className="rounded-lg border border-cp-border bg-cp-elevated p-3">
                    <div className="text-xs font-medium text-cp-text">Unsupported</div>
                    <div className="text-lg font-bold font-mono text-cp-text mt-1">
                      {factualityBuckets.unsupported}
                    </div>
                  </div>
                </div>

                {evaluatedCount > 0 && (
                  <div className="mt-3 text-xs text-cp-muted">
                    These buckets are derived from the numerical Shadow factuality scores:
                    100% is supported, 1–99% is partially supported, and 0% is unsupported.
                    The numerical scores remain the source of truth for the headline average.
                  </div>
                )}
              </div>

              <div className="bg-cp-surface border border-cp-border rounded-lg p-5">
                <div className="text-sm font-medium text-cp-text mb-2">
                  What to investigate
                </div>
                {belowPerfect.length > 0 ? (
                  <div className="text-xs text-cp-secondary leading-5">
                    Start with the lowest-scoring evaluation above. Open its trace and
                    compare the agent response with the evidence available to it.
                    That is where the lost points are coming from.
                  </div>
                ) : evaluatedCount > 0 ? (
                  <div className="text-xs text-cp-secondary leading-5">
                    Every completed evaluation is 100%. If the headline score is not
                    100%, the score and evaluation set are inconsistent and should be refreshed.
                  </div>
                ) : (
                  <div className="text-xs text-cp-secondary leading-5">
                    There are no completed factuality evaluations yet.
                  </div>
                )}
              </div>
            </>
          );
        })()}
      </div>
    )}
    {/* COST */}
    {tab === "cost" && (
      <div className="space-y-6">
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Total Cost", value: fmtCost(app.totalCost) },
            { label: "Avg per Trace", value: app.traces.length > 0 ? fmtCost(app.totalCost / app.traces.length) : "N/A" },
            { label: "Total Tokens", value: totalTokens > 0 ? totalTokens.toLocaleString() : "N/A" },
          ].map(({ label, value }) => (
            <div key={label} className="bg-cp-surface border border-cp-border rounded-lg p-4">
              <div className="text-xs text-cp-muted mb-1">{label}</div>
              <div className="text-2xl font-bold font-mono text-cp-text">{value}</div>
            </div>
          ))}
        </div>

        {analytics?.models && analytics.models.length > 0 && (
          <div className="bg-cp-surface border border-cp-border rounded-lg p-4">
            <div className="text-sm font-medium text-cp-text mb-4">Cost by Model</div>
            <div className="space-y-3">
              {analytics.models.map(m => {
                const maxCost = Math.max(...analytics.models.map(x => x.total_cost_usd));
                return (
                  <div key={`${m.provider}:${m.model}`}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="font-mono text-cp-text">
                        {m.provider ? `${m.provider} / ${m.model}` : m.model}
                      </span>
                      <span className="text-cp-secondary">{fmtCost(m.total_cost_usd)}</span>
                    </div>
                    <div className="h-1.5 bg-cp-elevated rounded-full">
                      <div className="h-full rounded-full bg-amber-600"
                        style={{ width: `${maxCost > 0 ? (m.total_cost_usd / maxCost) * 100 : 0}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {analytics?.most_expensive_requests && analytics.most_expensive_requests.length > 0 && (
          <div className="bg-cp-surface border border-cp-border rounded-lg p-4">
            <div className="text-sm font-medium text-cp-text mb-3">Most Expensive Traces</div>
            {analytics.most_expensive_requests.map((r, i) => (
              <button key={r.trace_id} onClick={() => onSelectTrace(r.trace_id)}
                className={`w-full flex items-center gap-4 py-2 text-left text-xs hover:text-cp-text text-cp-secondary transition-colors ${i > 0 ? "border-t border-cp-border/50" : ""}`}>
                <span className="font-mono flex-1 truncate">{r.trace_id.slice(0, 16)}…</span>
                <span className="text-cp-text font-mono">{fmtCost(r.estimated_cost_usd)}</span>
                <span className="text-cp-muted">{(r.input_tokens + r.output_tokens).toLocaleString()} tokens</span>
              </button>
            ))}
          </div>
        )}
      </div>
    )}

    {/* SAFETY */}
    {tab === "safety" && (
      <div className="space-y-6">
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Safety Flags", value: String(app.safetyFlags),
              color: app.safetyFlags > 0 ? "#dc2626" : "#16a34a" },
            { label: "Blocked", value: String(blockedRootIds.size),
              color: blockedRootIds.size > 0 ? "#d97706" : "#16a34a" },
            { label: "Safe Rate", value: `${((1 - blockedRootIds.size / Math.max(1, app.traces.length)) * 100).toFixed(1)}%`,
              color: blockedRootIds.size > 0 ? "#d97706" : "#16a34a" },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-cp-surface border border-cp-border rounded-lg p-4 text-center">
              <div className="text-3xl font-bold font-mono" style={{ color }}>{value}</div>
              <div className="text-xs text-cp-muted mt-1">{label}</div>
            </div>
          ))}
        </div>

        {safetyTraces.length > 0 ? (
          <div>
            <div className="text-sm font-medium text-cp-text mb-3">Flagged Traces</div>
            <div className="bg-cp-surface border border-cp-border rounded-lg overflow-hidden">
              {safetyTraces.map((t, i) => (
                <button key={t.id} onClick={() => onSelectTrace(t.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-cp-hover transition-colors ${i > 0 ? "border-t border-cp-border/50" : ""}`}>
                  <Shield size={12} className="text-cp-error flex-shrink-0" />
                  <span className="text-xs font-mono text-cp-secondary flex-1 truncate">{t.id}</span>
                  <span className="text-xs text-cp-muted">{t.safety_type || "N/A"}</span>
                  <span className="text-xs text-cp-muted">{t.safety_action || "N/A"}</span>
                  <span className="text-xs text-cp-muted">{fmtTime(t.created_at)}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center py-16 text-cp-secondary">
            <Shield size={32} className="text-cp-success mb-3" />
            <div className="text-sm">No safety violations detected</div>
          </div>
        )}
      </div>
    )}
  </div>
</div>

);
}
// ─── Applications Home ────────────────────────────────────────────────────────
function ApplicationsHome({ onSelectApp }: { onSelectApp: (app: AppGroup) => void }) {
const [apps, setApps] = useState<AppGroup[]>([]);
const [loading, setLoading] = useState(true);
const [error, setError] = useState<string | null>(null);
const [search, setSearch] = useState("");
const [filter, setFilter] = useState<"all" | "healthy" | "warning" | "critical">("all");
const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
const load = useCallback(async () => {
  setLoading(true);
  setError(null);
  try {
    const nextApps = await loadApplicationGroups();
    setApps(nextApps);
  } catch (err: any) {
    setError(err?.message || "Failed to load applications");
  } finally {
    setLoading(false);
  }
}, []);
useEffect(() => { load(); }, [load]);

const filtered = apps.filter(a => {
  if (filter !== "all" && a.health !== filter) return false;
  if (search && !a.name.toLowerCase().includes(search.toLowerCase()) &&
      !a.applicationId.toLowerCase().includes(search.toLowerCase())) return false;
  return true;
});
const counts = {
  healthy: apps.filter(a => a.health === "healthy").length,
  warning: apps.filter(a => a.health === "warning").length,
  critical: apps.filter(a => a.health === "critical").length,
};
return (
<div className="flex flex-col h-screen bg-cp-app">
{/* Top nav */}
<div className="flex items-center gap-4 px-6 h-14 border-b border-cp-border flex-shrink-0 bg-cp-surface">
<div className="flex items-center gap-2">
<div className="w-6 h-6 rounded bg-cp-purple flex items-center justify-center">
<Command size={12} className="text-white" />
</div>
<span className="text-sm font-bold text-cp-text tracking-tight">ControlPlane.AI</span>
</div>
<div className="flex-1" />
<div className="flex items-center gap-2">
<button onClick={load}
         className="flex items-center gap-1.5 text-xs text-cp-secondary hover\:text-cp-text px-2 py-1.5 rounded border border-cp-border hover\:border-cp-border-strong transition-colors">
<RefreshCw size={12} /> Refresh
</button>
<button className="p-1.5 rounded border border-cp-border text-cp-secondary hover\:text-cp-text transition-colors">
<Settings size={14} />
</button>
</div>
</div>

  <div className="flex-1 overflow-y-auto p-6">
    <div className="flex items-center justify-between mb-6">
      <div>
        <h1 className="text-xl font-bold text-cp-text">Applications</h1>
        <p className="text-xs text-cp-secondary mt-0.5">
          AI application observability and control plane
        </p>
      </div>
      <button className="flex items-center gap-1.5 text-xs bg-cp-purple text-white px-3 py-2 rounded hover\:bg-cp-purple/90 transition-colors">
        <Plus size={12} /> Add Application
      </button>
    </div>

    {!loading && !error && apps.length > 0 && (
      <div className="flex gap-4 mb-6">
        {[
          { label: "Healthy", count: counts.healthy, color: "#16a34a" },
          { label: "Warning", count: counts.warning, color: "#d97706" },
          { label: "Critical", count: counts.critical, color: "#dc2626" },
        ].map(({ label, count, color }) => (
          <div key={label} className="flex items-center gap-2 text-xs">
            <span className="w-2 h-2 rounded-full" style={{ background: color }} />
            <span className="text-cp-secondary">{label}</span>
            <span className="font-mono text-cp-text">{count}</span>
          </div>
        ))}
      </div>
    )}

    <div className="flex items-center gap-3 mb-6">
      <div className="relative flex-1 max-w-xs">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-cp-muted" />
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search applications…"
          className="w-full bg-cp-elevated border border-cp-border rounded pl-8 pr-3 py-2 text-xs text-cp-text placeholder-cp-muted outline-none focus:border-cp-border-strong" />
      </div>

      <div className="flex gap-0.5 bg-cp-elevated border border-cp-border rounded p-0.5">
        {(["all", "healthy", "warning", "critical"] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-2.5 py-1 text-xs rounded capitalize transition-colors ${
              filter === f ? "bg-cp-active text-cp-text" : "text-cp-secondary hover\:text-cp-text"
            }`}>
            {f}
          </button>
        ))}
      </div>

      <div className="flex gap-0.5 bg-cp-elevated border border-cp-border rounded p-0.5 ml-auto">
        <button onClick={() => setViewMode("grid")}
          className={`p-1.5 rounded transition-colors ${viewMode === "grid" ? "bg-cp-active text-cp-text" : "text-cp-muted hover\:text-cp-secondary"}`}>
          <Grid3x3 size={13} />
        </button>
        <button onClick={() => setViewMode("list")}
          className={`p-1.5 rounded transition-colors ${viewMode === "list" ? "bg-cp-active text-cp-text" : "text-cp-muted hover\:text-cp-secondary"}`}>
          <LayoutList size={13} />
        </button>
      </div>
    </div>

    {loading && (
      <div className="flex items-center justify-center py-24 text-cp-secondary text-sm gap-2">
        <Loader2 size={18} className="animate-spin" /> Connecting to backend…
      </div>
    )}

    {!loading && error && (
      <div className="flex flex-col items-center justify-center py-24">
        <AlertCircle size={32} className="text-cp-error mb-4" />
        <div className="text-sm font-medium text-cp-text mb-1">Cannot connect to backend</div>
        <div className="text-xs text-cp-secondary mb-4 max-w-sm text-center">
          Ensure the ControlPlane.AI API is running at <span className="font-mono text-cp-text">{API_BASE}</span>
        </div>
        <code className="text-xs text-cp-error bg-cp-elevated border border-cp-border rounded px-3 py-2">
          {error}
        </code>
        <button onClick={load}
          className="mt-4 text-xs text-cp-blue hover:underline flex items-center gap-1">
          <RefreshCw size={11} /> Try again
        </button>
      </div>
    )}

    {!loading && !error && apps.length === 0 && (
      <div className="flex flex-col items-center justify-center py-24 text-cp-secondary text-sm">
        <BarChart2 size={32} className="mb-3 text-cp-muted" />
        No applications found. Create an application and send your first run to get started.
      </div>
    )}

    {!loading && !error && filtered.length > 0 && (
      viewMode === "grid" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map(app => (
            <AppCard key={app.applicationId} app={app} onClick={() => onSelectApp(app)} />
          ))}
        </div>
      ) : (
        <AppListView apps={filtered} onSelect={onSelectApp} />
      )
    )}

    {!loading && !error && apps.length > 0 && filtered.length === 0 && (
      <div className="text-center py-16 text-xs text-cp-muted">
        No applications match your filters.
      </div>
    )}
  </div>
</div>
);
}

function AppCard({ app, onClick }: { app: AppGroup; onClick: () => void }) {
const hc = healthColor(app.health);
return (
<button onClick={onClick}
   className="bg-cp-surface border border-cp-border rounded-lg p-5 text-left hover\:bg-cp-hover hover\:border-cp-border-strong transition-all group text-left w-full">
<div className="flex items-start justify-between mb-4">
<div className="flex-1 min-w-0">
<div className="text-sm font-semibold text-cp-text truncate">
{app.name}
</div>
<div className="text-xs text-cp-muted font-mono truncate mt-0.5">ID {app.applicationId.slice(0, 8)}…</div>
</div>
<div className="flex items-center gap-1.5 ml-3 flex-shrink-0">
<span className="w-2 h-2 rounded-full" style={{ background: hc }} />
<span className="text-xs font-medium capitalize" style={{ color: hc }}>{app.health}</span>
</div>
</div>

  <div className="grid grid-cols-2 gap-x-4 gap-y-2.5 mb-4">
    {[
      { label: "Reliability", value: `${app.reliability.toFixed(1)}%`,
        color: app.reliability >= 97 ? "#16a34a" : app.reliability >= 90 ? "#d97706" : "#dc2626" },
      { label: "Quality", value: app.quality != null ? `${app.quality.toFixed(0)}%` : "N/A",
        color: app.quality == null ? "#6b6b68" : app.quality >= 90 ? "#16a34a" : app.quality >= 80 ? "#d97706" : "#dc2626" },
      { label: "P95 Latency", value: fmtMs(app.p95Latency), color: undefined },
      { label: "Traces", value: app.traces.length.toLocaleString(), color: undefined },
    ].map(({ label, value, color }) => (
      <div key={label}>
        <div className="text-xs text-cp-muted">{label}</div>
        <div className="text-sm font-mono font-medium" style={{ color: color || "#1a1a18" }}>
          {value}
        </div>
      </div>
    ))}
  </div>

  <div className="flex items-center justify-between border-t border-cp-border pt-3">
    <span className="text-xs text-cp-muted">{fmtTime(app.lastActivity)}</span>
    <span className="text-xs text-cp-purple flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
      Open <ArrowRight size={11} />
    </span>
  </div>
</button>

);
}
function AppListView({ apps, onSelect }: { apps: AppGroup[]; onSelect: (a: AppGroup) => void }) {
return (
<div className="bg-cp-surface border border-cp-border rounded-lg overflow-hidden">
<div className="flex items-center gap-4 px-4 py-2 border-b border-cp-border text-xs text-cp-muted">
<span className="flex-1">Application</span>
<span className="w-24 text-right">Reliability</span>
<span className="w-20 text-right">Quality</span>
<span className="w-24 text-right">P95</span>
<span className="w-16 text-right">Traces</span>
<span className="w-20 text-right">Flags</span>
<span className="w-24 text-right">Last Active</span>
<span className="w-4" />
</div>
{apps.map((app, i) => {
const hc = healthColor(app.health);
return (
<button key={app.applicationId} onClick={() => onSelect(app)}
className={`w-full flex items-center gap-4 px-4 py-3 text-left hover:bg-cp-hover transition-colors ${i > 0 ? "border-t border-cp-border/50" : ""}`}>
<div className="flex items-center gap-2 flex-1 min-w-0">
<span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: hc }} />
<span className="text-sm text-cp-text font-medium truncate">{app.name}</span>
</div>
<span className="text-xs font-mono w-24 text-right" style={{
           color: app.reliability >= 97 ? "#16a34a" : app.reliability >= 90 ? "#d97706" : "#dc2626"
}}>
{app.reliability.toFixed(1)}%
</span>
<span className="text-xs font-mono w-20 text-right" style={{
color: app.quality == null ? "#9e9e9b" : app.quality >= 90 ? "#16a34a" : app.quality >= 80 ? "#d97706" : "#dc2626"
}}>
{app.quality != null ? `${app.quality.toFixed(0)}%` : "N/A"}
</span>
<span className="text-xs font-mono text-cp-secondary w-24 text-right">{fmtMs(app.p95Latency)}</span>
<span className="text-xs text-cp-secondary w-16 text-right">{app.traces.length.toLocaleString()}</span>
<span className="text-xs w-20 text-right"
           style={{ color: app.safetyFlags > 0 ? "#dc2626" : "#9e9e9b" }}>
{app.safetyFlags > 0 ? `${app.safetyFlags} flagged` : "—"}
</span>
<span className="text-xs text-cp-muted w-24 text-right">{fmtTime(app.lastActivity)}</span>
<ArrowRight size={12} className="text-cp-muted w-4" />
</button>
);
})}
</div>
);
}
// ─── Root App ─────────────────────────────────────────────────────────────────
export default function App(): React.JSX.Element {
const [screen, setScreen] = useState<Screen>("home");
const [selectedApp, setSelectedApp] = useState<AppGroup | null>(null);
const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
const handleSelectApp = (app: AppGroup) => {
setSelectedApp(app);
setScreen("app");
};
const handleSelectTrace = (traceId: string) => {
setSelectedTraceId(traceId);
setScreen("trace");
};
if (screen === "trace" && selectedTraceId && selectedApp) {
return (
<TraceInvestigation
traceId={selectedTraceId}
sessionTraces={selectedApp.traces}
onSelectTrace={handleSelectTrace}
onBack={() => { setSelectedTraceId(null); setScreen("app"); }}
/>
);
}
if (screen === "app" && selectedApp) {
return (
<ApplicationWorkspace
app={selectedApp}
onBack={() => { setSelectedApp(null); setScreen("home"); }}
onSelectTrace={handleSelectTrace}
/>
);
}
return <ApplicationsHome onSelectApp={handleSelectApp} />;
}
