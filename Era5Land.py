from instructions import show_instructions
from daily_generator import build_gee_code_daily
import streamlit as st
import datetime as dt
import re

# ---------------------------
# Helpers
# ---------------------------

def sanitize_name(name: str) -> str:
    """Transforma o nome num identificador seguro para usar no JavaScript."""
    safe = re.sub(r"[^0-9a-zA-Z_]+", "_", name.strip())
    if not safe:
        safe = "loc"
    return safe


def compute_doy(month: int, day: int) -> int | None:
    """Devolve o dia do ano (1–366) para um mês/dia numa year fictício (2001)."""
    try:
        d = dt.date(2001, month, day)
        return d.timetuple().tm_yday
    except ValueError:
        return None


def build_gee_code(
    event_label: str,
    start_year: int,
    end_year: int,
    start_month: int,
    start_day: int,
    end_month: int,
    end_day: int,
    locations_text: str,
):
    """
    Gera código JavaScript para o Google Earth Engine com:
    - janela sazonal (pode passar o fim do ano)
    - intervalo de anos
    - várias localizações (centróides)
    """

    # Configuração das variáveis/“eventos”
    event_config = {
        # --- Precipitação ---
        "Precipitação total (mm/h)": {
            # acumulada desde 00h; continua a usar total_precipitation e converte para mm
            "band": "total_precipitation",
            "value_prop": "precip_mm",
            "value_expr": "ee.Number(v.get('total_precipitation')).multiply(1000)",
            "title_suffix": "Precipitação total (mm/h)",
        },
        "Precipitação total horária (mm)": {
            # já vem desagregada hora a hora em m → converter para mm
            "band": "total_precipitation_hourly",
            "value_prop": "precip_h_mm",
            "value_expr": "ee.Number(v.get('total_precipitation_hourly')).multiply(1000)",
            "title_suffix": "Precipitação total horária (mm)",
        },

        # --- Temperaturas ---
        "Temperatura 2 m (°C)": {
            "band": "temperature_2m",
            "value_prop": "temp_C",
            "value_expr": "ee.Number(v.get('temperature_2m')).subtract(273.15)",
            "title_suffix": "Temperatura 2 m (°C)",
        },
        "Ponto de orvalho 2 m (°C)": {
            "band": "dewpoint_temperature_2m",
            "value_prop": "dewpoint_C",
            "value_expr": "ee.Number(v.get('dewpoint_temperature_2m')).subtract(273.15)",
            "title_suffix": "Ponto de orvalho 2 m (°C)",
        },

        # --- Solo ---
        "Humidade do solo camada 1 (0–7 cm)": {
            "band": "volumetric_soil_water_layer_1",
            "value_prop": "soilw1",
            # já vem como fração volumétrica (0–1)
            "value_expr": "ee.Number(v.get('volumetric_soil_water_layer_1'))",
            "title_suffix": "Humidade do solo camada 1",
        },

        # --- Radiação ---
        "Radiação solar global horária (W/m²)": {
            # J/m2 acumulados na hora → dividir por 3600 para W/m2 médios
            "band": "surface_solar_radiation_downwards_hourly",
            "value_prop": "swdown_Wm2",
            "value_expr": "ee.Number(v.get('surface_solar_radiation_downwards_hourly')).divide(3600)",
            "title_suffix": "Radiação solar global horária (W/m²)",
        },

        # --- Runoff / escoamento ---
        "Runoff total horário (mm)": {
            "band": "runoff_hourly",
            "value_prop": "runoff_mm",
            "value_expr": "ee.Number(v.get('runoff_hourly')).multiply(1000)",
            "title_suffix": "Runoff total horário (mm)",
        },

        # --- Evapotranspiração ---
        "Evapotranspiração potencial horária (mm)": {
            "band": "potential_evaporation_hourly",
            "value_prop": "pev_mm",
            "value_expr": "ee.Number(v.get('potential_evaporation_hourly')).multiply(1000)",
            "title_suffix": "Evapotranspiração potencial horária (mm)",
        },
        # --- Velocidade do Vento a 10m ---
        "Velocidade do vento 10 m (m/s)": {
            "bands": ["u_component_of_wind_10m", "v_component_of_wind_10m"],
            "value_prop": "wind10m_ms",
            "special": "wind10m",
            "title_suffix": "Velocidade do vento a 10 m (m/s)"
        },
    }

    if event_label not in event_config:
        return "// ERRO: evento não reconhecido."

    cfg = event_config[event_label]

    # Parse das localizações: Nome, lon, lat
    locations = []
    for line in locations_text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            continue
        name, lon_str, lat_str = parts
        try:
            lon = float(lon_str.replace(",", "."))
            lat = float(lat_str.replace(",", "."))
            locations.append({"name": name, "lon": lon, "lat": lat})
        except ValueError:
            continue

    if not locations:
        return "// ERRO: nenhuma localização válida encontrada. Formato esperado: Nome, lon, lat"

    # Dia do ano para início/fim (janela sazonal)
    start_doy = compute_doy(start_month, start_day)
    end_doy = compute_doy(end_month, end_day)

    if start_doy is None or end_doy is None:
        return "// ERRO: combinação inválida de mês/dia na janela sazonal."

    wraps_year = start_doy > end_doy  # se verdadeiro, janela passa pelo fim do ano

    # Construção do código JS
    lines = []

    # Cabeçalho
    lines.append("// -----------------------------------------------------")
    lines.append("// Código gerado automaticamente (ERA5-Land – janela sazonal)")
    lines.append("// -----------------------------------------------------")
    lines.append("")
    lines.append("// 1) Dataset ERA5-Land (horário)")
    lines.append("var dataset = ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY');")
    lines.append("")
    lines.append("// 2) Intervalo de anos a considerar")
    lines.append(f"var startYear = {start_year};")
    lines.append(f"var endYear   = {end_year};")
    lines.append("var base = dataset.filter(ee.Filter.calendarRange(startYear, endYear, 'year'));")
    lines.append("")
    lines.append("// 3) Janela sazonal (aplicada a todos os anos)")
    lines.append(f"//    Início: {start_day:02d}-{start_month:02d}  |  Fim: {end_day:02d}-{end_month:02d}")
    lines.append(f"var startDoy = {start_doy};")
    lines.append(f"var endDoy   = {end_doy};")
    lines.append("")

    if not wraps_year:
        # Janela está toda dentro do mesmo ano (ex.: 01-01 a 31-01 ou 15-01 a 12-03)
        lines.append("// Janela contínua dentro do ano (não passa pelo fim do ano)")
        lines.append("var seasonal = base.filter(ee.Filter.dayOfYear(startDoy, endDoy));")
    else:
        # Janela passa pelo fim do ano (ex.: 15-11 a 15-02)
        lines.append("// Janela passa pelo fim do ano: união de [startDoy, 366] U [1, endDoy]")
        lines.append("var part1 = base.filter(ee.Filter.dayOfYear(startDoy, 366));")
        lines.append("var part2 = base.filter(ee.Filter.dayOfYear(1, endDoy));")
        lines.append("var seasonal = part1.merge(part2);")

    lines.append("")
    lines.append(f"// 4) Selecionar banda do evento: {event_label}")
    lines.append(f"var band = '{cfg['band']}';")
    lines.append("var imgs = seasonal.select(band);")
    lines.append("")

    # Para cada localização, criamos geometria, série temporal, gráfico e export CSV
    for loc in locations:
        safe = sanitize_name(loc["name"])
        lon = loc["lon"]
        lat = loc["lat"]

        lines.append("// -----------------------------------------------------")
        lines.append(f"// Local: {loc['name']}  (lon={lon}, lat={lat})")
        lines.append("// -----------------------------------------------------")
        lines.append(f"var point_{safe} = ee.Geometry.Point([{lon}, {lat}]);")
        lines.append("")
        lines.append(f"var ts_{safe} = ee.FeatureCollection(imgs.map(function(img) {{")
        lines.append("  var v = img.reduceRegion({")
        lines.append("    reducer: ee.Reducer.mean(),")
        lines.append(f"    geometry: point_{safe},")
        lines.append("    scale: 11100,  // ~11 km (resolução ERA5-Land)")
        lines.append("    bestEffort: true")
        lines.append("  });")
        lines.append("")
        lines.append("  return ee.Feature(null, {")
        lines.append("    'time': img.date().format(),")
        lines.append(f"    '{cfg['value_prop']}': {cfg['value_expr']}")
        lines.append("  });")
        lines.append("}));")
        lines.append("")
        lines.append("// Gráfico rápido no Code Editor")
        lines.append(
            f"print(ui.Chart.feature.byFeature(ts_{safe}, 'time', '{cfg['value_prop']}')"
        )
        lines.append(
            f"  .setOptions({{title: '{cfg['title_suffix']} – {loc['name']}'}}));"
        )
        lines.append("")
        lines.append("// Exportar tabela para CSV no Google Drive")
        lines.append("Export.table.toDrive({")
        lines.append(f"  collection: ts_{safe},")
        lines.append(f"  description: 'ERA5Land_{safe}_{cfg['value_prop']}',")
        lines.append("  fileFormat: 'CSV'")
        lines.append("});")
        lines.append("")

    return "\n".join(lines)


