import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
import httpx
from dotenv import load_dotenv
from sdk.controlplane.client import ControlPlane
from sdk.controlplane.openai import OpenAIClient

load_dotenv()
# ============================================================
# APPLICATION CONFIG
# ============================================================

CONTROLPLANE_URL = "http://127.0.0.1:8000"

APPLICATION_NAME = "Weather Agent"

LAT = 40.7128
LON = -74.0060
LOCATION = "New York City"

WEATHER_TIMEOUT = 15

load_dotenv()
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
# WEATHER WORKFLOW
# ============================================================

async def main():

    # --------------------------------------------------------
    # INPUT
    # --------------------------------------------------------

    session_id = input(
        "Enter project/session ID: "
    ).strip()

    if not session_id:
        print("ERROR: project/session ID is required.")
        return

    prompt = (
        f"Should I go running outside in {LOCATION} today? "
        "Check the weather and air quality and give me a recommendation."
    )

    context = {
        "location": LOCATION,
        "latitude": LAT,
        "longitude": LON,
        "activity": "running",
        "preference": "outdoor activity",
    }

    # ========================================================
    # CONTROLPLANE APPLICATION
    # ========================================================
    #
    # THIS IS THE ONLY CONTROLPLANE SETUP THE DEVELOPER NEEDS.
    #
    # The developer names the application.
    #
    # ControlPlane creates:
    #   application ID
    #   run ID
    #   trace ID
    #   span IDs
    #
    # None of those IDs are created or supplied here.
    # ========================================================

    controlplane = ControlPlane(
        api_url=CONTROLPLANE_URL,
    )

    app = controlplane.application(
        APPLICATION_NAME,
        session_id=session_id,
    )

    openai_client = OpenAIClient(
        controlplane=controlplane,
    )

    print()
    print("=" * 70)
    print("CONTROLPLANE WEATHER AGENT")
    print("=" * 70)
    print(f"Application: {APPLICATION_NAME}")
    print()

    # ========================================================
    # APPLICATION RUN
    # ========================================================

    with app.run(
        input=prompt,
        context=context,
    ) as run:

        # ----------------------------------------------------
        # 1. PARSE REQUEST
        # ----------------------------------------------------

        print("[1] Parsing request...")

        parse_span = run.span(
            name="Parse Weather Request",
            span_type="agent",
            input_data=prompt,
            output_data={
                "location": LOCATION,
                "latitude": LAT,
                "longitude": LON,
                "activity": "running",
            },
            duration_ms=180,
            metadata={
                "step": "parse",
            },
        )

        # ----------------------------------------------------
        # 2. VALIDATE LOCATION
        # ----------------------------------------------------

        print("[2] Validating location...")

        location_span = run.span(
            name="Validate Location",
            span_type="tool",
            input_data={
                "location": LOCATION,
                "latitude": LAT,
                "longitude": LON,
            },
            output_data={
                "valid": True,
                "timezone": "America/New_York",
                "resolved_location": LOCATION,
            },
            parent=parse_span,
            duration_ms=120,
            metadata={
                "step": "location_validation",
            },
        )

        # ----------------------------------------------------
        # 3. WEATHER + AIR QUALITY IN PARALLEL
        # ----------------------------------------------------

        print("[3] Running weather + air quality tools in parallel...")

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
                    (asyncio.get_running_loop().time() - start)
                    * 1000
                )

                current = data["current"]

                output = {
                    "temperature_c": current["temperature_2m"],
                    "apparent_temperature_c": (
                        current["apparent_temperature"]
                    ),
                    "humidity": current["relative_humidity_2m"],
                    "precipitation_mm": current["precipitation"],
                    "rain_mm": current["rain"],
                    "wind_kmh": current["wind_speed_10m"],
                    "weather_code": current["weather_code"],
                }

                ended = datetime.now(timezone.utc).isoformat()

                run.span(
                    name="Weather Tool",
                    span_type="tool",
                    input_data=weather_input,
                    output_data=output,
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

                run.error_span(
                    name="Weather Tool",
                    span_type="tool",
                    input_data=weather_input,
                    exc=exc,
                    parent=location_span,
                    metadata={
                        "tool": "open-meteo",
                        "parallel": True,
                    },
                )

                raise

        async def run_air():

            started = datetime.now(timezone.utc).isoformat()
            start = asyncio.get_running_loop().time()

            try:
                data = await air_quality_tool()

                duration = int(
                    (asyncio.get_running_loop().time() - start)
                    * 1000
                )

                current = data["current"]

                output = {
                    "pm10": current["pm10"],
                    "pm2_5": current["pm2_5"],
                    "us_aqi": current["us_aqi"],
                }

                ended = datetime.now(timezone.utc).isoformat()

                run.span(
                    name="Air Quality Tool",
                    span_type="tool",
                    input_data=air_input,
                    output_data=output,
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

                run.error_span(
                    name="Air Quality Tool",
                    span_type="tool",
                    input_data=air_input,
                    exc=exc,
                    parent=location_span,
                    metadata={
                        "tool": "open-meteo-air-quality",
                        "parallel": True,
                    },
                )

                raise

        weather_result, air_result = await asyncio.gather(
            run_weather(),
            run_air(),
        )

        weather_data, weather_output = weather_result
        air_data, air_output = air_result

        # ----------------------------------------------------
        # 4. ANALYZE CONDITIONS
        # ----------------------------------------------------

        print("[4] Analyzing conditions...")

        temperature = weather_output["temperature_c"]
        rain = weather_output["rain_mm"]
        wind = weather_output["wind_kmh"]
        aqi = air_output["us_aqi"]

        analysis_input = {
            "weather": weather_output,
            "air_quality": air_output,
            "activity": "running",
        }

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

        analysis_span = run.span(
            name="Analyze Conditions",
            span_type="agent",
            input_data=analysis_input,
            output_data=analysis_output,
            parent=location_span,
            duration_ms=350,
        )

        # ----------------------------------------------------
        # 5. CONDITIONAL SAFETY BRANCH
        # ----------------------------------------------------

        print(f"[5] Conditional branch: {condition}")

        if condition == "rain":

            branch_name = "Rain Safety Check"

            branch_input = {
                "condition": condition,
                "rain_mm": rain,
                "activity": "running",
            }

            branch_output = {
                "recommendation": (
                    "Avoid outdoor running because of rain."
                ),
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
                "recommendation": (
                    "Avoid running during peak heat."
                ),
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
                "recommendation": (
                    "Running is possible with appropriate layers."
                ),
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
                "recommendation": (
                    "Avoid exposed running routes because of wind."
                ),
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
                    "Avoid prolonged outdoor exercise "
                    "because of poor air quality."
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
                "recommendation": (
                    "Outdoor running conditions look reasonable."
                ),
                "severity": "low",
            }

        branch_span = run.span(
            name=branch_name,
            span_type="guardrail",
            input_data=branch_input,
            output_data=branch_output,
            parent=analysis_span,
            duration_ms=220,
            metadata={
                "conditional": True,
                "selected_branch": condition,
            },
        )

        # ----------------------------------------------------
        # 6. RECOMMENDATION
        # ----------------------------------------------------

        print("[6] Generating recommendation...")

        recommendation_input = {
            "weather": weather_output,
            "air_quality": air_output,
            "analysis": analysis_output,
            "safety_check": branch_output,
        }

        recommendation_messages = [
            {
                "role": "system",
                "content": (
                    "You are the recommendation agent for a weather "
                    "activity workflow. Give a concise recommendation "
                    "about whether the user should run outside. Use "
                    "the supplied weather, air quality, analysis, and "
                    "safety check. Do not invent measurements."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"User question: {prompt}\n\n"
                    f"Weather: {weather_output}\n"
                    f"Air quality: {air_output}\n"
                    f"Analysis: {analysis_output}\n"
                    f"Safety check: {branch_output}"
                ),
            },
        ]

        llm_response = await asyncio.to_thread(
            openai_client.chat,
            model="gpt-4.1-mini",
            messages=recommendation_messages,
            context=context,
            run=run,
        )

        llm_recommendation = (
            llm_response.choices[0].message.content or ""
        ).strip()

        if not llm_recommendation:
            raise RuntimeError(
                "OpenAI returned an empty recommendation."
            )

        recommendation_output = {
            "should_run": (
                branch_output["severity"] == "low"
            ),
            "recommendation": llm_recommendation,
            "rule_based_safety": branch_output["recommendation"],
        }

        recommendation_span = run.span(
            name="Recommendation Agent",
            span_type="agent",
            input_data=recommendation_input,
            output_data=recommendation_output,
            parent=branch_span,
            duration_ms=500,
        )

        # ----------------------------------------------------
        # 7. FINAL RESPONSE
        # ----------------------------------------------------

        print("[7] Generating final response...")

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
            f"{recommendation_output['recommendation']}"
        )

        final_span = run.span(
            name="Final Response",
            span_type="llm",
            input_data=final_input,
            output_data=final_output,
            parent=recommendation_span,
            duration_ms=650,
            metadata={
                "model": "weather-agent-v1",
            },
        )

        # ----------------------------------------------------
        # 8. LOGGING FAN-OUT
        # ----------------------------------------------------

        print("[8] Creating logging branches...")

        logging_span = run.span(
            name="Workflow Logger",
            span_type="chain",
            input_data=final_output,
            output_data=(
                "Workflow result prepared for observability."
            ),
            parent=final_span,
            duration_ms=100,
        )

        run.span(
            name="Metrics",
            span_type="tool",
            input_data={
                "latency": "measured",
            },
            output_data={
                "recorded": True,
                "metric": "weather_agent_latency",
            },
            parent=logging_span,
            duration_ms=80,
        )

        run.span(
            name="Audit Log",
            span_type="tool",
            input_data={
                "decision": recommendation_output,
            },
            output_data={
                "recorded": True,
                "event": "weather_recommendation",
            },
            parent=logging_span,
            duration_ms=80,
        )

        run.span(
            name="Analytics",
            span_type="tool",
            input_data={
                "location": LOCATION,
                "condition": condition,
            },
            output_data={
                "recorded": True,
                "event": "weather_agent_completed",
            },
            parent=logging_span,
            duration_ms=80,
        )

        # ----------------------------------------------------
        # DONE
        # ----------------------------------------------------

        print()
        print("=" * 70)
        print("WORKFLOW COMPLETE")
        print("=" * 70)
        print()
        print(final_output)
        print()
        print("ControlPlane recorded the application run.")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())