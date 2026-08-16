import asyncio
import uuid
from datetime import datetime, timezone

import httpx
import requests


# ============================================================
# CONFIG
# ============================================================

CONTROLPLANE = "http://127.0.0.1:8000"

# Deterministic location for the live API test.
LAT = 40.7128
LON = -74.0060
LOCATION = "New York City"

TRACE_TIMEOUT = 10
WEATHER_TIMEOUT = 15


# ============================================================
# HELPERS
# ============================================================

def new_id():
    return str(uuid.uuid4())


def post_json(path, payload):
    r = requests.post(
        f"{CONTROLPLANE}{path}",
        json=payload,
        timeout=TRACE_TIMEOUT,
    )
    r.raise_for_status()
    return r.json() if r.content else None


def get_json(path):
    r = requests.get(
        f"{CONTROLPLANE}{path}",
        timeout=TRACE_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def create_trace(trace_id, prompt, context):
    return post_json(
        "/traces",
        {
            "id": trace_id,
            "provider": "weather-agent",
            "model": "weather-agent-v1",
            "input": prompt,
            "output": None,
            "context": context,
            "status": "running",
            "latency_ms": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": 0,
        },
    )


def create_span(
    trace_id,
    name,
    span_type,
    input_data,
    output_data,
    parent=None,
    duration_ms=0,
    status="success",
    metadata=None,
    span_id=None,
    started_at=None,
    ended_at=None,
):
    span_id = span_id or new_id()

    payload = {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent,
        "name": name,
        "span_type": span_type,
        "input": input_data,
        "output": output_data,
        "duration_ms": duration_ms,
        "status": status,
        "metadata": metadata or {},
    }

    # Include timestamps when the backend accepts them. They make
    # parallelism and ordering independently verifiable.
    if started_at is not None:
        payload["started_at"] = started_at
    if ended_at is not None:
        payload["ended_at"] = ended_at

    post_json("/spans", payload)
    return span_id


def create_error_span(
    trace_id,
    name,
    span_type,
    input_data,
    exc,
    parent=None,
    metadata=None,
):
    return create_span(
        trace_id=trace_id,
        name=name,
        span_type=span_type,
        input_data=input_data,
        output_data={"error": str(exc)},
        parent=parent,
        duration_ms=0,
        status="error",
        metadata={
            **(metadata or {}),
            "error_type": type(exc).__name__,
        },
    )


def get_span_list(span_response):
    """
    Normalize ControlPlane span responses into a flat list.

    The current /spans/{trace_id} endpoint returns a plain list.
    Wrapped response shapes are supported for compatibility.
    """
    if isinstance(span_response, list):
        return span_response

    if isinstance(span_response, dict):
        spans = span_response.get("spans")
        if isinstance(spans, list):
            return spans

        data = span_response.get("data")
        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            spans = data.get("spans")
            if isinstance(spans, list):
                return spans

        trace = span_response.get("trace")
        if isinstance(trace, dict):
            spans = trace.get("spans")
            if isinstance(spans, list):
                return spans

    return []


# ============================================================
# REAL WEATHER TOOLS
# ============================================================

async def weather_tool():
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": LAT,
        "longitude": LON,
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "apparent_temperature,"
            "precipitation,"
            "rain,"
            "weather_code,"
            "wind_speed_10m"
        ),
        "hourly": (
            "temperature_2m,"
            "precipitation_probability,"
            "precipitation,"
            "weather_code,"
            "wind_speed_10m"
        ),
        "forecast_days": 2,
        "timezone": "auto",
    }

    async with httpx.AsyncClient(timeout=WEATHER_TIMEOUT) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


async def air_quality_tool():
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"

    params = {
        "latitude": LAT,
        "longitude": LON,
        "current": "pm10,pm2_5,us_aqi",
        "timezone": "auto",
    }

    async with httpx.AsyncClient(timeout=WEATHER_TIMEOUT) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


# ============================================================
# OBSERVABILITY VALIDATION
# ============================================================

