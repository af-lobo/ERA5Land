import streamlit as st
from era5_daily_analysis import (
    streamlit_upload_and_load,
    detect_variable_columns,
    summarize_daily_variables,
    frost_stats,
    heavy_rain_events,
)

def show_era5_csv_page():
    st.title("Análise ERA5 diária – CSV do Google Earth Engine")

    df = streamlit_upload_and_load(st, "Carrega ficheiro diário ERA5 do GEE")

    if df is None:
        st.info("Carrega um ficheiro CSV exportado do GEE para começar.")
        return

    st.subheader("Pré-visualização")
    st.dataframe(df.head())

    var_cols = detect_variable_columns(df)
    st.subheader("Variáveis disponíveis")
    st.write(var_cols)

    summary = summarize_daily_variables(df, var_cols)
    st.subheader("Resumo estatístico")
    st.dataframe(summary)

    st.subheader("Geadas (Tmin < 0°C)")
    st.write(frost_stats(df, threshold_C=0.0))

    st.subheader("Chuva intensa (>20 mm)")
    st.write(heavy_rain_events(df, precip_col="precip_mm", threshold_mm=20))
