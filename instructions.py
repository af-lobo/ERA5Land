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

- banda(s) necessárias,
- função de conversão (p.ex. Kelvin → °C),
- nome da coluna final para o CSV,
- gráfico a apresentar no GEE.

---

## 1.4. Localizações (centróides)

As localizações devem ser introduzidas com o formato:

Nome, lon, lat
Exemplo:
Evora, -7.909, 38.571
Santarem, -8.683, 39.236

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
   - Preencher anos, janela sazonal, variável e localizações.
   - Carregar em **Gerar código**.
   - Copiar o código gerado.

2. No GEE:
   - `File → New Script`
   - Colar o código
   - Clicar **Run**

3. Na aba **Console** aparecem:
   - gráficos por localização

4. Na aba **Tasks**:
   - “Run” em cada tarefa → gera CSV no Google Drive

---

## 2.3. Estrutura típica do código gerado

1. Seleção do dataset (ERA5-Land ou ERA5)
2. Filtro por intervalo de anos
3. Cálculo da janela sazonal
4. Seleção de banda(s)
5. Loop por localizações
6. Gráficos + exportações CSV
"""
        )

    # ---------------------------------------------------------------------
    # 3. VARIÁVEIS DISPONÍVEIS
    # ---------------------------------------------------------------------
    with st.expander("3️⃣ Variáveis disponíveis (ERA5-Land e ERA5)", expanded=False):

        st.markdown(r"""
## 3.1. Precipitação

### Precipitação total (mm/h)
- Banda: `total_precipitation`
- Unidade original: metros
- Conversão: ×1000 → mm
- Uso: precipitação acumulada por hora

### Precipitação horária (mm)
- Banda: `total_precipitation_hourly`
- Unidade: metros
- Conversão: ×1000 → mm

---

## 3.2. Temperaturas

### Temperatura 2 m (°C)
- Banda: `temperature_2m`
- Unidade original: Kelvin
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
- Unidade original: J/m²
- Conversão para média horária: ÷3600 → W/m²

---

## 3.5. Evapotranspiração

### Evapotranspiração potencial horária (mm)
- Banda: `potential_evaporation_hourly`
- Unidade original: metros
- Conversão: ×1000 → mm

---

## 3.6. Runoff

### Runoff total horário (mm)
- Banda: `runoff_hourly`
- Unidade original: metros
- Conversão: ×1000 → mm

---

## 3.7. Vento a 10 m (ERA5)

Dataset: `ECMWF/ERA5/HOURLY`

Bandas:
- `u_component_of_wind_10m`
- `v_component_of_wind_10m`

Magnitude do vento:

    V = √(u² + v²)

Código correspondente:
""")

        st.code(
            "var u = ee.Number(v.get('u_component_of_wind_10m'));\n"
            "var w = ee.Number(v.get('v_component_of_wind_10m'));\n"
            "var wind_speed = u.pow(2).add(w.pow(2)).sqrt();",
            language="javascript",
        )

        st.markdown(
            r"""
Uso:
- episódios de vento forte,
- danos estruturais,
- análise de risco em estufas,
- interação com geada.

"""
        )

    # ---------------------------------------------------------------------
    # 4. NOTAS TÉCNICAS
    # ---------------------------------------------------------------------
    with st.expander("4️⃣ Notas técnicas e boas práticas", expanded=False):

        st.markdown(
            r"""
### Resolução
ERA5-Land e ERA5 têm resolução horizontal ~0.1° (~11 km), por isso usamos:


