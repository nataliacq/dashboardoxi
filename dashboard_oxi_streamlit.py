from datetime import datetime

import pandas as pd
import streamlit as st

SHEET_ID = "1s05TfnAHtRQpnjX0iwOcLsWVX1rCfz_v"
SHEET_NAME = "Estado"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"

st.set_page_config(page_title="Estado OXI", layout="wide")
st.title("Estado OXI")

if st.sidebar.button("🔄 Actualizar"):
    st.rerun()

try:
    with st.spinner("Cargando datos desde Google Sheets..."):
        df = pd.read_csv(CSV_URL)
    st.caption(f"Última carga: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    st.dataframe(df, use_container_width=True, hide_index=True)
except Exception as exc:
    st.error(f"No se pudo cargar el Google Sheet: {exc}")
