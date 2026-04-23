from zoneinfo import available_timezones

import streamlit as st

from instructions import show_instructions
from daily_generator import build_gee_code_daily
from era5_csv_page import show_era5_csv_page


VARIABLES_META = {
    "total_precipitation_hourly": {
        "label": "Precipitação horária",
        "help": "Precipitação total horária. Exportada em mm."
    },
    "temperature_2m": {
        "label": "Temperatura a 2 m",
        "help": "Temperatura do ar a 2 metros acima da superfície. No modo diário gera Tmin, Tmax e Tmean."
    },
    "dewpoint_temperature_2m": {
        "label": "Ponto de orvalho a 2 m",
        "help": "Temperatura à qual o ar atinge saturação, a 2 metros."
    },
    "volumetric_soil_water_layer_1": {
        "label": "Humidade do solo camada 1",
        "help": "Conteúdo volumétrico de água na camada superficial do solo (0–7 cm)."
    },
    "surface_solar_radiation_downwards_hourly": {
        "label": "Radiação solar horária",
        "help": "Radiação solar descendente à superfície no intervalo horário. No modo diário gera soma diária e média em W/m²."
    },
    "potential_evaporation_hourly": {
        "label": "Evapotranspiração potencial horária",
        "help": "Evapotranspiração potencial no intervalo horário. No modo diário gera total diário."
    },
    "runoff_hourly": {
        "label": "Runoff horário",
        "help": "Escoamento no intervalo horário. No modo diário gera total diário."
    },
    "u_component_of_wind_10m": {
        "label": "Vento 10 m - componente U",
        "help": "Componente zonal do vento a 10 metros."
    },
    "v_component_of_wind_10m": {
        "label": "Vento 10 m - componente V",
        "help": "Componente meridional do vento a 10 metros."
    },
    "instantaneous_10m_wind_gust": {
        "label": "Rajada máxima a 10 m",
        "help": "Rajada instantânea máxima do vento a 10 metros. No modo diário gera a rajada máxima do dia."
    },
}


st.set_page_config(
    page_title="Gerador de Código GEE – ERA5-Land",
    layout="wide",
)

page = st.sidebar.radio(
    "Navegação",
    ["Gerar código GEE", "Análise CSV ERA5", "Instruções"]
)


if page == "Gerar código GEE":
    st.title("Gerador de Código")
    st.caption(
        "Define a janela sazonal, o intervalo de anos, a timezone, as variáveis "
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
        help="daily = série diária; hourly = série horária; both = ambas."
    )

    timezone_options = ["UTC"] + sorted(tz for tz in available_timezones() if tz != "UTC")
    default_tz = "America/Santiago" if "America/Santiago" in timezone_options else "UTC"

    timezone_str = st.selectbox(
        "Timezone local a aplicar a todas as localizações deste pedido",
        options=timezone_options,
        index=timezone_options.index(default_tz),
        help=(
            "Podes pesquisar na lista. Esta timezone será aplicada a todas as "
            "localizações inseridas neste pedido."
        ),
    )

    st.markdown("#### Variáveis a exportar")

    select_all_variables = st.checkbox(
        "Selecionar todas as variáveis",
        value=True,
        help="Se ativa, todas as variáveis ficam selecionadas por defeito."
    )

    selected_variables = []
    cols = st.columns(2)
    items = list(VARIABLES_META.items())

    for i, (var_name, meta) in enumerate(items):
        with cols[i % 2]:
            checked = st.checkbox(
                meta["label"],
                value=select_all_variables,
                help=meta["help"],
                key=f"var_{var_name}"
            )
            if checked:
                selected_variables.append(var_name)

    if not selected_variables:
        st.warning("Seleciona pelo menos uma variável.")

    st.markdown(
        """
No formato das localizações, usa uma linha por centróide:

`Nome,lon,lat`

Exemplo:

`Dagoberto,-71.42160751,-35.71990245`
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
        elif not selected_variables:
            st.error("Seleciona pelo menos uma variável.")
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
                selected_variables=selected_variables,
            )

            st.subheader("Código JavaScript para colar no GEE")
            st.code(gee_code, language="javascript")

            st.download_button(
                "📥 Descarregar código como ficheiro .js",
                gee_code,
                file_name=f"era5_{export_mode}.js",
                mime="text/javascript",
            )

elif page == "Análise CSV ERA5":
    show_era5_csv_page()

elif page == "Instruções":
    show_instructions()
