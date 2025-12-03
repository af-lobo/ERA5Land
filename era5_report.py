# era5_report.py
#
# Funções para gerar relatório PDF a partir dos dados diários ERA5.

from __future__ import annotations

import io
from typing import Dict, Any

import numpy as np
import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors


EVENT_LABELS: Dict[str, Dict[str, str]] = {
    "pt": {
        "title": "Análise de Risco Climático",
        "location": "Localização",
        "coords": "Coordenadas",
        "period": "Período analisado",
        "seasonal_window": "Janela sazonal aplicada",
        "events_summary": "Resumo de frequência e severidade dos eventos",
        "days": "N.º de dias",
        "prob": "Probabilidade",
        "params": "Parâmetros utilizados",
        "stats": "Estatísticas principais",
        "no_data": "Sem ocorrências neste período.",
        "frost": "Geada",
        "rain_day": "Dia chuvoso",
        "heavy_rain": "Chuva forte",
        "heat": "Calor extremo",
        "strong_wind": "Vento forte",
        "precip": "Precipitação (mm/dia)",
        "tmin": "Tmin (°C)",
        "tmax": "Tmax (°C)",
        "tmean": "Tmean (°C)",
        "dew": "Ponto de orvalho (°C)",
        "wind": "Vento médio (m/s)",
        "gust": "Rajada máx. (m/s)",
    },
    "en": {
        "title": "Climate Risk Analysis",
        "location": "Location",
        "coords": "Coordinates",
        "period": "Analysed period",
        "seasonal_window": "Applied seasonal window",
        "events_summary": "Summary of event frequency and severity",
        "days": "No. of days",
        "prob": "Probability",
        "params": "Parameters used",
        "stats": "Key statistics",
        "no_data": "No occurrences in this period.",
        "frost": "Frost",
        "rain_day": "Rainy day",
        "heavy_rain": "Heavy rain",
        "heat": "Heatwave",
        "strong_wind": "Strong wind",
        "precip": "Precipitation (mm/day)",
        "tmin": "Tmin (°C)",
        "tmax": "Tmax (°C)",
        "tmean": "Tmean (°C)",
        "dew": "Dew point (°C)",
        "wind": "Mean wind (m/s)",
        "gust": "Max gust (m/s)",
    },
    "es": {
        "title": "Análisis de Riesgo Climático",
        "location": "Localización",
        "coords": "Coordenadas",
        "period": "Período analizado",
        "seasonal_window": "Ventana estacional aplicada",
        "events_summary": "Resumen de frecuencia y severidad de eventos",
        "days": "N.º de días",
        "prob": "Probabilidad",
        "params": "Parámetros utilizados",
        "stats": "Estadísticas principales",
        "no_data": "Sin ocurrencias en este período.",
        "frost": "Helada",
        "rain_day": "Día lluvioso",
        "heavy_rain": "Lluvia intensa",
        "heat": "Calor extremo",
        "strong_wind": "Viento fuerte",
        "precip": "Precipitación (mm/día)",
        "tmin": "Tmin (°C)",
        "tmax": "Tmax (°C)",
        "tmean": "Tmean (°C)",
        "dew": "Punto de rocío (°C)",
        "wind": "Viento medio (m/s)",
        "gust": "Ráfaga máx. (m/s)",
    },
}


def _safe_stats(series: pd.Series) -> Dict[str, Any]:
    """Min, max, mean com protecção para séries vazias."""
    if series is None or series.empty:
        return {"min": None, "max": None, "mean": None}
    return {
        "min": float(series.min()),
        "max": float(series.max()),
        "mean": float(series.mean()),
    }


