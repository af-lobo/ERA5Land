"""
Módulo para análise de ficheiros diários ERA5 exportados do Google Earth Engine.

Funcionalidades principais:
- load_era5_daily_from_gee: ler e limpar o CSV (formato GEE com .geo em JSON).
- detectar variáveis climáticas.
- sumarizar estatísticas diárias.
- contar eventos extremos (geadas, chuva intensa, etc.).
- helpers para usar em Streamlit (upload de ficheiro).
- função para fazer upload do CSV para o Google Drive (necessita credenciais).

Autor: António + ChatGPT
"""

import os
import io
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd


# ============================================================
# 1. Leitura e limpeza do CSV ERA5 diário exportado do GEE
# ============================================================

def _read_all_lines(source) -> List[str]:
    """
    Lê todas as linhas de:
      - um caminho (str ou PathLike) OU
      - um ficheiro file-like (por ex. st.file_uploader em Streamlit).

    Devolve uma lista de strings (linhas).
    """
    if isinstance(source, (str, os.PathLike)):
        with open(source, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        # presumimos file-like (BytesIO ou texto)
        content = source.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8")

    return content.splitlines()


def load_era5_daily_from_gee(source) -> pd.DataFrame:
    """
    Lê um CSV diário ERA5 exportado do GEE, no formato observado em:
      /mnt/data/ERA5_diario_Futrono.csv

    Formato:
      - primeira linha: header normal com colunas
        (inclui '.geo' no fim)
      - linhas seguintes: uma string com todos os valores + JSON do .geo
        ex: "0,1995-01-01,8.54,...,2.97,""{""type"":""MultiPoint"",""coordinates"":[]}""

    Parâmetro:
      - source: caminho para o ficheiro (str / PathLike)
                OU objecto file-like (BytesIO, etc.)

    Devolve:
      - DataFrame com colunas:
          'system:index', 'date', variáveis climáticas...
        A coluna '.geo' é descartada.
    """
    lines = _read_all_lines(source)
    if not lines:
        raise ValueError("Ficheiro CSV vazio ou não legível.")

    header_line = lines[0].strip()
    header = header_line.split(",")

    # vamos descartar a última coluna (.geo)
    if header[-1].strip() != ".geo":
        # não é crítico, mas avisamos no log
        # (podes trocar por logging.warning se quiseres)
        print("Aviso: última coluna do header não é '.geo':", header[-1])

    cols = header[:-1]

    rows = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue

        s = line

        # remover aspas exteriores
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]

        # remover parte do .geo (começa tipicamente em ,""{)
        cut_idx = s.find(',""{')
        if cut_idx != -1:
            s_vals = s[:cut_idx]
        else:
            s_vals = s

        parts = s_vals.split(",")
        rows.append(parts)

    # verificar comprimento das linhas vs header
    unique_lengths = {len(r) for r in rows}
    if len(unique_lengths) != 1 or list(unique_lengths)[0] != len(cols):
        raise ValueError(
            f"Inconsistência no número de colunas: header tem {len(cols)}, "
            f"mas as linhas têm comprimentos {unique_lengths}"
        )

    df = pd.DataFrame(rows, columns=cols)

    # tipos
    if "date" not in df.columns:
        raise ValueError("Coluna 'date' não encontrada no CSV.")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for c in df.columns:
        if c not in ["system:index", "date"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


# ============================================================
# 2. Identificação de variáveis climáticas
# ============================================================

def detect_variable_columns(df: pd.DataFrame) -> List[str]:
    """
    Devolve a lista de colunas que consideramos variáveis "numéricas de clima",
    excluindo colunas administrativas.
    """
    ignore = {"system:index", "date"}
    var_cols = [
        c for c in df.columns
        if c not in ignore and np.issubdtype(df[c].dtype, np.number)
    ]
    return var_cols


# ============================================================
# 3. Sumário estatístico diário
# ============================================================

def summarize_daily_variables(df: pd.DataFrame,
                              var_cols: Optional[List[str]] = None
                              ) -> pd.DataFrame:
    """
    Cria um resumo estatístico para cada variável:
      - n_days, mean, median, min, max, std
      - percentis: 1, 5, 10, 90, 95, 99
    """
    if var_cols is None:
        var_cols = detect_variable_columns(df)

    summaries = []
    for col in var_cols:
        series = df[col].astype(float)
        desc = {
            "variable": col,
            "n_days": int(series.count()),
            "mean": series.mean(),
            "median": series.median(),
            "min": series.min(),
            "max": series.max(),
            "std": series.std(),
            "p01": series.quantile(0.01),
            "p05": series.quantile(0.05),
            "p10": series.quantile(0.10),
            "p90": series.quantile(0.90),
            "p95": series.quantile(0.95),
            "p99": series.quantile(0.99),
        }
        summaries.append(desc)

    return pd.DataFrame(summaries)


# ============================================================
# 4. Contagem de eventos extremos genéricos por thresholds
# ============================================================

def count_extreme_events(df: pd.DataFrame,
                         thresholds: Dict[str, Dict[str, float]]
                         ) -> pd.DataFrame:
    """
    thresholds: dicionário no formato:
      {
        "nome_variavel": {
            "lt": valor_inferior (opcional),
            "gt": valor_superior (opcional)
        },
        ...
      }

    Exemplo:
      thresholds = {
          "tmin_C": {"lt": 0.0},        # geadas (Tmin < 0°C)
          "precip_mm": {"gt": 20.0},    # chuva diária > 20 mm
      }

    Devolve DataFrame com nº de dias que cumprem cada condição.
    """
    results = []

    for var, cond in thresholds.items():
        if var not in df.columns:
            continue

        series = df[var].astype(float)
        mask = pd.Series(True, index=df.index)

        if "lt" in cond:
            mask &= series < cond["lt"]
        if "gt" in cond:
            mask &= series > cond["gt"]

        n_days = int(mask.sum())
        dates = df.loc[mask, "date"]

        results.append({
            "variable": var,
            "condition": cond,
            "n_days": n_days,
            "first_date": dates.min() if n_days > 0 else None,
            "last_date": dates.max() if n_days > 0 else None,
        })

    return pd.DataFrame(results)


# ============================================================
# 5. Funções específicas (ex.: geadas e chuva intensa)
# ============================================================

def frost_stats(df: pd.DataFrame,
                tmin_col: str = "tmin_C",
                threshold_C: float = 0.0) -> Dict[str, Any]:
    """
    Estatísticas simples de geadas:
      - nº de dias com Tmin abaixo do threshold_C
      - primeiras/últimas datas de geada
    """
    if tmin_col not in df.columns:
        raise ValueError(f"Coluna {tmin_col} não existe no DataFrame.")

    series = df[tmin_col].astype(float)
    mask = series < threshold_C
    n_days = int(mask.sum())
    frost_dates = df.loc[mask, "date"]

    return {
        "tmin_col": tmin_col,
        "threshold_C": threshold_C,
        "n_frost_days": n_days,
        "first_frost_date": frost_dates.min() if n_days > 0 else None,
        "last_frost_date": frost_dates.max() if n_days > 0 else None,
    }


def heavy_rain_events(df: pd.DataFrame,
                      precip_col: str = "precip_mm",
                      threshold_mm: float = 20.0,
                      min_consec_days: int = 1
                      ) -> Dict[str, Any]:
    """
    Conta eventos de chuva intensa:

    - Um "evento" é uma sequência de dias consecutivos em que precip_mm >= threshold_mm.
    - min_consec_days controla o nº mínimo de dias consecutivos para ser considerado evento.

    Devolve:
      - n_events
      - lista de eventos com (start_date, end_date, length)
    """
    if precip_col not in df.columns:
        raise ValueError(f"Coluna {precip_col} não existe no DataFrame.")

    df_sorted = df.sort_values("date").reset_index(drop=True)
    rain = df_sorted[precip_col].astype(float)
    dates = df_sorted["date"]

    is_heavy = rain >= threshold_mm

    events = []
    in_event = False
    start_idx = None

    for i, flag in enumerate(is_heavy):
        if flag and not in_event:
            in_event = True
            start_idx = i
        elif not flag and in_event:
            # terminou evento
            end_idx = i - 1
            length = end_idx - start_idx + 1
            if length >= min_consec_days:
                events.append({
                    "start_date": dates.iloc[start_idx],
                    "end_date": dates.iloc[end_idx],
                    "length_days": int(length),
                })
            in_event = False

    # caso termine em evento
    if in_event:
        end_idx = len(is_heavy) - 1
        length = end_idx - start_idx + 1
        if length >= min_consec_days:
            events.append({
                "start_date": dates.iloc[start_idx],
                "end_date": dates.iloc[end_idx],
                "length_days": int(length),
            })

    return {
        "precip_col": precip_col,
        "threshold_mm": threshold_mm,
        "min_consec_days": min_consec_days,
        "n_events": len(events),
        "events": events,
    }


# ============================================================
# 6. Helpers para Streamlit (upload de ficheiro)
# ============================================================

def streamlit_upload_and_load(st, label: str = "Carrega CSV ERA5 diário (exportado do GEE)"):
    """
    Helper para usar directamente numa app Streamlit.

    Exemplo de uso na tua app:
        import streamlit as st
        from era5_daily_analysis import streamlit_upload_and_load

        df = streamlit_upload_and_load(st)
        if df is not None:
            st.write(df.head())

    """
    uploaded = st.file_uploader(label, type="csv")

    if uploaded is None:
        return None

    # 'uploaded' é um ficheiro em memória (BytesIO-like),
    # que o load_era5_daily_from_gee já sabe tratar.
    df = load_era5_daily_from_gee(uploaded)
    return df


# ============================================================
# 7. Upload do CSV para o Google Drive
# ============================================================

def upload_file_to_google_drive(local_path: str,
                                file_name: Optional[str] = None,
                                folder_id: Optional[str] = None,
                                credentials_path: str = "credentials.json"
                                ) -> str:
    """
    Faz upload de um ficheiro local para o Google Drive, para uma pasta específica.

    NOTA IMPORTANTE:
      - Esta função só funciona quando correres o código no teu ambiente
        com as credenciais configuradas.
      - Requer:
          pip install google-api-python-client google-auth google-auth-httplib2

      - credentials_path: ficheiro JSON de Service Account OU OAuth,
        consoante a forma como configurares o acesso.
      - folder_id: ID da pasta 'era5' no teu Drive (tens de obter uma vez).

    Devolve:
      - file_id do ficheiro criado no Drive.
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    if file_name is None:
        file_name = os.path.basename(local_path)

    scopes = ["https://www.googleapis.com/auth/drive.file"]
    creds = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=scopes,
    )

    service = build("drive", "v3", credentials=creds)

    file_metadata = {"name": file_name}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaFileUpload(local_path, resumable=True)

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()

    return file.get("id")


# ============================================================
# 8. Exemplo de utilização em modo script
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Análise básica de ficheiro diário ERA5 exportado do GEE."
    )
    parser.add_argument("--csv", required=True, help="Caminho para o CSV ERA5 diário.")
    parser.add_argument("--frost-threshold", type=float, default=0.0,
                        help="Threshold de geada (Tmin < valor, em °C).")
    parser.add_argument("--rain-threshold", type=float, default=20.0,
                        help="Threshold de chuva intensa (mm/dia).")

    args = parser.parse_args()

    df = load_era5_daily_from_gee(args.csv)

    print("Colunas:", df.columns.tolist())
    print("\nPrimeiras linhas:")
    print(df.head())

    var_cols = detect_variable_columns(df)
    print("\nVariáveis climáticas detectadas:", var_cols)

    summary_df = summarize_daily_variables(df, var_cols)
    print("\nResumo estatístico:")
    print(summary_df)

    frost = frost_stats(df, threshold_C=args.frost_threshold)
    print("\nGeadas:")
    print(frost)

    heavy_rain = heavy_rain_events(
        df,
        threshold_mm=args.rain_threshold,
        min_consec_days=1
    )
    print("\nEventos de chuva intensa:")
    print(heavy_rain)


if __name__ == "__main__":
    main()
