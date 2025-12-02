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


EVENT_LABELS: Dict[str, str] = {
    "frost": "Geada",
    "rain_day": "Dia chuvoso",
    "heavy_rain": "Chuva forte",
    "heat": "Calor extremo",
    "strong_wind": "Vento forte",
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
        # máscara vazia ou sem eventos -> ignora
        if mask is None or mask.sum() == 0:
            continue

        sub = df[mask].copy()
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


def _fmt(val: Any) -> str:
    """Formata números com 2 casas decimais; devolve '-' se None."""
    if val is None:
        return "-"
    try:
        return f"{float(val):.2f}"
    except Exception:
        return str(val)


def generate_pdf_report(
    df: pd.DataFrame,
    masks: Dict[str, pd.Series],
    params: Dict[str, Any] | None = None,
    seasonal_info: Dict[str, Any] | None = None,
) -> bytes:
    """
    Gera um relatório PDF em memória a partir dos dados diários ERA5.

    df          -> DataFrame já filtrado (por ex. pela janela sazonal).
    masks       -> dicionário de máscaras de eventos (frost, rain_day, etc.).
    params      -> parâmetros usados para definir os eventos.
    seasonal_info -> info opcional sobre a janela sazonal (label, nº de dias).
    """
    # Calcula estatísticas por evento
    event_stats = build_event_stats_for_report(df, masks)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story: list = []

    # ------------------------------
    # Cabeçalho
    # ------------------------------
    story.append(Paragraph("Relatório ERA5 diário", styles["Title"]))
    story.append(Spacer(1, 0.4 * cm))

    # Informação sobre janela sazonal
    if seasonal_info:
        label = seasonal_info.get("label", "")
        num_days = seasonal_info.get("num_days", len(df))
        txt = f"Janela sazonal em análise: <b>{label}</b> (nº de dias: {num_days})."
    else:
        txt = f"Número de dias considerados na análise: <b>{len(df)}</b>."

    story.append(Paragraph(txt, styles["Normal"]))
    story.append(Spacer(1, 0.3 * cm))

    # ------------------------------
    # Parâmetros utilizados
    # ------------------------------
    if params:
        story.append(Paragraph("Parâmetros usados na detecção de eventos:", styles["Heading2"]))
        data = [["Evento / Parâmetro", "Valor"]]
        for key, value in params.items():
            data.append([str(key), str(value)])

        tbl = Table(data, hAlign="LEFT")
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
        story.append(tbl)
        story.append(Spacer(1, 0.5 * cm))

    # ------------------------------
    # Estatísticas por evento
    # ------------------------------
    if not event_stats:
        story.append(Paragraph("Não foram identificados eventos com os parâmetros definidos.", styles["Normal"]))
    else:
        for event_key, stats in event_stats.items():
            label = EVENT_LABELS.get(event_key, event_key)

            story.append(Paragraph(label, styles["Heading2"]))
            story.append(Spacer(1, 0.1 * cm))

            days = stats.get("days", 0)
            prob = stats.get("prob_pct", 0.0)
            txt = f"Número de dias com evento: <b>{days}</b> ({prob:.1f}% dos dias na janela)."
            story.append(Paragraph(txt, styles["Normal"]))
            story.append(Spacer(1, 0.1 * cm))

            # Tabela com min / max / média das variáveis relevantes
            var_rows = []
            for var_name, label_var in [
                ("precip_mm", "Precipitação diária (mm)"),
                ("tmin_C", "Temperatura mínima (°C)"),
                ("tmax_C", "Temperatura máxima (°C)"),
                ("tmean_C", "Temperatura média (°C)"),
                ("dew2m_mean_C", "Ponto de orvalho médio (°C)"),
                ("wind_mean_ms", "Vento médio (m/s)"),
                ("gust_max_ms", "Rajada máxima (m/s)"),
            ]:
                if var_name in stats:
                    s = stats[var_name]
                    var_rows.append(
                        [
                            label_var,
                            _fmt(s["min"]),
                            _fmt(s["max"]),
                            _fmt(s["mean"]),
                        ]
                    )

            if var_rows:
                data = [["Variável", "Mínimo", "Máximo", "Média"]] + var_rows
                tbl = Table(data, hAlign="LEFT")
                tbl.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                        ]
                    )
                )
                story.append(tbl)
                story.append(Spacer(1, 0.4 * cm))

    # Constrói o PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
