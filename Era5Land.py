from zoneinfo import available_timezones

import streamlit as st

from instructions import show_instructions
from daily_generator import build_gee_code_daily
from era5_csv_page import show_era5_csv_page


# ---------------------------
# Layout principal da app
# ---------------------------

st.set_page_config(
    page_title="Gerador de Código GEE – ERA5-Land",
    layout="wide",
)

page = st.sidebar.radio(
    "Navegação",
    ["Gerar código GEE", "Análise CSV ERA5", "Instruções"]
)


# ---------------------------
# Página: Gerar código
# ---------------------------
if page == "Gerar código GEE":
    st.title("Gerador de Código")
    st.caption(
        "Define a janela sazonal, o intervalo de anos, o modo de exportação "
        "e obtém o código JavaScript para o Google Earth Engine."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Intervalo de anos (histórico)")
        start_year = st.number_input("Ano inicial", value=1995, step=1)
        end_year = st.number_input("Ano final", value=2024, step=1)

    with col2:
        st.markdown("#### Janela sazonal")
        start_month = st.number_input("Mês inicial", min_value=1, max_value=12, value=1)
        start_day = st.number_input("Dia inicial", min_value=1, max_value=31, value=1)
        end_month = st.number_input("Mês final", min_value=1, max_value=12, value=12)
        end_day = st.number_input("Dia final", min_value=1, max_value=31, value=31)

    st.markdown("#### Configuração de exportação")

    export_mode = st.radio(
        "Modo de exportação",
        ["daily", "hourly", "both"],
        horizontal=True,
        help=(
            "daily = exporta série diária; "
            "hourly = exporta série horária; "
            "both = exporta ambas."
        ),
    )

    timezone_options = ["UTC"] + sorted(tz for tz in available_timezones() if tz != "UTC")
    default_tz = "America/Santiago" if "America/Santiago" in timezone_options else "UTC"

    timezone_str = st.selectbox(
        "Timezone local a aplicar a todas as localizações deste pedido",
        options=timezone_options,
        index=timezone_options.index(default_tz),
        help=(
            "Usa formato IANA. Podes pesquisar na lista. "
            "A timezone escolhida será aplicada a todas as localizações deste pedido."
        ),
    )

    st.markdown(
        """
O gerador pode exportar:

- **daily**: série diária com precipitação diária, temperatura mínima/máxima/média,
  ponto de orvalho médio, humidade do solo, radiação, evapotranspiração,
  vento médio e rajada máxima.
- **hourly**: série horária de precipitação com data/hora UTC e local.
- **both**: gera os dois ficheiros.
"""
    )

    locations_text = st.text_area(
        "Localizações (uma por linha, formato: nome,lon,lat)",
        value="Futrono,-72.4,-40.15",
        height=150,
        help="Exemplo: Dagoberto,-71.42160751,-35.71990245",
    )

    if st.button("Gerar código para o GEE"):
        if start_year > end_year:
            st.error("O ano inicial deve ser menor ou igual ao ano final.")
        else:
            gee_code = build_gee_code_daily(
                start_year=int(start_year),
                end_year=int(end_year),
                start_month=int(start_month),
                start_day=int(start_day),
                end_month=int(end_month),
                end_day=int(end_day),
                locations_text=locations_text,
                export_mode=export_mode,
                timezone_str=timezone_str,
            )

            st.subheader("Código JavaScript para colar no GEE")
            st.code(gee_code, language="javascript")

            st.download_button(
                "📥 Descarregar código como ficheiro .js",
                gee_code,
                file_name=f"era5_{export_mode}.js",
                mime="text/javascript",
            )


# ---------------------------
# Página: Análise CSV ERA5
# ---------------------------
elif page == "Análise CSV ERA5":
    show_era5_csv_page()


# ---------------------------
# Página: Instruções
# ---------------------------
elif page == "Instruções":
    show_instructions()
