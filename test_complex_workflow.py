import requests
import uuid
from time import sleep

API = "http://127.0.0.1:8000"

def uid():
    return str(uuid.uuid4())


def create_trace(trace_id, prompt, context, output):
    r = requests.post(
        f"{API}/traces",
        json={
            "id": trace_id,
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "input": prompt,
            "output": output,
            "input_tokens": 420,
            "output_tokens": 680,
            "latency_ms": 4200,
            "estimated_cost_usd": 0.0042,
            "context": context,
            "status": "success",
        },
    )

    r.raise_for_status()


def create_span(
    trace_id,
    name,
    span_type,
    input_text,
    output_text,
    parent=None,
    duration=300,
    metadata=None,
):
    span_id = uid()

    r = requests.post(
        f"{API}/spans",
        json={
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent,
            "name": name,
            "span_type": span_type,
            "input": input_text,
            "output": output_text,
            "duration_ms": duration,
            "status": "success",
            "metadata": metadata or {},
        },
    )

    r.raise_for_status()

    return span_id


# ============================================================
# TRACE
# ============================================================

trace_id = uid()

USER_PROMPT = (
    "A customer says their payment failed twice but their bank "
    "shows two pending charges. Determine what happened and "
    "prepare an appropriate response."
)

TRACE_CONTEXT = (
    "Customer: Sarah Chen\n"
    "Account ID: ACC-48291\n"
    "Payment provider: Stripe\n"
    "Currency: USD\n"
    "Recent order: ORD-92817"
)

FINAL_OUTPUT = (
    "The payment attempts were authorized but neither charge "
    "was captured. The duplicate pending charges should be "
    "released automatically by the payment provider. "
    "No second payment is required."
)

create_trace(
    trace_id,
    USER_PROMPT,
    TRACE_CONTEXT,
    FINAL_OUTPUT,
)


# ============================================================
# 1. API GATEWAY
# ============================================================

gateway = create_span(
    trace_id,
    "API Gateway",
    "chain",
    USER_PROMPT,
    "Request accepted and authenticated.",
    duration=120,
)


# ============================================================
# 2. REQUEST VALIDATOR
# ============================================================

validator = create_span(
    trace_id,
    "Request Validator",
    "chain",
    "Validate customer request and account metadata.",
    "Request valid. Account ACC-48291 found.",
    gateway,
    180,
)


# ============================================================
# 3. INTENT CLASSIFIER
# ============================================================

classifier = create_span(
    trace_id,
    "Intent Classifier",
    "chain",
    "Customer reports two pending payment charges.",
    "Intent = payment_failure_with_duplicate_pending_charges",
    validator,
    260,
)


# ============================================================
# 4. ROUTER
# ============================================================

router = create_span(
    trace_id,
    "Workflow Router",
    "chain",
    "payment_failure_with_duplicate_pending_charges",
    "Execute billing investigation workflow.",
    classifier,
    150,
)


# ============================================================
# BRANCH A — BILLING
# ============================================================

billing_agent = create_span(
    trace_id,
    "Billing Agent",
    "agent",
    "Investigate payment status for ORD-92817.",
    "Two payment attempts detected.",
    router,
    520,
)

billing_tool = create_span(
    trace_id,
    "Stripe Payment Lookup",
    "tool",
    "Lookup payment attempts for order ORD-92817.",
    (
        "Payment attempt 1: authorized, not captured\n"
        "Payment attempt 2: authorized, not captured"
    ),
    billing_agent,
    410,
)

billing_result = create_span(
    trace_id,
    "Billing Result",
    "chain",
    (
        "Payment attempt 1: authorized, not captured\n"
        "Payment attempt 2: authorized, not captured"
    ),
    "Both authorizations are pending and neither payment was captured.",
    billing_tool,
    240,
)


# ============================================================
# BRANCH B — FRAUD / SAFETY
# ============================================================

fraud_agent = create_span(
    trace_id,
    "Fraud Detection Agent",
    "agent",
    "Check whether duplicate payment attempts indicate fraud.",
    "No fraud indicators detected.",
    router,
    620,
)

fraud_tool = create_span(
    trace_id,
    "Fraud Risk Service",
    "tool",
    "Evaluate ACC-48291 and ORD-92817.",
    (
        "risk_score=0.03\n"
        "velocity_check=passed\n"
        "device_check=passed\n"
        "location_check=passed"
    ),
    fraud_agent,
    350,
)

fraud_result = create_span(
    trace_id,
    "Fraud Assessment",
    "chain",
    "risk_score=0.03",
    "Transaction pattern is legitimate; no escalation required.",
    fraud_tool,
    180,
)


# ============================================================
# BRANCH C — CUSTOMER ACCOUNT
# ============================================================

account_agent = create_span(
    trace_id,
    "Account Agent",
    "agent",
    "Retrieve customer account and order information.",
    "Account and order data retrieved.",
    router,
    480,
)

