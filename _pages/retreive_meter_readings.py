import json
import math
import zipfile
import pandas as pd
import streamlit as st
import requests
from io import BytesIO


def convert(response_json):
    json_file = BytesIO()
    json_file.write(response_json)
    return json_file


def request(message_type, ceeps_id, usage_points_chunk, start_date, end_date):
    base_url = "https://api.informatika.si/enotna-vstopna-tocka/merilni-podatki/meter-readings"

    encoded_string = st.secrets['encoded_string_nme']
    if ceeps_id == "SFA":
        encoded_string = st.secrets['encoded_string_sfa']

    headers = {
        'accept': 'application/json',
        'Authorization': f'Basic {encoded_string}'
    }

    if message_type == 'Daily 15 minute':
        base_url += '?messageType=D1_15MIN'
    elif message_type == 'Monthly 15 minute':
        base_url += '?messageType=M1_15MIN'
    elif message_type == 'Specify date':
        base_url += f'?startTime={start_date}&endTime={end_date}'

    usage_points_str = '&'.join(f"usagePoints={point}" for point in usage_points_chunk)
    complete_url = f"{base_url}&{usage_points_str}"

    return requests.get(complete_url, headers=headers)


def get_zip(json_responses):
    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for response_json in json_responses:
            meter_readings = response_json.get("meterReadings", [])
            for meter_reading in meter_readings:
                usage_point = meter_reading["usagePoint"]
                filename = f"{usage_point}.json"
                json_data = json.dumps(meter_reading, separators=(",", ":"))
                zip_file.writestr(filename, json_data)

    zip_buffer.seek(0)

    return zip_buffer


def main():
    st.set_page_config(layout="centered")

    st.subheader("Meter readings DEV MODE")

    ceeps_id = st.selectbox('CEEPS Identity', ('NME', 'SFA'))

    message_type = st.selectbox('Type of meter readings', ('Daily 15 minute', 'Monthly 15 minute', 'Specify date'))

    start_date, end_date = "", ""
    if message_type == 'Specify date':
        col_left, col_right = st.columns(2)
        with col_left:
            start_date = st.date_input('Start date')
        with col_right:
            end_date = st.date_input('End date')

    uploaded_file = st.file_uploader('Upload a file', type='xlsx')

    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file, converters={'Merilna točka': str})

        usage_points_list = df['Merilna točka'].tolist()

        if st.button('Retrieve', type='primary'):
            chunk_size = 50
            num_chunks = math.ceil(len(usage_points_list) / chunk_size)
            json_responses = []

            for i in range(num_chunks):
                usage_points_chunk = usage_points_list[i * chunk_size:(i + 1) * chunk_size]
                response = request(message_type, ceeps_id, usage_points_chunk, start_date, end_date)
                if response.status_code != 200:
                    st.write(f"Error in chunk {i + 1}: {response.json()}")
                else:
                    json_responses.append(response.json())

            if json_responses:
                st.download_button(
                    "Download",
                    type='primary',
                    data=json.dumps(json_responses),
                    file_name='meter_readings.json',
                    mime='application/json'
                )
                st.download_button(
                    "Download ZIP",
                    type='primary',
                    data=get_zip(json_responses),
                    file_name='meter_readings.zip'
                )


main()