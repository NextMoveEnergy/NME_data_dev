"""
Streamlit page: xFLEX Battery EMS Monitor

Required Streamlit secrets (recommended):

[xflex]
username = "YOUR_USERNAME"
password = "YOUR_PASSWORD"

Alternative:
[xflex]
api_key = "YOUR_FULL_API_KEY"

The API key is sent as:
    Authorization: Bearer <API-KEY>

This page polls the xFLEX/HIQ API once per minute while the page is open.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import altair as alt
import pandas as pd
import requests
import streamlit as st


API_URL = "https://hiqapi.robotina.com/nextMoveEnergy"
DEFAULT_PLANTS = ["SK_Skrlj_1", "SK_Skrlj_2"]
REQUEST_TIMEOUT_SECONDS = 20
REFRESH_INTERVAL = "60s"
MAX_HISTORY_POINTS = 720


st.set_page_config(
    page_title="Battery EMS Monitor",
    page_icon="🔋",
    layout="wide",
)


st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2.5rem;
            max-width: 1500px;
        }
        .ems-title {
            font-size: 2.0rem;
            font-weight: 750;
            margin-bottom: 0.1rem;
        }
        .ems-subtitle {
            color: rgba(128, 128, 128, 0.95);
            margin-bottom: 1.0rem;
        }
        .status-card {
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 14px;
            padding: 1rem 1.1rem;
            margin-bottom: 0.7rem;
        }
        .status-ok { border-left: 5px solid #2e7d32; }
        .status-error { border-left: 5px solid #c62828; }
        .status-warning { border-left: 5px solid #ef6c00; }
        .soc-panel {
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 16px;
            padding: 1.0rem 1.2rem 1.1rem 1.2rem;
            margin-bottom: 0.8rem;
        }
        .soc-label {
            font-size: 0.9rem;
            color: rgba(128, 128, 128, 0.95);
            margin-bottom: 0.2rem;
        }
        .soc-value {
            font-size: 3.0rem;
            line-height: 1.05;
            font-weight: 800;
            margin-bottom: 0.55rem;
        }
        .soc-bar-bg {
            width: 100%;
            height: 14px;
            background: rgba(128, 128, 128, 0.18);
            border-radius: 999px;
            overflow: hidden;
            margin-bottom: 0.35rem;
        }
        .soc-bar-fill {
            height: 14px;
            border-radius: 999px;
        }
        .soc-small {
            color: rgba(128, 128, 128, 0.95);
            font-size: 0.88rem;
        }
        div[data-testid="stMetric"] {
            border: 1px solid rgba(128, 128, 128, 0.20);
            border-radius: 12px;
            padding: 0.75rem 0.85rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_api_key() -> str:
    """Read xFLEX credentials from Streamlit secrets."""
    try:
        cfg = st.secrets["xflex"]
    except Exception as exc:
        raise RuntimeError("Missing [xflex] configuration in Streamlit secrets.") from exc

    api_key = str(cfg.get("api_key", "")).strip()
    if api_key:
        return api_key

    username = str(cfg.get("username", "")).strip()
    password = str(cfg.get("password", "")).strip()
    if not username or not password:
        raise RuntimeError(
            "Configure either xflex.api_key or both xflex.username and xflex.password "
            "in Streamlit secrets."
        )

    return f"{username}_{password}"


def parse_api_error(response: requests.Response) -> str:
    """Create a readable API error without assuming the body is JSON."""
    status = response.status_code
    reason = response.reason or "HTTP error"
    content_type = response.headers.get("Content-Type", "unknown")

    friendly = {
        400: "Bad request. The API rejected one or more request parameters.",
        401: "Authentication failed. Check the xFLEX API credentials.",
        403: "Access denied. The API key does not have permission for this plant or variable.",
        404: "Plant/data not found, or the device did not return valid real-time data.",
        405: "HTTP method not allowed by the API.",
        406: "The API rejected the requested response content type.",
        412: "A required URL/API entry is missing.",
        415: "The API rejected the request content type.",
        429: "API call limit reached. Too many requests were sent in the allowed time window.",
        500: "The xFLEX/HIQ server reported an internal error.",
        502: "Gateway error while contacting the xFLEX backend.",
        503: "The xFLEX service is temporarily unavailable.",
        504: "The xFLEX gateway timed out while waiting for the backend.",
    }

    detail = friendly.get(status, "The API returned an unsuccessful response.")
    body = (response.text or "").strip()

    try:
        payload = response.json()
        if isinstance(payload, dict):
            errors = payload.get("errors")
            if isinstance(errors, list) and errors:
                parts = []
                for item in errors:
                    if isinstance(item, dict):
                        code = item.get("error_code", "?")
                        message = item.get("error_message", "Unknown API error")
                        parts.append(f"{code}: {message}")
                if parts:
                    body = " | ".join(parts)
            else:
                body = json.dumps(payload, ensure_ascii=False)
    except ValueError:
        pass

    if len(body) > 900:
        body = body[:900] + "…"

    extra = f" Response: {body}" if body else ""
    return f"HTTP {status} {reason}. {detail} Content-Type: {content_type}.{extra}"


def fetch_energy_data(plant_id: str) -> dict[str, Any]:
    """Read current real-time energy data for one plant."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {get_api_key()}",
    }
    body = {"plantID": plant_id, "RTdataType": "energy"}

    try:
        response = requests.post(
            API_URL,
            headers=headers,
            json=body,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.Timeout as exc:
        raise RuntimeError(
            f"Request timed out after {REQUEST_TIMEOUT_SECONDS} seconds."
        ) from exc
    except requests.ConnectionError as exc:
        raise RuntimeError("Could not connect to the xFLEX API server.") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Network/API request failed: {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(parse_api_error(response))

    try:
        payload = response.json()
    except ValueError as exc:
        preview = (response.text or "<empty response>").strip()[:800]
        raise RuntimeError(
            "The API returned HTTP 200 but the response was not valid JSON. "
            f"Response: {preview}"
        ) from exc

    try:
        result = payload["response"]["result"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("The API response did not contain response.result.") from exc

    if not isinstance(result, list) or not result:
        raise RuntimeError("The API response contained no real-time result data.")
    if not isinstance(result[0], dict):
        raise RuntimeError("The first real-time result is not a JSON object.")

    return result[0]


def soc_from_raw(raw_value: Any) -> float | None:
    """battery_soc[7] is in 0.1% units, e.g. 762 = 76.2%."""
    if raw_value in (None, "", "?"):
        return None
    try:
        value = float(raw_value) / 10.0
    except (TypeError, ValueError):
        return None
    if value < 0 or value > 100:
        return None
    return value


def numeric_or_none(value: Any) -> float | None:
    if value in (None, "", "?"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_capacity(wh: float | None) -> str:
    return "—" if wh is None else f"{wh / 1000:,.1f} kWh"


def format_power(watts: float | None) -> str:
    if watts is None:
        return "—"
    return f"{watts / 1000:,.1f} kW" if abs(watts) >= 1000 else f"{watts:,.0f} W"


def operating_mode(setpoint_w: float | None) -> str:
    if setpoint_w is None:
        return "Unknown"
    if setpoint_w > 100:
        return "Charging"
    if setpoint_w < -100:
        return "Discharging"
    return "Idle"


def soc_color(soc: float | None) -> str:
    if soc is None:
        return "#757575"
    if soc < 20:
        return "#c62828"
    if soc < 40:
        return "#ef6c00"
    return "#2e7d32"


def ensure_session_state() -> None:
    st.session_state.setdefault("xflex_history", [])
    st.session_state.setdefault("xflex_last_success", {})
    st.session_state.setdefault("xflex_last_error", {})


def add_history(plant_id: str, soc: float, api_timestamp: str | None, polled_at: datetime) -> None:
    history = st.session_state.xflex_history
    dedupe_key = (plant_id, api_timestamp, round(soc, 4))

    for row in reversed(history[-20:]):
        row_key = (
            row.get("plant"),
            row.get("api_timestamp"),
            round(float(row.get("soc", -999)), 4),
        )
        if row_key == dedupe_key:
            return

    history.append(
        {
            "time": polled_at,
            "plant": plant_id,
            "soc": soc,
            "api_timestamp": api_timestamp,
        }
    )

    max_rows = MAX_HISTORY_POINTS * max(1, len(DEFAULT_PLANTS))
    if len(history) > max_rows:
        st.session_state.xflex_history = history[-max_rows:]


def render_soc_card(
    plant_id: str,
    soc: float | None,
    capacity_wh: float | None,
    setpoint_w: float | None,
    api_timestamp: str | None,
) -> None:
    pct = 0 if soc is None else max(0, min(100, soc))
    color = soc_color(soc)
    soc_text = "Unavailable" if soc is None else f"{soc:.1f}%"

    st.markdown(
        f"""
        <div class="soc-panel">
            <div class="soc-label">{plant_id} · State of Charge</div>
            <div class="soc-value">{soc_text}</div>
            <div class="soc-bar-bg">
                <div class="soc-bar-fill" style="width:{pct:.1f}%; background:{color};"></div>
            </div>
            <div class="soc-small">
                Battery capacity: {format_capacity(capacity_wh)}
                &nbsp;&nbsp;•&nbsp;&nbsp;
                EMS mode: {operating_mode(setpoint_w)}
                &nbsp;&nbsp;•&nbsp;&nbsp;
                API timestamp: {api_timestamp or "—"}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_history_chart(selected_plants: list[str]) -> None:
    rows = [
        row for row in st.session_state.xflex_history
        if row["plant"] in selected_plants
    ]

    if not rows:
        st.info("SOC history will appear after the first successful API reading.")
        return

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"])

    chart = (
        alt.Chart(df)
        .mark_line(point=True, strokeWidth=2.5)
        .encode(
            x=alt.X("time:T", title="Poll time", axis=alt.Axis(format="%H:%M")),
            y=alt.Y(
                "soc:Q",
                title="State of Charge (%)",
                scale=alt.Scale(domain=[0, 100]),
            ),
            color=alt.Color("plant:N", title="Battery / plant"),
            tooltip=[
                alt.Tooltip("plant:N", title="Plant"),
                alt.Tooltip("time:T", title="Polled", format="%Y-%m-%d %H:%M:%S"),
                alt.Tooltip("soc:Q", title="SOC", format=".1f"),
                alt.Tooltip("api_timestamp:N", title="API timestamp"),
            ],
        )
        .properties(height=360)
        .interactive()
    )
    st.altair_chart(chart, use_container_width=True)


ensure_session_state()

st.markdown('<div class="ems-title">🔋 Battery EMS Monitor</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="ems-subtitle">Live xFLEX battery State of Charge monitoring · automatic refresh every 60 seconds</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Monitor settings")
    selected_plants = st.multiselect(
        "Plants",
        options=DEFAULT_PLANTS,
        default=DEFAULT_PLANTS,
        help="Plants to poll from the xFLEX real-time energy endpoint.",
    )
    st.caption("Polling interval: 60 seconds")

    if st.button("Clear chart history", use_container_width=True):
        st.session_state.xflex_history = []
        st.rerun()

    st.divider()
    st.caption(
        "Credentials are read from Streamlit secrets and are never displayed on this page."
    )


@st.fragment(run_every=REFRESH_INTERVAL)
def live_monitor() -> None:
    if not selected_plants:
        st.warning("Select at least one plant in the sidebar.")
        return

    poll_started = datetime.now(timezone.utc)
    successful: list[str] = []
    errors: dict[str, str] = {}
    readings: dict[str, dict[str, Any]] = {}

    for plant_id in selected_plants:
        try:
            data = fetch_energy_data(plant_id)
            soc = soc_from_raw(data.get("battery_soc[7]"))
            capacity = numeric_or_none(data.get("battery_capacity[7]"))
            setpoint = numeric_or_none(data.get("plant_setpoint_used"))
            api_timestamp = data.get("UTCtimeStamp")

            if soc is None:
                raise RuntimeError(
                    "battery_soc[7] is unavailable or invalid in the API response."
                )

            readings[plant_id] = {
                "soc": soc,
                "capacity": capacity,
                "setpoint": setpoint,
                "api_timestamp": api_timestamp,
            }

            add_history(
                plant_id,
                soc,
                str(api_timestamp) if api_timestamp is not None else None,
                poll_started,
            )

            st.session_state.xflex_last_success[plant_id] = {
                "time": poll_started,
                "soc": soc,
                "api_timestamp": api_timestamp,
            }
            st.session_state.xflex_last_error.pop(plant_id, None)
            successful.append(plant_id)

        except Exception as exc:
            message = str(exc)
            errors[plant_id] = message
            st.session_state.xflex_last_error[plant_id] = {
                "time": poll_started,
                "message": message,
            }

    if len(successful) == len(selected_plants):
        css_class = "status-ok"
        headline = "● LIVE · All selected batteries are online"
        time_label = "Last poll"
    elif successful:
        css_class = "status-warning"
        headline = "● PARTIAL · Some battery data could not be retrieved"
        time_label = "Last poll"
    else:
        css_class = "status-error"
        headline = "● OFFLINE / API ERROR · No selected battery returned a valid SOC"
        time_label = "Last poll attempt"

    st.markdown(
        f"""
        <div class="status-card {css_class}">
            <b>{headline}</b><br>
            {time_label}: {poll_started.strftime('%Y-%m-%d %H:%M:%S UTC')}
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(len(selected_plants))
    for col, plant_id in zip(cols, selected_plants):
        with col:
            reading = readings.get(plant_id)

            if reading:
                render_soc_card(
                    plant_id,
                    reading["soc"],
                    reading["capacity"],
                    reading["setpoint"],
                    str(reading["api_timestamp"])
                    if reading["api_timestamp"] is not None
                    else None,
                )

                m1, m2 = st.columns(2)
                with m1:
                    st.metric("Plant setpoint", format_power(reading["setpoint"]))
                with m2:
                    st.metric("EMS state", operating_mode(reading["setpoint"]))
            else:
                last_good = st.session_state.xflex_last_success.get(plant_id)
                last_soc = None
                last_success_text = "Never"

                if last_good:
                    last_soc = last_good.get("soc")
                    last_time = last_good.get("time")
                    if isinstance(last_time, datetime):
                        last_success_text = last_time.strftime("%Y-%m-%d %H:%M:%S UTC")

                st.markdown(
                    f"""
                    <div class="soc-panel">
                        <div class="soc-label">{plant_id} · State of Charge</div>
                        <div class="soc-value">{"—" if last_soc is None else f"{last_soc:.1f}%"}</div>
                        <div class="soc-small">
                            Current reading unavailable.<br>
                            Last successful SOC call: {last_success_text}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    if errors:
        st.subheader("API status & errors")
        for plant_id, message in errors.items():
            with st.expander(f"{plant_id} · Data unavailable", expanded=True):
                st.error(message)
                last_good = st.session_state.xflex_last_success.get(plant_id)
                if last_good:
                    last_time = last_good.get("time")
                    last_soc = last_good.get("soc")
                    st.caption(
                        "Last successful reading: "
                        f"{last_soc:.1f}% at "
                        f"{last_time.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )

    st.divider()
    st.subheader("SOC history")
    render_history_chart(selected_plants)

    with st.expander("Latest technical details"):
        rows = []
        for plant_id in selected_plants:
            reading = readings.get(plant_id)
            if reading:
                rows.append(
                    {
                        "Plant": plant_id,
                        "SOC (%)": reading["soc"],
                        "Battery capacity (kWh)": (
                            reading["capacity"] / 1000
                            if reading["capacity"] is not None
                            else None
                        ),
                        "Setpoint (kW)": (
                            reading["setpoint"] / 1000
                            if reading["setpoint"] is not None
                            else None
                        ),
                        "API UTC timestamp": reading["api_timestamp"],
                        "Poll UTC": poll_started.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No successful readings in the latest poll.")


live_monitor()
