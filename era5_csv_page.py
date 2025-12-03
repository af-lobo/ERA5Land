import streamlit as st
import altair as alt

from era5_daily_analysis import (
    streamlit_upload_and_load,
    detect_variable_columns,
    summarize_daily_variables,
    compute_event_masks,
    summarize_event_frequency_severity,
    yearly_event_counts,
    apply_seasonal_window,      # <-- importante
)

from era5_report import generate_pdf_report


def show_era5_csv_page():
    st.title("Análise ERA5 diária – CSV do Google Earth Engine")

    # -------------------------------------------------
    # 1. Carregar CSV
    # -------------------------------------------------
    df = streamlit_upload_and_load(st, "Carrega ficheiro diário ERA5 do GEE")

    if df is None:
        st.info("Carrega um ficheiro CSV exportado do GEE para começar.")
        return

    st.subheader("Pré-visualização")
    st.dataframe(df.head())

    # Vamos trabalhar sempre numa cópia que pode ser filtrada sazonalmente
    df_for_analysis = df.copy()

    # -------------------------------------------------
    # 2. Janela sazonal
    # -------------------------------------------------
    st.subheader("Janela sazonal para análise 🔁")

    seasonal_info = {"active": False}
    use_seasonal = st.checkbox(
        "Aplicar janela sazonal (mesmo que o CSV tenha o ano completo)"
    )

    if use_seasonal:
        month_labels = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                        "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        month_to_int = {label: i + 1 for i, label in enumerate(month_labels)}

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            start_month_label = st.selectbox("Mês início", month_labels, index=0)
            start_day = st.number_input("Dia início", min_value=1, max_value=31, value=1)
        with col_s2:
            end_month_label = st.selectbox("Mês fim", month_labels, index=11)
            end_day = st.number_input("Dia fim", min_value=1, max_value=31, value=31)

        start_month = month_to_int[start_month_label]
        end_month = month_to_int[end_month_label]

        try:
            df_for_analysis, seasonal_info = apply_seasonal_window(
                df,
                start_month=int(start_month),
                start_day=int(start_day),
                end_month=int(end_month),
                end_day=int(end_day),
            )

            if seasonal_info.get("active"):
                st.write(
                    "Janela sazonal aplicada: "
                    + f"{start_day}-{start_month_label} até "
                    + f"{end_day}-{end_month_label} "
                    + f"(dias em análise: {seasonal_info.get('n_days_after', 'NA')})"
                )
            else:
                st.write(
                    "Não foi possível aplicar janela sazonal; a análise será feita com o ano completo."
                )
        except ValueError as e:
            # Qualquer problema com datas / parsing cai aqui
            st.error(
                "Erro ao aplicar janela sazonal. "
                "Verifica se a coluna 'date' do CSV está no formato YYYY-MM-DD."
            )
            st.text(str(e))
            df_for_analysis = df.copy()
            seasonal_info = {"active": False}

    else:
        st.write(f"Nenhum filtro sazonal aplicado (dias em análise: {len(df_for_analysis)})")

    # -------------------------------------------------
    # 3. Variáveis e resumo estatístico
    # -------------------------------------------------
    var_cols = detect_variable_columns(df_for_analysis)
    st.subheader("Variáveis disponíveis")
    st.write(var_cols)

    summary = summarize_daily_variables(df_for_analysis, var_cols)
    st.subheader("Resumo estatístico")
    st.dataframe(summary)

    # -------------------------------------------------
    # 4. Parâmetros dos eventos
    # -------------------------------------------------
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

    # -------------------------------------------------
    # 5. Cálculo dos eventos (usando df_for_analysis!)
    # -------------------------------------------------
    masks = compute_event_masks(
        df_for_analysis,
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

    # -------------------------------------------------
    # 6. Frequência e severidade
    # -------------------------------------------------
    from era5_report import build_event_stats_for_report  # opcional, se quiseres alinhar tudo

    freq_sev = summarize_event_frequency_severity(df_for_analysis, masks)
    st.subheader("Frequência e severidade dos eventos")
    st.dataframe(freq_sev)

    # -------------------------------------------------
    # 7. Ocorrências por ano (gráfico)
    # -------------------------------------------------
    yearly = yearly_event_counts(df_for_analysis, masks)

    st.subheader("Número de dias de evento por ano")

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

    # -------------------------------------------------
    # 8. Botão de relatório PDF
    # -------------------------------------------------
    st.subheader("Relatório PDF")

    col_meta1, col_meta2 = st.columns(2)
    with col_meta1:
        location_name = st.text_input("Nome da localização", value="Local 1")
        lat = st.number_input("Latitude", value=0.0, format="%.6f")
        lon = st.number_input("Longitude", value=0.0, format="%.6f")
    with col_meta2:
        lang_label = st.selectbox(
            "Idioma do relatório",
            options=[("pt", "Português"), ("en", "English"), ("es", "Español")],
            index=0,
            format_func=lambda x: x[1],
        )
        lang_code = lang_label[0]

    if st.button("📄 Gerar relatório em PDF deste ficheiro"):
        # dicionário de parâmetros a passar para o relatório
        params_for_report = {
            "frost_temp_C": frost_temp,
            "frost_max_wind_ms": frost_max_wind,
            "frost_max_dew_delta_C": frost_dew_delta,
            "rain_threshold_mm": rain_thresh,
            "heavy_rain_threshold_mm": heavy_rain_thresh,
            "heat_threshold_C": heat_thresh,
            "wind_gust_threshold_ms": wind_gust_thresh,
        }

        meta = {
            "location_name": location_name,
            "lat": lat,
            "lon": lon,
            "filename": getattr(df, "name", ""),
        }

        pdf_bytes = generate_pdf_report(
            df_for_analysis,      # df já com janela sazonal aplicada
            seasonal_info,
            masks,
            freq_sev,
            params_for_report,    # <-- aqui em vez de params_dict
            meta=meta,
            lang=lang_code,
        )

        st.download_button(
            "⬇️ Descarregar relatório PDF",
            data=pdf_bytes,
            file_name="analise_risco_climatico.pdf",
            mime="application/pdf",
        )
