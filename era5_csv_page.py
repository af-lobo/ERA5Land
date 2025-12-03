import streamlit as st
import altair as alt

from era5_daily_analysis import (
    streamlit_upload_and_load,
    detect_variable_columns,
    summarize_daily_variables,
    compute_event_masks,
    summarize_event_frequency_severity,
    yearly_event_counts,
    apply_seasonal_window,   # janela sazonal
)

from era5_report import generate_pdf_report


def show_era5_csv_page():
    st.title("Análise ERA5 diária – CSV do Google Earth Engine")

    # -------------------------------------------------
    # 1. Upload e leitura do ficheiro
    # -------------------------------------------------
    df = streamlit_upload_and_load(st, "Carrega ficheiro diário ERA5 do GEE")

    if df is None:
        st.info("Carrega um ficheiro CSV exportado do GEE para começar.")
        return

    st.subheader("Pré-visualização")
    st.dataframe(df.head())

    # -------------------------------------------------
    # 2. Variáveis disponíveis
    # -------------------------------------------------
    var_cols = detect_variable_columns(df)
    st.subheader("Variáveis disponíveis")
    st.write(var_cols)

    # ---------------------------------------------------------
# 3. Janela sazonal para análise
# ---------------------------------------------------------
st.header("Janela sazonal para análise")

use_seasonal = st.checkbox(
    "Aplicar janela sazonal (mesmo que o CSV tenha o ano completo)",
    value=False,
)

# meses para o selectbox (label -> número do mês)
MONTH_LABELS = [
    ("Jan", 1),
    ("Fev", 2),
    ("Mar", 3),
    ("Abr", 4),
    ("Mai", 5),
    ("Jun", 6),
    ("Jul", 7),
    ("Ago", 8),
    ("Set", 9),
    ("Out", 10),
    ("Nov", 11),
    ("Dez", 12),
]

df_for_analysis = df.copy()
seasonal_info = None  # <-- importante inicializar

if use_seasonal:
    st.markdown("Seleciona a janela sazonal (aplicada a todos os anos).")

    col_sm, col_em = st.columns(2)
    with col_sm:
        start_month_label = st.selectbox(
            "Mês início",
            options=MONTH_LABELS,
            format_func=lambda x: x[0],
            index=0,
        )
    with col_em:
        end_month_label = st.selectbox(
            "Mês fim",
            options=MONTH_LABELS,
            format_func=lambda x: x[0],
            index=11,
        )

    start_month = start_month_label[1]
    end_month = end_month_label[1]

    col_sd, col_ed = st.columns(2)
    with col_sd:
        start_day = st.number_input("Dia início", min_value=1, max_value=31, value=1)
    with col_ed:
        end_day = st.number_input("Dia fim", min_value=1, max_value=31, value=31)

    try:
        df_for_analysis = apply_seasonal_window(
            df,
            start_month=int(start_month),
            start_day=int(start_day),
            end_month=int(end_month),
            end_day=int(end_day),
        )

        seasonal_info = {
            "start_month": int(start_month),
            "start_day": int(start_day),
            "end_month": int(end_month),
            "end_day": int(end_day),
        }

        st.success(
            f"Janela sazonal aplicada: {start_day:02d}/{start_month:02d} "
            f"- {end_day:02d}/{end_month:02d}. "
            f"Dias em análise: {len(df_for_analysis)}"
        )

    except Exception:
        st.error(
            "Erro ao aplicar janela sazonal.\n\n"
            "Verifica se a coluna 'date' do CSV está no formato YYYY-MM-DD."
        )
        return  # pára a função se algo correu mal

else:
    st.caption(
        f"Nenhum filtro sazonal aplicado (dias em análise: {len(df_for_analysis)})"
    )

    # -------------------------------------------------
    # 4. Estatísticas básicas
    # -------------------------------------------------
    summary = summarize_daily_variables(df_for_analysis, var_cols)
    st.subheader("Resumo estatístico")
    st.dataframe(summary)

    # -------------------------------------------------
    # 5. Parâmetros dos eventos
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
    # 6. Cálculo dos eventos
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
    # 7. Frequência e severidade
    # -------------------------------------------------
    freq_sev = summarize_event_frequency_severity(df_for_analysis, masks)
    st.subheader("Frequência e severidade dos eventos")
    st.dataframe(freq_sev)

    # -------------------------------------------------
    # 8. Ocorrências por ano (gráfico)
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

    if available_keys:
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
    else:
        st.info("Nenhum evento encontrado para o período/variáveis seleccionados.")

    # -------------------------------------------------
    # 9. Relatório PDF
    # -------------------------------------------------
    st.subheader("Relatório PDF")

    col_meta1, col_meta2 = st.columns(2)
    with col_meta1:
        location_name = st.text_input("Nome da localização", value="Local 1")
        lat = st.number_input("Latitude", value=0.0, format="%.6f")
        lon = st.number_input("Longitude", value=0.0, format="%.6f")

    with col_meta2:
        lang_choice = st.selectbox(
            "Idioma do relatório",
            options=[("pt", "Português"), ("en", "English"), ("es", "Español")],
            index=0,
            format_func=lambda x: x[1],
        )
        lang_code = lang_choice[0]

    if st.button("📄 Gerar relatório em PDF deste ficheiro"):
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
            "lat": float(lat),
            "lon": float(lon),
            "filename": getattr(df, "name", ""),
        }

        pdf_bytes = generate_pdf_report(
            df_for_analysis,
            seasonal_info,
            masks,
            freq_sev,
            params_for_report,
            meta=meta,
            lang=lang_code,
        )

        st.download_button(
            "⬇️ Descarregar relatório PDF",
            data=pdf_bytes,
            file_name="analise_risco_climatico.pdf",
            mime="application/pdf",
        )
