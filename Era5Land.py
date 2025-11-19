from instructions import show_instructions
from daily_generator import build_gee_code_daily
from era5_csv_page import show_era5_csv_page
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

st.title("Gerador de Código")
st.caption("Define uma janela sazonal (pode passar o fim do ano) e obtém o código JS para o GEE.")

page = st.sidebar.radio("Navegação", ["Gerar código GEE", "Análise CSV ERA5", "Instruções"])

# ---------------------------
# Página: Gerar código
# ---------------------------
if page == "Gerar código GEE":
    st.title("Gerador de Código")
    st.caption("Define uma janela sazonal (pode passar o fim do ano) e obtém o código JS para o GEE.")

    col1, col2 = st.columns(2)

    # --- Coluna 1: anos ---
    with col1:
        st.markdown("#### Intervalo de anos (histórico)")
        start_year = st.number_input("Ano inicial", value=1995, step=1)
        end_year   = st.number_input("Ano final", value=2024, step=1)

    # --- Coluna 2: datas da janela sazonal ---
    with col2:
        st.markdown("#### Janela sazonal")
        start_month = st.number_input("Mês inicial", min_value=1, max_value=12, value=9)
        start_day   = st.number_input("Dia inicial", min_value=1, max_value=31, value=5)
        end_month   = st.number_input("Mês final", min_value=1, max_value=12, value=10)
        end_day     = st.number_input("Dia final", min_value=1, max_value=31, value=15)

    st.markdown("""
Serão exportadas, para cada localização, séries **diárias** com:
precipitação, temperaturas mínima/máxima/média, ponto de orvalho,
humidade do solo (camada 1), radiação, evapotranspiração potencial,
vento médio a 10 m e rajada máxima diária.
""")
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
