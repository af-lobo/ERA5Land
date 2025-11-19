import streamlit as st
from era5_daily_analysis import (
    streamlit_upload_and_load,
    detect_variable_columns,
    summarize_daily_variables,
    compute_event_masks,
    summarize_event_frequency_severity,
    yearly_event_counts,
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
    
    # --------------------------
    # Parâmetros dos eventos
    # --------------------------
    
    with st.expander("Parâmetros dos eventos climáticos", expanded=True):
        st.markdown("### Geada")
        frost_temp = st.number_input("Temperatura máxima para geada (°C)", value=0.0, step=0.5)
        frost_max_wind = st.number_input("Vento médio máximo (m/s)", value=3.0, step=0.5)
        frost_dew_delta = st.number_input(
            "Diferença máxima |Tmin - ponto de orvalho| (°C)",
            value=2.0,
            step=0.5,
            help="Valores baixos indicam ar húmido, favorável à formação de geada.",
        )

        st.markdown("### Chuva")
        rain_thresh = st.number_input("Limite para 'dia chuvoso' (mm/dia)", value=0.2, step=0.1)
        heavy_rain_thresh = st.number_input("Limite para 'chuva forte' (mm/dia)", value=20.0, step=1.0)

        st.markdown("### Calor e vento")
        heat_thresh = st.number_input("Limite para calor extremo (Tmax ≥ °C)", value=35.0, step=1.0)
        wind_gust_thresh = st.number_input("Limite para vento forte (rajada ≥ m/s)", value=20.0, step=1.0)
    summary = summarize_daily_variables(df, var_cols)
    
    # --------------------------
    # Cálculo dos eventos
    # --------------------------
    
    masks = compute_event_masks(
        df,
        frost_temp_C=frost_temp,
        frost_max_wind_ms=frost_max_wind,
        frost_max_dew_delta_C=frost_dew_delta,
        rain_threshold_mm=rain_thresh,
        heavy_rain_threshold_mm=heavy_rain_thresh,
        heat_threshold_C=heat_thresh,
        wind_gust_threshold_ms=wind_gust_thresh,
    )

    if not masks:
        st.warning("Não foi possível calcular eventos (faltam algumas variáveis).")
        return

    # --------------------------
    # Ocorrências por ano (gráfico)
    # --------------------------
    yearly = yearly_event_counts(df, masks)

    st.subheader("Número de dias de evento por ano")

    # selector de evento
    event_labels = {
        "frost": "Geada",
        "rain_day": "Dia chuvoso",
        "heavy_rain": "Chuva forte",
        "heat": "Calor extremo",
        "strong_wind": "Vento forte",
    }
    available_keys = sorted({e for e in yearly["event_key"].unique()})
    key = st.selectbox(
        "Escolhe o tipo de evento para visualizar",
        options=available_keys,
        format_func=lambda k: event_labels.get(k, k),
    )

    yearly_sel = yearly[yearly["event_key"] == key]

    chart = (
        alt.Chart(yearly_sel)
        .mark_bar()
        .encode(
            x=alt.X("year:O", title="Ano"),
            y=alt.Y("dias_evento:Q", title="Nº de dias com evento"),
            tooltip=["year", "dias_evento"],
        )
        .properties(height=300)
    )

    st.altair_chart(chart, use_container_width=True)

    
    freq_sev = summarize_event_frequency_severity(df, masks)
    st.subheader("Frequência e severidade dos eventos")
    st.dataframe(freq_sev)
    
    st.subheader("Resumo estatístico")
    st.dataframe(summary)

    st.subheader("Geadas (Tmin < 0°C)")
    st.write(frost_stats(df, threshold_C=0.0))

    st.subheader("Chuva intensa (>20 mm)")
    st.write(heavy_rain_events(df, precip_col="precip_mm", threshold_mm=20))
