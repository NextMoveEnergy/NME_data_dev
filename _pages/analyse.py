import streamlit as st
import pandas as pd
from datetime import datetime


def get_duplicates_count(df, start, end):
    return 0


def get_missing_readings_count(df, start, end):
    return 0


def validation(df, first_value, last_value):
    st.subheader("Validation")
    st.write("Choose a time interval you would like to validate")

    # Create two columns
    col_left, col_right = st.columns(2)

    # Create a start date and time input in the first column
    with col_left:
        start_date = st.date_input('Select a start date', first_value.date())
        start_time = st.time_input('Select a start time', first_value.time())
        start_datetime = datetime.combine(start_date, start_time)
        st.write('Start timestamp:', start_datetime)

    # Create an end date and time input in the second column
    with col_right:
        end_date = st.date_input('Select an end date', last_value.date())
        end_time = st.time_input('Select an end time', last_value.time())
        end_datetime = datetime.combine(end_date, end_time)
        st.write('End timestamp:', end_datetime)

    if st.button('Validate'):
        st.write(f"Number of duplicates:\n{get_duplicates_count(df, start_datetime, end_datetime)}")
        st.write(f"Missing readings from interval:\n{get_missing_readings_count(df, start_datetime, end_datetime)}")


def get_uploaded_file_type(df):
    CEEPS_file_columns = ['timestamp', 'value']
    MojElektro_file_columns = ['Časovna značka', 'Energija A+', 'Energija A-']

    if set(CEEPS_file_columns).issubset(df.columns):
        return "CEEPS"
    elif set(MojElektro_file_columns).issubset(df.columns):
        return "MojElektro"
    else:
        return "Unknown"


def get_kWh_format(input):
    return format(input, ',').replace(",", "@").replace(".", ",").replace("@", ".")


def details(df):
    st.subheader("Details")

    # Create two columns
    col1, col2 = st.columns(2)

    # Display the dataframe in the first column
    col1.write(df)

    # Display statistics in the second column
    first_value = pd.to_datetime(df.iloc[0]['timestamp'])
    last_value = pd.to_datetime(df.iloc[-1]['timestamp'])

    num_rows = len(df)

    sum_value_A_plus = round(sum(df['Energija A+']), 3)
    sum_value_A_minus = round(sum(df['Energija A-']), 3)
    formatted_sum_A_plus = get_kWh_format(sum_value_A_plus)
    formatted_sum_A_minus = get_kWh_format(sum_value_A_minus)

    col2.write(f"First value:\n{first_value}")
    col2.write(f"Last value:\n{last_value}")
    col2.write(f"Number of rows: {num_rows}")
    col2.write(f"Sum of A+ values:\n{formatted_sum_A_plus} kWh")
    col2.write(f"Sum of A- values:\n{formatted_sum_A_minus} kWh")

    validation(df, first_value, last_value)


def standardize(df, type_of_reading):
    pass


def initialization():
    st.subheader("Initialization")
    uploaded_file = st.file_uploader("Choose a file with 15 minute electricity readings", type=["xlsx"])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)

        type_of_reading = get_uploaded_file_type(df)
        st.write('You selected `%s` type of %s' % (uploaded_file.name, type_of_reading))

        df = standardize(df, type_of_reading)


def main():
    initialization()


if __name__ == "__main__":
    main()