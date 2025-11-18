import streamlit as st
import datetime as dt
import re

# ---------------------------
# Helpers
# ---------------------------

def sanitize_name(name: str) -> str:
    """
    Transforma o nome num identificador seguro para usar no JavaScript:
    - substitui espaços e caracteres estranhos por "_"
    """
    safe = re.sub(r"[^0-9a-zA-Z_]+", "_", name.strip())
    if not safe:
        safe = "loc"
    return safe


def build_gee_code(event_label, start_date, end_date, locations_text):
    """
    Gera código JavaScript para o Google Earth Engine com base nas escolhas do utilizador.
    """

    # Mapeamento dos eventos para bandas do ERA5-Land
    event_config = {
        "Precipitação total (mm/h)": {
            "band": "total_precipitation",
            "value_prop": "precip_mm",
            # total_precipitation vem em metros de água -> multiplicar por 1000 para mm
            "value_expr": "ee.Number(v.get('total_precipitation')).multiply(1000)",
            "title_suffix": "Precipitação total (mm/h)"
        },
        "Temperatura 2 m (°C)": {
            "band": "temperature_2m",
            "value_prop": "temp_C",
            # temperature_2m vem em Kelvin -> converter para °C
            "value_expr": "ee.Number(v.get('temperature_2m')).subtract(273.15)",
            "title_suffix": "Temperatura 2 m (°C)"
        },
    }

    if event_label not in event_config:
        return "// ERRO: evento não reconhecido."

    cfg = event_config[event_label]

    # Parse das localizações (uma por linha: Nome, lon, lat)
    locations = []
    for line in locations_text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            continue  # ignora linhas mal formatadas
        name, lon_str, lat_str = parts
        try:
            lon = float(lon_str.replace(",", "."))
            lat = float(lat_str.replace(",", "."))
            locations.append({"name": name, "lon": lon, "lat": lat})
        except ValueError:
            continue

    if not locations:
        return "// ERRO: nenhuma localização válida encontrada. Verifica o formato: Nome, lon, lat"

    # Converter datas para string YYYY-MM-DD
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    lines = []

    # Cabeçalho
    lines.append("// -----------------------------------------------------")
    lines.append("// Código gerado automaticamente pela app Streamlit")
    lines.append("// Objetivo: consultar ERA5-Land (ECMWF/ERA5_LAND/HOURLY)")
    lines.append("// -----------------------------------------------------")
    lines.append("")
    lines.append("// 1) Dataset ERA5-Land (horário)")
    lines.append("var dataset = ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY');")
    lines.append("")
    lines.append("// 2) Janela temporal")
    lines.append(f"var start = '{start_str}';")
    lines.append(f"var end   = '{end_str}';")
    lines.append("var imgs = dataset.filterDate(start, end);")
    lines.append("")
    lines.append(f"// 3) Selecionar banda do evento: {event_label}")
    lines.append(f"var band = '{cfg['band']}';")
    lines.append("imgs = imgs.select(band);")
    lines.append("")

    # Para cada localização geramos:
    # - geometria
    # - série temporal (FeatureCollection)
    # - gráfico
    # - exportação para CSV
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
        lines.append(f"  var v = img.reduceRegion({{")
        lines.append(f"    reducer: ee.Reducer.mean(),")
        lines.append(f"    geometry: point_{safe},")
        lines.append(f"    scale: 11100,  // ~11 km (resolução ERA5-Land)")
        lines.append(f"    bestEffort: true")
        lines.append(f"  }});")
        lines.append("")
        lines.append(f"  return ee.Feature(null, {{")
        lines.append(f"    'time': img.date().format(),")
        lines.append(f"    '{cfg['value_prop']}': {cfg['value_expr']}")
        lines.append(f"  }});")
        lines.append(f"}}));")
        lines.append("")
        lines.append("// Gráfico rápido no Code Editor")
        lines.append(f"print(ui.Chart.feature.byFeature(ts_{safe}, 'time', '{cfg['value_prop']}')",
                     )
        lines[-1] += f"\n  .setOptions({{title: '{cfg['title_suffix']} - {loc['name']}'}}));"
        lines.append("")
        lines.append("// Exportar para CSV no Google Drive")
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
    page_title="Gerador de Código GEE – ERA5-Land",
    layout="wide",
)

st.title("Gerador de Código para Google Earth Engine (ERA5-Land)")
st.caption("App simples para construir o código JavaScript a colar no https://code.earthengine.google.com/")

# Navegação
page = st.sidebar.radio(
    "Navegação",
    ["Gerar código GEE", "Instruções"],
)

