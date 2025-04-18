import streamlit as st
import pandas as pd


def podatki_merilnega_mesta():
    st.subheader("Podatki merilnega mesta")

    # Create a two-column layout
    col1, col2 = st.columns([1, 2])

    with col1:
        st.header("Upload File")
        # Option to upload an Excel file
        uploaded_file = st.file_uploader("Upload an Excel file", type=['xlsx'])

        if uploaded_file is not None:
            # Read the uploaded Excel file into the DataFrame
            st.session_state.df = pd.read_excel(uploaded_file)
            st.success('File uploaded successfully!')

    with col2:
        st.header("Manual Data Entry")
        # Input field for manually entering the number
        input_data = st.text_input('Enter the number in the format 2-183082')

        # Add the entered data to the DataFrame when the "Add" button is clicked
        if st.button('Add'):
            if input_data:
                # Add the input data as a new row to the DataFrame
                new_row = pd.DataFrame([[input_data]], columns=["Merilno mesto"])
                st.session_state.df = pd.concat([st.session_state.df, new_row], ignore_index=True)
            else:
                st.error('Please enter a value')

    # Display the current DataFrame in the main section
    st.header("DataFrame")
    edited_df = st.data_editor(st.session_state.df, num_rows="dynamic", key='data_editor')
    st.session_state.df = edited_df


def main():
    st.set_page_config(layout="wide")

    st.title("Moj Elektro")

    podatki_merilnega_mesta()

main()