account_tool = create_span(
    trace_id,
    "Account Lookup",
    "tool",
    "Lookup ACC-48291 and ORD-92817.",
    (
        "Customer: Sarah Chen\n"
        "Order: ORD-92817\n"
        "Amount: $149.00\n"
        "Order status: payment_pending"
    ),
    account_agent,
    300,
)

account_result = create_span(
    trace_id,
    "Account Result",
    "chain",
    "Customer and order information.",
    "Order ORD-92817 is awaiting payment capture.",
    account_tool,
    190,
)


# ============================================================
# RETRIEVAL BRANCH
# ============================================================

retrieval = create_span(
    trace_id,
    "Policy Retrieval",
    "retriever",
    "Find policy for duplicate pending payment authorizations.",
    "Relevant payment authorization policy found.",
    router,
    430,
)

vector_search = create_span(
    trace_id,
    "Vector Search",
    "retriever",
    "Search payment support knowledge base.",
    (
        "KB-142: Authorized payments may remain pending "
        "until automatically released."
    ),
    retrieval,
    280,
)

reranker = create_span(
    trace_id,
    "Document Reranker",
    "retriever",
    "Rank retrieved payment-policy documents.",
    "KB-142 ranked as highest-confidence document.",
    vector_search,
    210,
)

policy_result = create_span(
    trace_id,
    "Policy Result",
    "chain",
    "KB-142: Authorized payments may remain pending.",
    "Pending authorizations do not necessarily represent captured charges.",
    reranker,
    170,
)


# ============================================================
# SYNTHESIS
# ============================================================

synthesis_input = """
Billing:
- Two payment attempts
- Both authorized
- Neither captured

Fraud:
- Risk score 0.03
- No fraud indicators

Account:
- Order ORD-92817
- $149.00
- payment_pending

Policy:
- Pending authorizations may be released automatically
"""

synthesis = create_span(
    trace_id,
    "Evidence Synthesizer",
    "chain",
    synthesis_input,
    (
        "The customer has two legitimate authorization holds. "
        "Neither transaction was captured."
    ),
    router,
    520,
)


# ============================================================
# FINAL LLM
# ============================================================

final_llm = create_span(
    trace_id,
    "Response Generator",
    "llm",
    (
        "Generate a customer-facing response using the billing, "
        "fraud, account, and policy evidence."
    ),
    (
        "The two charges are authorization holds rather than "
        "completed payments. Neither payment was captured. "
        "The holds should be released automatically."
    ),
    synthesis,
    780,
)


# ============================================================
# SAFETY CHECK
# ============================================================

safety = create_span(
    trace_id,
    "Safety / Policy Checker",
    "guardrail",
    (
        "Review proposed response for financial advice, "
        "unsupported claims, and sensitive information."
    ),
    "Response approved. No unsafe claims detected.",
    final_llm,
    260,
)


# ============================================================
# RESPONSE FORMATTER
# ============================================================

formatter = create_span(
    trace_id,
    "Response Formatter",
    "chain",
    (
        "Approved response:\n"
        "The two charges are authorization holds..."
    ),
    FINAL_OUTPUT,
    safety,
    210,
)


# ============================================================
# LOGGING FAN-OUT
# ============================================================

logging = create_span(
    trace_id,
    "Workflow Logging",
    "chain",
    FINAL_OUTPUT,
    "Workflow result recorded.",
    formatter,
    100,
)

metrics = create_span(
    trace_id,
    "Metrics",
    "tool",
    "Record latency=4200ms, tokens=1100.",
    "Metrics recorded.",
    logging,
    90,
)

audit = create_span(
    trace_id,
    "Audit Log",
    "tool",
    "Record workflow decision and payment investigation.",
    "Audit record created.",
    logging,
    90,
)

analytics = create_span(
    trace_id,
    "Analytics",
    "tool",
    "Record intent=payment_failure_with_duplicate_pending_charges.",
    "Analytics event recorded.",
    logging,
    90,
)


print()
print("=" * 70)
print("COMPLEX WORKFLOW CREATED")
print("=" * 70)
print()
print(f"Trace ID: {trace_id}")
print()
print(f"Open:")
print(f"http://localhost:5173/")
print()
print("Nodes created:")
print("  API Gateway")
print("  Request Validator")
print("  Intent Classifier")
print("  Workflow Router")
print("  Billing Agent")
print("  Stripe Payment Lookup")
print("  Billing Result")
print("  Fraud Detection Agent")
print("  Fraud Risk Service")
print("  Fraud Assessment")
print("  Account Agent")
print("  Account Lookup")
print("  Account Result")
print("  Policy Retrieval")
print("  Vector Search")
print("  Document Reranker")
print("  Policy Result")
print("  Evidence Synthesizer")
print("  Response Generator")
print("  Safety / Policy Checker")
print("  Response Formatter")
print("  Workflow Logging")
print("  Metrics")
print("  Audit Log")
print("  Analytics")
print()
print("Every span has its own input + output.")
print("=" * 70)