"""
ERA5 Daily Analysis Utilities
=============================

Funções de apoio para:
- carregar CSVs diários ERA5 (GEE)
- detectar colunas de variáveis
- calcular estatísticas descritivas
- construir máscaras de eventos climáticos (geada, chuva, calor, vento)
- contar ocorrências por ano
- integração com Streamlit (upload + load)
"""

import pandas as pd
from datetime import datetime


# -------------------------------------------------------------------------
# 1. CARREGAMENTO & UTILITÁRIOS BÁSICOS
# -------------------------------------------------------------------------

def load_era5_csv(path_or_buffer) -> pd.DataFrame:
    """
    Carrega um CSV ERA5 (ficheiro ou buffer) e força tipos adequados.
    Assume:
      - coluna 'date' em formato YYYY-MM-DD
      - restantes variáveis numéricas nas colunas standard
    """
    df = pd.read_csv(path_or_buffer)

    # Converter data
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Converter colunas numéricas
    numeric_cols = [
        "precip_mm",
        "tmin_C",
        "tmax_C",
        "tmean_C",
        "dew2m_mean_C",
        "soilw1_mean",
        "rad_Jm2_day",
        "rad_Wm2_mean",
        "pev_mm_day",
        "wind_mean_ms",
        "gust_max_ms",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def streamlit_upload_and_load(st, label: str):
    """
    Pequeno helper para Streamlit:
    - mostra um file_uploader
    - quando o utilizador faz upload, lê o CSV com load_era5_csv
    """
    uploaded = st.file_uploader(label, type=["csv"])
    if uploaded is None:
        return None

    try:
        df = load_era5_csv(uploaded)
        return df
    except Exception as e:
        st.error(f"Erro ao ler CSV: {e}")
        return None


# -------------------------------------------------------------------------
# 2. DETECÇÃO DE VARIÁVEIS & ESTATÍSTICAS
# -------------------------------------------------------------------------

def detect_variable_columns(df: pd.DataFrame):
    """
    Devolve a lista de colunas 'relevantes' (numéricas) para análise.
    Exclui colunas óbvias de índice/geo.
    """
    exclude = {"date", "system:index", ".geo"}
    numeric_cols = []

    for col in df.columns:
        if col in exclude:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            numeric_cols.append(col)

    return numeric_cols


def summarize_daily_variables(df: pd.DataFrame, var_cols):
    """
    Faz um resumo estatístico tipo describe() para as variáveis diárias.
    """
    if not var_cols:
        return pd.DataFrame()

    summary = df[var_cols].describe().T
    summary = summary.rename(
        columns={
            "count": "n",
            "mean": "média",
            "std": "desvio_padrao",
            "min": "mín",
            "25%": "p25",
            "50%": "p50",
            "75%": "p75",
            "max": "máx",
        }
    )
    return summary.reset_index().rename(columns={"index": "variável"})


# -------------------------------------------------------------------------
# 3. EVENTOS CLIMÁTICOS – MÁSCARAS
# -------------------------------------------------------------------------

def compute_event_masks(
    df: pd.DataFrame,
    frost_temp_C: float = 0.0,
    frost_max_wind_ms: float = 3.0,
    frost_max_dew_delta_C: float = 2.0,
    rain_threshold_mm: float = 0.2,
    heavy_rain_threshold_mm: float = 20.0,
    heat_threshold_C: float = 35.0,
    wind_gust_threshold_ms: float = 20.0,
):
    """
    Constrói um dicionário de máscaras booleanas para diferentes eventos:

      - 'frost'       : geada (tmin <= frost_temp, vento médio e |Tmin - dew| controlados)
      - 'rain_day'    : dia chuvoso (precip >= rain_threshold)
      - 'heavy_rain'  : chuva forte (precip >= heavy_rain_threshold)
      - 'heat'        : calor extremo (tmax >= heat_threshold)
      - 'strong_wind' : vento forte (gust_max >= wind_gust_threshold)

    Só cria a máscara se as colunas necessárias existirem.
    """

    masks = {}

    # Garantir que temos coluna 'date' em datetime
    if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # ------ Geada  --------------------------------------------------------
    frost_cols = {"tmin_C", "dew2m_mean_C", "wind_mean_ms"}
    if frost_cols.issubset(df.columns):
        dew_delta = (df["tmin_C"] - df["dew2m_mean_C"]).abs()
        mask_frost = (
            (df["tmin_C"] <= frost_temp_C)
            & (df["wind_mean_ms"] <= frost_max_wind_ms)
            & (dew_delta <= frost_max_dew_delta_C)
        )
        masks["frost"] = mask_frost

    # ------ Dia chuvoso ---------------------------------------------------
    if "precip_mm" in df.columns:
        masks["rain_day"] = df["precip_mm"] >= rain_threshold_mm
        masks["heavy_rain"] = df["precip_mm"] >= heavy_rain_threshold_mm

    # ------ Calor extremo -------------------------------------------------
    if "tmax_C" in df.columns:
        masks["heat"] = df["tmax_C"] >= heat_threshold_C

    # ------ Vento forte ---------------------------------------------------
    if "gust_max_ms" in df.columns:
        masks["strong_wind"] = df["gust_max_ms"] >= wind_gust_threshold_ms

    return masks


# -------------------------------------------------------------------------
# 4. FREQÜÊNCIA E “SEVERIDADE”
# -------------------------------------------------------------------------

def summarize_event_frequency_severity(df: pd.DataFrame, masks: dict) -> pd.DataFrame:
    """
    Para cada evento em `masks`, calcula:

      - nº de dias com evento
      - % de dias com evento
      - uma métrica simples de severidade média (depende do tipo de evento)

    Retorna DataFrame com colunas:
      event_key, n_days, total_days, freq_pct, metric, severity_mean
    """

    total_days = len(df)
    if total_days == 0 or not masks:
        return pd.DataFrame()

    rows = []

    for key, mask in masks.items():
        n = int(mask.sum())
        if n == 0:
            rows.append(
                {
                    "event_key": key,
                    "n_days": 0,
                    "total_days": total_days,
                    "freq_pct": 0.0,
                    "metric": None,
                    "severity_mean": None,
                }
            )
            continue

        # Escolher uma métrica de severidade “natural” para cada evento
        if key in ("rain_day", "heavy_rain"):
            metric_col = "precip_mm"
        elif key == "frost":
            metric_col = "tmin_C"
        elif key == "heat":
            metric_col = "tmax_C"
        elif key == "strong_wind":
            metric_col = "gust_max_ms"
        else:
            metric_col = None

        if metric_col is not None and metric_col in df.columns:
            severity_mean = float(df.loc[mask, metric_col].mean())
        else:
            severity_mean = None

        rows.append(
            {
                "event_key": key,
                "n_days": n,
                "total_days": total_days,
                "freq_pct": 100.0 * n / total_days,
                "metric": metric_col,
                "severity_mean": severity_mean,
            }
        )

    return pd.DataFrame(rows)


# -------------------------------------------------------------------------
# 5. CONTAGEM POR ANO
# -------------------------------------------------------------------------

def yearly_event_counts(df: pd.DataFrame, masks: dict) -> pd.DataFrame:
    """
    Constrói uma tabela (ano, event_key, dias_evento) para cada máscara.
    """

    if "date" not in df.columns:
        return pd.DataFrame()

    out_rows = []
    dates = pd.to_datetime(df["date"], errors="coerce")
    years = dates.dt.year

    for key, mask in masks.items():
        if mask is None:
            continue
        series = pd.Series(mask)
        df_tmp = pd.DataFrame({"year": years, "mask": series})
        grp = df_tmp[df_tmp["mask"]].groupby("year").size().reset_index(name="dias_evento")
        grp["event_key"] = key
        out_rows.append(grp)

    if not out_rows:
        return pd.DataFrame()

    result = pd.concat(out_rows, ignore_index=True)
    return result[["year", "event_key", "dias_evento"]]