def build_event_stats_for_report(
    df: pd.DataFrame,
    masks: Dict[str, pd.Series],
) -> Dict[str, Dict[str, Any]]:
    """
    Calcula nº de dias, probabilidade e estatísticas básicas para cada evento.
    df já deve estar filtrado pela janela sazonal (se existir).
    """
    total_days = len(df)
    results: Dict[str, Dict[str, Any]] = {}

    if total_days == 0:
        return results

    for key, mask in masks.items():
        if mask is None:
            continue

        # Garante que a máscara alinha com o DataFrame
        series_mask = pd.Series(mask, index=df.index)
        if series_mask.sum() == 0:
            # queremos mesmo assim registar "zero dias" – o caller trata disso
            days = 0
            prob = 0.0
            sub = df.iloc[[]].copy()
        else:
            sub = df[series_mask].copy()
            days = len(sub)
            prob = 100.0 * days / total_days

        stats: Dict[str, Any] = {
            "days": int(days),
            "prob_pct": float(prob),
        }

        # Só calcula se as colunas existirem
        if "precip_mm" in sub.columns:
            stats["precip_mm"] = _safe_stats(sub["precip_mm"])
        if "tmin_C" in sub.columns:
            stats["tmin_C"] = _safe_stats(sub["tmin_C"])
        if "tmax_C" in sub.columns:
            stats["tmax_C"] = _safe_stats(sub["tmax_C"])
        if "tmean_C" in sub.columns:
            stats["tmean_C"] = _safe_stats(sub["tmean_C"])
        if "dew2m_mean_C" in sub.columns:
            stats["dew2m_mean_C"] = _safe_stats(sub["dew2m_mean_C"])
        if "wind_mean_ms" in sub.columns:
            stats["wind_mean_ms"] = _safe_stats(sub["wind_mean_ms"])
        if "gust_max_ms" in sub.columns:
            stats["gust_max_ms"] = _safe_stats(sub["gust_max_ms"])

        results[key] = stats

    return results


