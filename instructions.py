import streamlit as st


def show_instructions():

    st.title("Instruções – ERA5-Land / ERA5 via Google Earth Engine")

    st.markdown(
        r"""
Esta página explica como funciona a aplicação, como usar o Google Earth Engine (GEE)
e o racional de cada variável incluída. A ideia é poderes revisitar este guia mesmo meses depois
e perceber rapidamente todo o fluxo de trabalho.
"""
    )

    # ---------------------------------------------------------------------
    # 1. COMO FUNCIONA A APP
    # ---------------------------------------------------------------------
    with st.expander("1️⃣ Como funciona a app (janela sazonal, anos, centróides)", expanded=True):

        st.markdown(
            r"""
## 1.1. Janela sazonal

A *janela sazonal* é um **período dentro do ano**, por exemplo:

- 1–31 Janeiro  
- 15 Novembro–15 Fevereiro  
- 5 Setembro–10 Outubro  

Este período é aplicado a **todos os anos do intervalo histórico** que selecionares na app
(por exemplo: 1995–2024).

A app converte mês/dia para **dia do ano** (`doy`) e depois aplica filtros no GEE.

---

## 1.2. Tipos de janela sazonal

### ✔️ Janela dentro do ano  
(ex.: 1 Janeiro → 31 Março, ou 5 Fevereiro → 20 Abril)

Código gerado:
"""
        )

        st.code(
            "var seasonal = base.filter(ee.Filter.dayOfYear(startDoy, endDoy));",
            language="javascript",
        )

        st.markdown(
            r"""
---

### ✔️ Janela que passa o fim do ano  
(ex.: 15 Novembro → 15 Fevereiro)

Código gerado:
"""
        )

        st.code(
            "var part1 = base.filter(ee.Filter.dayOfYear(startDoy, 366));\n"
            "var part2 = base.filter(ee.Filter.dayOfYear(1, endDoy));\n"
            "var seasonal = part1.merge(part2);",
            language="javascript",
        )

        st.markdown(
            r"""
---

## 1.3. Variáveis da app

Ao escolheres a variável (precipitação, temperatura, etc.) a app seleciona internamente:

- banda(s) necessárias  
- conversão (ex.: Kelvin → °C, metros → mm)  
- nome da coluna final  
- gráfico no GEE  

---

## 1.4. Localizações (centróides)

As localizações devem ser introduzidas com o formato:

- Nome, lon, lat (Ex.: Evora, -7.909, 38.571)


Cada linha gera no código GEE:

- `ee.Geometry.Point([lon, lat])`
- uma série temporal (`FeatureCollection`)
- gráfico
- exportação CSV
"""
        )

    # ---------------------------------------------------------------------
    # 2. GEE – PASSO A PASSO
    # ---------------------------------------------------------------------
    with st.expander("2️⃣ Passo-a-passo no Google Earth Engine", expanded=False):

        st.markdown(
            r"""
## 2.1. Abrir o Code Editor do GEE

- Criar conta: https://earthengine.google.com  
- Editor: https://code.earthengine.google.com

---

## 2.2. Fluxo completo

1. Na app Streamlit:
   - Preencher anos, variável, janela sazonal e localizações  
   - Gerar código  
   - Copiar para o GEE  

2. No GEE:
   - `File → New Script`  
   - Colar código  
   - `Run`  

3. No **Console**:
   - aparecem gráficos por localização  

4. No **Tasks**:
   - clicar “Run” para gerar CSV no Drive  

---

## 2.3. Estrutura típica do código gerado

1. Seleção do dataset  
2. Filtro por intervalo de anos  
3. Janela sazonal  
4. Seleção de banda(s)  
5. Loop por localizações  
6. Gráficos  
7. Exportação CSV
"""
        )

    # ---------------------------------------------------------------------
    # 3. VARIÁVEIS DISPONÍVEIS
    # ---------------------------------------------------------------------
    with st.expander("3️⃣ Variáveis disponíveis (ERA5-Land e ERA5)", expanded=False):

        st.markdown(
            r"""
## 3.1. Precipitação

### Precipitação total (mm/h)
- Banda: `total_precipitation`
- Unidade original: metros
- Conversão: ×1000 → mm

### Precipitação horária (mm)
- Banda: `total_precipitation_hourly`
- Conversão: ×1000 → mm

---

## 3.2. Temperaturas

### Temperatura 2 m (°C)
- Banda: `temperature_2m`
- Conversão: K − 273.15 → °C

### Ponto de orvalho 2 m (°C)
- Banda: `dewpoint_temperature_2m`
- Conversão: K − 273.15 → °C

---

## 3.3. Solo

### Humidade do solo (0–7 cm)
- Banda: `volumetric_soil_water_layer_1`
- Unidade: fração (0–1)

---

## 3.4. Radiação

### Radiação solar global horária (W/m²)
- Banda: `surface_solar_radiation_downwards_hourly`
- Conversão: J/m² ÷ 3600 → W/m²

---

## 3.5. Evapotranspiração

### Evapotranspiração potencial horária (mm)
- Banda: `potential_evaporation_hourly`
- Conversão: ×1000 → mm

---

## 3.6. Runoff

### Runoff total horário (mm)
- Banda: `runoff_hourly`
- Conversão: ×1000 → mm

---

## 3.7. Vento a 10 m (ERA5)

Dataset: `ECMWF/ERA5/HOURLY`

Bandas:
- `u_component_of_wind_10m`
- `v_component_of_wind_10m`

Magnitude do vento:  
`V = √(u² + v²)`

Código:
"""
        )

        st.code(
            "var u = ee.Number(v.get('u_component_of_wind_10m'));\n"
            "var w = ee.Number(v.get('v_component_of_wind_10m'));\n"
            "var wind_speed = u.pow(2).add(w.pow(2)).sqrt();",
            language="javascript",
        )

    # ---------------------------------------------------------------------
    # 4. NOTAS TÉCNICAS
    # ---------------------------------------------------------------------
    with st.expander("4️⃣ Notas técnicas e boas práticas", expanded=False):

        st.markdown(
            r"""
### Resolução espacial
ERA5-Land e ERA5: ~0.1° → ~11 km  
Logo usamos:


### Resolução temporal
Ambos são horários.

### Geometria
Usamos pontos:  
`ee.Geometry.Point([lon, lat])`

### Exportações
Cada localização gera 1 CSV independente.

### Unidades
- Temperaturas: Kelvin → °C  
- Precipitação / evaporação / runoff: metros → mm  
- Radiação: J/m² → W/m²  
- Vento: m/s  
"""
        )

    # ---------------------------------------------------------------------
    # 5. RESUMO
    # ---------------------------------------------------------------------
    with st.expander("5️⃣ Resumo rápido (checklist)", expanded=False):

        st.markdown(
            r"""
1. Escolher variáveis  
2. Selecionar janela sazonal  
3. Definir anos  
4. Inserir localizações  
5. Gerar código  
6. Colar no GEE  
7. Exportar CSV  

Pronto!
"""
        )
