# era5_report.py
#
# Geração de relatório PDF a partir dos dados diários ERA5.

from __future__ import annotations

import io
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors


# -------------------------------------------------------------------
# Textos por idioma
# -------------------------------------------------------------------

TEXTS: Dict[str, Dict[str, str]] = {
    "pt": {
        "title": "Análise de Risco Climático",
        "summary": "Resumo geral",
        "n_days": "Número de dias no ficheiro analisado",
        "period": "Período temporal",
        "season": "Janela sazonal aplicada",
        "season_not_applied": "Nenhuma janela sazonal aplicada (ano completo)",
        "season_days": "Dias antes do filtro / após filtro",
        "params": "Parâmetros dos eventos",
        "stats": "Estatísticas por tipo de evento",
        "charts": "Evolução anual do número de dias com evento",
        "event": "Evento",
        "days": "Nº dias",
        "prob": "Probabilidade",
        "precip": "Precipitação (mm)\nmin / média / máx",
        "tmin": "Tmin (°C)\nmin / média / máx",
        "tmax": "Tmax (°C)\nmin / média / máx",
        "gust": "Rajada (m/s)\nmin / média / máx",
        "no_data": "Sem dados suficientes.",
        "location": "Localização",
        "map_title": "Mapa (posição aproximada do centróide)",
    },
    "en": {
        "title": "Climate Risk Analysis",
        "summary": "General summary",
        "n_days": "Number of days in the file",
        "period": "Time period",
        "season": "Seasonal window applied",
        "season_not_applied": "No seasonal window applied (full year)",
        "season_days": "Days before / after seasonal filter",
        "params": "Event thresholds",
        "stats": "Statistics by event type",
        "charts": "Yearly number of event days",
        "event": "Event",
        "days": "Nº days",
        "prob": "Probability",
        "precip": "Precipitation (mm)\nmin / mean / max",
        "tmin": "Tmin (°C)\nmin / mean / max",
        "tmax": "Tmax (°C)\nmin / mean / max",
        "gust": "Gust (m/s)\nmin / mean / max",
        "no_data": "Not enough data.",
        "location": "Location",
        "map_title": "Map (approximate centroid position)",
    },
    "es": {
        "title": "Análisis de Riesgo Climático",
        "summary": "Resumen general",
        "n_days": "Número de días en el fichero",
        "period": "Período temporal",
        "season": "Ventana estacional aplicada",
        "season_not_applied": "Sin ventana estacional (año completo)",
        "season_days": "Días antes / después del filtro estacional",
        "params": "Parámetros de los eventos",
        "stats": "Estadísticas por tipo de evento",
        "charts": "Número anual de días con evento",
        "event": "Evento",
        "days": "Nº días",
        "prob": "Probabilidad",
        "precip": "Precipitación (mm)\nmín / media / máx",
        "tmin": "Tmin (°C)\nmín / media / máx",
        "tmax": "Tmax (°C)\nmáx / media / máx",
        "gust": "Ráfaga (m/s)\nmín / media / máx",
        "no_data": "No hay datos suficientes.",
        "location": "Ubicación",
        "map_title": "Mapa (posición aproximada del centróide)",
    },
}

# etiquetas dos eventos por idioma
EVENT_LABELS: Dict[str, Dict[str, str]] = {
    "pt": {
        "frost": "Geada",
        "rain_day": "Dia chuvoso",
        "heavy_rain": "Chuva forte",
        "heat": "Calor extremo",
        "strong_wind": "Vento forte",
    },
    "en": {
        "frost": "Frost",
        "rain_day": "Rainy day",
        "heavy_rain": "Heavy rain",
        "heat": "Heat stress",
        "strong_wind": "Strong wind",
    },
    "es": {
        "frost": "Helada",
        "rain_day": "Día lluvioso",
        "heavy_rain": "Lluvia fuerte",
        "heat": "Calor extremo",
        "strong_wind": "Viento fuerte",
    },
}


# -------------------------------------------------------------------
# Helpers de estatística
# -------------------------------------------------------------------


