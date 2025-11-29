"""
ERA5 Daily Analysis Utilities
============================

Ferramentas para analisar os CSVs diários gerados pelo GEE (ERA5-Land + ERA5).

Inclui:
- filtragem por janela sazonal
- análises de eventos climáticos (geada, chuva persistente, vento extremo, etc.)
- agregações anuais e estatísticas
"""

import pandas as pd
from datetime import datetime, timedelta


# -------------------------------------------------------------------------
# 1. UTILITÁRIOS
# -------------------------------------------------------------------------

def compute_doy(month: int, day: int) -> int:
    """Devolve o dia do ano (1–366) usando um ano fixo (2001)."""
    ref = datetime(2001, month, day)
    return ref.timetuple().tm_yday


def filter_seasonal_window(df: pd.DataFrame,
                           start_month: int, start_day: int,
                           end_month: int, end_day: int) -> pd.DataFrame:
    """
    Filtra um DataFrame ERA5 diário segundo uma janela sazonal.

    Exemplo:
        df = filter_seasonal_window(df, 1, 1, 2, 28)
    """
    df = df.copy()

    # Converter a data
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    df["doy"] = df["date"].dt.dayofyear

    # Dia do ano para a janela
    start_doy = compute_doy(start_month, start_day)
    end_doy = compute_doy(end_month, end_day)

    # Janela dentro do ano
    if start_doy <= end_doy:
        mask = (df["doy"] >= start_doy) & (df["doy"] <= end_doy)
    else:
        # Janela passa pelo fim do ano (ex.: Set–Mar)
        mask = (df["doy"] >= start_doy) | (df["doy"] <= end_doy)

    return df[mask].reset_index(drop=True)


# -------------------------------------------------------------------------
# 2. EVENTOS CLIMÁTICOS
# -------------------------------------------------------------------------

def detect_frost(df: pd.DataFrame, threshold: float = 0.0) -> pd.DataFrame:
    """
    Detecta dias com geada: tmin_C <= threshold (default 0°C)
    """
    frost_df = df[df["tmin_C"] <= threshold].copy()
    frost_df["event"] = "frost"
    return frost_df


def detect_extreme_rain(df: pd.DataFrame, threshold_mm: float = 50.0) -> pd.DataFrame:
    """
    Detecta dias com precipitação extrema (>= threshold_mm).
    """
    rain_df = df[df["precip_mm"] >= threshold_mm].copy()
    rain_df["event"] = "extreme_rain"
    return rain_df


def detect_extreme_wind(df: pd.DataFrame, threshold_ms: float = 20.0) -> pd.DataFrame:
    """
    Detecta dias com rajadas máximas diárias (gust_max_ms) >= threshold_ms.
    """
    wind_df = df[df["gust_max_ms"] >= threshold_ms].copy()
    wind_df["event"] = "extreme_wind"
    return wind_df


def detect_persistent_rain(df: pd.DataFrame,
                           threshold_mm: float = 5.0,
                           min_consecutive_days: int = 3) -> pd.DataFrame:
    """
    Detecta episódios de chuva persistente:
        - precip_mm >= threshold_mm
        - durante pelo menos min_consecutive_days consecutivos
    """

    df = df.copy()
    df["rain_flag"] = df["precip_mm"] >= threshold_mm

    periods = []
    start = None
    streak = 0

    for i in range(len(df)):
        if df.loc[i, "rain_flag"]:
            if start is None:
                start = df.loc[i, "date"]
            streak += 1
        else:
            if streak >= min_consecutive_days:
                end = df.loc[i - 1, "date"]
                periods.append({"start": start, "end": end, "days": streak})
            start = None
            streak = 0

    # Se terminar com um período válido
    if streak >= min_consecutive_days:
        periods.append({
            "start": start,
            "end": df.loc[len(df) - 1, "date"],
            "days": streak
        })

    return pd.DataFrame(periods)


# -------------------------------------------------------------------------
# 3. AGREGADOS ANUAIS E ESTATÍSTICAS
# -------------------------------------------------------------------------

def count_events_per_year(event_df: pd.DataFrame) -> pd.DataFrame:
    """
    Conta o número de ocorrências de um tipo de evento por ano.
    """
    if "date" not in event_df:
        return pd.DataFrame()

    out = event_df.copy()
    out["year"] = pd.to_datetime(out["date"]).dt.year

    return out.groupby("year").size().reset_index(name="count")


def compute_annual_stats(df: pd.DataFrame,
                         column: str,
                         agg: str = "mean") -> pd.DataFrame:
    """
    Calcula estatísticas anuais para uma variável do CSV:
    - mean, max, min, sum, median, etc.
    """
    if column not in df:
        return pd.DataFrame()

    out = df.copy()
    out["year"] = pd.to_datetime(out["date"]).dt.year

    return out.groupby("year")[column].agg(agg).reset_index()


# -------------------------------------------------------------------------
# 4. CARREGAMENTO DO CSV
# -------------------------------------------------------------------------

def load_era5_csv(path: str) -> pd.DataFrame:
    """
    Carrega um CSV gerado pela app/Google Earth Engine.
    Verifica e corrige tipos automaticamente.
    """

    df = pd.read_csv(path)

    # converter para datetime
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # garantir que colunas numéricas são numéricas
    numeric_cols = [
        "precip_mm", "tmin_C", "tmax_C", "tmean_C",
        "dew2m_mean_C", "soilw1_mean",
        "rad_Jm2_day", "rad_Wm2_mean",
        "pev_mm_day", "wind_mean_ms", "gust_max_ms"
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# -------------------------------------------------------------------------
# 5. AJUDA PARA ANÁLISES COMPLEXAS
# -------------------------------------------------------------------------

def join_events(*dfs) -> pd.DataFrame:
    """
    Junta vários DataFrames de eventos distintos num só.
    Útil para criar uma tabela consolidada (ex.: geada + chuva extrema).
    """
    out = pd.concat(dfs, ignore_index=True)
    out = out.sort_values("date").reset_index(drop=True)
    return out
