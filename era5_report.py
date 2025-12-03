# era5_report.py
#
# Geração de relatório PDF a partir dos dados diários ERA5.

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


# ----------------------------------------------------------------------
# Labels por idioma
# ----------------------------------------------------------------------

EVENT_LABELS: Dict[str, Dict[str, str]] = {
    "pt": {
        "title": "Análise de Risco Climático",
        "location": "Localização",
        "coords": "Coordenadas (lat, lon)",
        "period": "Período do ficheiro",
        "seasonal_window": "Janela sazonal de análise",
        "events_summary": "Resumo de frequência de eventos",
        "days": "Nº dias com evento",
        "prob": "Probabilidade no período",
        "params": "Parâmetros usados",
        "stats": "Estatísticas das variáveis (dias com evento)",
        "no_data": "Nenhum dia com este tipo de evento no período analisado.",
        "precip": "Precipitação (mm/dia)",
        "tmin": "Temperatura mínima (°C)",
        "tmax": "Temperatura máxima (°C)",
        "tmean": "Temperatura média (°C)",
        "dew": "Ponto de orvalho 2 m (°C)",
        "wind": "Vento médio (m/s)",
        "gust": "Rajada máxima (m/s)",
        "frost": "Geada",
        "rain_day": "Dia chuvoso",
        "heavy_rain": "Chuva forte",
        "heat": "Calor extremo",
        "strong_wind": "Vento forte",
    },
    "en": {
        "title": "Climate Risk Analysis",
        "location": "Location",
        "coords": "Coordinates (lat, lon)",
        "period": "File period",
        "seasonal_window": "Seasonal window for analysis",
        "events_summary": "Event frequency summary",
        "days": "Number of event days",
        "prob": "Probability in the period",
        "params": "Parameters used",
        "stats": "Variable statistics (event days only)",
        "no_data": "No days with this type of event in the analysed period.",
        "precip": "Precipitation (mm/day)",
        "tmin": "Minimum temperature (°C)",
        "tmax": "Maximum temperature (°C)",
        "tmean": "Mean temperature (°C)",
        "dew": "Dew point 2 m (°C)",
        "wind": "Mean wind (m/s)",
        "gust": "Max gust (m/s)",
        "frost": "Frost",
        "rain_day": "Rainy day",
        "heavy_rain": "Heavy rain",
        "heat": "Heat stress",
        "strong_wind": "Strong wind",
    },
    "es": {
        "title": "Análisis de Riesgo Climático",
        "location": "Localización",
        "coords": "Coordenadas (lat, lon)",
        "period": "Periodo del fichero",
        "seasonal_window": "Ventana estacional de análisis",
        "events_summary": "Resumen de frecuencia de eventos",
        "days": "Nº de días con evento",
        "prob": "Probabilidad en el periodo",
        "params": "Parámetros utilizados",
        "stats": "Estadísticas de las variables (solo días con evento)",
        "no_data": "No hay días con este tipo de evento en el periodo analizado.",
        "precip": "Precipitación (mm/día)",
        "tmin": "Temperatura mínima (°C)",
        "tmax": "Temperatura máxima (°C)",
        "tmean": "Temperatura media (°C)",
        "dew": "Punto de rocío 2 m (°C)",
        "wind": "Viento medio (m/s)",
        "gust": "Racha máxima (m/s)",
        "frost": "Helada",
        "rain_day": "Día lluvioso",
        "heavy_rain": "Lluvia intensa",
        "heat": "Calor extremo",
        "strong_wind": "Viento fuerte",
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
        if mask is None or mask.sum() == 0:
            continue

        sub = df[mask].copy()
        days = len(sub)
        prob = 100.0 * days / total_days

        stats: Dict[str, Any] = {
            "days": int(days),
            "prob_pct": float(prob),
        }

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


# ----------------------------------------------------------------------
# Gerar PDF
# ----------------------------------------------------------------------


def generate_pdf_report(
    df: pd.DataFrame,
    masks: Dict[str, pd.Series],
    freq_sev: pd.DataFrame,          # mantido na assinatura, mas não é usado
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

    # Escolher labels
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

    title_style = styles["Title"]
    normal = styles["Normal"]
    heading = styles["Heading2"]

    # --------------------------------------------------
    # 1. Cabeçalho
    # --------------------------------------------------
    story.append(Paragraph(labels["title"], title_style))
    story.append(Spacer(1, 0.5 * cm))

    # Localização + coords
    story.append(Paragraph(f"{labels['location']}: {location_name}", normal))
    if lat is not None and lon is not None:
        story.append(
            Paragraph(
                f"{labels['coords']}: {lat:.4f}, {lon:.4f}",
                normal,
            )
        )

    # Período do ficheiro
    if "date" in df.columns:
        try:
            dmin = pd.to_datetime(df["date"]).min().date()
            dmax = pd.to_datetime(df["date"]).max().date()
            story.append(
                Paragraph(f"{labels['period']}: {dmin} – {dmax}", normal)
            )
        except Exception:
            pass

    # Janela sazonal
    if seasonal_info is not None:
        sm = seasonal_info.get("start_month")
        sd = seasonal_info.get("start_day")
        em = seasonal_info.get("end_month")
        ed = seasonal_info.get("end_day")
        if sm and sd and em and ed:
            story.append(
                Paragraph(
                    f"{labels['seasonal_window']}: {sd:02d}/{sm:02d} – {ed:02d}/{em:02d}",
                    normal,
                )
            )

    story.append(Spacer(1, 0.7 * cm))

    # --------------------------------------------------
    # 2. Estatísticas globais por evento
    # --------------------------------------------------
    all_event_keys = ["frost", "rain_day", "heavy_rain", "heat", "strong_wind"]
    event_stats = build_event_stats_for_report(df, masks)

    story.append(Paragraph(labels["events_summary"], heading))
    story.append(Spacer(1, 0.2 * cm))

    table_data = [
        ["Evento", labels["days"], labels["prob"]],
    ]

    for key in all_event_keys:
        label = labels.get(key, key)
        stats = event_stats.get(key)
        if not stats:
            days = 0
            prob = 0.0
        else:
            days = int(stats.get("days", 0))
            prob = float(stats.get("prob_pct", 0.0))

        table_data.append(
            [
                label,
                f"{days}",
                f"{prob:.1f} %",
            ]
        )

    summary_table = Table(table_data, hAlign="LEFT")
    summary_table.setStyle(
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
    story.append(summary_table)
    story.append(Spacer(1, 0.7 * cm))

    # --------------------------------------------------
    # 3. Secções por evento
    # --------------------------------------------------
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
            ("heat_thresh", "Calor extremo Tmax ≥ (°C)"),
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

        # Estatísticas
        stats = event_stats.get(key)
        if not stats:
            story.append(Paragraph(labels["no_data"], normal))
            story.append(Spacer(1, 0.7 * cm))
            continue

        story.append(Paragraph(labels["stats"], styles["Heading3"]))

        rows = [["", "min", "média", "max"]]

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

    # --------------------------------------------------
    # 4. Build
    # --------------------------------------------------
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
