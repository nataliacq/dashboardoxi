import io

import pandas as pd
import requests
import streamlit as st

FILE_ID = "1s05TfnAHtRQpnjX0iwOcLsWVX1rCfz_v"
SHEET_NAME = "Estado"


@st.cache_data(show_spinner="Cargando datos desde Google Drive...")
def load_estado() -> pd.DataFrame:
    session = requests.Session()
    url = f"https://drive.google.com/uc?export=download&id={FILE_ID}"
    response = session.get(url, stream=True)

    # Google muestra una página de advertencia para archivos grandes; extraer token de confirmación
    confirm_token = None
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            confirm_token = value
            break

    if confirm_token:
        url = f"https://drive.google.com/uc?export=download&id={FILE_ID}&confirm={confirm_token}"
        response = session.get(url, stream=True)

    response.raise_for_status()
    return pd.read_excel(io.BytesIO(response.content), sheet_name=SHEET_NAME)


st.set_page_config(page_title="Estado OXI", layout="wide")
st.title("Estado OXI")

try:
    df = load_estado()
    st.dataframe(df, use_container_width=True, hide_index=True)
except Exception as exc:
    st.error(f"No se pudo cargar el archivo: {exc}")