def validate_spans(trace_id, trace_detail, expected_names):
    spans = get_span_list(trace_detail)

    failures = []

    if not spans:
        failures.append("No spans were returned by GET /spans/{trace_id}.")
        return failures, spans

    by_name = {str(s.get("name")): s for s in spans}

    # Every expected node must exist.
    for name in expected_names:
        if name not in by_name:
            failures.append(f"Missing expected span: {name}")

    # Every span must have the fields required for node-level I/O inspection.
    required = (
        "id",
        "trace_id",
        "name",
        "span_type",
        "input",
        "output",
        "status",
    )

    for span in spans:
        for field in required:
            if field not in span:
                failures.append(
                    f"Span {span.get('name', '<unnamed>')} is missing field '{field}'."
                )

        if str(span.get("trace_id")) != str(trace_id):
            failures.append(
                f"Span {span.get('name')} has the wrong trace_id."
            )

        if span.get("input") is None:
            failures.append(f"Span {span.get('name')} has null input.")

        if span.get("output") is None:
            failures.append(f"Span {span.get('name')} has null output.")

    # Parent references must point to spans in this trace.
    span_ids = {
        str(s.get("id"))
        for s in spans
        if s.get("id") is not None
    }

    for span in spans:
        parent = span.get("parent_span_id")
        if parent is not None and str(parent) not in span_ids:
            failures.append(
                f"Orphaned parent_span_id on {span.get('name')}: {parent}"
            )

    # Expected topology.
    parent_expectations = {
        "Parse Weather Request": None,
        "Validate Location": "Parse Weather Request",
        "Weather Tool": "Validate Location",
        "Air Quality Tool": "Validate Location",
        "Analyze Conditions": "Validate Location",
        "Recommendation Agent": None,  # checked below because it depends on the selected branch
        "Final Response": "Recommendation Agent",
        "Workflow Logger": "Final Response",
        "Metrics": "Workflow Logger",
        "Audit Log": "Workflow Logger",
        "Analytics": "Workflow Logger",
    }

    for child, parent_name in parent_expectations.items():
        if child not in by_name:
            continue
        if parent_name is None:
            continue

        actual_parent_id = by_name[child].get("parent_span_id")
        expected_parent_id = by_name.get(parent_name, {}).get("id")

        if expected_parent_id is not None and str(actual_parent_id) != str(expected_parent_id):
            failures.append(
                f"Wrong parent for {child}: "
                f"expected {parent_name}, got {actual_parent_id}"
            )

    # Parallel branches must share the same parent.
    weather_parent = by_name.get("Weather Tool", {}).get("parent_span_id")
    air_parent = by_name.get("Air Quality Tool", {}).get("parent_span_id")

    if weather_parent != air_parent:
        failures.append(
            "Weather Tool and Air Quality Tool do not have the same parent."
        )

    # Exactly one conditional safety branch should execute.
    branch_names = {
        "Rain Safety Check",
        "Heat Safety Check",
        "Cold Safety Check",
        "Wind Safety Check",
        "Air Quality Safety Check",
        "Outdoor Activity Check",
    }

    executed_branches = [
        name for name in branch_names
        if name in by_name
    ]

    if len(executed_branches) != 1:
        failures.append(
            "Expected exactly one conditional safety branch; "
            f"found {len(executed_branches)}: {executed_branches}"
        )

    # Recommendation must follow the selected branch.
    if executed_branches and "Recommendation Agent" in by_name:
        branch_id = by_name[executed_branches[0]].get("id")
        recommendation_parent = by_name["Recommendation Agent"].get(
            "parent_span_id"
        )
        if str(recommendation_parent) != str(branch_id):
            failures.append(
                "Recommendation Agent is not parented to the selected safety branch."
            )

    # If timestamps exist, verify the parallel calls overlap.
    weather = by_name.get("Weather Tool")
    air = by_name.get("Air Quality Tool")

    if weather and air:
        ws = weather.get("started_at")
        we = weather.get("ended_at")
        aas = air.get("started_at")
        aae = air.get("ended_at")

        if all(v is not None for v in (ws, we, aas, aae)):
            # ISO strings are compared only after normalization through datetime.
            def parse_ts(value):
                if isinstance(value, datetime):
                    return value
                return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

            try:
                ws_dt, we_dt = parse_ts(ws), parse_ts(we)
                as_dt, ae_dt = parse_ts(aas), parse_ts(aae)

                overlaps = max(ws_dt, as_dt) < min(we_dt, ae_dt)
                if not overlaps:
                    failures.append(
                        "Weather Tool and Air Quality Tool are marked parallel "
                        "but their timestamps do not overlap."
                    )
            except Exception:
                failures.append(
                    "Could not parse span timestamps for the parallelism check."
                )

    return failures, spans