# ---------------------------
# Página: Gerar código
# ---------------------------
if page == "Gerar código GEE":
    st.header("Configuração da consulta")

    col1, col2 = st.columns(2)

    with col1:
        event_label = st.selectbox(
            "Tipo de evento / variável",
            [
                "Precipitação total (mm/h)",
                "Temperatura 2 m (°C)",
            ],
            help=(
                "Lista simplificada. Podes depois ajustar a banda no código "
                "(ex.: dewpoint_temperature_2m, runoff, etc.)."
            ),
        )

        start_date = st.date_input(
            "Data de início",
            value=dt.date(2025, 1, 1),
            help="Formato: AAAA-MM-DD",
        )
        end_date = st.date_input(
            "Data de fim",
            value=dt.date(2025, 1, 15),
            help="Formato: AAAA-MM-DD (exclusivo no GEE, mas convém manter assim por consistência).",
        )

    with col2:
        st.markdown("#### Localizações (centróides)")
        st.write(
            "Introduz uma localização por linha no formato:\n\n"
            "`Nome, lon, lat`\n\n"
            "Exemplos:\n"
            "`Evora, -7.909, 38.571`\n"
            "`Santarem, -8.683, 39.236`"
        )

        default_locs = "Evora, -7.909, 38.571\nSantarem, -8.683, 39.236"
        locations_text = st.text_area(
            "Lista de localizações",
            value=default_locs,
            height=150,
        )

    st.markdown("---")

    if st.button("Gerar código JavaScript para o GEE"):
        if start_date >= end_date:
            st.error("A data de início deve ser anterior à data de fim.")
        else:
            gee_code = build_gee_code(
                event_label=event_label,
                start_date=start_date,
                end_date=end_date,
                locations_text=locations_text,
            )

            st.subheader("Código JavaScript para o Code Editor do Google Earth Engine")
            st.code(gee_code, language="javascript")

            st.download_button(
                "📥 Descarregar código como ficheiro .js",
                gee_code,
                file_name="era5land_query.js",
                mime="text/javascript",
            )

# ---------------------------
# Página: Instruções
# ---------------------------
elif page == "Instruções":
    st.header("Instruções para recolha de dados ERA5-Land via Google Earth Engine")

    st.markdown(
        """
### 1. Criar conta e aceder ao Google Earth Engine

1. Acede a [https://earthengine.google.com/](https://earthengine.google.com/) e pede acesso (se ainda não tiveres).
2. Depois de aprovado, entra em [https://code.earthengine.google.com/](https://code.earthengine.google.com/).

---

### 2. Usar esta app Streamlit

1. Na página **Gerar código GEE**:
   - Escolhe o **tipo de evento** (precipitação total ou temperatura a 2 m).
   - Define a **janela temporal** (data de início e data de fim).
   - Introduz as **localizações** (centróides) uma por linha, no formato  
     `Nome, lon, lat`  
     Ex.:  
     `Evora, -7.909, 38.571`  
     `Santarem, -8.683, 39.236`
2. Clica em **“Gerar código JavaScript para o GEE”**.
3. Copia o código gerado ou descarrega o ficheiro `.js`.

---

### 3. Colar o código no Code Editor do GEE

1. No [Code Editor](https://code.earthengine.google.com/), cria um **New Script**.
2. Apaga o conteúdo existente e cola o código gerado pela app.
3. Carrega em **Run** (botão ▶️).

O código vai:

- Definir o dataset ERA5-Land: `ECMWF/ERA5_LAND/HOURLY`
- Filtrar pela janela temporal (start, end).
- Criar um ponto por localização (`ee.Geometry.Point`).
- Construir uma série temporal com:
  - `time` – data/hora
  - `precip_mm` ou `temp_C`, consoante o evento
- Criar **gráficos** (`ui.Chart.feature.byFeature(...)`).
- Gerar **Export.table.toDrive(...)** para cada localização.

---

### 4. Obter os ficheiros CSV

1. Depois de carregares em **Run**, abre a aba **Tasks** (canto superior direito).
2. Para cada exportação (por localização), clica em **Run**.
3. Confirma as opções (pasta do Google Drive, nome do ficheiro, formato CSV).
4. Quando terminar, os ficheiros ficam disponíveis no teu **Google Drive**.

---

### 5. Notas e truques rápidos

- O ERA5-Land tem resolução aproximada de **0.1º (~11 km)**; por isso o `scale` foi definido como `11100`.
- As unidades:
  - `total_precipitation` → metros de água → é convertido para **mm** multiplicando por 1000.
  - `temperature_2m` → Kelvin → é convertido para **°C** subtraindo 273.15.
- Se quiseres outras variáveis (ex.: `dewpoint_temperature_2m`, `surface_runoff`), basta:
  1. Trocar o nome da banda em `band = '...'`.
  2. Ajustar a expressão de conversão (`value_expr`) e o label (`value_prop`) na app (ou diretamente no código).

---

### 6. Próximos passos (ideias para evoluir)

- Adicionar opção de **agregação diária** (mínimo, máximo, média).
- Permitir escolher entre **ERA5-Land** e **ERA5** (para rajadas de vento, por exemplo).
- Gerar código para séries **espaciais** (médias numa área em vez de pontuais em centróides).

Se quiseres, no passo seguinte posso:
- acrescentar já a opção de **temperatura mínima diária**; ou  
- adaptar o gerador para criar também código para **ERA5 (não-Land)** com `10m_wind_gust`.
"""
    )
