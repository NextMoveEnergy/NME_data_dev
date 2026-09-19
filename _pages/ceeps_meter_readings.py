import json
import math
import zipfile
from io import BytesIO
from typing import Any

import pandas as pd
import requests
import streamlit as st


PAGE_TITLE = "CEEPS Meter Readings"
DEFAULT_API_URL = (
    "https://api-test.informatika.si/"
    "enotna-vstopna-tocka/merilni-podatki/meter-readings"
)
USAGE_POINT_COLUMN = "Merilna točka"
CHUNK_SIZE = 50
REQUEST_TIMEOUT_SECONDS = 60


class CEEPSRequestError(Exception):
    """Raised when a request to CEEPS cannot be completed successfully."""


def get_api_url() -> str:
    """Return the configured API URL, falling back to the current test endpoint."""
    return st.secrets.get("ceeps_meter_readings_url", DEFAULT_API_URL)


def get_authorization_token(ceeps_id: str) -> str:
    """Return the Basic Auth token for the selected CEEPS identity."""
    secret_key = "encoded_string_sfa" if ceeps_id == "SFA" else "encoded_string_nme"

    try:
        token = st.secrets[secret_key]
    except KeyError as exc:
        raise CEEPSRequestError(
            f"Missing Streamlit secret: '{secret_key}'."
        ) from exc

    if not token:
        raise CEEPSRequestError(
            f"Streamlit secret '{secret_key}' is empty."
        )

    return token


def build_request_params(
    message_type: str,
    usage_points: list[str],
    start_date: Any,
    end_date: Any,
) -> list[tuple[str, str]]:
    """Build query parameters for the CEEPS meter-readings endpoint."""
    params: list[tuple[str, str]] = []

    if message_type == "Daily 15 minute":
        params.append(("messageType", "D1_15MIN"))
    elif message_type == "Monthly 15 minute":
        params.append(("messageType", "M1_15MIN"))
    elif message_type == "Specify date":
        params.extend(
            [
                ("startTime", str(start_date)),
                ("endTime", str(end_date)),
            ]
        )
    else:
        raise CEEPSRequestError(f"Unsupported message type: {message_type}")

    params.extend(("usagePoints", point) for point in usage_points)
    return params


