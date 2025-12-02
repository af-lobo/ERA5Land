import streamlit as st
import altair as alt

from era5_daily_analysis import (
    streamlit_upload_and_load,
    detect_variable_columns,
    summarize_daily_variables,
    compute_event_masks,
    summarize_event_frequency_severity,
    yearly_event_counts,
    apply_seasonal_window,   # <- IMPORT DA JANELA SAZONAL
)

from era5_report import generate_pdf_report

def show_era5_csv_page():
    st.title("Análise ERA5 diária – CSV do Google Earth Engine")

    # -------------------------------------------------
    # 1) Carregar ficheiro
    # -------------------------------------------------
    df_raw = streamlit_upload_and_load(st, "Carrega ficheiro diário ERA5 do GEE")

    if df_raw is None:
        st.info("Carrega um ficheiro CSV exportado do GEE para começar.")
        return

    st.subheader("Pré-visualização (dados originais)")
    st.dataframe(df_raw.head())

    # -------------------------------------------------
    # 2) Janela sazonal para ANÁLISE
    # (o CSV pode ter ano completo, mas aqui filtras só o período de interesse)
    # -------------------------------------------------
    st.subheader("Janela sazonal para análise")

    use_window = st.checkbox(
        "Aplicar janela sazonal (mesmo que o CSV tenha o ano completo)",
        value=False,
    )

    if use_window:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Início**")
            start_month = st.number_input("Mês inicial", min_value=1, max_value=12, value=1, step=1)
            start_day = st.number_input("Dia inicial", min_value=1, max_value=31, value=1, step=1)

        with col2:
            st.markdown("**Fim**")
            end_month = st.number_input("Mês final", min_value=1, max_value=12, value=12, step=1)
            end_day = st.number_input("Dia final", min_value=1, max_value=31, value=31, step=1)

        df = apply_seasonal_window(
            df_raw,
            start_month=int(start_month),
            start_day=int(start_day),
            end_month=int(end_month),
            end_day=int(end_day),
        )

        st.caption(
            f"Janela aplicada a todos os anos: "
            f"{start_day:02d}/{start_month:02d} – {end_day:02d}/{end_month:02d} "
            f"(dias após filtro: {len(df)} de {len(df_raw)})"
        )

        if df.empty:
            st.warning(
                "Após aplicar a janela sazonal não ficou nenhum dia. "
                "Ajusta as datas ou desactiva a opção de janela sazonal."
            )
            return
    else:
        df = df_raw.copy()
        st.caption(f"Nenhum filtro sazonal aplicado (dias em análise: {len(df)})")

    # -------------------------------------------------
    # 3) Variáveis disponíveis
    # -------------------------------------------------
    var_cols = detect_variable_columns(df)
    st.subheader("Variáveis disponíveis na série filtrada")
    st.write(var_cols)

    # -----------------------------------
    # 4) Estatísticas básicas
    # -----------------------------------
    summary = summarize_daily_variables(df, var_cols)
    st.subheader("Resumo estatístico")
    if summary.empty:
        st.info("Não foram encontradas variáveis numéricas conhecidas para resumir.")
    else:
        st.dataframe(summary)

    # -----------------------------------
    # 5) Parâmetros dos eventos
    # -----------------------------------
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

    # -----------------------------------
    # 6) Cálculo dos eventos
    # -----------------------------------
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

    # -----------------------------------
    # 7) Frequência e severidade
    # -----------------------------------
    freq_sev = summarize_event_frequency_severity(df, masks)
    st.subheader("Frequência e severidade dos eventos")
    st.dataframe(freq_sev)

    # -----------------------------------
    # 8) Ocorrências por ano (gráfico)
    # -----------------------------------
    yearly = yearly_event_counts(df, masks)

    st.subheader("Número de dias de evento por ano")

    event_labels = {
        "frost": "Geada",
        "rain_day": "Dia chuvoso",
        "heavy_rain": "Chuva forte",
        "heat": "Calor extremo",
        "strong_wind": "Vento forte",
    }

    if yearly.empty:
        st.info("Não há dados suficientes para o gráfico anual.")
        return

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

# -----------------------------------------------------
#  GERAR RELATÓRIO PDF
# -----------------------------------------------------
st.subheader("Gerar relatório PDF")

if st.button("📄 Gerar relatório PDF"):
    
    # --- Construir dicionário de parâmetros usados ---
    event_params = {
        "frost": {
            "Temp máx. para geada (°C)": frost_temp,
            "Vento médio máx. (m/s)": frost_max_wind,
            "Δ(Tmin - Orvalho) máx. (°C)": frost_dew_delta,
        },
        "rain_day": {
            "Limite para dia chuvoso (mm)": rain_thresh,
        },
        "heavy_rain": {
            "Limite para chuva forte (mm)": heavy_rain_thresh,
        },
        "heat": {
            "Limite para calor extremo (°C)": heat_thresh,
        },
        "strong_wind": {
            "Limite para vento forte (m/s)": wind_gust_thresh,
        },
    }

    # --- Criar relatório PDF em memória ---
    pdf_bytes = generate_pdf_report(
        df=df_seasonal,                    # dataframe já filtrado
        masks=masks,                       # máscaras de eventos
        event_params=event_params,         # parâmetros escolhidos
        seasonal_info=seasonal_info,       # texto da janela sazonal
        report_title=report_title,         # título do relatório
    )

    st.success("Relatório gerado com sucesso!")

    # --- Botão para descarregar ---
    st.download_button(
        label="⬇️ Descarregar relatório PDF",
        data=pdf_bytes,
        file_name=f"Relatorio_ERA5_{report_title}.pdf",
        mime="application/pdf",
    )
