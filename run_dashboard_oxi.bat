@echo off
cd /d %~dp0
if not exist "OXI ESTADO.xlsm" (
    echo No se encontro OXI ESTADO.xlsm en esta carpeta.
    echo Coloca el Excel junto a este .bat y al archivo dashboard_oxi_streamlit.py
    pause
    exit /b 1
)
pip install -r requirements_dashboard_oxi.txt
streamlit run dashboard_oxi_streamlit.py
