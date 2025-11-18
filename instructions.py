import streamlit as st


def show_instructions():
    st.title("Instruções – ERA5-Land / ERA5 via Google Earth Engine")

    st.markdown(
        r"""
Esta página resume **como funciona a app**, **como usar o Google Earth Engine (GEE)**  
e o **racional de cada variável** que a app suporta.

A ideia é que consigas, no futuro, perceber rapidamente:

- o que faz cada campo da app,
- como é construída a janela sazonal,
- que bandas são usadas em cada variável,
- e como levar tudo até ao Google Earth Engine e ao CSV final.
"""
    )

    # ---------------------------------------------------------------------
    # 1. Como funciona a app
    # ---------------------------------------------------------------------
    with st.expander("1️⃣ Como funciona a app (janela sazonal, anos, centróides)", expanded=True):
        st.markdown(
            r"""
### 1.1. Conceito de *janela sazonal*

- A **janela sazonal** é um período fixo dentro do ano, por exemplo:
  - 1–31 Janeiro  
  - 15 Novembro–15 Fevereiro  
  - 5 Setembro–10 Outubro  

- Essa janela é aplicada **a todos os anos históricos** do intervalo selecionado (por exemplo, 1995–2024).

Ou seja:
- Se escolheres **1995–2024** e **15 Novembro–15 Fevereiro**, a app gera código para ir buscar **todos os registos horários nesse período de dias**, para **cada um desses anos**.

---

### 1.2. Intervalo de anos

Na app escolhes:

- **Ano inicial** (ex.: 1995)
- **Ano final**   (ex.: 2024)

Esse intervalo é aplicado com:

- `calendarRange(startYear, endYear, 'year')` no GEE

Isto garante que só entram imagens entre esses anos.

---

### 1.3. Janela sazonal – lógica interna

A app transforma “mês/dia” em **day of year** (`doy`), ou seja:

- 1 Janeiro → 1  
- 31 Janeiro → 31  
- 15 Novembro → 319 (num ano tipo 2001)  
- 15 Fevereiro → 46  

Depois existem dois casos:

1. **Janela totalmente dentro do ano**  
   (ex.: 1 Janeiro–31 Março) → `startDoy < endDoy`  

2. **Janela que passa o fim do ano**  
   (ex.: 15 Novembro–15 Fevereiro) → `startDoy > endDoy`

No código GEE isto aparece como:

- Caso 1 (janela simples dentro do ano): filtra de `startDoy` a `endDoy`
- Caso 2 (passa o fim do ano): faz a união de dois intervalos:
  - de `startDoy` a 366  
  - de 1 a `endDoy`
"""
        )

        st.markdown("**Exemplo de janela sazonal simples (não passa o fim do ano):**")
        st.code(
            "var seasonal = base.filter(ee.Filter.dayOfYear(startDoy, endDoy));",
            language="javascript",
        )

        st.markdown("**Exemplo de janela que passa o fim do ano (15 Nov–15 Fev):**")
        st.code(
            "var part1 = base.filter(ee.Filter.dayOfYear(startDoy, 366));\n"
            "var part2 = base.filter(ee.Filter.dayOfYear(1, endDoy));\n"
            "var seasonal = part1.merge(part2);",
            language="javascript",
        )

        st.markdown(
            r"""
---

### 1.4. Variável escolhida na app

Na app escolhes uma variável (“Tipo de evento / variável”), por exemplo:

- Precipitação total horária (mm)  
- Temperatura 2 m (°C)  
- Humidade do solo camada 1 (0–7 cm)  
- Etc.

Cada variável tem, no código:

- **nome da banda** (`band` ou lista de bandas)
- **regra de conversão de unidades** (ex.: Kelvin → °C, metros → mm)
- **label** (nome da coluna no CSV: `precip_mm`, `temp_C`, etc.)
- eventualmente um **tratamento especial** (como o vento a 10 m, que usa duas componentes).

---

### 1.5. Localizações (centróides)

Na caixa de texto:

```text
Evora, -7.909, 38.571
Santarem, -8.683, 39.236
