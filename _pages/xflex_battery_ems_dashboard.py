"""
Streamlit page: xFLEX Battery EMS Dashboard

Required Streamlit secrets:

[xflex]
username = "YOUR_USERNAME"
password = "YOUR_PASSWORD"

or:

[xflex]
api_key = "YOUR_FULL_API_KEY"

The page polls live "energy" data every 60 seconds while open.
Schedule data (today/tomorrow) can be inspected for both plants.
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


st.set_page_config(
    page_title="Battery EMS Dashboard",
    page_icon="🔋",
    layout="wide",
)


st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.25rem;
            padding-bottom: 2.5rem;
            max-width: 1550px;
        }

        .dashboard-title {
            font-size: 2rem;
            font-weight: 760;
            margin-bottom: 0.1rem;
        }

        .dashboard-subtitle {
            color: rgba(128,128,128,.95);
            margin-bottom: 1rem;
        }

        .status-card, .soc-card, .flow-card {
            border: 1px solid rgba(128,128,128,.22);
            border-radius: 15px;
            padding: 1rem 1.1rem;
            margin-bottom: .8rem;
        }

        .status-ok { border-left: 5px solid #2e7d32; }
        .status-warning { border-left: 5px solid #ef6c00; }
        .status-error { border-left: 5px solid #c62828; }

        .card-label {
            color: rgba(128,128,128,.95);
            font-size: .88rem;
            margin-bottom: .2rem;
        }

        .big-value {
            font-size: 2.7rem;
            line-height: 1.05;
            font-weight: 800;
            margin-bottom: .55rem;
        }

        .flow-value {
            font-size: 1.8rem;
            line-height: 1.1;
            font-weight: 760;
            margin-bottom: .25rem;
        }

        .small-note {
            color: rgba(128,128,128,.95);
            font-size: .84rem;
        }

        .soc-bar-bg {
            width: 100%;
            height: 14px;
            background: rgba(128,128,128,.18);
            border-radius: 999px;
            overflow: hidden;
            margin-bottom: .4rem;
        }

        .soc-bar-fill {
            height: 14px;
            border-radius: 999px;
        }

        div[data-testid="stMetric"] {
            border: 1px solid rgba(128,128,128,.18);
            border-radius: 12px;
            padding: .7rem .8rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------

def get_api_key() -> str:
    try:
        cfg = st.secrets["xflex"]
    except Exception as exc:
        raise RuntimeError(
            "Missing [xflex] configuration in Streamlit secrets."
        ) from exc

    api_key = str(cfg.get("api_key", "")).strip()
    if api_key:
        return api_key

    username = str(cfg.get("username", "")).strip()
    password = str(cfg.get("password", "")).strip()

    if not username or not password:
        raise RuntimeError(
            "Configure either xflex.api_key or both xflex.username and "
            "xflex.password in Streamlit secrets."
        )

    return f"{username}_{password}"


def parse_api_error(response: requests.Response) -> str:
    status = response.status_code
    reason = response.reason or "HTTP error"
    content_type = response.headers.get("Content-Type", "unknown")

    friendly = {
        400: "Bad request. The API rejected one or more request parameters.",
        401: "Authentication failed. Check the xFLEX API credentials.",
        403: "Access denied. The API key does not have permission for this resource.",
        404: "Plant/data not found, or the device did not return valid real-time data.",
        405: "HTTP method not allowed.",
        406: "The API rejected the requested response content type.",
        412: "A required API entry is missing.",
        415: "The API rejected the request content type.",
        429: "API call limit reached. Too many requests were sent.",
        500: "The xFLEX/HIQ server reported an internal error.",
        502: "Gateway error while contacting the xFLEX backend.",
        503: "The xFLEX service is temporarily unavailable.",
        504: "The xFLEX gateway timed out.",
    }

    detail = friendly.get(status, "The API returned an unsuccessful response.")
    body = (response.text or "").strip()

    try:
        payload = response.json()
        if isinstance(payload, dict):
            errors = payload.get("errors")
            if isinstance(errors, list) and errors:
                parsed = []
                for item in errors:
                    if isinstance(item, dict):
                        parsed.append(
                            f"{item.get('error_code', '?')}: "
                            f"{item.get('error_message', 'Unknown API error')}"
                        )
                if parsed:
                    body = " | ".join(parsed)
            else:
                body = json.dumps(payload, ensure_ascii=False)
    except (ValueError, requests.exceptions.JSONDecodeError):
        pass

    if len(body) > 900:
        body = body[:900] + "…"

    response_part = f" Response: {body}" if body else ""
    return (
        f"HTTP {status} {reason}. {detail} "
        f"Content-Type: {content_type}.{response_part}"
    )


def fetch_data(plant_id: str, rt_data_type: str) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {get_api_key()}",
    }

    body = {
        "plantID": plant_id,
        "RTdataType": rt_data_type,
    }

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
    except (ValueError, requests.exceptions.JSONDecodeError) as exc:
        preview = (response.text or "<empty response>").strip()[:800]
        raise RuntimeError(
            "The API returned HTTP 200 but the response was not valid JSON. "
            f"Response: {preview}"
        ) from exc

    try:
        result = payload["response"]["result"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            "The API response did not contain response.result."
        ) from exc

    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        raise RuntimeError("The API returned no usable result data.")

    return result[0]


# Cache schedule reads briefly so ordinary Streamlit reruns do not cause
# unnecessary repeated API calls.
@st.cache_data(ttl=60, show_spinner=False)
def fetch_schedule_data(plant_id: str, rt_data_type: str) -> dict[str, Any]:
    return fetch_data(plant_id, rt_data_type)


# ---------------------------------------------------------------------
# Data conversion helpers
# ---------------------------------------------------------------------

def number(value: Any) -> float | None:
    if value in (None, "", "?"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def soc_percent(raw_value: Any) -> float | None:
    value = number(raw_value)
    if value is None:
        return None

    # API documentation: battery_soc[7] is in 0.1%.
    value /= 10.0
    return value if 0 <= value <= 100 else None


def wh_15min_to_kw(value: Any) -> float | None:
    """
    Convert energy accumulated in the running 15-minute interval to an
    equivalent average kW over a full 15-minute period:
        Wh / 1000 kWh * 4 = kW

    Important: this is NOT an instantaneous power measurement.
    """
    wh = number(value)
    if wh is None:
        return None
    return wh * 4.0 / 1000.0


def kwh_15min_to_kw(value: Any) -> float | None:
    kwh = number(value)
    if kwh is None:
        return None
    return kwh * 4.0


def fmt_kw(value: float | None) -> str:
    return "—" if value is None else f"{value:,.1f} kW"


def fmt_kwh(value: float | None) -> str:
    return "—" if value is None else f"{value:,.2f} kWh"


def fmt_capacity(value_wh: float | None) -> str:
    return "—" if value_wh is None else f"{value_wh / 1000:,.0f} kWh"


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


def current_flows(data: dict[str, Any], plant_id: str) -> dict[str, float | None]:
    """
    Build useful current 15-minute flow metrics from documented read fields.

    These are equivalent average kW values derived from Wh accumulated in the
    running 15-minute interval. The API table supplied does not expose a true
    instantaneous PV/grid power variable.
    """
    flows = {
        "grid_import_kw": wh_15min_to_kw(data.get("source_energy_15min[0]")),
        "grid_export_kw": wh_15min_to_kw(data.get("consumer_energy_15min[0]")),
        "battery_export_kw": wh_15min_to_kw(data.get("source_energy_15min[7]")),
        "battery_import_kw": wh_15min_to_kw(data.get("consumer_energy_15min[7]")),
        "pv_1_kw": None,
        "pv_2_kw": None,
    }

    # Mapping follows the supplied variable table:
    # SK_Skrlj_1: [4] is marked debug/ignore; [5] is the meaningful PV channel.
    # SK_Skrlj_2: [4] = PV 1 (75 kW), [5] = PV 2 (258 kW).
    if plant_id == "SK_Skrlj_1":
        flows["pv_1_kw"] = wh_15min_to_kw(data.get("source_energy_15min[5]"))
    elif plant_id == "SK_Skrlj_2":
        flows["pv_1_kw"] = wh_15min_to_kw(data.get("source_energy_15min[4]"))
        flows["pv_2_kw"] = wh_15min_to_kw(data.get("source_energy_15min[5]"))
    else:
        flows["pv_1_kw"] = wh_15min_to_kw(data.get("source_energy_15min[4]"))
        flows["pv_2_kw"] = wh_15min_to_kw(data.get("source_energy_15min[5]"))

    return flows


def schedule_dataframe(data: dict[str, Any], prefix: str) -> pd.DataFrame:
    rows = []

    for i in range(96):
        raw = data.get(f"{prefix}[{i}]")
        kwh = number(raw)

        hour = (i * 15) // 60
        minute = (i * 15) % 60
        end_total_minutes = ((i + 1) * 15) % (24 * 60)
        end_hour = end_total_minutes // 60
        end_minute = end_total_minutes % 60

        rows.append(
            {
                "Interval": f"{hour:02d}:{minute:02d}–{end_hour:02d}:{end_minute:02d}",
                "Start": f"{hour:02d}:{minute:02d}",
                "Energy (kWh/15 min)": kwh,
                "Average power (kW)": kwh_15min_to_kw(kwh),
                "Action": (
                    "Discharge"
                    if kwh is not None and kwh < 0
                    else "Charge"
                    if kwh is not None and kwh > 0
                    else "Idle"
                    if kwh == 0
                    else "Unavailable"
                ),
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------

def render_soc_card(
    plant_id: str,
    soc: float | None,
    capacity_wh: float | None,
    setpoint_w: float | None,
    api_timestamp: str | None,
) -> None:
    pct = 0 if soc is None else max(0, min(100, soc))
    soc_text = "Unavailable" if soc is None else f"{soc:.1f}%"

    st.markdown(
        f"""
        <div class="soc-card">
            <div class="card-label">{plant_id} · Battery state of charge</div>
            <div class="big-value">{soc_text}</div>
            <div class="soc-bar-bg">
                <div class="soc-bar-fill"
                     style="width:{pct:.1f}%; background:{soc_color(soc)};">
                </div>
            </div>
            <div class="small-note">
                Capacity: {fmt_capacity(capacity_wh)}
                &nbsp;•&nbsp;
                EMS state: {operating_mode(setpoint_w)}
                &nbsp;•&nbsp;
                API timestamp: {api_timestamp or "—"}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_flow_card(label: str, value: float | None, note: str) -> None:
    st.markdown(
        f"""
        <div class="flow-card">
            <div class="card-label">{label}</div>
            <div class="flow-value">{fmt_kw(value)}</div>
            <div class="small-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_plant_live(plant_id: str, data: dict[str, Any]) -> None:
    soc = soc_percent(data.get("battery_soc[7]"))
    capacity = number(data.get("battery_capacity[7]"))
    setpoint_w = number(data.get("plant_setpoint_used"))
    api_timestamp = data.get("UTCtimeStamp")
    flows = current_flows(data, plant_id)

    render_soc_card(
        plant_id=plant_id,
        soc=soc,
        capacity_wh=capacity,
        setpoint_w=setpoint_w,
        api_timestamp=str(api_timestamp) if api_timestamp is not None else None,
    )

    st.markdown("#### Live energy flow")

    if plant_id == "SK_Skrlj_2":
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_flow_card(
                "Solar PV 1",
                flows["pv_1_kw"],
                "Running 15-min equivalent average · source_energy_15min[4]",
            )
        with c2:
            render_flow_card(
                "Solar PV 2",
                flows["pv_2_kw"],
                "Running 15-min equivalent average · source_energy_15min[5]",
            )
        with c3:
            render_flow_card(
                "Grid import",
                flows["grid_import_kw"],
                "Energy taken from grid in the running 15-min interval",
            )
        with c4:
            render_flow_card(
                "Grid export",
                flows["grid_export_kw"],
                "Energy delivered to grid in the running 15-min interval",
            )
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            render_flow_card(
                "Solar PV",
                flows["pv_1_kw"],
                "Mapped PV channel · running 15-min equivalent average",
            )
        with c2:
            render_flow_card(
                "Grid import",
                flows["grid_import_kw"],
                "Energy taken from grid in the running 15-min interval",
            )
        with c3:
            render_flow_card(
                "Grid export",
                flows["grid_export_kw"],
                "Energy delivered to grid in the running 15-min interval",
            )

    b1, b2, b3 = st.columns(3)
    with b1:
        st.metric(
            "Battery charging",
            fmt_kw(flows["battery_import_kw"]),
            help="Derived from consumer_energy_15min[7].",
        )
    with b2:
        st.metric(
            "Battery discharging",
            fmt_kw(flows["battery_export_kw"]),
            help="Derived from source_energy_15min[7].",
        )
    with b3:
        st.metric(
            "EMS setpoint",
            fmt_kw(setpoint_w / 1000 if setpoint_w is not None else None),
            help="Actual plant_setpoint_used. Positive = charging/import; negative = discharging/export.",
        )

    st.caption(
        "PV and grid kW values above are calculated from energy accumulated in the "
        "current 15-minute interval. They are not true instantaneous power values, "
        "because the supplied API variable list does not expose instantaneous PV/grid kW."
    )


def render_schedule(plant_id: str) -> None:
    with st.expander(f"{plant_id} · Battery schedule", expanded=False):
        day_choice = st.selectbox(
            "Schedule",
            ["Today", "Tomorrow"],
            key=f"schedule_day_{plant_id}",
        )

        rt_type = (
            "energy_tt_today"
            if day_choice == "Today"
            else "energy_tt_tomorrow"
        )
        prefix = rt_type

        try:
            schedule_data = fetch_schedule_data(plant_id, rt_type)
            df = schedule_dataframe(schedule_data, prefix)
        except Exception as exc:
            st.error(f"Could not retrieve {day_choice.lower()} schedule: {exc}")
            return

        valid = df["Energy (kWh/15 min)"].notna().sum()
        if valid == 0:
            st.warning("The API returned no usable schedule values.")
            return

        charge_kwh = df.loc[
            df["Energy (kWh/15 min)"] > 0, "Energy (kWh/15 min)"
        ].sum()
        discharge_kwh = -df.loc[
            df["Energy (kWh/15 min)"] < 0, "Energy (kWh/15 min)"
        ].sum()

        m1, m2, m3 = st.columns(3)
        m1.metric("Scheduled charge", fmt_kwh(charge_kwh))
        m2.metric("Scheduled discharge", fmt_kwh(discharge_kwh))
        m3.metric("Intervals received", f"{valid}/96")

        chart_df = df.dropna(subset=["Average power (kW)"]).copy()

        chart = (
            alt.Chart(chart_df)
            .mark_bar()
            .encode(
                x=alt.X(
                    "Start:N",
                    title="15-minute interval",
                    sort=None,
                    axis=alt.Axis(labelAngle=-60, labelOverlap=True),
                ),
                y=alt.Y(
                    "Average power (kW):Q",
                    title="Scheduled average power (kW)",
                ),
                tooltip=[
                    alt.Tooltip("Interval:N", title="Interval"),
                    alt.Tooltip(
                        "Energy (kWh/15 min):Q",
                        title="Energy",
                        format=".2f",
                    ),
                    alt.Tooltip(
                        "Average power (kW):Q",
                        title="Average power",
                        format=".1f",
                    ),
                    alt.Tooltip("Action:N", title="Action"),
                ],
            )
            .properties(height=330)
        )

        st.altair_chart(chart, use_container_width=True)

        st.dataframe(
            df[[
                "Interval",
                "Energy (kWh/15 min)",
                "Average power (kW)",
                "Action",
            ]],
            use_container_width=True,
            hide_index=True,
            height=400,
        )

        st.caption(
            "Schedule sign convention from the API documentation: "
            "negative = battery discharging/export, positive = charging/import."
        )


# ---------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------

st.markdown(
    '<div class="dashboard-title">🔋 Battery EMS Dashboard</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="dashboard-subtitle">'
    'Live battery SOC, PV/grid energy flow and uploaded battery schedules'
    '</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Dashboard settings")
    selected_plants = st.multiselect(
        "Plants",
        options=DEFAULT_PLANTS,
        default=DEFAULT_PLANTS,
    )
    st.caption("Live polling interval: 60 seconds")
    st.caption(
        "The live page does not keep historical SOC after a full browser/app refresh."
    )


@st.fragment(run_every=REFRESH_INTERVAL)
def live_dashboard() -> None:
    if not selected_plants:
        st.warning("Select at least one plant in the sidebar.")
        return

    polled_at = datetime.now(timezone.utc)
    readings: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}

    for plant_id in selected_plants:
        try:
            readings[plant_id] = fetch_data(plant_id, "energy")
        except Exception as exc:
            errors[plant_id] = str(exc)

    if len(readings) == len(selected_plants):
        st.markdown(
            f"""
            <div class="status-card status-ok">
                <b>● LIVE · All selected systems are online</b><br>
                Last API poll: {polled_at.strftime("%Y-%m-%d %H:%M:%S UTC")}
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif readings:
        st.markdown(
            f"""
            <div class="status-card status-warning">
                <b>● PARTIAL · Some systems could not be read</b><br>
                Last API poll: {polled_at.strftime("%Y-%m-%d %H:%M:%S UTC")}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="status-card status-error">
                <b>● OFFLINE / API ERROR · No selected system returned live data</b><br>
                Last API attempt: {polled_at.strftime("%Y-%m-%d %H:%M:%S UTC")}
            </div>
            """,
            unsafe_allow_html=True,
        )

    for plant_id in selected_plants:
        st.subheader(plant_id)

        if plant_id in readings:
            render_plant_live(plant_id, readings[plant_id])
        else:
            st.error(
                f"Could not retrieve live data for {plant_id}: "
                f"{errors.get(plant_id, 'Unknown error')}"
            )

        st.divider()


live_dashboard()


st.subheader("Battery schedules")
st.caption(
    "Read-back view of the schedules currently stored in the EMS. "
    "Use this to verify that the uploaded Today/Tomorrow values are correct."
)

for plant in selected_plants:
    render_schedule(plant)
