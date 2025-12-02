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


EVENT_LABELS: Dict[str, str] = {
    "frost": "Geada",
    "rain_day": "Dia chuvoso",
    "heavy_rain": "Chuva forte",
    "heat": "Calor extremo",
    "strong_wind": "Vento forte",
}


# -----------------------------------------------------------
# Helpers internos
# -----------------------------------------------------------

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
        days = int(len(sub))
        prob = 100.0 * days / total_days

        stats: Dict[str, Any] = {
            "days": days,
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


def _fmt_range(stat_dict: Dict[str, Any] | None, ndigits: int = 1) -> str:
    """Formata 'min / mean / max' ou devolve '-' se não houver dados."""
    if not isinstance(stat_dict, dict):
        return "-"

    vmin = stat_dict.get("min")
    vmax = stat_dict.get("max")
    vmean = stat_dict.get("mean")

    if vmin is None or vmax is None or vmean is None:
        return "-"

    fmt = f"{{:.{ndigits}f}}"
    return f"{fmt.format(vmin)} / {fmt.format(vmean)} / {fmt.format(vmax)}"


def _fmt_pct(x: float | None, ndigits: int = 1) -> str:
    if x is None:
        return "-"
    return f"{x:.{ndigits}f}%"


# -----------------------------------------------------------
# Função principal: gerar PDF
# -----------------------------------------------------------

def generate_pdf_report(
    df: pd.DataFrame,
    masks: Dict[str, pd.Series],
    seasonal_info: Dict[str, Any] | None = None,
    event_params: Dict[str, Any] | None = None,
    location_name: str | None = None,
    filename_hint: str | None = None,
) -> bytes:
    """
    Gera um relatório PDF em memória e devolve os bytes.

    - df: DataFrame (já eventualmente filtrado pela janela sazonal)
    - masks: dicionário {event_key: série booleana}
    - seasonal_info: dict devolvido por apply_seasonal_window (ou None)
    - event_params: parâmetros usados para definir os eventos (limiares, etc.)
    """

    if seasonal_info is None:
        seasonal_info = {}
    if event_params is None:
        event_params = {}

    # --------- Informações gerais ---------
    total_days = int(len(df))
    if "date" in df.columns:
        try:
            dates = pd.to_datetime(df["date"], errors="coerce")
            date_min = dates.min()
            date_max = dates.max()
            if pd.isna(date_min) or pd.isna(date_max):
                date_min_str = date_max_str = "N/D"
            else:
                date_min_str = date_min.strftime("%Y-%m-%d")
                date_max_str = date_max.strftime("%Y-%m-%d")
        except Exception:
            date_min_str = date_max_str = "N/D"
    else:
        date_min_str = date_max_str = "N/D"

    # Estatísticas por evento
    stats_by_event = build_event_stats_for_report(df, masks)

    # --------- Construção do PDF ---------
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title="Relatório ERA5 diário",
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    story = []

    # Título
    title = "Relatório ERA5 diário"
    if location_name:
        title += f" – {location_name}"
    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 0.5 * cm))

    # Secção: resumo geral
    story.append(Paragraph("<b>1. Resumo geral</b>", styles["Heading2"]))
    story.append(
        Paragraph(
            f"Número de dias no ficheiro analisado: <b>{total_days}</b><br/>"
            f"Período temporal: <b>{date_min_str}</b> a <b>{date_max_str}</b>",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 0.3 * cm))

    # Informação da janela sazonal (se activa)
    if seasonal_info.get("active"):
        sm = seasonal_info.get("start_month")
        sd = seasonal_info.get("start_day")
        em = seasonal_info.get("end_month")
        ed = seasonal_info.get("end_day")
        ndays_after = seasonal_info.get("n_days_after")
        ndays_before = seasonal_info.get("n_days_before")

        wraps = seasonal_info.get("wraps_year", False)
        if wraps:
            extra = " (janela atravessa o fim do ano)"
        else:
            extra = ""

        story.append(
            Paragraph(
                f"Janela sazonal aplicada: <b>{sd:02d}/{sm:02d}</b> – "
                f"<b>{ed:02d}/{em:02d}</b>{extra}<br/>"
                f"Dias antes do filtro: <b>{ndays_before}</b> • "
                f"Dias após filtro: <b>{ndays_after}</b>",
                styles["Normal"],
            )
        )
    else:
        story.append(
            Paragraph(
                "Nenhuma janela sazonal adicional foi aplicada na análise.",
                styles["Normal"],
            )
        )

    story.append(Spacer(1, 0.5 * cm))

    # Secção: parâmetros dos eventos
    if event_params:
        story.append(Paragraph("<b>2. Parâmetros dos eventos</b>", styles["Heading2"]))
        rows = [["Evento", "Parâmetros"]]
        # Formatar um texto amigável
        # (fazemos apenas um dump simples das chaves/valores)
        for key, label in EVENT_LABELS.items():
            # filtrar só parâmetros relevantes a esse evento, se houver
            relevant = {
                k: v
                for k, v in event_params.items()
                if key in k or (key == "frost" and "frost" in k)
            }
            if not relevant:
                continue
            param_text = ", ".join(f"{k} = {v}" for k, v in relevant.items())
            rows.append([label, param_text])

        if len(rows) > 1:
            table = Table(rows, colWidths=[5 * cm, 10 * cm])
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ]
                )
            )
            story.append(table)
        else:
            story.append(
                Paragraph(
                    "Parâmetros específicos dos eventos não foram indicados.",
                    styles["Normal"],
                )
            )

        story.append(Spacer(1, 0.5 * cm))

    # Secção: estatísticas por evento
    story.append(Paragraph("<b>3. Estatísticas por tipo de evento</b>", styles["Heading2"]))

    if not stats_by_event:
        story.append(
            Paragraph(
                "Nenhum dos eventos definidos ocorreu na janela analisada "
                "(ou faltam variáveis necessárias no CSV).",
                styles["Normal"],
            )
        )
    else:
        # Tabela com eventos nas linhas e algumas métricas nas colunas
        header = [
            "Evento",
            "Nº dias",
            "Probabilidade",
            "Precipitação (mm)\nmin / média / máx",
            "Tmin (°C)\nmin / média / máx",
            "Tmax (°C)\nmin / média / máx",
            "Rajada (m/s)\nmin / média / máx",
        ]
        rows = [header]

        for key, stats in stats_by_event.items():
            label = EVENT_LABELS.get(key, key)
            days = stats.get("days", 0)
            prob = _fmt_pct(stats.get("prob_pct"))

            precip_txt = _fmt_range(stats.get("precip_mm"))
            tmin_txt = _fmt_range(stats.get("tmin_C"))
            tmax_txt = _fmt_range(stats.get("tmax_C"))
            gust_txt = _fmt_range(stats.get("gust_max_ms"))

            rows.append(
                [label, str(days), prob, precip_txt, tmin_txt, tmax_txt, gust_txt]
            )

        table = Table(rows, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ]
            )
        )
        story.append(table)

    # Construir o PDF
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    return pdf_bytes
