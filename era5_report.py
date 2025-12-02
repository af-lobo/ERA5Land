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


def generate_pdf_report(
    df: pd.DataFrame,
    masks: Dict[str, pd.Series],
    event_params: Dict[str, Dict[str, Any]],
    seasonal_info: str,
    report_title: str = "Relatório ERA5 diário",
) -> bytes:
    """
    Gera um PDF em memória com o resumo dos eventos.

    df           -> DataFrame já filtrado pela janela sazonal.
    masks        -> dicionário {event_key: máscara booleana}.
    event_params -> parâmetros usados em cada evento (limiares, etc.).
    seasonal_info-> texto descritivo da janela sazonal.
    """
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
    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    normal = styles["Normal"]

    elements = []

    # ---- Cabeçalho ----
    elements.append(Paragraph(report_title, title_style))
    elements.append(Spacer(1, 0.4 * cm))

    if "date" in df.columns and not df.empty:
        start_date = str(df["date"].min())
        end_date = str(df["date"].max())
        elements.append(
            Paragraph(
                f"Período de dados: <b>{start_date}</b> a <b>{end_date}</b>",
                normal,
            )
        )

    elements.append(Paragraph(seasonal_info, normal))
    elements.append(Spacer(1, 0.5 * cm))

    total_days = len(df)
    elements.append(
        Paragraph(f"Número de dias em análise: <b>{total_days}</b>", normal)
    )
    elements.append(Spacer(1, 0.7 * cm))

    # ---- Estatísticas por evento ----
    event_stats = build_event_stats_for_report(df, masks)

    for key, stats in event_stats.items():
        label = EVENT_LABELS.get(key, key)

        elements.append(Paragraph(label, heading_style))
        elements.append(Spacer(1, 0.2 * cm))

        # Parâmetros usados
        params = event_params.get(key, {})
        if params:
            param_rows = [["Parâmetro", "Valor"]]
            for pname, pval in params.items():
                param_rows.append([pname, str(pval)])

            table = Table(param_rows, hAlign="LEFT")
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ]
                )
            )
            elements.append(Paragraph("<b>Parâmetros utilizados:</b>", normal))
            elements.append(table)
            elements.append(Spacer(1, 0.2 * cm))

        # Indicadores principais
        days = stats.get("days", 0)
        prob = stats.get("prob_pct", np.nan)

        rows = [
            ["Indicador", "Valor"],
            ["Dias com evento", f"{days}"],
            ["Probabilidade na janela", f"{prob:.2f} %"],
        ]

        # Helper interno para acrescentar linhas de estatísticas
        def add_var_stats(name_key: str, label_txt: str):
            v = stats.get(name_key)
            if not v or v["min"] is None:
                return
            rows.append(
                [
                    f"{label_txt} (mín / média / máx)",
                    f"{v['min']:.2f} / {v['mean']:.2f} / {v['max']:.2f}",
                ]
            )

        add_var_stats("precip_mm", "Precipitação diária (mm)")
        add_var_stats("tmin_C", "Temperatura mínima (°C)")
        add_var_stats("tmax_C", "Temperatura máxima (°C)")
        add_var_stats("tmean_C", "Temperatura média (°C)")
        add_var_stats("wind_mean_ms", "Vento médio (m/s)")
        add_var_stats("gust_max_ms", "Rajada máxima (m/s)")

        stats_table = Table(rows, hAlign="LEFT")
        stats_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            )
        )

        elements.append(Paragraph("<b>Resumo estatístico:</b>", normal))
        elements.append(stats_table)
        elements.append(Spacer(1, 0.7 * cm))

    if not event_stats:
        elements.append(
            Paragraph(
                "Não foram identificados eventos com os critérios definidos.",
                normal,
            )
        )

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
