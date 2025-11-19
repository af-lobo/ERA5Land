import ee
import pandas as pd
from datetime import datetime

# Inicializar (podes mover isto para o arranque da app)
ee.Initialize()

def get_era5_land_daily_point(lat, lon, start_date, end_date):
    # 1. Geometria do ponto
    point = ee.Geometry.Point([lon, lat])

    # 2. Colecção ERA5-Land horário
    col = (ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
           .filterDate(start_date, end_date)
           .select(["total_precipitation", "temperature_2m", "wind_speed_10m"]))

    # 3. Construir lista de dias
    start = ee.Date(start_date)
    end = ee.Date(end_date)
    n_days = end.difference(start, "day").int()
    days = ee.List.sequence(0, n_days.subtract(1))

    def daily_image(day):
        day = ee.Number(day)
        date = start.advance(day, "day")
        next_date = date.advance(1, "day")

        daily = (col
                 .filterDate(date, next_date)
                 .sum()  # soma precip; para temp poderias usar .mean() numa colecção separada
                 .set("date", date.format("YYYY-MM-dd")))

        return daily

    daily_ic = ee.ImageCollection(days.map(daily_image))

    # 4. Extrair série temporal para o ponto
    def image_to_feature(img):
        img = ee.Image(img)
        values = img.reduceRegion(
            reducer=ee.Reducer.first(),  # temos só uma imagem por dia já agregada
            geometry=point,
            scale=10000,
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
    df["date"] = pd.to_datetime(df["date"])
    return df

# Exemplo de uso:
# df = get_era5_land_daily_point(lat=-31.5, lon=-71.2, start_date="2000-01-01", end_date="2000-01-10")
