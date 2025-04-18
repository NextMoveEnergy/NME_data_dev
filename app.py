import streamlit as st

pg = st.navigation([
    st.Page('_pages/generate_upn_xml.py', title="Generate UPN XML"),
    st.Page('_pages/retreive_meter_readings.py', title="Meter readings"),
    st.Page('_pages/priloga_a.py', title="Priloga A 2.6"),
    st.Page('_pages/priloga_b.py', title="Priloga A 2.7"),
    st.Page('_pages/json_dist.py', title="Json to distribution"),
    #st.Page('_pages/mojelektro_client.py', title="Moj Elektro"),
])

pg.run()