# ---------------------------
# Layout principal da app
# ---------------------------

st.set_page_config(
    page_title="Gerador de Código GEE – ERA5-Land (janela sazonal)",
    layout="wide",
)

st.title("Gerador de Código para Google Earth Engine (ERA5-Land)")
st.caption("Define uma janela sazonal (pode passar o fim do ano) e obtém o código JS para o GEE.")

page = st.sidebar.radio("Navegação", ["Gerar código GEE", "Instruções"])

# ---------------------------
# Página: Gerar código
# ---------------------------
if page == "Gerar código GEE":
    st.header("Configuração da análise sazonal")

    col1, col2 = st.columns(2)

    # ---- Coluna 1: variável e anos ----
    with col1:
        event_label = st.selectbox(
            "Tipo de evento / variável",
            [
                "Precipitação total (mm/h)",
        "Precipitação total horária (mm)",
        "Temperatura 2 m (°C)",
        "Ponto de orvalho 2 m (°C)",
        "Humidade do solo camada 1 (0–7 cm)",
        "Radiação solar global horária (W/m²)",
        "Runoff total horário (mm)",
        "Evapotranspiração potencial horária (mm)",
            ],
        )

        st.markdown("#### Intervalo de anos (histórico)")
        start_year = st.number_input("Ano inicial", value=1995, step=1)
        end_year = st.number_input("Ano final", value=2024, step=1)

    # ---- Coluna 2: janela sazonal e localizações ----
    with col2:
        st.markdown("#### Janela sazonal (aplicada a todos os anos)")

        months = {
            1: "Jan",
            2: "Fev",
            3: "Mar",
            4: "Abr",
            5: "Mai",
            6: "Jun",
            7: "Jul",
            8: "Ago",
            9: "Set",
            10: "Out",
            11: "Nov",
            12: "Dez",
        }

        c1, c2 = st.columns(2)
        with c1:
            start_month = st.selectbox(
                "Mês início", list(months.keys()), format_func=lambda m: months[m], index=0
            )
            start_day = st.number_input("Dia início", min_value=1, max_value=31, value=1)
        with c2:
            end_month = st.selectbox(
                "Mês fim", list(months.keys()), format_func=lambda m: months[m], index=0
            )
            end_day = st.number_input("Dia fim", min_value=1, max_value=31, value=31)

    st.markdown("#### Localizações (centróides)")
    st.write(
        "Introduz uma localização por linha no formato:\n\n"
        "`Nome, lon, lat`\n\n"
        "Exemplos:\n"
        "`Evora, -7.909, 38.571`\n"
        "`Santarem, -8.683, 39.236`"
    )

    default_locs = "Evora, -7.909, 38.571\nSantarem, -8.683, 39.236"
    locations_text = st.text_area("Lista de localizações", value=default_locs, height=150)

    st.markdown("---")

    if st.button("Gerar código JavaScript para o GEE"):
        gee_code = build_gee_code_daily(
            start_year=int(start_year),
            end_year=int(end_year),
            start_month=int(start_month),
            start_day=int(start_day),
            end_month=int(end_month),
            end_day=int(end_day),
            locations_text=locations_text,
    )

        st.code(gee_code, language="javascript")

            st.download_button(
                "📥 Descarregar código como ficheiro .js",
                gee_code,
                file_name="era5land_sazonal.js",
                mime="text/javascript",
            )

# ---------------------------
# Página: Instruções
# ---------------------------
elif page == "Instruções":
    show_instructions()
