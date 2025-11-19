# gee_client.py
import ee
import pandas as pd

# ---------------------------------------------------------
# INICIALIZAÇÃO DO GOOGLE EARTH ENGINE
# ---------------------------------------------------------
# NOTA:
# 1) Primeiro, numa consola Python, corre:
#       import ee
#       ee.Authenticate()
#    (ou 'earthengine authenticate' na linha de comandos)
# 2) Depois, aqui no módulo, basta fazer ee.Initialize()
# ---------------------------------------------------------

try:
    ee.Initialize()
except Exception as e:
    # Se der erro de auth, podes tratar aqui ou só deixar rebentar na app
    print("Falha ao inicializar o Earth Engine. Tens a autenticação feita?")
    print(e)


def get_era5_land_daily_point(lat, lon, start_date, end_date):
    """
    Devolve um DataFrame com série diária ERA5-Land para um ponto.
    Variáveis incluídas:
        - total_precipitation (soma diária)
        - temperature_2m (média diária)
        - wind_speed_10m (média diária)
    :param lat: latitude (float)
    :param lon: longitude (float)
    :param start_date: string "YYYY-MM-DD"
    :param end_date: string "YYYY-MM-DD"
    :return: pandas.DataFrame com colunas [date, total_precipitation, temperature_2m, wind_speed_10m]
    """

    # 1. Geometria do ponto
    point = ee.Geometry.Point([lon, lat])

    # 2. Colecção ERA5-Land horário
    base_col = ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY").filterDate(start_date, end_date)

    # Colecção para precipitação (vamos somar por dia)
    precip_col = base_col.select("total_precipitation")

    # Colecção para temperatura e vento (vamos fazer média diária)
    temp_wind_col = base_col.select(["temperature_2m", "wind_speed_10m"])

    # 3. Construir lista de dias
    start = ee.Date(start_date)
    end = ee.Date(end_date)
    n_days = end.difference(start, "day").int()
    days = ee.List.sequence(0, n_days.subtract(1))

    def daily_image(day):
        day = ee.Number(day)
        date = start.advance(day, "day")
        next_date = date.advance(1, "day")

        # Soma diária de precip
        daily_precip = precip_col.filterDate(date, next_date).sum()

        # Média diária de temperatura e vento
        daily_temp_wind = temp_wind_col.filterDate(date, next_date).mean()

        # Junta as bandas numa única imagem
        daily = (daily_precip
                 .addBands(daily_temp_wind)
                 .set("date", date.format("YYYY-MM-dd")))

        return daily

    daily_ic = ee.ImageCollection(days.map(daily_image))

    # 4. Extrair série temporal para o ponto
    def image_to_feature(img):
        img = ee.Image(img)
        values = img.reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=point,
            scale=11000,   # ~11 km, resolução típica ERA5-Land
            bestEffort=True,
        )
        return ee.Feature(None, values.set("date", img.get("date")))

    fc = daily_ic.map(image_to_feature)
    data = fc.getInfo()["features"]

    # 5. Converter para DataFrame
    records = []
    for f in data:
        p = f["properties"]
        records.append({
            "date": p["date"],
            "total_precipitation": p.get("total_precipitation"),
            "temperature_2m": p.get("temperature_2m"),
            "wind_speed_10m": p.get("wind_speed_10m"),
        })

    df = pd.DataFrame(records)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

    return df