def _safe_stats(series: pd.Series) -> Dict[str, Optional[float]]:
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
    Inclui eventos mesmo com 0 ocorrências.
    """
    total_days = len(df)
    results: Dict[str, Dict[str, Any]] = {}

    if total_days == 0:
        return results

    for key, mask in masks.items():
        if mask is None:
            days = 0
        else:
            days = int(mask.sum())

        prob = 100.0 * days / total_days if total_days > 0 else 0.0
        sub = df[mask] if mask is not None else df.iloc[0:0]

        stats: Dict[str, Any] = {
            "days": days,
            "prob_pct": float(prob),
            "precip_mm": _safe_stats(sub["precip_mm"]) if "precip_mm" in sub else None,
            "tmin_C": _safe_stats(sub["tmin_C"]) if "tmin_C" in sub else None,
            "tmax_C": _safe_stats(sub["tmax_C"]) if "tmax_C" in sub else None,
            "tmean_C": _safe_stats(sub["tmean_C"]) if "tmean_C" in sub else None,
            "dew2m_mean_C": _safe_stats(sub["dew2m_mean_C"]) if "dew2m_mean_C" in sub else None,
            "wind_mean_ms": _safe_stats(sub["wind_mean_ms"]) if "wind_mean_ms" in sub else None,
            "gust_max_ms": _safe_stats(sub["gust_max_ms"]) if "gust_max_ms" in sub else None,
        }

        results[key] = stats

    return results


def _fmt_stats(stats: Optional[Dict[str, Any]]) -> str:
    if not stats or stats["min"] is None:
        return "—"
    return f"{stats['min']:.1f} / {stats['mean']:.1f} / {stats['max']:.1f}"


# -------------------------------------------------------------------
# Gráfico de localização (mapa simples)
# -------------------------------------------------------------------


def _make_location_map(lat: float, lon: float, title: str) -> io.BytesIO:
    """
    Cria um pequeno "mapa" muito simples: eixos lat/lon e o ponto do centróide.
    Não depende de dados externos.
    """
    fig, ax = plt.subplots(figsize=(3.0, 4.0))
    ax.scatter(lon, lat, s=40)
    ax.set_xlabel("Lon")
    ax.set_ylabel("Lat")
    ax.set_title(title)

    # janelas simples que funcionam bem para Portugal/Chile, etc.
    ax.set_xlim(lon - 5, lon + 5)
    ax.set_ylim(lat - 5, lat + 5)

    ax.grid(True, linestyle="--", linewidth=0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="PNG", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


# -------------------------------------------------------------------
# Gráficos anuais por evento
# -------------------------------------------------------------------


def _yearly_counts(df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    """Conta nº de dias com evento por ano, incluindo anos com 0."""
    if "date" not in df.columns:
        return pd.DataFrame(columns=["year", "days"])

    years = df["date"].dt.year
    all_years = np.arange(years.min(), years.max() + 1)

    if mask is None:
        counts = pd.Series(0, index=all_years)
    else:
        tmp = df.loc[mask].copy()
        tmp_years = tmp["date"].dt.year
        counts = tmp_years.value_counts().reindex(all_years, fill_value=0).sort_index()

    return pd.DataFrame({"year": all_years, "days": counts.values})


def _make_yearly_bar_chart(
    yearly_df: pd.DataFrame,
    title: str,
) -> io.BytesIO:
    """Gera um gráfico de barras simples (year vs days)."""
    fig, ax = plt.subplots(figsize=(4.5, 2.5))
    ax.bar(yearly_df["year"], yearly_df["days"])
    ax.set_xlabel("Ano")
    ax.set_ylabel("Dias")
    ax.set_title(title)
    ax.grid(axis="y", linestyle="--", linewidth=0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="PNG", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


# -------------------------------------------------------------------
# Função principal de geração do PDF
# -------------------------------------------------------------------


def generate_pdf_report(
    df: pd.DataFrame,
    seasonal_info: Dict[str, Any],
    masks: Dict[str, pd.Series],
    freq_sev: pd.DataFrame,
    params: Dict[str, Any],
    meta: Optional[Dict[str, Any]] = None,
    lang: str = "pt",
) -> bytes:
    """
    Gera o PDF a partir dos dados diários.

    meta pode conter:
      - location_name: str
      - lat: float
      - lon: float
      - filename: str
    """
    lang = lang if lang in TEXTS else "pt"
    T = TEXTS[lang]
    labels = EVENT_LABELS[lang]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    # -------------------------------------------------
    # Título
    # -------------------------------------------------
    title = T["title"]
    if meta and meta.get("location_name"):
        title += f" – {meta['location_name']}"
    story.append(Paragraph(f"<b>{title}</b>", styles["Title"]))
    story.append(Spacer(1, 0.4 * cm))

    # Mapa de localização (se tivermos lat/lon)
    if meta and meta.get("lat") is not None and meta.get("lon") is not None:
        map_buf = _make_location_map(
            float(meta["lat"]),
            float(meta["lon"]),
            T["map_title"],
        )
        story.append(Image(map_buf, width=7 * cm, height=7 * cm))
        story.append(Spacer(1, 0.3 * cm))

        loc_label = T["location"]
        coords_text = f"{loc_label}: {meta.get('location_name', '')}  (lat={meta['lat']:.4f}, lon={meta['lon']:.4f})"
        story.append(Paragraph(coords_text, styles["Normal"]))
        story.append(Spacer(1, 0.4 * cm))

    # -------------------------------------------------
    # 1. Resumo geral
    # -------------------------------------------------
    story.append(Paragraph(f"<b>1. {T['summary']}</b>", styles["Heading2"]))
    story.append(Spacer(1, 0.2 * cm))

    if len(df) > 0 and "date" in df.columns:
        start_date = df["date"].min().strftime("%Y-%m-%d")
        end_date = df["date"].max().strftime("%Y-%m-%d")
    else:
        start_date = end_date = "—"

    n_days = len(df)

    story.append(Paragraph(f"{T['n_days']}: {n_days}", styles["Normal"]))
    story.append(Paragraph(f"{T['period']}: {start_date} a {end_date}", styles["Normal"]))

    if seasonal_info and seasonal_info.get("applied", False):
        sm, sd = seasonal_info.get("start", (1, 1))
        em, ed = seasonal_info.get("end", (12, 31))
        story.append(
            Paragraph(
                f"{T['season']}: {sd:02d}/{sm:02d} – {ed:02d}/{em:02d}",
                styles["Normal"],
            )
        )
        before = seasonal_info.get("days_before", "–")
        after = seasonal_info.get("days_after", "–")
        story.append(
            Paragraph(
                f"{T['season_days']}: {before} → {after}",
                styles["Normal"],
            )
        )
    else:
        story.append(Paragraph(T["season_not_applied"], styles["Normal"]))

    story.append(Spacer(1, 0.5 * cm))

    # -------------------------------------------------
    # 2. Parâmetros dos eventos
    # -------------------------------------------------
    story.append(Paragraph(f"<b>2. {T['params']}</b>", styles["Heading2"]))
    story.append(Spacer(1, 0.2 * cm))

    param_rows = []

    # Geada
    param_rows.append(
        [
            labels.get("frost", "frost"),
            f"frost_temp_C = {params.get('frost_temp_C')}, "
            f"frost_max_wind_ms = {params.get('frost_max_wind_ms')}, "
            f"frost_max_dew_delta_C = {params.get('frost_max_dew_delta_C')}",
        ]
    )

    # Chuva
    param_rows.append(
        [
            labels.get("rain_day", "rain_day"),
            f"rain_threshold_mm = {params.get('rain_threshold_mm')}",
        ]
    )
    param_rows.append(
        [
            labels.get("heavy_rain", "heavy_rain"),
            f"heavy_rain_threshold_mm = {params.get('heavy_rain_threshold_mm')}",
        ]
    )

    # Calor
    param_rows.append(
        [
            labels.get("heat", "heat"),
            f"heat_threshold_C = {params.get('heat_threshold_C')}",
        ]
    )

    # Vento
    param_rows.append(
        [
            labels.get("strong_wind", "strong_wind"),
            f"wind_gust_threshold_ms = {params.get('wind_gust_threshold_ms')}",
        ]
    )

    table_params = Table(param_rows, colWidths=[5 * cm, 11 * cm])
    table_params.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ]
        )
    )
    story.append(table_params)
    story.append(Spacer(1, 0.6 * cm))

    # -------------------------------------------------
    # 3. Estatísticas por tipo de evento
    # -------------------------------------------------
    story.append(Paragraph(f"<b>3. {T['stats']}</b>", styles["Heading2"]))
    story.append(Spacer(1, 0.2 * cm))

    event_stats = build_event_stats_for_report(df, masks)

    if not event_stats:
        story.append(Paragraph(T["no_data"], styles["Normal"]))
    else:
        header = [
            T["event"],
            T["days"],
            T["prob"],
            T["precip"],
            T["tmin"],
            T["tmax"],
            T["gust"],
        ]
        rows = [header]

        for key in ["rain_day", "heavy_rain", "frost", "heat", "strong_wind"]:
            stats = event_stats.get(key)
            if stats is None:
                continue
            label = labels.get(key, key)
            row = [
                label,
                stats["days"],
                f"{stats['prob_pct']:.1f}%",
                _fmt_stats(stats.get("precip_mm")),
                _fmt_stats(stats.get("tmin_C")),
                _fmt_stats(stats.get("tmax_C")),
                _fmt_stats(stats.get("gust_max_ms")),
            ]
            rows.append(row)

        table_stats = Table(rows, colWidths=[3.2 * cm, 2 * cm, 2.2 * cm, 3.0 * cm, 3.0 * cm, 3.0 * cm, 3.0 * cm])
        table_stats.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(table_stats)

    story.append(Spacer(1, 0.6 * cm))

    # -------------------------------------------------
    # 4. Gráficos anuais
    # -------------------------------------------------
    story.append(Paragraph(f"<b>4. {T['charts']}</b>", styles["Heading2"]))
    story.append(Spacer(1, 0.2 * cm))

    if len(df) == 0 or "date" not in df.columns:
        story.append(Paragraph(T["no_data"], styles["Normal"]))
    else:
        for key in ["rain_day", "heavy_rain", "frost", "heat", "strong_wind"]:
            mask = masks.get(key)
            yearly = _yearly_counts(df, mask)
            label = labels.get(key, key)

            chart_buf = _make_yearly_bar_chart(yearly, label)
            story.append(Image(chart_buf, width=12 * cm, height=5 * cm))
            story.append(Spacer(1, 0.2 * cm))

    # -------------------------------------------------
    # Build PDF
    # -------------------------------------------------
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
