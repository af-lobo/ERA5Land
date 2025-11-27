import re
import datetime as dt

def build_gee_code_daily(
    start_year: int,
    end_year: int,
    start_month: int,
    start_day: int,
    end_month: int,
    end_day: int,
    locations_text: str,
) -> str:
    """
    Gera código JavaScript para o GEE em MODO DIÁRIO:
    - ERA5-Land: precipitação, temp min/max/média, orvalho, solo, radiação, evapotranspiração
    - ERA5: vento médio 10m + rajada máxima diária
    - Exporta um CSV por localização
    """

    # Parse das localizações
    locations = []
    for line in locations_text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            continue
        name, lon_str, lat_str = parts
        try:
            lon = float(lon_str.replace(",", "."))
            lat = float(lat_str.replace(",", "."))
        except ValueError:
            continue
        safe = re.sub(r"[^0-9a-zA-Z_]+", "_", name.strip())
        if not safe:
            safe = "loc"
        locations.append({"name": name.strip(), "safe": safe, "lon": lon, "lat": lat})

    if not locations:
        return "// ERRO: nenhuma localização válida. Formato: Nome, lon, lat"

    # Converter lista de dicionários para lista JS
    loc_js = ",\n".join(
        [f"  {{name: '{loc['safe']}', lon: {loc['lon']}, lat: {loc['lat']}}}" for loc in locations]
    )

    # Construir o script JS
    js = f"""
// -------------------------------------------------------------
// ERA5-Land + ERA5 – Séries DIÁRIAS por localização
// -------------------------------------------------------------

var startYear = {start_year};
var endYear   = {end_year};

var startMonth = {start_month};
var startDay   = {start_day};
var endMonth   = {end_month};
var endDay     = {end_day};

var locations = [
{loc_js}
];

// ===== FUNÇÕES =====

var computeDoy = function(month, day) {{
  var d = ee.Date.fromYMD(2001, month, day);
  return d.getRelative('day', 'year').add(1);
}};

var startDoy = computeDoy(startMonth, startDay);
var endDoy   = computeDoy(endMonth, endDay);
var wrapsYear = startDoy.gt(endDoy);

var sanitizeName = function(name) {{
  return name.replace(/[^0-9a-zA-Z_]+/g, '_');
}};

// ===== DATASETS =====

var era5land = ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY')
  .filter(ee.Filter.calendarRange(startYear, endYear, 'year'));

var era5 = ee.ImageCollection('ECMWF/ERA5/HOURLY')
  .filter(ee.Filter.calendarRange(startYear, endYear, 'year'));

var filterSeasonal = function(ic) {{
  if (wrapsYear) {{
    var part1 = ic.filter(ee.Filter.dayOfYear(startDoy, 366));
    var part2 = ic.filter(ee.Filter.dayOfYear(1, endDoy));
    return part1.merge(part2);
  }} else {{
    return ic.filter(ee.Filter.dayOfYear(startDoy, endDoy));
  }}
}};

var seaLand = filterSeasonal(era5land);
var seaEra5 = filterSeasonal(era5);

// ===== AGREGAR DIARIAMENTE =====

var makeDailySeries = function(point) {{

  var startDate = ee.Date.fromYMD(startYear, 1, 1);
  var endDate   = ee.Date.fromYMD(endYear, 12, 31);
  var nDays     = endDate.difference(startDate, 'day');

  var days = ee.List.sequence(0, nDays.subtract(1));

  var fc = ee.FeatureCollection(days.map(function(d) {{
    d = ee.Number(d);
    var day  = startDate.advance(d, 'day');
    var next = day.advance(1, 'day');

    var landDay = seaLand.filterDate(day, next);
    var era5Day = seaEra5.filterDate(day, next);

    var hasData = landDay.size().gt(0);

    return ee.Algorithms.If(
      hasData,
      (function() {{

        // ===== ERA5-Land =====

        var precip_m = landDay.select('total_precipitation').sum();
        var tmin_K   = landDay.select('temperature_2m').min();
        var tmax_K   = landDay.select('temperature_2m').max();
        var tmean_K  = landDay.select('temperature_2m').mean();
        var dew_K    = landDay.select('dewpoint_temperature_2m').mean();
        var soil     = landDay.select('volumetric_soil_water_layer_1').mean();
        var rad_J    = landDay.select('surface_solar_radiation_downwards').sum();
        var rad_Wm2  = landDay.select('surface_solar_radiation_downwards').mean();
        var pev_m    = landDay.select('potential_evaporation').sum();

        // ===== ERA5 (vento + rajada) =====

        var u_mean = era5Day.select('u_component_of_wind_10m').mean();
        var v_mean = era5Day.select('v_component_of_wind_10m').mean();
        var gust   = era5Day.select('instantaneous_10m_wind_gust').max();

        return ee.Feature(null, {{
          'date': day.format('YYYY-MM-dd'),
          'precip_mm': precip_m.multiply(1000),
          'tmin_C': tmin_K.subtract(273.15),
          'tmax_C': tmax_K.subtract(273.15),
          'tmean_C': tmean_K.subtract(273.15),
          'dew2m_mean_C': dew_K.subtract(273.15),
          'soilw1_mean': soil,
          'rad_Jm2_day': rad_J,
          'rad_Wm2_mean': rad_Wm2.divide(3600),
          'pev_mm_day': pev_m.multiply(1000),
          'wind_mean_ms': u_mean.pow(2).add(v_mean.pow(2)).sqrt(),
          'gust_max_ms': gust
        }});

      }})(),
      null
    );
  }}));

  return fc.filter(ee.Filter.notNull(['precip_mm']));
}};

// ===== EXPORTAR =====

locations.forEach(function(loc) {{
  var point = ee.Geometry.Point([loc.lon, loc.lat]);
  var daily = makeDailySeries(point);

  Export.table.toDrive({{
    collection: daily,
    description: 'ERA5_diario_' + sanitizeName(loc.name) +
                 '_{start_year}_{end_year}',
    fileFormat: 'CSV'
  }});
}});
"""

    return js
