import pandas as pd
import numpy as np
from typing import Dict, List, Optional


# ---------------------------------------------------------
# 1. Carregar ficheiro via Streamlit
# ---------------------------------------------------------
def streamlit_upload_and_load(st, label: str) -> Optional[pd.DataFrame]:
    """
    Mostra um file_uploader no Streamlit e devolve um DataFrame
    com a coluna 'date' convertida para datetime (se existir).
    """
    uploaded = st.file_uploader(label, type=["csv"])
    if uploaded is None:
        return None

    # Lê o CSV tal como vem do GEE
    df = pd.read_csv(uploaded)

    # Converte a coluna 'date' se existir
    if "date" in df.columns:
        try:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        except Exception:
            pass

    return df


# ---------------------------------------------------------
# 2. Deteção de colunas de variáveis
# ---------------------------------------------------------
def detect_variable_columns(df: pd.DataFrame) -> List[str]:
    """
    Identifica colunas relevantes de variáveis meteorológicas
    no CSV gerado no GEE.
    """
    candidate_cols = [
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

    return [c for c in candidate_cols if c in df.columns]


# ---------------------------------------------------------
# 3. Resumo estatístico diário
# ---------------------------------------------------------
def summarize_daily_variables(df: pd.DataFrame, var_cols: List[str]) -> pd.DataFrame:
    """
    Produz estatísticas resumo (count, mean, std, min, quartis, max)
    para as colunas de variáveis.
    """
    if not var_cols:
        return pd.DataFrame()

    summary = df[var_cols].describe().T
    summary = summary.rename(columns={"50%": "median"})
    return summary


# ---------------------------------------------------------
# 4. Aplicar janela sazonal opcional (para análise)
# ---------------------------------------------------------
def apply_seasonal_window(
    df: pd.DataFrame,
    start_month: int = 1,
    start_day: int = 1,
    end_month: int = 12,
    end_day: int = 31,
) -> pd.DataFrame:
    """
    Filtra o DataFrame para uma janela sazonal (mês/dia) aplicada
    a todos os anos. Se a janela passar pelo fim do ano (ex.: 15 Nov–15 Fev),
    é tratada automaticamente.
    """
    if "date" not in df.columns or not np.issubdtype(df["date"].dtype, np.datetime64):
        # Se não houver coluna date em datetime, devolve o df original
        return df

    df = df.copy()
    doy = df["date"].dt.dayofyear

    # construímos um ano de referência (2001) para calcular DOY de limites
    start_ref = pd.Timestamp(year=2001, month=start_month, day=start_day)
    end_ref = pd.Timestamp(year=2001, month=end_month, day=end_day)
    start_doy = start_ref.dayofyear
    end_doy = end_ref.dayofyear

    if start_doy <= end_doy:
        mask = (doy >= start_doy) & (doy <= end_doy)
    else:
        # janela que passa por 31/12
        mask = (doy >= start_doy) | (doy <= end_doy)

    return df.loc[mask].copy()


# ---------------------------------------------------------
# 5. Cálculo de máscaras de eventos
# ---------------------------------------------------------
def compute_event_masks(
    df: pd.DataFrame,
    frost_temp_C: float = 0.0,
    frost_max_wind_ms: float = 3.0,
    frost_max_dew_delta_C: float = 2.0,
    rain_threshold_mm: float = 0.2,
    heavy_rain_threshold_mm: float = 20.0,
    heat_threshold_C: float = 35.0,
    wind_gust_threshold_ms: float = 20.0,
) -> Dict[str, pd.Series]:
    """
    Cria uma série de máscaras booleanas (uma por tipo de evento),
    assumindo nomes de colunas do CSV diário.
    """
    masks: Dict[str, pd.Series] = {}

    # Garantir que temos coluna date em datetime (para outras análises)
    if "date" in df.columns and not np.issubdtype(df["date"].dtype, np.datetime64):
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # ---------- Geada ----------
    if {"tmin_C", "wind_mean_ms", "dew2m_mean_C"}.issubset(df.columns):
        dew_delta = (df["tmin_C"] - df["dew2m_mean_C"]).abs()
        frost_mask = (
            (df["tmin_C"] <= frost_temp_C)
            & (df["wind_mean_ms"] <= frost_max_wind_ms)
            & (dew_delta <= frost_max_dew_delta_C)
        )
        masks["frost"] = frost_mask

    # ---------- Chuva ----------
    if "precip_mm" in df.columns:
        masks["rain_day"] = df["precip_mm"] >= rain_threshold_mm
        masks["heavy_rain"] = df["precip_mm"] >= heavy_rain_threshold_mm

    # ---------- Calor ----------
    if "tmax_C" in df.columns:
        masks["heat"] = df["tmax_C"] >= heat_threshold_C

    # ---------- Vento forte ----------
    if "gust_max_ms" in df.columns:
        masks["strong_wind"] = df["gust_max_ms"] >= wind_gust_threshold_ms

    return masks


# ---------------------------------------------------------
# 6. Resumo de frequência e severidade
# ---------------------------------------------------------
def summarize_event_frequency_severity(
    df: pd.DataFrame, masks: Dict[str, pd.Series]
) -> pd.DataFrame:
    """
    Para cada tipo de evento devolve:
      - nº total de dias com evento
      - % de dias no período
      - severidade média (quando faz sentido)
    """
    if not masks:
        return pd.DataFrame()

    results = []
    total_days = len(df)

    # Qual variável usar como "severidade" por evento
    severity_var = {
        "frost": "tmin_C",
        "rain_day": "precip_mm",
        "heavy_rain": "precip_mm",
        "heat": "tmax_C",
        "strong_wind": "gust_max_ms",
    }

    for key, mask in masks.items():
        days_event = int(mask.sum())
        perc = 100.0 * days_event / total_days if total_days > 0 else 0.0

        sev_col = severity_var.get(key)
        if sev_col is not None and sev_col in df.columns:
            sev_mean = df.loc[mask, sev_col].mean()
        else:
            sev_mean = np.nan

        results.append(
            {
                "event_key": key,
                "dias_evento": days_event,
                "percent_dias": perc,
                "severidade_media": sev_mean,
            }
        )

    return pd.DataFrame(results)


# ---------------------------------------------------------
# 7. Contagem anual de eventos
# ---------------------------------------------------------
def yearly_event_counts(df: pd.DataFrame, masks: Dict[str, pd.Series]) -> pd.DataFrame:
    """
    Devolve um DataFrame com colunas:
      - year
      - event_key
      - dias_evento
    para facilitar a construção de gráficos.
    """
    if "date" not in df.columns:
        return pd.DataFrame()

    if not np.issubdtype(df["date"].dtype, np.datetime64):
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    df = df.dropna(subset=["date"]).copy()
    df["year"] = df["date"].dt.year

    rows = []
    for key, mask in masks.items():
        tmp = df.loc[mask].groupby("year").size().reset_index(name="dias_evento")
        tmp["event_key"] = key
        rows.append(tmp)

    if not rows:
        return pd.DataFrame()

    return pd.concat(rows, ignore_index=True)
