import json
import math
import time
import zipfile
from io import BytesIO

import pandas as pd
import requests
import streamlit as st


API_URL = (
    "https://api.informatika.si/"
    "enotna-vstopna-tocka/merilni-podatki/meter-readings"
)

CHUNK_SIZE = 50
REQUEST_TIMEOUT_SECONDS = 60
MAX_RETRIES = 3
RETRY_STATUS_CODES = {429, 502, 503, 504}


def get_authorization_header(ceeps_id: str) -> str:
    """Return the Basic Authorization header value for the selected CEEPS identity."""
    secret_name = "encoded_string_sfa" if ceeps_id == "SFA" else "encoded_string_nme"

    try:
        encoded_string = st.secrets[secret_name]
    except KeyError as exc:
        raise RuntimeError(
            f"Missing Streamlit secret: '{secret_name}'. "
            "Please configure it in secrets.toml or Streamlit Cloud secrets."
        ) from exc

    return f"Basic {encoded_string}"


def build_request_params(
    message_type: str,
    usage_points_chunk: list[str],
    start_date,
    end_date,
) -> list[tuple[str, str]]:
    """Build query parameters without manually concatenating a URL."""
    params: list[tuple[str, str]] = []

    if message_type == "Daily 15 minute":
        params.append(("messageType", "D1_15MIN"))
    elif message_type == "Monthly 15 minute":
        params.append(("messageType", "M1_15MIN"))
    elif message_type == "Specify date":
        params.append(("startTime", str(start_date)))
        params.append(("endTime", str(end_date)))
    else:
        raise ValueError(f"Unsupported message type: {message_type}")

    for usage_point in usage_points_chunk:
        params.append(("usagePoints", usage_point))

    return params


def request_meter_readings(
    message_type: str,
    ceeps_id: str,
    usage_points_chunk: list[str],
    start_date,
    end_date,
) -> requests.Response:
    """
    Request one chunk of meter readings from the production CEEPS API.

    Retries are used only for temporary server/rate-limit responses.
    """
    headers = {
        "Accept": "application/json",
        "Authorization": get_authorization_header(ceeps_id),
    }

    params = build_request_params(
        message_type=message_type,
        usage_points_chunk=usage_points_chunk,
        start_date=start_date,
        end_date=end_date,
    )

    last_response = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                API_URL,
                headers=headers,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            last_response = response
        except requests.Timeout as exc:
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"CEEPS request timed out after {REQUEST_TIMEOUT_SECONDS} seconds."
                ) from exc

            time.sleep(attempt * 2)
            continue

        except requests.ConnectionError as exc:
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    "Could not connect to the CEEPS API. "
                    "Please check network connectivity and API availability."
                ) from exc

            time.sleep(attempt * 2)
            continue

        except requests.RequestException as exc:
            raise RuntimeError(f"CEEPS request failed: {exc}") from exc

        if response.status_code not in RETRY_STATUS_CODES:
            return response

        if attempt < MAX_RETRIES:
            retry_after = response.headers.get("Retry-After")
            try:
                delay = int(retry_after) if retry_after else attempt * 2
            except ValueError:
                delay = attempt * 2

            time.sleep(min(delay, 10))

    return last_response


def parse_json_response(response: requests.Response):
    """Safely decode a CEEPS response as JSON."""
    try:
        return response.json()
    except requests.exceptions.JSONDecodeError as exc:
        content_type = response.headers.get("Content-Type", "unknown")
        body_preview = (response.text or "<empty response>").strip()[:2000]

        raise ValueError(
            "CEEPS returned a response that is not valid JSON.\n\n"
            f"HTTP status: {response.status_code}\n"
            f"Content-Type: {content_type}\n"
            f"Response: {body_preview}"
        ) from exc


