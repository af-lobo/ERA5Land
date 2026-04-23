"""
Módulo para gerar código Google Earth Engine (JavaScript)
para séries ERA5-Land diárias e/ou horárias por localização.

Autor: António + ChatGPT
"""

from typing import List, Dict


# ============================================================
# 1. Parsing das localizações
# ============================================================

def _parse_locations(text: str) -> List[Dict]:
    """
    Espera texto com linhas do tipo:
      Nome, lon, lat

    Exemplo:
      Dagoberto, -71.42160751, -35.71990245
    """
    locations = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            continue

        try:
            name = parts[0]
            lon = float(parts[1])
            lat = float(parts[2])

            locations.append({
                "name": name,
                "lon": lon,
                "lat": lat,
            })
        except Exception:
            continue

    return locations


# ============================================================
# 2. Geração do código GEE
# ============================================================

def build_gee_code_daily(
    start_year: int,
    end_year: int,
    start_month: int,
    start_day: int,
    end_month: int,
    end_day: int,
    locations_text: str,
    export_mode: str = "daily",
    timezone_str: str = "UTC",
) -> str:
    """
    Gera código JavaScript para o Google Earth Engine.

    Modos suportados:
      - daily
      - hourly
      - both

    Notas:
      - a timezone é única por pedido e vem do frontend;
      - o modo daily calcula a precipitação diária a partir de
        total_precipitation_hourly somada no dia local;
      - o modo hourly exporta precipitação horária com timestamps UTC e local.
    """

    locations = _parse_locations(locations_text)

    if not locations:
        return (
            "// ERRO: nenhuma localização válida encontrada.\n"
            "// Formato esperado por linha:\n"
            "//   Nome, lon, lat\n"
            "// Exemplo:\n"
            "//   Dagoberto, -71.42160751, -35.71990245"
        )

    export_mode = export_mode.lower().strip()
    if export_mode not in {"daily", "hourly", "both"}:
        export_mode = "daily"

    lines: List[str] = []

    # ---------------------------------------------------------
    # Cabeçalho
    # ---------------------------------------------------------
    lines.append("// -------------------------------------------------------------")
    lines.append("// ERA5-Land – Série diária e/ou horária por localização")
    lines.append("// Código gerado automaticamente pela app ERA5Land")
    lines.append("// -------------------------------------------------------------")
    lines.append("")

    lines.append(f"var startYear = {int(start_year)};")
    lines.append(f"var endYear   = {int(end_year)};")
    lines.append("")
    lines.append(f"var startMonth = {int(start_month)};")
    lines.append(f"var startDay   = {int(start_day)};")
    lines.append(f"var endMonth   = {int(end_month)};")
    lines.append(f"var endDay     = {int(end_day)};")
    lines.append("")
    lines.append(f"var exportMode = '{export_mode}';")
    lines.append(f"var tz = '{timezone_str}';")
    lines.append("")

    # ---------------------------------------------------------
    # Localizações
    # ---------------------------------------------------------
    lines.append("var locations = [")

    for i, loc in enumerate(locations):
        name = str(loc["name"]).replace("\\", "\\\\").replace("'", "\\'")
        line = f"  {{name: '{name}', lon: {loc['lon']}, lat: {loc['lat']}}}"
        if i < len(locations) - 1:
            line += ","
        lines.append(line)

    lines.append("];")
    lines.append("")

    # ---------------------------------------------------------
    # Corpo JS
    # ---------------------------------------------------------
    body = r"""
var sanitizeName = function(name) {
  return name.replace(/[^0-9a-zA-Z_]+/g, '_');
};

// DATASETS
var era5land = ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY');
var era5 = ee.ImageCollection('ECMWF/ERA5/HOURLY');

// ===== FUNÇÕES BÁSICAS =====

var computeDoy = function(month, day) {
  var d = ee.Date.fromYMD(2001, month, day);
  return d.getRelative('day', 'year').add(1);
};

var startDoy = computeDoy(startMonth, startDay);
var endDoy   = computeDoy(endMonth, endDay);
var wrapsYear = startDoy.gt(endDoy);

var isDayInSeason = function(dayLocal) {
  var doy = dayLocal.getRelative('day', 'year').add(1);
  return ee.Algorithms.If(
    wrapsYear,
    doy.gte(startDoy).or(doy.lte(endDoy)),
    doy.gte(startDoy).and(doy.lte(endDoy))
  );
};


// ============================================================
// DAILY (dia local)
// ============================================================

var makeDailySeries = function(point) {

  var startDateLocal = ee.Date.fromYMD(startYear, 1, 1, tz);
  var endDateLocalExclusive = ee.Date.fromYMD(endYear + 1, 1, 1, tz);

  var nDays = endDateLocalExclusive.difference(startDateLocal, 'day');
  var days = ee.List.sequence(0, nDays.subtract(1));

  var fc = ee.FeatureCollection(
    days.map(function(d) {
      d = ee.Number(d);

      var dayLocal = startDateLocal.advance(d, 'day');
      var nextLocal = dayLocal.advance(1, 'day');

      var inSeason = isDayInSeason(dayLocal);

      return ee.Algorithms.If(
        inSeason,
        (function() {

          var landDay = era5land.filterDate(dayLocal, nextLocal);
          var era5Day = era5.filterDate(dayLocal, nextLocal);

          var hasData = landDay.size().gt(0);

          return ee.Algorithms.If(
            hasData,
            (function() {

              // Precipitação diária correta: soma das horas do dia local
              var precipImg = landDay.select('total_precipitation_hourly')
                .sum()
                .rename('precip_hourly_sum');

              var tminImg = landDay.select('temperature_2m')
                .min()
                .rename('tmin_K');

              var tmaxImg = landDay.select('temperature_2m')
                .max()
                .rename('tmax_K');

              var tmeanImg = landDay.select('temperature_2m')
                .mean()
                .rename('tmean_K');

              var dewMeanImg = landDay.select('dewpoint_temperature_2m')
                .mean()
                .rename('dewmean_K');

              var soilImg = landDay.select('volumetric_soil_water_layer_1')
                .mean()
                .rename('soilw1');

              var radSumImg = landDay.select('surface_solar_radiation_downwards')
                .sum()
                .rename('rad_Jm2');

              var radMeanImg = landDay.select('surface_solar_radiation_downwards')
                .mean()
                .rename('rad_Jm2_per_h');

              var pevImg = landDay.select('potential_evaporation')
                .sum()
                .rename('pev_m');

              var uMeanImg = era5Day.select('u_component_of_wind_10m')
                .mean()
                .rename('u10');

              var vMeanImg = era5Day.select('v_component_of_wind_10m')
                .mean()
                .rename('v10');

              var gustMaxImg = era5Day.select('instantaneous_10m_wind_gust')
                .max()
                .rename('gust10');

              var aggImg = ee.Image.cat([
                precipImg,
                tminImg, tmaxImg, tmeanImg, dewMeanImg,
                soilImg,
                radSumImg, radMeanImg,
                pevImg,
                uMeanImg, vMeanImg, gustMaxImg
              ]);

              var vals = aggImg.reduceRegion({
                reducer: ee.Reducer.mean(),
                geometry: point,
                scale: 11100,
                bestEffort: true
              });

              var valid = vals.size().gt(0);

              return ee.Algorithms.If(
                valid,
                (function() {

                  var u = ee.Number(vals.get('u10'));
                  var v = ee.Number(vals.get('v10'));
                  var windMean = u.pow(2).add(v.pow(2)).sqrt();

                  return ee.Feature(null, {
                    'timezone': tz,
                    'date_local': dayLocal.format('YYYY-MM-dd', tz),
                    'precip_mm': ee.Number(vals.get('precip_hourly_sum')).multiply(1000),
                    'tmin_C': ee.Number(vals.get('tmin_K')).subtract(273.15),
                    'tmax_C': ee.Number(vals.get('tmax_K')).subtract(273.15),
                    'tmean_C': ee.Number(vals.get('tmean_K')).subtract(273.15),
                    'dew2m_mean_C': ee.Number(vals.get('dewmean_K')).subtract(273.15),
                    'soilw1_mean': vals.get('soilw1'),
                    'rad_Jm2_day': vals.get('rad_Jm2'),
                    'rad_Wm2_mean': ee.Number(vals.get('rad_Jm2_per_h')).divide(3600),
                    'pev_mm_day': ee.Number(vals.get('pev_m')).multiply(1000),
                    'wind_mean_ms': windMean,
                    'gust_max_ms': ee.Number(vals.get('gust10'))
                  });

                })(),
                null
              );

            })(),
            null
          );

        })(),
        null
      );
    })
  );

  return fc.filter(ee.Filter.notNull(['precip_mm']));
};


// ============================================================
// HOURLY (UTC + local)
// ============================================================

var makeHourlySeries = function(point) {

  var startDateLocal = ee.Date.fromYMD(startYear, startMonth, startDay, tz);
  var endDateLocalExclusive = ee.Date.fromYMD(endYear, endMonth, endDay, tz)
    .advance(1, 'day');

  var hourly = era5land
    .filterDate(startDateLocal, endDateLocalExclusive)
    .select('total_precipitation_hourly');

  var fc = ee.FeatureCollection(
    hourly.map(function(img) {

      var vals = img.reduceRegion({
        reducer: ee.Reducer.mean(),
        geometry: point,
        scale: 11100,
        bestEffort: true
      });

      var hasVal = vals.contains('total_precipitation_hourly');
      var dt = img.date();

      return ee.Feature(null, {
        'timezone': tz,
        'datetime_utc': dt.format('YYYY-MM-dd HH:mm:ss', 'UTC'),
        'datetime_local': dt.format('YYYY-MM-dd HH:mm:ss', tz),
        'date_local': dt.format('YYYY-MM-dd', tz),
        'hour_local': ee.Number.parse(dt.format('H', tz)),
        'precip_mm': ee.Algorithms.If(
          hasVal,
          ee.Number(vals.get('total_precipitation_hourly')).multiply(1000),
          null
        )
      });

    })
  );

  return fc.filter(ee.Filter.notNull(['precip_mm']));
};


// ============================================================
// EXPORT
// ============================================================

locations.forEach(function(loc) {

  var point = ee.Geometry.Point([loc.lon, loc.lat]);

  if (exportMode === 'daily' || exportMode === 'both') {
    var daily = makeDailySeries(point);

    Export.table.toDrive({
      collection: daily,
      description: 'ERA5_daily_' + sanitizeName(loc.name),
      fileFormat: 'CSV'
    });
  }

  if (exportMode === 'hourly' || exportMode === 'both') {
    var hourly = makeHourlySeries(point);

    Export.table.toDrive({
      collection: hourly,
      description: 'ERA5_hourly_' + sanitizeName(loc.name),
      fileFormat: 'CSV'
    });
  }

});
"""
    lines.append(body)

    return "\n".join(lines)