def request_meter_readings(
    session: requests.Session,
    message_type: str,
    ceeps_id: str,
    usage_points: list[str],
    start_date: Any,
    end_date: Any,
) -> requests.Response:
    """Request one chunk of meter readings from CEEPS."""
    token = get_authorization_token(ceeps_id)
    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {token}",
    }
    params = build_request_params(
        message_type=message_type,
        usage_points=usage_points,
        start_date=start_date,
        end_date=end_date,
    )

    try:
        return session.get(
            get_api_url(),
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.Timeout as exc:
        raise CEEPSRequestError(
            f"CEEPS did not respond within {REQUEST_TIMEOUT_SECONDS} seconds."
        ) from exc
    except requests.ConnectionError as exc:
        raise CEEPSRequestError(
            "Could not connect to the CEEPS API. Check network access and API availability."
        ) from exc
    except requests.RequestException as exc:
        raise CEEPSRequestError(f"CEEPS request failed: {exc}") from exc


def parse_json_response(response: requests.Response) -> Any:
    """Parse a response as JSON and raise a useful error when the body is not JSON."""
    try:
        return response.json()
    except requests.exceptions.JSONDecodeError as exc:
        content_type = response.headers.get("Content-Type", "unknown")
        body_preview = response.text.strip()[:1000] or "<empty response body>"
        raise CEEPSRequestError(
            "CEEPS returned a response that is not valid JSON. "
            f"HTTP {response.status_code}, Content-Type: {content_type}. "
            f"Response preview: {body_preview}"
        ) from exc


def get_error_details(response: requests.Response) -> str:
    """Return readable details for a non-successful HTTP response."""
    content_type = response.headers.get("Content-Type", "unknown")

    try:
        payload = response.json()
        body = json.dumps(payload, ensure_ascii=False, indent=2)
    except (requests.exceptions.JSONDecodeError, ValueError):
        body = response.text.strip() or "<empty response body>"

    if len(body) > 2000:
        body = f"{body[:2000]}\n... [truncated]"

    return (
        f"HTTP {response.status_code} {response.reason or ''}\n"
        f"Content-Type: {content_type}\n"
        f"Response: {body}"
    )


def normalize_usage_points(df: pd.DataFrame) -> list[str]:
    """Validate and normalize usage point IDs from the uploaded spreadsheet."""
    if USAGE_POINT_COLUMN not in df.columns:
        available_columns = ", ".join(map(str, df.columns)) or "<none>"
        raise ValueError(
            f"Required column '{USAGE_POINT_COLUMN}' was not found. "
            f"Available columns: {available_columns}"
        )

    usage_points = (
        df[USAGE_POINT_COLUMN]
        .dropna()
        .astype(str)
        .str.strip()
    )
    usage_points = usage_points[usage_points != ""]

    # Keep the original order while removing duplicates.
    return list(dict.fromkeys(usage_points.tolist()))


def create_zip(json_responses: list[dict[str, Any]]) -> BytesIO:
    """Create a ZIP file containing one JSON file per usage point."""
    zip_buffer = BytesIO()
    written_names: set[str] = set()

    with zipfile.ZipFile(
        zip_buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zip_file:
        for response_json in json_responses:
            meter_readings = response_json.get("meterReadings", [])

            if not isinstance(meter_readings, list):
                continue

            for meter_reading in meter_readings:
                if not isinstance(meter_reading, dict):
                    continue

                usage_point = str(meter_reading.get("usagePoint", "unknown")).strip()
                safe_usage_point = usage_point.replace("/", "_").replace("\\", "_")
                filename = f"{safe_usage_point or 'unknown'}.json"

                # Prevent accidental overwriting if the same usage point appears twice.
                if filename in written_names:
                    counter = 2
                    stem = filename[:-5]
                    while f"{stem}_{counter}.json" in written_names:
                        counter += 1
                    filename = f"{stem}_{counter}.json"

                written_names.add(filename)
                json_data = json.dumps(
                    meter_reading,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                zip_file.writestr(filename, json_data)

    zip_buffer.seek(0)
    return zip_buffer


def load_usage_points(uploaded_file: Any) -> list[str]:
    """Read and validate usage points from an uploaded XLSX file."""
    try:
        df = pd.read_excel(
            uploaded_file,
            converters={USAGE_POINT_COLUMN: str},
        )
    except Exception as exc:
        raise ValueError(f"Could not read the uploaded Excel file: {exc}") from exc

    return normalize_usage_points(df)


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, layout="centered")

    st.subheader(PAGE_TITLE)
    st.caption("Retrieve meter-reading JSON data from the CEEPS API.")

    ceeps_id = st.selectbox("CEEPS identity", ("NME", "SFA"))
    message_type = st.selectbox(
        "Meter reading type",
        ("Daily 15 minute", "Monthly 15 minute", "Specify date"),
    )

    start_date = None
    end_date = None

    if message_type == "Specify date":
        col_left, col_right = st.columns(2)
        with col_left:
            start_date = st.date_input("Start date")
        with col_right:
            end_date = st.date_input("End date")

        if start_date > end_date:
            st.error("Start date must be before or equal to end date.")
            return

    uploaded_file = st.file_uploader(
        "Upload an Excel file containing the 'Merilna točka' column",
        type=("xlsx",),
    )

    if uploaded_file is None:
        return

    try:
        usage_points = load_usage_points(uploaded_file)
    except ValueError as exc:
        st.error(str(exc))
        return

    if not usage_points:
        st.warning("No valid usage points were found in the uploaded file.")
        return

    st.success(f"Loaded {len(usage_points)} unique usage point(s).")

    if not st.button("Retrieve meter readings", type="primary"):
        return

    num_chunks = math.ceil(len(usage_points) / CHUNK_SIZE)
    json_responses: list[dict[str, Any]] = []
    failed_chunks: list[int] = []

    progress_bar = st.progress(0.0)
    status_text = st.empty()

    with requests.Session() as session:
        for index in range(num_chunks):
            chunk_number = index + 1
            usage_points_chunk = usage_points[
                index * CHUNK_SIZE : (index + 1) * CHUNK_SIZE
            ]

            status_text.write(
                f"Retrieving chunk {chunk_number} of {num_chunks} "
                f"({len(usage_points_chunk)} usage point(s))..."
            )

            try:
                response = request_meter_readings(
                    session=session,
                    message_type=message_type,
                    ceeps_id=ceeps_id,
                    usage_points=usage_points_chunk,
                    start_date=start_date,
                    end_date=end_date,
                )
            except CEEPSRequestError as exc:
                failed_chunks.append(chunk_number)
                st.error(f"Chunk {chunk_number}: {exc}")
                progress_bar.progress(chunk_number / num_chunks)
                continue

            if not response.ok:
                failed_chunks.append(chunk_number)
                with st.expander(
                    f"Chunk {chunk_number} failed — HTTP {response.status_code}",
                    expanded=True,
                ):
                    st.code(get_error_details(response), language="text")
                progress_bar.progress(chunk_number / num_chunks)
                continue

            try:
                parsed_response = parse_json_response(response)
            except CEEPSRequestError as exc:
                failed_chunks.append(chunk_number)
                st.error(f"Chunk {chunk_number}: {exc}")
                progress_bar.progress(chunk_number / num_chunks)
                continue

            if not isinstance(parsed_response, dict):
                failed_chunks.append(chunk_number)
                st.error(
                    f"Chunk {chunk_number}: CEEPS returned valid JSON, "
                    "but the top-level value is not a JSON object."
                )
                progress_bar.progress(chunk_number / num_chunks)
                continue

            json_responses.append(parsed_response)
            progress_bar.progress(chunk_number / num_chunks)

    status_text.empty()

    successful_chunks = len(json_responses)
    if successful_chunks:
        st.success(
            f"Completed {successful_chunks} of {num_chunks} chunk(s) successfully."
        )

        st.download_button(
            "Download combined JSON",
            type="primary",
            data=json.dumps(json_responses, ensure_ascii=False, indent=2),
            file_name="ceeps_meter_readings.json",
            mime="application/json",
        )

        st.download_button(
            "Download ZIP (one JSON per usage point)",
            data=create_zip(json_responses),
            file_name="ceeps_meter_readings.zip",
            mime="application/zip",
        )

    if failed_chunks:
        failed_chunk_text = ", ".join(map(str, failed_chunks))
        st.warning(
            f"Failed chunk(s): {failed_chunk_text}. "
            "Successful chunks, if any, are still available for download."
        )

    if not json_responses:
        st.error("No meter-reading data was retrieved successfully.")


main()
