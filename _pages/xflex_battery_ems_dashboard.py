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
from zoneinfo import ZoneInfo
from typing import Any

import altair as alt
import pandas as pd
import requests
import streamlit as st


API_URL = "https://hiqapi.robotina.com/nextMoveEnergy"
DEFAULT_PLANTS = ["SK_Skrlj_1", "SK_Skrlj_2"]
REQUEST_TIMEOUT_SECONDS = 20
REFRESH_INTERVAL = "60s"
LOCAL_TZ = ZoneInfo("Europe/Ljubljana")


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

        .battery-wrap {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin: .7rem 0 .9rem 0;
        }

        .battery-shell {
            position: relative;
            width: 170px;
            height: 78px;
            border: 4px solid rgba(128,128,128,.78);
            border-radius: 12px;
            padding: 5px;
            box-sizing: border-box;
            background: rgba(128,128,128,.06);
        }

        .battery-shell:after {
            content: "";
            position: absolute;
            right: -13px;
            top: 22px;
            width: 9px;
            height: 28px;
            border-radius: 0 6px 6px 0;
            background: rgba(128,128,128,.78);
        }

        .battery-fill {
            height: 100%;
            border-radius: 6px;
            transition: width .35s ease;
        }

        .battery-percentage {
            font-size: 2.65rem;
            font-weight: 820;
            line-height: 1;
        }

        .section-note {
            border: 1px solid rgba(128,128,128,.18);
            border-radius: 12px;
            padding: .75rem .9rem;
            margin: .2rem 0 .9rem 0;
            background: rgba(128,128,128,.035);
            font-size: .88rem;
            color: rgba(128,128,128,.95);
        }

        .signal-chip {
            display: inline-block;
            padding: .18rem .5rem;
            margin-left: .25rem;
            border-radius: 999px;
            border: 1px solid rgba(128,128,128,.22);
            font-size: .76rem;
            color: rgba(128,128,128,.95);
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
# Time helpers
# ---------------------------------------------------------------------

def now_ljubljana() -> datetime:
    """Return the current timezone-aware time in Ljubljana."""
    return datetime.now(LOCAL_TZ)


def format_ljubljana_time(value: Any) -> str:
    """
    Convert API UTC timestamps to Europe/Ljubljana.

    The xFLEX API field is named UTCtimeStamp and the documentation describes
    it as UTC. Naive API timestamps are therefore interpreted as UTC first.
    """
    if value in (None, "", "?"):
        return "—"

    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return raw

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")


def current_schedule_index(local_now: datetime | None = None) -> int:
    """Return the current 15-minute schedule slot index (0..95) in Ljubljana time."""
    local_now = local_now or now_ljubljana()
    return (local_now.hour * 60 + local_now.minute) // 15


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


def api_timestamp_datetime(value: Any) -> datetime | None:
    """Parse the documented UTCtimeStamp as a timezone-aware UTC datetime."""
    if value in (None, "", "?"):
        return None

    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(str(value).strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def running_interval_wh_to_kw(value: Any, api_timestamp: Any) -> float | None:
    """
    Estimate average kW since the start of the current 15-minute interval.

    The API exposes accumulated Wh in the running quarter-hour, not a true
    instantaneous power signal. This divides accumulated energy by elapsed
    interval time, giving a live interval-average estimate.
    """
    wh = number(value)
    if wh is None:
        return None

    dt = api_timestamp_datetime(api_timestamp) or datetime.now(timezone.utc)
    elapsed_seconds = (dt.minute % 15) * 60 + dt.second + dt.microsecond / 1_000_000

    if elapsed_seconds < 30:
        return None

    return (wh / 1000.0) / (elapsed_seconds / 3600.0)


def completed_15min_wh_to_kw(value: Any) -> float | None:
    """Convert Wh from a completed 15-minute interval to average kW."""
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


def wh_to_kwh(value: Any) -> float | None:
    wh = number(value)
    if wh is None:
        return None
    return wh / 1000.0


def kw_to_15min_kwh(value_kw: float | None) -> float | None:
    """Convert a kW setpoint/power value to its 15-minute energy equivalent."""
    if value_kw is None:
        return None
    return value_kw * 0.25


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


def current_flows(data: dict[str, Any], plant_id: str) -> dict[str, Any]:
    """
    Exact mapping from the supplied signal table.

    Each running 15-minute API field is stored as energy in Wh. The dashboard
    therefore shows BOTH:
      - accumulated energy in the current interval (kWh), and
      - average power so far in the current interval (kW).

    [0] GRID
      source_energy_*[0]   = imported energy FROM grid
      consumer_energy_*[0] = exported energy TO grid

    [4] PV 1
      source_energy_*[4]   = PV 1 produced energy
      consumer_energy_*[4] = PV 1 consumed energy (normally near zero)

    [5] PV 2
      source_energy_*[5]   = PV 2 produced energy
      consumer_energy_*[5] = PV 2 consumed energy (normally near zero)

    [7] HEE / BATTERY
      source_energy_*[7]   = produced/exported energy = discharging
      consumer_energy_*[7] = consumed energy = charging
    """
    ts = data.get("UTCtimeStamp")

    result: dict[str, Any] = {
        "grid_meter": "Shared site grid",
        "grid_import_kw": running_interval_wh_to_kw(
            data.get("source_energy_15min[0]"), ts
        ),
        "grid_import_kwh": wh_to_kwh(
            data.get("source_energy_15min[0]")
        ),
        "grid_export_kw": running_interval_wh_to_kw(
            data.get("consumer_energy_15min[0]"), ts
        ),
        "grid_export_kwh": wh_to_kwh(
            data.get("consumer_energy_15min[0]")
        ),
        "grid_import_last_kw": completed_15min_wh_to_kw(
            data.get("source_energy_15min_last[0]")
        ),
        "grid_import_last_kwh": wh_to_kwh(
            data.get("source_energy_15min_last[0]")
        ),
        "grid_export_last_kw": completed_15min_wh_to_kw(
            data.get("consumer_energy_15min_last[0]")
        ),
        "grid_export_last_kwh": wh_to_kwh(
            data.get("consumer_energy_15min_last[0]")
        ),
        "battery_discharge_kw": running_interval_wh_to_kw(
            data.get("source_energy_15min[7]"), ts
        ),
        "battery_discharge_kwh": wh_to_kwh(
            data.get("source_energy_15min[7]")
        ),
        "battery_charge_kw": running_interval_wh_to_kw(
            data.get("consumer_energy_15min[7]"), ts
        ),
        "battery_charge_kwh": wh_to_kwh(
            data.get("consumer_energy_15min[7]")
        ),
        "battery_discharge_last_kw": completed_15min_wh_to_kw(
            data.get("source_energy_15min_last[7]")
        ),
        "battery_discharge_last_kwh": wh_to_kwh(
            data.get("source_energy_15min_last[7]")
        ),
        "battery_charge_last_kw": completed_15min_wh_to_kw(
            data.get("consumer_energy_15min_last[7]")
        ),
        "battery_charge_last_kwh": wh_to_kwh(
            data.get("consumer_energy_15min_last[7]")
        ),
        "pv_channels": [],
    }

    if plant_id == "SK_Skrlj_1":
        result["pv_channels"] = [
            {
                "name": "PV · SK Škrlj SolarEdge",
                "meter": "M1.3",
                "installed_kw": 487,
                "signal": "source_energy_15min[5]",
                "current_kw": running_interval_wh_to_kw(
                    data.get("source_energy_15min[5]"), ts
                ),
                "current_kwh": wh_to_kwh(
                    data.get("source_energy_15min[5]")
                ),
                "last_kw": completed_15min_wh_to_kw(
                    data.get("source_energy_15min_last[5]")
                ),
                "last_kwh": wh_to_kwh(
                    data.get("source_energy_15min_last[5]")
                ),
            }
        ]

    elif plant_id == "SK_Skrlj_2":
        result["pv_channels"] = [
            {
                "name": "PV 1 · Soldin",
                "meter": "M2.3",
                "installed_kw": 75,
                "signal": "source_energy_15min[4]",
                "current_kw": running_interval_wh_to_kw(
                    data.get("source_energy_15min[4]"), ts
                ),
                "current_kwh": wh_to_kwh(
                    data.get("source_energy_15min[4]")
                ),
                "last_kw": completed_15min_wh_to_kw(
                    data.get("source_energy_15min_last[4]")
                ),
                "last_kwh": wh_to_kwh(
                    data.get("source_energy_15min_last[4]")
                ),
            },
            {
                "name": "PV 2 · Škrlj",
                "meter": "M2.4",
                "installed_kw": 258,
                "signal": "source_energy_15min[5]",
                "current_kw": running_interval_wh_to_kw(
                    data.get("source_energy_15min[5]"), ts
                ),
                "current_kwh": wh_to_kwh(
                    data.get("source_energy_15min[5]")
                ),
                "last_kw": completed_15min_wh_to_kw(
                    data.get("source_energy_15min_last[5]")
                ),
                "last_kwh": wh_to_kwh(
                    data.get("source_energy_15min_last[5]")
                ),
            },
        ]

    return result


def schedule_dataframe(
    data: dict[str, Any],
    prefix: str,
    *,
    today_utc_to_ljubljana: bool = False,
) -> pd.DataFrame:
    """
    Build a 96-slot schedule table.

    Observed API behaviour:
    - energy_tt_today is returned on a UTC-indexed 15-minute timeline.
    - energy_tt_tomorrow already matches the uploaded/local schedule.

    Therefore ONLY today's schedule is remapped from UTC slots to
    Europe/Ljubljana slots. This fixes the observed 2-hour summer-time shift
    without altering tomorrow's schedule.

    Example during CEST (UTC+2):
        local 12:00 -> raw UTC slot 10:00
    """
    rows = []

    local_now = now_ljubljana()
    utc_offset_minutes = int(
        (local_now.utcoffset().total_seconds() if local_now.utcoffset() else 0) / 60
    )
    offset_slots = utc_offset_minutes // 15

    for local_index in range(96):
        if today_utc_to_ljubljana:
            raw_index = (local_index - offset_slots) % 96
        else:
            raw_index = local_index

        raw = data.get(f"{prefix}[{raw_index}]")
        kwh = number(raw)

        hour = (local_index * 15) // 60
        minute = (local_index * 15) % 60
        end_total_minutes = ((local_index + 1) * 15) % (24 * 60)
        end_hour = end_total_minutes // 60
        end_minute = end_total_minutes % 60

        rows.append(
            {
                "Index": local_index,
                "Raw API index": raw_index,
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
    soc_text = "—" if soc is None else f"{soc:.1f}%"
    fill_color = soc_color(soc)

    st.markdown(
        f"""
        <div class="soc-card">
            <div class="card-label">{plant_id} · Battery state of charge</div>
            <div class="battery-wrap">
                <div class="battery-shell">
                    <div class="battery-fill"
                         style="width:{pct:.1f}%; background:{fill_color};">
                    </div>
                </div>
                <div>
                    <div class="battery-percentage">{soc_text}</div>
                    <div class="small-note">{operating_mode(setpoint_w)}</div>
                </div>
            </div>
            <div class="small-note">
                Nominal capacity: {fmt_capacity(capacity_wh)}
                &nbsp;•&nbsp;
                EMS setpoint: {fmt_kw(setpoint_w / 1000 if setpoint_w is not None else None)}
                &nbsp;•&nbsp;
                API timestamp: {format_ljubljana_time(api_timestamp)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_flow_card(
    label: str,
    current_kw: float | None,
    *,
    current_kwh: float | None = None,
    meter: str,
    signal: str,
    previous_kw: float | None = None,
    previous_kwh: float | None = None,
    installed_kw: float | None = None,
) -> None:
    capacity_text = (
        f" · Installed: {installed_kw:.0f} kW"
        if installed_kw is not None
        else ""
    )

    st.markdown(
        f"""
        <div class="flow-card">
            <div class="card-label">
                {label}
                <span class="signal-chip">{meter}</span>
            </div>

            <div class="flow-value">{fmt_kw(current_kw)}</div>
            <div style="font-size:1.15rem;font-weight:700;margin-top:-.15rem;margin-bottom:.35rem;">
                {fmt_kwh(current_kwh)}
            </div>

            <div class="small-note">
                Current 15-min interval: average power so far + accumulated energy{capacity_text}<br>
                Previous full 15 min: {fmt_kw(previous_kw)} · {fmt_kwh(previous_kwh)}<br>
                Signal: {signal}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_site_grid(readings: dict[str, dict[str, Any]]) -> None:
    """
    Show SK1 and SK2 grid meters separately, plus their combined totals.
    Both power (kW) and 15-minute energy (kWh) are displayed.
    """

    st.subheader("Grid overview")
    st.caption(
        "Each grid meter is shown separately, plus the combined SK1 + SK2 total. "
        "Every flow is shown in both kW and kWh."
    )

    grid_values: dict[str, dict[str, Any]] = {}

    for plant_id, meter_name in (
        ("SK_Skrlj_1", "M1.1"),
        ("SK_Skrlj_2", "M2.1"),
    ):
        if plant_id not in readings:
            continue

        data = readings[plant_id]
        ts = data.get("UTCtimeStamp")

        grid_values[plant_id] = {
            "meter": meter_name,
            "import_kw": running_interval_wh_to_kw(
                data.get("source_energy_15min[0]"), ts
            ),
            "import_kwh": wh_to_kwh(
                data.get("source_energy_15min[0]")
            ),
            "export_kw": running_interval_wh_to_kw(
                data.get("consumer_energy_15min[0]"), ts
            ),
            "export_kwh": wh_to_kwh(
                data.get("consumer_energy_15min[0]")
            ),
            "import_last_kw": completed_15min_wh_to_kw(
                data.get("source_energy_15min_last[0]")
            ),
            "import_last_kwh": wh_to_kwh(
                data.get("source_energy_15min_last[0]")
            ),
            "export_last_kw": completed_15min_wh_to_kw(
                data.get("consumer_energy_15min_last[0]")
            ),
            "export_last_kwh": wh_to_kwh(
                data.get("consumer_energy_15min_last[0]")
            ),
        }

    meter_cols = st.columns(2)

    for col, plant_id, title in zip(
        meter_cols,
        ("SK_Skrlj_1", "SK_Skrlj_2"),
        ("SK1 grid", "SK2 grid"),
    ):
        with col:
            values = grid_values.get(plant_id)

            if not values:
                st.error(f"{title}: data unavailable")
                continue

            st.markdown(f"#### {title} · {values['meter']}")

            render_flow_card(
                "Import from grid",
                values["import_kw"],
                current_kwh=values["import_kwh"],
                meter=values["meter"],
                signal="source_energy_15min[0]",
                previous_kw=values["import_last_kw"],
                previous_kwh=values["import_last_kwh"],
            )

            render_flow_card(
                "Export to grid",
                values["export_kw"],
                current_kwh=values["export_kwh"],
                meter=values["meter"],
                signal="consumer_energy_15min[0]",
                previous_kw=values["export_last_kw"],
                previous_kwh=values["export_last_kwh"],
            )

    sk1 = grid_values.get("SK_Skrlj_1")
    sk2 = grid_values.get("SK_Skrlj_2")

    st.markdown("#### Combined grid total")

    if sk1 and sk2:
        def add_optional(a: float | None, b: float | None) -> float | None:
            if a is None or b is None:
                return None
            return a + b

        total_import_kw = add_optional(sk1["import_kw"], sk2["import_kw"])
        total_import_kwh = add_optional(sk1["import_kwh"], sk2["import_kwh"])
        total_export_kw = add_optional(sk1["export_kw"], sk2["export_kw"])
        total_export_kwh = add_optional(sk1["export_kwh"], sk2["export_kwh"])

        total_import_last_kw = add_optional(
            sk1["import_last_kw"], sk2["import_last_kw"]
        )
        total_import_last_kwh = add_optional(
            sk1["import_last_kwh"], sk2["import_last_kwh"]
        )
        total_export_last_kw = add_optional(
            sk1["export_last_kw"], sk2["export_last_kw"]
        )
        total_export_last_kwh = add_optional(
            sk1["export_last_kwh"], sk2["export_last_kwh"]
        )

        total_cols = st.columns(3)

        with total_cols[0]:
            render_flow_card(
                "Total grid import",
                total_import_kw,
                current_kwh=total_import_kwh,
                meter="M1.1 + M2.1",
                signal="Σ source_energy_15min[0]",
                previous_kw=total_import_last_kw,
                previous_kwh=total_import_last_kwh,
            )

        with total_cols[1]:
            render_flow_card(
                "Total grid export",
                total_export_kw,
                current_kwh=total_export_kwh,
                meter="M1.1 + M2.1",
                signal="Σ consumer_energy_15min[0]",
                previous_kw=total_export_last_kw,
                previous_kwh=total_export_last_kwh,
            )

        with total_cols[2]:
            if (
                total_import_kw is not None
                and total_export_kw is not None
                and total_import_kwh is not None
                and total_export_kwh is not None
            ):
                net_kw = total_import_kw - total_export_kw
                net_kwh = total_import_kwh - total_export_kwh

                if net_kw > 0.05:
                    net_label = "Net import"
                    display_kw = net_kw
                    display_kwh = max(net_kwh, 0)
                elif net_kw < -0.05:
                    net_label = "Net export"
                    display_kw = abs(net_kw)
                    display_kwh = abs(min(net_kwh, 0))
                else:
                    net_label = "Net grid flow"
                    display_kw = 0.0
                    display_kwh = abs(net_kwh)

                st.metric(net_label, fmt_kw(display_kw))
                st.metric("15-min net energy", fmt_kwh(display_kwh))
                st.caption(
                    "Derived from total import − total export. "
                    "kWh is the accumulated current 15-minute interval."
                )
            else:
                st.metric("Net grid flow", "—")
                st.metric("15-min net energy", "—")

        st.markdown(
            """
            <div class="section-note">
                <b>Units:</b> kW is the average power so far in the running
                15-minute interval. kWh is the actual accumulated energy in that
                same interval. This makes the live values directly comparable
                with the kWh/15min schedule.
            </div>
            """,
            unsafe_allow_html=True,
        )

    else:
        st.warning(
            "Combined grid total requires valid live data from both SK1 and SK2."
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

    st.markdown("#### Solar generation")
    pv_channels = flows["pv_channels"]

    if pv_channels:
        pv_cols = st.columns(len(pv_channels))
        for col, pv in zip(pv_cols, pv_channels):
            with col:
                render_flow_card(
                    pv["name"],
                    pv["current_kw"],
                    current_kwh=pv["current_kwh"],
                    meter=pv["meter"],
                    signal=pv["signal"],
                    previous_kw=pv["last_kw"],
                    previous_kwh=pv["last_kwh"],
                    installed_kw=pv["installed_kw"],
                )

    if plant_id == "SK_Skrlj_1":
        st.caption(
            "The supplied mapping explicitly marks channel [4] as debug/ignore "
            "for SK_Skrlj_1. Its real documented PV production channel is "
            "source_energy_15min[5] (M1.3, SolarEdge 487 kW)."
        )

    st.markdown("#### Battery / HEE flow")
    battery_meter = "M1.2" if plant_id == "SK_Skrlj_1" else "M2.2"

    b1, b2, b3 = st.columns(3)
    with b1:
        render_flow_card(
            "Battery charging",
            flows["battery_charge_kw"],
            current_kwh=flows["battery_charge_kwh"],
            meter=battery_meter,
            signal="consumer_energy_15min[7]",
            previous_kw=flows["battery_charge_last_kw"],
            previous_kwh=flows["battery_charge_last_kwh"],
        )
    with b2:
        render_flow_card(
            "Battery discharging",
            flows["battery_discharge_kw"],
            current_kwh=flows["battery_discharge_kwh"],
            meter=battery_meter,
            signal="source_energy_15min[7]",
            previous_kw=flows["battery_discharge_last_kw"],
            previous_kwh=flows["battery_discharge_last_kwh"],
        )
    with b3:
        setpoint_kw = setpoint_w / 1000 if setpoint_w is not None else None
        setpoint_15min_kwh = kw_to_15min_kwh(setpoint_kw)

        st.metric(
            "Actual EMS setpoint",
            fmt_kw(setpoint_kw),
            help=(
                "plant_setpoint_used [W]. Negative = export/discharging; "
                "positive = import/charging."
            ),
        )
        st.metric(
            "15-min energy equivalent",
            fmt_kwh(setpoint_15min_kwh),
            help=(
                "Derived as setpoint kW × 0.25 h. This is the energy that would "
                "result if the current setpoint stayed constant for the full 15 minutes."
            ),
        )
        st.caption(
            "The kWh value here is derived from the controller setpoint; it is not "
            "a separate measured energy signal."
        )

    st.markdown(
        """
        <div class="section-note">
            <b>About kW and kWh:</b> the API provides accumulated Wh in the
            running 15-minute interval. The dashboard now shows that measured energy
            directly as <b>kWh</b>, and also calculates average <b>kW</b> so far in
            the same interval. For the previous completed 15-minute interval, both
            average kW and measured kWh are shown as well.
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Exact API signal mapping used"):
        if plant_id == "SK_Skrlj_1":
            rows = [
                ["Site grid import", "Shared grid [0]", "source_energy_15min[0]", "Imported energy from grid"],
                ["Site grid export", "Shared grid [0]", "consumer_energy_15min[0]", "Exported energy to grid"],
                ["PV production", "M1.3", "source_energy_15min[5]", "PV 3 / SK Škrlj / SolarEdge 487 kW"],
                ["Battery discharge", "M1.2", "source_energy_15min[7]", "HEE 1 produced/exported energy"],
                ["Battery charge", "M1.2", "consumer_energy_15min[7]", "HEE 1 consumed energy"],
                ["SOC", "HEE 1", "battery_soc[7]", "Battery SOC in 0.1% units"],
            ]
        else:
            rows = [
                ["Site grid import", "Shared grid [0]", "source_energy_15min[0]", "Imported energy from grid"],
                ["Site grid export", "Shared grid [0]", "consumer_energy_15min[0]", "Exported energy to grid"],
                ["PV 1 production", "M2.3", "source_energy_15min[4]", "Soldin 75 kW"],
                ["PV 2 production", "M2.4", "source_energy_15min[5]", "Škrlj 258 kW"],
                ["Battery discharge", "M2.2", "source_energy_15min[7]", "HEE 2 produced/exported energy"],
                ["Battery charge", "M2.2", "consumer_energy_15min[7]", "HEE 2 consumed energy"],
                ["SOC", "HEE 2", "battery_soc[7]", "Battery SOC in 0.1% units"],
            ]

        st.dataframe(
            pd.DataFrame(
                rows,
                columns=[
                    "Dashboard value",
                    "Meter / device",
                    "API signal",
                    "Meaning in documentation",
                ],
            ),
            use_container_width=True,
            hide_index=True,
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
            df = schedule_dataframe(
                schedule_data,
                prefix,
                today_utc_to_ljubljana=(day_choice == "Today"),
            )
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

        if day_choice == "Today":
            local_now = now_ljubljana()
            slot_index = current_schedule_index(local_now)
            current_row = df.loc[df["Index"] == slot_index].iloc[0]
            current_energy = current_row["Energy (kWh/15 min)"]
            current_action = current_row["Action"]
            current_power = current_row["Average power (kW)"]

            st.info(
                f"Current Ljubljana time: "
                f"{local_now.strftime('%Y-%m-%d %H:%M:%S %Z')} · "
                f"Current schedule interval: {current_row['Interval']} · "
                f"Scheduled action: {current_action} · "
                f"Scheduled average power: {fmt_kw(current_power)}"
            )

            with st.expander("Time mapping details", expanded=False):
                offset_hours = (
                    local_now.utcoffset().total_seconds() / 3600
                    if local_now.utcoffset()
                    else 0
                )
                st.write(
                    f"Today mapping: Europe/Ljubljana = UTC{offset_hours:+.0f}. "
                    f"Local slot {int(current_row['Index'])} reads raw API slot "
                    f"{int(current_row['Raw API index'])}."
                )

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

        if day_choice == "Today":
            st.caption(
                "Today's API schedule is remapped from UTC-indexed 15-minute slots "
                "to Europe/Ljubljana local time. Tomorrow is left unchanged because "
                "the API already returns it aligned with the uploaded local schedule. "
                "Sign convention: negative = discharging/export, positive = charging/import."
            )
        else:
            st.caption(
                "Tomorrow's schedule is shown exactly as returned by the API because "
                "it already matches the uploaded Europe/Ljubljana schedule. "
                "Sign convention: negative = discharging/export, positive = charging/import."
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
    'Live battery SOC, PV production, individual & combined grid flow and EMS schedules · Europe/Ljubljana time'
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

    polled_at = now_ljubljana()
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
                Last API poll: {polled_at.strftime("%Y-%m-%d %H:%M:%S %Z")}
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif readings:
        st.markdown(
            f"""
            <div class="status-card status-warning">
                <b>● PARTIAL · Some systems could not be read</b><br>
                Last API poll: {polled_at.strftime("%Y-%m-%d %H:%M:%S %Z")}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="status-card status-error">
                <b>● OFFLINE / API ERROR · No selected system returned live data</b><br>
                Last API attempt: {polled_at.strftime("%Y-%m-%d %H:%M:%S %Z")}
            </div>
            """,
            unsafe_allow_html=True,
        )

    if readings:
        render_site_grid(readings)
        st.divider()

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