def format_http_error(response: requests.Response) -> str:
    """Return a readable error message for a non-successful HTTP response."""
    content_type = response.headers.get("Content-Type", "unknown")
    body = (response.text or "<empty response>").strip()

    try:
        parsed = response.json()
        body = json.dumps(parsed, ensure_ascii=False, indent=2)
    except (requests.exceptions.JSONDecodeError, ValueError):
        pass

    body = body[:3000]

    friendly_messages = {
        400: "The request was rejected as invalid.",
        401: "Authentication failed. Please check the configured CEEPS credentials.",
        403: "Access was denied by the CEEPS API.",
        404: "The requested CEEPS API endpoint was not found.",
        429: "The CEEPS API rate limit was reached.",
        500: "The CEEPS API encountered an internal server error.",
        502: "The CEEPS gateway received an invalid response from the backend.",
        503: "The CEEPS service is currently unavailable.",
        504: "The CEEPS gateway timed out while waiting for the backend.",
    }

    summary = friendly_messages.get(
        response.status_code,
        "The CEEPS API returned an unsuccessful response.",
    )

    return (
        f"{summary}\n\n"
        f"HTTP {response.status_code} {response.reason}\n"
        f"Content-Type: {content_type}\n"
        f"Response: {body}"
    )


def create_zip(json_responses: list[dict]) -> BytesIO:
    """Create a ZIP archive containing one JSON file per usage point."""
    zip_buffer = BytesIO()
    used_filenames: set[str] = set()

    with zipfile.ZipFile(
        zip_buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zip_file:
        for response_index, response_json in enumerate(json_responses, start=1):
            meter_readings = response_json.get("meterReadings", [])

            if not isinstance(meter_readings, list):
                continue

            for reading_index, meter_reading in enumerate(meter_readings, start=1):
                if not isinstance(meter_reading, dict):
                    continue

                usage_point = str(
                    meter_reading.get(
                        "usagePoint",
                        f"unknown_{response_index}_{reading_index}",
                    )
                ).strip()

                safe_usage_point = "".join(
                    char if char.isalnum() or char in ("-", "_", ".") else "_"
                    for char in usage_point
                )

                base_filename = safe_usage_point or f"reading_{response_index}_{reading_index}"
                filename = f"{base_filename}.json"

                duplicate_index = 2
                while filename in used_filenames:
                    filename = f"{base_filename}_{duplicate_index}.json"
                    duplicate_index += 1

                used_filenames.add(filename)

                json_data = json.dumps(
                    meter_reading,
                    ensure_ascii=False,
                    indent=2,
                )
                zip_file.writestr(filename, json_data)

    zip_buffer.seek(0)
    return zip_buffer


def load_usage_points(uploaded_file) -> list[str]:
    """Read and validate usage points from the uploaded Excel file."""
    try:
        df = pd.read_excel(
            uploaded_file,
            converters={"Merilna točka": str},
        )
    except Exception as exc:
        raise ValueError(f"Could not read the Excel file: {exc}") from exc

    required_column = "Merilna točka"

    if required_column not in df.columns:
        available_columns = ", ".join(map(str, df.columns))
        raise ValueError(
            f"The Excel file must contain a '{required_column}' column. "
            f"Available columns: {available_columns or 'none'}"
        )

    usage_points = (
        df[required_column]
        .dropna()
        .astype(str)
        .str.strip()
    )

    usage_points = [
        point
        for point in usage_points
        if point and point.lower() != "nan"
    ]

    # Preserve the original order while removing duplicates.
    usage_points = list(dict.fromkeys(usage_points))

    if not usage_points:
        raise ValueError("No valid usage points were found in the Excel file.")

    return usage_points


def main():
    st.set_page_config(
        page_title="CEEPS Meter Readings",
        layout="centered",
    )

    st.subheader("CEEPS Meter Readings")
    st.caption("Retrieve meter readings from the production CEEPS API.")

    ceeps_id = st.selectbox(
        "CEEPS Identity",
        ("NME", "SFA"),
    )

    message_type = st.selectbox(
        "Type of meter readings",
        (
            "Daily 15 minute",
            "Monthly 15 minute",
            "Specify date",
        ),
    )

    start_date = ""
    end_date = ""

    if message_type == "Specify date":
        col_left, col_right = st.columns(2)

        with col_left:
            start_date = st.date_input("Start date")

        with col_right:
            end_date = st.date_input("End date")

        if start_date > end_date:
            st.error("Start date cannot be later than end date.")

    uploaded_file = st.file_uploader(
        "Upload Excel file with meter points",
        type=["xlsx"],
        help="The file must contain a column named 'Merilna točka'.",
    )

    if uploaded_file is None:
        return

    try:
        usage_points_list = load_usage_points(uploaded_file)
    except ValueError as exc:
        st.error(str(exc))
        return

    st.success(
        f"Loaded {len(usage_points_list)} unique meter point"
        f"{'s' if len(usage_points_list) != 1 else ''}."
    )

    if message_type == "Specify date" and start_date > end_date:
        return

    if not st.button(
        "Retrieve meter readings",
        type="primary",
        use_container_width=True,
    ):
        return

    num_chunks = math.ceil(len(usage_points_list) / CHUNK_SIZE)
    json_responses: list[dict] = []
    failed_chunks: list[int] = []

    progress_bar = st.progress(0)
    status_placeholder = st.empty()

    for i in range(num_chunks):
        chunk_number = i + 1
        usage_points_chunk = usage_points_list[
            i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE
        ]

        status_placeholder.info(
            f"Retrieving chunk {chunk_number} of {num_chunks} "
            f"({len(usage_points_chunk)} meter points)..."
        )

        try:
            response = request_meter_readings(
                message_type=message_type,
                ceeps_id=ceeps_id,
                usage_points_chunk=usage_points_chunk,
                start_date=start_date,
                end_date=end_date,
            )
        except RuntimeError as exc:
            failed_chunks.append(chunk_number)
            st.error(f"Chunk {chunk_number}: {exc}")
            progress_bar.progress(chunk_number / num_chunks)
            continue

        if response.status_code != 200:
            failed_chunks.append(chunk_number)
            st.error(
                f"Chunk {chunk_number} failed:\n\n"
                f"{format_http_error(response)}"
            )
            progress_bar.progress(chunk_number / num_chunks)
            continue

        try:
            response_json = parse_json_response(response)
        except ValueError as exc:
            failed_chunks.append(chunk_number)
            st.error(f"Chunk {chunk_number}: {exc}")
            progress_bar.progress(chunk_number / num_chunks)
            continue

        if not isinstance(response_json, dict):
            failed_chunks.append(chunk_number)
            st.error(
                f"Chunk {chunk_number}: CEEPS returned valid JSON, "
                "but the top-level value is not a JSON object."
            )
            progress_bar.progress(chunk_number / num_chunks)
            continue

        json_responses.append(response_json)
        progress_bar.progress(chunk_number / num_chunks)

    status_placeholder.empty()

    successful_chunks = len(json_responses)

    if successful_chunks:
        if failed_chunks:
            st.warning(
                f"Completed with partial success: "
                f"{successful_chunks}/{num_chunks} chunks succeeded. "
                f"Failed chunks: {', '.join(map(str, failed_chunks))}."
            )
        else:
            st.success(
                f"Retrieval completed successfully. "
                f"All {num_chunks} chunk{'s' if num_chunks != 1 else ''} succeeded."
            )

        json_download = json.dumps(
            json_responses,
            ensure_ascii=False,
            indent=2,
        )

        col_json, col_zip = st.columns(2)

        with col_json:
            st.download_button(
                "Download JSON",
                type="primary",
                data=json_download,
                file_name="ceeps_meter_readings.json",
                mime="application/json",
                use_container_width=True,
            )

        with col_zip:
            st.download_button(
                "Download ZIP",
                data=create_zip(json_responses),
                file_name="ceeps_meter_readings.zip",
                mime="application/zip",
                use_container_width=True,
            )

    else:
        st.error(
            "No meter readings were retrieved successfully. "
            "Review the error messages above for details."
        )


main()
