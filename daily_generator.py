"""
Módulo para gerar código Google Earth Engine (JavaScript)
para séries ERA5-Land (diárias e/ou horárias).

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
                "lat": lat
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
    timezone_str: str = "America/Santiago",
) -> str:

    locations = _parse_locations(locations_text)

    if not locations:
        return "// ERRO: nenhuma localização válida."

    export_mode = export_mode.lower().strip()
    if export_mode not in {"daily", "hourly", "both"}:
        export_mode = "daily"

    lines: List[str] = []

    # ---------------------------------------------------------
    # Cabeçalho
    # ---------------------------------------------------------
    lines.append("// -------------------------------------------------------------")
    lines.append("// ERA5-Land – Série diária e/ou horária")
    lines.append("// Código gerado automaticamente")
    lines.append("// -------------------------------------------------------------")
    lines.append("")

    lines.append(f"var startYear = {start_year};")
    lines.append(f"var endYear   = {end_year};")
    lines.append("")
    lines.append(f"var startMonth = {start_month};")
    lines.append(f"var startDay   = {start_day};")
    lines.append(f"var endMonth   = {end_month};")
    lines.append(f"var endDay     = {end_day};")
    lines.append("")
    lines.append(f"var exportMode = '{export_mode}';")
    lines.append(f"var tz = '{timezone_str}';")
    lines.append("")

    # ---------------------------------------------------------
    # Localizações
    # ---------------------------------------------------------
    lines.append("var locations = [")

    for i, loc in enumerate(locations):
        line = f"  {{name: '{loc['name']}', lon: {loc['lon']}, lat: {loc['lat']}}}"
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

// DATASET
var era5land = ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY');


// ============================================================
// DAILY (CORRIGIDO)
// ============================================================

var makeDailySeries = function(point) {

  var startDateLocal = ee.Date.fromYMD(startYear, 1, 1, tz);
  var endDateLocal = ee.Date.fromYMD(endYear + 1, 1, 1, tz);

  var nDays = endDateLocal.difference(startDateLocal, 'day');

  var days = ee.List.sequence(0, nDays.subtract(1));

  var fc = ee.FeatureCollection(
    days.map(function(d) {

      var dayLocal = startDateLocal.advance(d, 'day');
      var nextLocal = dayLocal.advance(1, 'day');

      var landDay = era5land.filterDate(dayLocal, nextLocal);

      var hasData = landDay.size().gt(0);

      return ee.Algorithms.If(
        hasData,
        (function() {

          // PRECIPITAÇÃO CORRETA (soma horária)
          var precipImg = landDay.select('total_precipitation_hourly')
            .sum();

          var tmin = landDay.select('temperature_2m').min();
          var tmax = landDay.select('temperature_2m').max();
          var tmean = landDay.select('temperature_2m').mean();

          var agg = ee.Image.cat([precipImg, tmin, tmax, tmean]);

          var vals = agg.reduceRegion({
            reducer: ee.Reducer.mean(),
            geometry: point,
            scale: 11100,
            bestEffort: true
          });

          return ee.Feature(null, {
            'date_local': dayLocal.format('YYYY-MM-dd', tz),
            'precip_mm': ee.Number(vals.get('total_precipitation_hourly')).multiply(1000),
            'tmin_C': ee.Number(vals.get('temperature_2m_min')).subtract(273.15),
            'tmax_C': ee.Number(vals.get('temperature_2m_max')).subtract(273.15),
            'tmean_C': ee.Number(vals.get('temperature_2m_mean')).subtract(273.15)
          });

        })(),
        null
      );

    })
  );

  return fc.filter(ee.Filter.notNull(['precip_mm']));
};


// ============================================================
// HOURLY
// ============================================================

var makeHourlySeries = function(point) {

  var startDate = ee.Date.fromYMD(startYear, startMonth, startDay, tz);
  var endDate = ee.Date.fromYMD(endYear, endMonth, endDay, tz).advance(1, 'day');

  var hourly = era5land
    .filterDate(startDate, endDate)
    .select('total_precipitation_hourly');

  var fc = ee.FeatureCollection(
    hourly.map(function(img) {

      var vals = img.reduceRegion({
        reducer: ee.Reducer.mean(),
        geometry: point,
        scale: 11100,
        bestEffort: true
      });

      var dt = img.date();

      return ee.Feature(null, {
        'datetime_utc': dt.format('YYYY-MM-dd HH:mm:ss', 'UTC'),
        'datetime_local': dt.format('YYYY-MM-dd HH:mm:ss', tz),
        'date_local': dt.format('YYYY-MM-dd', tz),
        'hour_local': ee.Number.parse(dt.format('H', tz)),
        'precip_mm': ee.Number(vals.get('total_precipitation_hourly')).multiply(1000)
      });

    })
  );

  return fc;
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