# ============================================================
# MAIN TEST
# ============================================================

async def main():
    trace_id = new_id()

    prompt = (
        f"Should I go running outside in {LOCATION} today? "
        "Check the weather and air quality and give me a recommendation."
    )

    context = (
        f"Location: {LOCATION}\n"
        f"Latitude: {LAT}\n"
        f"Longitude: {LON}\n"
        "User activity: running\n"
        "Preference: outdoor activity"
    )

    print()
    print("=" * 70)
    print("CONTROLPLANE WEATHER AGENT TEST")
    print("=" * 70)

    # --------------------------------------------------------
    # 1. ROOT
    # --------------------------------------------------------

    print("[1] Creating trace...")
    create_trace(trace_id, prompt, context)

    # --------------------------------------------------------
    # 2. PARSE
    # --------------------------------------------------------

    print("[2] Parsing request...")

    parse_span = create_span(
        trace_id,
        "Parse Weather Request",
        "agent",
        prompt,
        {
            "location": LOCATION,
            "latitude": LAT,
            "longitude": LON,
            "activity": "running",
        },
        duration_ms=180,
        metadata={"step": "parse"},
    )

    # --------------------------------------------------------
    # 3. LOCATION
    # --------------------------------------------------------

    print("[3] Validating location...")

    location_span = create_span(
        trace_id,
        "Validate Location",
        "tool",
        {
            "location": LOCATION,
            "latitude": LAT,
            "longitude": LON,
        },
        {
            "valid": True,
            "timezone": "America/New_York",
            "resolved_location": LOCATION,
        },
        parent=parse_span,
        duration_ms=120,
        metadata={"step": "location_validation"},
    )

    # --------------------------------------------------------
    # 4. REAL TOOLS IN PARALLEL
    # --------------------------------------------------------

    print("[4] Running weather + air quality tools in parallel...")

    weather_input = {
        "latitude": LAT,
        "longitude": LON,
        "forecast_days": 2,
    }

    air_input = {
        "latitude": LAT,
        "longitude": LON,
        "location": LOCATION,
    }

    async def run_weather():
        started = datetime.now(timezone.utc).isoformat()
        start = asyncio.get_running_loop().time()

        try:
            data = await weather_tool()
            duration = int(
                (asyncio.get_running_loop().time() - start) * 1000
            )

            current = data["current"]
            output = {
                "temperature_c": current["temperature_2m"],
                "apparent_temperature_c": current["apparent_temperature"],
                "humidity": current["relative_humidity_2m"],
                "precipitation_mm": current["precipitation"],
                "rain_mm": current["rain"],
                "wind_kmh": current["wind_speed_10m"],
                "weather_code": current["weather_code"],
            }

            ended = datetime.now(timezone.utc).isoformat()

            create_span(
                trace_id,
                "Weather Tool",
                "tool",
                weather_input,
                output,
                parent=location_span,
                duration_ms=duration,
                metadata={
                    "tool": "open-meteo",
                    "parallel": True,
                },
                started_at=started,
                ended_at=ended,
            )

            return data, output

        except Exception as exc:
            ended = datetime.now(timezone.utc).isoformat()
            create_error_span(
                trace_id,
                "Weather Tool",
                "tool",
                weather_input,
                exc,
                parent=location_span,
                metadata={
                    "tool": "open-meteo",
                    "parallel": True,
                    "ended_at": ended,
                },
            )
            raise

    async def run_air():
        started = datetime.now(timezone.utc).isoformat()
        start = asyncio.get_running_loop().time()

        try:
            data = await air_quality_tool()
            duration = int(
                (asyncio.get_running_loop().time() - start) * 1000
            )

            current = data["current"]
            output = {
                "pm10": current["pm10"],
                "pm2_5": current["pm2_5"],
                "us_aqi": current["us_aqi"],
            }

            ended = datetime.now(timezone.utc).isoformat()

            create_span(
                trace_id,
                "Air Quality Tool",
                "tool",
                air_input,
                output,
                parent=location_span,
                duration_ms=duration,
                metadata={
                    "tool": "open-meteo-air-quality",
                    "parallel": True,
                },
                started_at=started,
                ended_at=ended,
            )

            return data, output

        except Exception as exc:
            ended = datetime.now(timezone.utc).isoformat()
            create_error_span(
                trace_id,
                "Air Quality Tool",
                "tool",
                air_input,
                exc,
                parent=location_span,
                metadata={
                    "tool": "open-meteo-air-quality",
                    "parallel": True,
                    "ended_at": ended,
                },
            )
            raise

    try:
        weather_result, air_result = await asyncio.gather(
            run_weather(),
            run_air(),
        )
    except Exception:
        print()
        print("FAIL: A real weather tool failed. The error span was recorded.")
        print(f"Trace ID: {trace_id}")
        raise

    weather_data, weather_output = weather_result
    air_data, air_output = air_result

    # --------------------------------------------------------
    # 5. ANALYSIS
    # --------------------------------------------------------

    print("[5] Analyzing conditions...")

    analysis_input = {
        "weather": weather_output,
        "air_quality": air_output,
        "activity": "running",
    }

    temperature = weather_output["temperature_c"]
    rain = weather_output["rain_mm"]
    wind = weather_output["wind_kmh"]
    aqi = air_output["us_aqi"]

    if rain > 2:
        condition = "rain"
    elif temperature >= 32:
        condition = "extreme_heat"
    elif temperature <= 5:
        condition = "cold"
    elif wind >= 40:
        condition = "strong_wind"
    elif aqi >= 150:
        condition = "poor_air_quality"
    else:
        condition = "good"

    analysis_output = {
        "condition": condition,
        "temperature_c": temperature,
        "rain_mm": rain,
        "wind_kmh": wind,
        "aqi": aqi,
    }

    analysis_span = create_span(
        trace_id,
        "Analyze Conditions",
        "agent",
        analysis_input,
        analysis_output,
        parent=location_span,
        duration_ms=350,
    )

    # --------------------------------------------------------
    # 6. CONDITIONAL BRANCH
    # --------------------------------------------------------

    print(f"[6] Conditional branch: {condition}")

    if condition == "rain":
        branch_name = "Rain Safety Check"
        branch_input = {
            "condition": condition,
            "rain_mm": rain,
            "activity": "running",
        }
        branch_output = {
            "recommendation": "Avoid outdoor running because of rain.",
            "severity": "moderate",
        }

    elif condition == "extreme_heat":
        branch_name = "Heat Safety Check"
        branch_input = {
            "condition": condition,
            "temperature_c": temperature,
            "activity": "running",
        }
        branch_output = {
            "recommendation": "Avoid running during peak heat.",
            "severity": "high",
        }

    elif condition == "cold":
        branch_name = "Cold Safety Check"
        branch_input = {
            "condition": condition,
            "temperature_c": temperature,
            "activity": "running",
        }
        branch_output = {
            "recommendation": "Running is possible with appropriate layers.",
            "severity": "moderate",
        }

    elif condition == "strong_wind":
        branch_name = "Wind Safety Check"
        branch_input = {
            "condition": condition,
            "wind_kmh": wind,
            "activity": "running",
        }
        branch_output = {
            "recommendation": "Avoid exposed running routes because of wind.",
            "severity": "moderate",
        }

    elif condition == "poor_air_quality":
        branch_name = "Air Quality Safety Check"
        branch_input = {
            "condition": condition,
            "aqi": aqi,
            "activity": "running",
        }
        branch_output = {
            "recommendation": (
                "Avoid prolonged outdoor exercise because of poor air quality."
            ),
            "severity": "high",
        }

    else:
        branch_name = "Outdoor Activity Check"
        branch_input = {
            "condition": condition,
            "temperature_c": temperature,
            "rain_mm": rain,
            "wind_kmh": wind,
            "aqi": aqi,
            "activity": "running",
        }
        branch_output = {
            "recommendation": "Outdoor running conditions look reasonable.",
            "severity": "low",
        }

    branch_span = create_span(
        trace_id,
        branch_name,
        "guardrail",
        branch_input,
        branch_output,
        parent=analysis_span,
        duration_ms=220,
        metadata={
            "conditional": True,
            "selected_branch": condition,
        },
    )

    # --------------------------------------------------------
    # 7. RECOMMENDATION
    # --------------------------------------------------------

    print("[7] Generating recommendation...")

    recommendation_input = {
        "weather": weather_output,
        "air_quality": air_output,
        "analysis": analysis_output,
        "safety_check": branch_output,
    }

    recommendation_output = {
        "should_run": branch_output["severity"] == "low",
        "recommendation": branch_output["recommendation"],
    }

    recommendation_span = create_span(
        trace_id,
        "Recommendation Agent",
        "agent",
        recommendation_input,
        recommendation_output,
        parent=branch_span,
        duration_ms=500,
    )

    # --------------------------------------------------------
    # 8. FINAL RESPONSE
    # --------------------------------------------------------

    print("[8] Generating final response...")

    final_input = {
        "user_question": prompt,
        "weather": weather_output,
        "air_quality": air_output,
        "recommendation": recommendation_output,
    }

    final_output = (
        f"Weather in {LOCATION}: "
        f"{temperature}°C, "
        f"{rain} mm rain, "
        f"{wind} km/h wind. "
        f"Air quality AQI: {aqi}. "
        f"{branch_output['recommendation']}"
    )

    final_span = create_span(
        trace_id,
        "Final Response",
        "llm",
        final_input,
        final_output,
        parent=recommendation_span,
        duration_ms=650,
        metadata={"model": "weather-agent-v1"},
    )

    # --------------------------------------------------------
    # 9. LOGGING FAN-OUT
    # --------------------------------------------------------

    print("[9] Creating logging branches...")

    logging_span = create_span(
        trace_id,
        "Workflow Logger",
        "chain",
        final_output,
        "Workflow result prepared for observability.",
        parent=final_span,
        duration_ms=100,
    )

    create_span(
        trace_id,
        "Metrics",
        "tool",
        {"trace_id": trace_id, "latency": "measured"},
        {"recorded": True, "metric": "weather_agent_latency"},
        parent=logging_span,
        duration_ms=80,
    )

    create_span(
        trace_id,
        "Audit Log",
        "tool",
        {"trace_id": trace_id, "decision": recommendation_output},
        {"recorded": True, "event": "weather_recommendation"},
        parent=logging_span,
        duration_ms=80,
    )

    create_span(
        trace_id,
        "Analytics",
        "tool",
        {"location": LOCATION, "condition": condition},
        {"recorded": True, "event": "weather_agent_completed"},
        parent=logging_span,
        duration_ms=80,
    )

    # --------------------------------------------------------
    # 10. READ BACK THE TRACE AND CHECK IT
    # --------------------------------------------------------

    print("[10] Reading spans back from ControlPlane...")

    # Give the API a moment to commit all writes.
    await asyncio.sleep(0.2)

    # Use the flat span endpoint for validation.
    # /traces/{trace_id} is a nested workflow tree and therefore only
    # exposes root spans at the top level.
    span_response = get_json(f"/spans/{trace_id}")

    expected_names = [
        "Parse Weather Request",
        "Validate Location",
        "Weather Tool",
        "Air Quality Tool",
        "Analyze Conditions",
        "Recommendation Agent",
        "Final Response",
        "Workflow Logger",
        "Metrics",
        "Audit Log",
        "Analytics",
    ]

    failures, spans = validate_spans(
        trace_id,
        span_response,
        expected_names,
    )


    print()
    print("=" * 70)
    print("OBSERVABILITY CHECK")
    print("=" * 70)
    print(f"Trace ID: {trace_id}")
    print(f"Span count: {len(spans)}")
    print(f"Selected condition: {condition}")

    print()
    print("RECORDED SPANS")
    print("-" * 70)

    for span in spans:
        print(
            f"- {span.get('name')} "
            f"[{span.get('span_type')}] "
            f"parent={span.get('parent_span_id')}"
        )

    print("-" * 70)

    if failures:
        print()
        print("FAIL")
        for failure in failures:
            print(f"  - {failure}")
        print("=" * 70)
        raise RuntimeError(
            f"Observability validation failed with {len(failures)} issue(s)."
        )

    print()
    print("PASS")
    print("  - All expected spans exist")
    print("  - Every span has input and output")
    print("  - Parent references are valid")
    print("  - Weather + Air Quality share a parent")
    print("  - Exactly one conditional branch executed")
    print("  - Recommendation follows the selected branch")
    print("  - Final response and logging fan-out exist")
    print()
    print("Trace UI:")
    print("http://localhost:5173")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())