def generate_pdf_report(
    df: pd.DataFrame,
    masks: Dict[str, pd.Series],
    freq_sev: pd.DataFrame,
    params: Dict[str, float],
    seasonal_info: Dict[str, Any] | None = None,
    lang: str = "pt",
    location_name: str = "Localização",
    lat: float | None = None,
    lon: float | None = None,
) -> bytes:
    """
    Gera um PDF em memória com o sumário de risco climático.

    Retorna os bytes do PDF (para download no Streamlit).
    """
    # Escolher dicionário de labels pelo idioma
    labels = EVENT_LABELS.get(lang, EVENT_LABELS["pt"])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    story = []

    # -----------------------------------------------------
    # 1. Cabeçalho / meta-informação
    # -----------------------------------------------------
    title_style = styles["Title"]
    normal = styles["Normal"]
    heading = styles["Heading2"]

    story.append(Paragraph(labels["title"], title_style))
    story.append(Spacer(1, 0.5 * cm))

    # Localização e coordenadas
    loc_text = f"{labels['location']}: {location_name}"
    story.append(Paragraph(loc_text, normal))

    if lat is not None and lon is not None:
        coords_text = f"{labels['coords']}: {lat:.4f}, {lon:.4f}"
        story.append(Paragraph(coords_text, normal))

    # Período
    if "date" in df.columns:
        try:
            dmin = pd.to_datetime(df["date"]).min().date()
            dmax = pd.to_datetime(df["date"]).max().date()
            period_text = f"{labels['period']}: {dmin} – {dmax}"
            story.append(Paragraph(period_text, normal))
        except Exception:
            pass

    # Janela sazonal (se existir)
    if seasonal_info is not None:
        sm = seasonal_info.get("start_month")
        sd = seasonal_info.get("start_day")
        em = seasonal_info.get("end_month")
        ed = seasonal_info.get("end_day")
        if sm and sd and em and ed:
            win_text = (
                f"{labels['seasonal_window']}: "
                f"{sd:02d}/{sm:02d} – {ed:02d}/{em:02d}"
            )
            story.append(Paragraph(win_text, normal))

    story.append(Spacer(1, 0.5 * cm))

    # -----------------------------------------------------
    # 2. Tabela resumo de frequência/severidade
    # -----------------------------------------------------
    story.append(Paragraph(labels["events_summary"], heading))
    story.append(Spacer(1, 0.2 * cm))

    # Queremos garantir que todos os eventos apareçam, mesmo sem ocorrências
    all_event_keys = ["frost", "rain_day", "heavy_rain", "heat", "strong_wind"]

    table_data = [
        [
            "Evento",
            labels["days"],
            labels["prob"],
        ]
    ]

    for key in all_event_keys:
        label = labels.get(key, key)
        row = freq_sev[freq_sev["event_key"] == key]
        if row.empty:
            days = 0
            prob = 0.0
        else:
            days = int(row["dias_evento"].iloc[0])
            prob = float(row["probabilidade_%"].iloc[0])

        table_data.append(
            [
                label,
                f"{days}",
                f"{prob:.1f} %",
            ]
        )

    table = Table(table_data, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.7 * cm))

    # -----------------------------------------------------
    # 3. Secções por evento (parâmetros + estatísticas)
    # -----------------------------------------------------
    event_stats = build_event_stats_for_report(df, masks)

    param_labels = {
        "frost": [
            ("frost_temp", "Tmax geada (°C)"),
            ("frost_max_wind", "Vento máx. (m/s)"),
            ("frost_dew_delta", "|Tmin - Td|max (°C)"),
        ],
        "rain_day": [
            ("rain_thresh", "Dia chuvoso ≥ (mm)"),
        ],
        "heavy_rain": [
            ("heavy_rain_thresh", "Chuva forte ≥ (mm)"),
        ],
        "heat": [
            ("heat_thresh", "Calor extremo Tmin ≥ (°C)"),
        ],
        "strong_wind": [
            ("wind_gust_thresh", "Rajada forte ≥ (m/s)"),
        ],
    }

    for key in all_event_keys:
        label = labels.get(key, key)
        story.append(Paragraph(label, heading))
        story.append(Spacer(1, 0.2 * cm))

        # Parâmetros
        story.append(Paragraph(labels["params"], styles["Heading3"]))
        plist = []
        for p_key, p_desc in param_labels.get(key, []):
            if p_key in params:
                plist.append(f"{p_desc}: {params[p_key]}")
        if not plist:
            plist.append("(sem parâmetros específicos)")
        for line in plist:
            story.append(Paragraph(line, normal))

        story.append(Spacer(1, 0.2 * cm))

        # Estatísticas do evento
        stats = event_stats.get(key)
        if not stats:
            story.append(Paragraph(labels["no_data"], normal))
            story.append(Spacer(1, 0.5 * cm))
            continue

        story.append(Paragraph(labels["stats"], styles["Heading3"]))

        # Tabela simples com algumas variáveis
        rows = [
            ["", "min", "média", "max"],
        ]

        def add_row(label_key: str, stat_key: str):
            if stat_key not in stats:
                return
            s = stats[stat_key]
            rows.append(
                [
                    labels[label_key],
                    f"{s['min']:.2f}" if s["min"] is not None else "-",
                    f"{s['mean']:.2f}" if s["mean"] is not None else "-",
                    f"{s['max']:.2f}" if s["max"] is not None else "-",
                ]
            )

        add_row("precip", "precip_mm")
        add_row("tmin", "tmin_C")
        add_row("tmax", "tmax_C")
        add_row("tmean", "tmean_C")
        add_row("dew", "dew2m_mean_C")
        add_row("wind", "wind_mean_ms")
        add_row("gust", "gust_max_ms")

        stats_table = Table(rows, hAlign="LEFT")
        stats_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            )
        )

        story.append(stats_table)
        story.append(Spacer(1, 0.7 * cm))

    # -----------------------------------------------------
    # 4. Build & return bytes
    # -----------------------------------------------------
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
