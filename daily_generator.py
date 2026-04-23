"""
Módulo para gerar código Google Earth Engine (JavaScript)
para séries ERA5-Land diárias e/ou horárias por localização.

Autor: António + ChatGPT
"""

from typing import List, Dict


SUPPORTED_VARIABLES = {
    "total_precipitation_hourly",
    "temperature_2m",
    "dewpoint_temperature_2m",
    "volumetric_soil_water_layer_1",
    "surface_solar_radiation_downwards_hourly",
    "potential_evaporation_hourly",
    "runoff_hourly",
    "u_component_of_wind_10m",
    "v_component_of_wind_10m",
    "instantaneous_10m_wind_gust",
}


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
                "lat": lat,
            })
        except Exception:
            continue

    return locations


def _normalize_selected_variables(selected_variables: List[str] | None) -> List[str]:
    if not selected_variables:
        return sorted(SUPPORTED_VARIABLES)

    cleaned = [v for v in selected_variables if v in SUPPORTED_VARIABLES]
    if not cleaned:
        return sorted(SUPPORTED_VARIABLES)

    # preserva ordem de entrada sem duplicados
    seen = set()
    out = []
    for v in cleaned:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


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
    selected_variables: List[str] | None = None,
) -> str:
    """
    Gera código JavaScript para o Google Earth Engine.

    Modos suportados:
      - daily
      - hourly
      - both

    selected_variables:
      lista de bandas/variáveis suportadas a exportar.
    """

    locations = _parse_locations(locations_text)
    selected_variables = _normalize_selected_variables(selected_variables)

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

    has_precip = "total_precipitation_hourly" in selected_variables
    has_temp = "temperature_2m" in selected_variables
    has_dew = "dewpoint_temperature_2m" in selected_variables
    has_soil = "volumetric_soil_water_layer_1" in selected_variables
    has_rad = "surface_solar_radiation_downwards_hourly" in selected_variables
    has_pev = "potential_evaporation_hourly" in selected_variables
    has_runoff = "runoff_hourly" in selected_variables
    has_u = "u_component_of_wind_10m" in selected_variables
    has_v = "v_component_of_wind_10m" in selected_variables
    has_gust = "instantaneous_10m_wind_gust" in selected_variables

    lines: List[str] = []

    lines.append("// -------------------------------------------------------------")
    lines.append("// ERA5-Land / ERA5 – Série diária e/ou horária por localização")
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

    lines.append("var locations = [")
    for i, loc in enumerate(locations):
        name = str(loc["name"]).replace("\\", "\\\\").replace("'", "\\'")
        line = f"  {{name: '{name}', lon: {loc['lon']}, lat: {loc['lat']}}}"
        if i < len(locations) - 1:
            line += ","
        lines.append(line)
    lines.append("];")
    lines.append("")

    pad_start_month = f"{int(start_month):02d}"
    pad_start_day = f"{int(start_day):02d}"
    pad_end_month = f"{int(end_month):02d}"
    pad_end_day = f"{int(end_day):02d}"

    # -------- DAILY snippets --------
    daily_agg_lines: List[str] = []
    daily_cat_items: List[str] = []
    daily_feature_lines: List[str] = []

    if has_precip:
        daily_agg_lines += [
            "              var precipImg = landDay.select('total_precipitation_hourly')",
            "                .sum()",
            "                .rename('precip_hourly_sum');",
            "",
        ]
        daily_cat_items.append("precipImg")
        daily_feature_lines.append(
            "                    'precip_mm': ee.Number(vals.get('precip_hourly_sum')).multiply(1000),"
        )

    if has_temp:
        daily_agg_lines += [
            "              var tminImg = landDay.select('temperature_2m')",
            "                .min()",
            "                .rename('tmin_K');",
            "",
            "              var tmaxImg = landDay.select('temperature_2m')",
            "                .max()",
            "                .rename('tmax_K');",
            "",
            "              var tmeanImg = landDay.select('temperature_2m')",
            "                .mean()",
            "                .rename('tmean_K');",
            "",
        ]
        daily_cat_items += ["tminImg", "tmaxImg", "tmeanImg"]
        daily_feature_lines += [
            "                    'tmin_C': ee.Number(vals.get('tmin_K')).subtract(273.15),",
            "                    'tmax_C': ee.Number(vals.get('tmax_K')).subtract(273.15),",
            "                    'tmean_C': ee.Number(vals.get('tmean_K')).subtract(273.15),",
        ]

    if has_dew:
        daily_agg_lines += [
            "              var dewMeanImg = landDay.select('dewpoint_temperature_2m')",
            "                .mean()",
            "                .rename('dewmean_K');",
            "",
        ]
        daily_cat_items.append("dewMeanImg")
        daily_feature_lines.append(
            "                    'dew2m_mean_C': ee.Number(vals.get('dewmean_K')).subtract(273.15),"
        )

    if has_soil:
        daily_agg_lines += [
            "              var soilImg = landDay.select('volumetric_soil_water_layer_1')",
            "                .mean()",
            "                .rename('soilw1');",
            "",
        ]
        daily_cat_items.append("soilImg")
        daily_feature_lines.append(
            "                    'soilw1_mean': vals.get('soilw1'),"
        )

    if has_rad:
        daily_agg_lines += [
            "              var radSumImg = landDay.select('surface_solar_radiation_downwards_hourly')",
            "                .sum()",
            "                .rename('rad_Jm2');",
            "",
            "              var radMeanImg = landDay.select('surface_solar_radiation_downwards_hourly')",
            "                .mean()",
            "                .rename('rad_Jm2_per_h');",
            "",
        ]
        daily_cat_items += ["radSumImg", "radMeanImg"]
        daily_feature_lines += [
            "                    'rad_Jm2_day': vals.get('rad_Jm2'),",
            "                    'rad_Wm2_mean': ee.Number(vals.get('rad_Jm2_per_h')).divide(3600),",
        ]

    if has_pev:
        daily_agg_lines += [
            "              var pevImg = landDay.select('potential_evaporation_hourly')",
            "                .sum()",
            "                .rename('pev_m');",
            "",
        ]
        daily_cat_items.append("pevImg")
        daily_feature_lines.append(
            "                    'pev_mm_day': ee.Number(vals.get('pev_m')).multiply(1000),"
        )

    if has_runoff:
        daily_agg_lines += [
            "              var runoffImg = landDay.select('runoff_hourly')",
            "                .sum()",
            "                .rename('runoff_m');",
            "",
        ]
        daily_cat_items.append("runoffImg")
        daily_feature_lines.append(
            "                    'runoff_mm_day': ee.Number(vals.get('runoff_m')).multiply(1000),"
        )

    if has_u:
        daily_agg_lines += [
            "              var uMeanImg = era5Day.select('u_component_of_wind_10m')",
            "                .mean()",
            "                .rename('u10');",
            "",
        ]
        daily_cat_items.append("uMeanImg")
        daily_feature_lines.append(
            "                    'u10_mean_ms': ee.Number(vals.get('u10')),"
        )

    if has_v:
        daily_agg_lines += [
            "              var vMeanImg = era5Day.select('v_component_of_wind_10m')",
            "                .mean()",
            "                .rename('v10');",
            "",
        ]
        daily_cat_items.append("vMeanImg")
        daily_feature_lines.append(
            "                    'v10_mean_ms': ee.Number(vals.get('v10')),"
        )

    if has_u and has_v:
        daily_feature_lines.append(
            "                    'wind_mean_ms': ee.Number(vals.get('u10')).pow(2).add(ee.Number(vals.get('v10')).pow(2)).sqrt(),"
        )

    if has_gust:
        daily_agg_lines += [
            "              var gustMaxImg = era5Day.select('instantaneous_10m_wind_gust')",
            "                .max()",
            "                .rename('gust10');",
            "",
        ]
        daily_cat_items.append("gustMaxImg")
        daily_feature_lines.append(
            "                    'gust_max_ms': ee.Number(vals.get('gust10')),"
        )

    # -------- HOURLY snippets --------
    hourly_piece_lines: List[str] = []
    hourly_cat_items: List[str] = []
    hourly_feature_lines: List[str] = []

    if has_precip:
        hourly_piece_lines += [
            "            var precipImg = landImg.select('total_precipitation_hourly')",
            "              .rename('precip_h');",
            "",
        ]
        hourly_cat_items.append("precipImg")
        hourly_feature_lines.append(
            "              'precip_mm': ee.Number(vals.get('precip_h')).multiply(1000),"
        )

    if has_temp:
        hourly_piece_lines += [
            "            var tempImg = landImg.select('temperature_2m')",
            "              .rename('temp_K');",
            "",
        ]
        hourly_cat_items.append("tempImg")
        hourly_feature_lines.append(
            "              'temp_C': ee.Number(vals.get('temp_K')).subtract(273.15),"
        )

    if has_dew:
        hourly_piece_lines += [
            "            var dewImg = landImg.select('dewpoint_temperature_2m')",
            "              .rename('dew_K');",
            "",
        ]
        hourly_cat_items.append("dewImg")
        hourly_feature_lines.append(
            "              'dew2m_C': ee.Number(vals.get('dew_K')).subtract(273.15),"
        )

    if has_soil:
        hourly_piece_lines += [
            "            var soilImg = landImg.select('volumetric_soil_water_layer_1')",
            "              .rename('soilw1');",
            "",
        ]
        hourly_cat_items.append("soilImg")
        hourly_feature_lines.append(
            "              'soilw1': vals.get('soilw1'),"
        )

    if has_rad:
        hourly_piece_lines += [
            "            var radImg = landImg.select('surface_solar_radiation_downwards_hourly')",
            "              .rename('rad_Jm2_h');",
            "",
        ]
        hourly_cat_items.append("radImg")
        hourly_feature_lines.append(
            "              'rad_Wm2': ee.Number(vals.get('rad_Jm2_h')).divide(3600),"
        )

    if has_pev:
        hourly_piece_lines += [
            "            var pevImg = landImg.select('potential_evaporation_hourly')",
            "              .rename('pev_m_h');",
            "",
        ]
        hourly_cat_items.append("pevImg")
        hourly_feature_lines.append(
            "              'pev_mm': ee.Number(vals.get('pev_m_h')).multiply(1000),"
        )

    if has_runoff:
        hourly_piece_lines += [
            "            var runoffImg = landImg.select('runoff_hourly')",
            "              .rename('runoff_m_h');",
            "",
        ]
        hourly_cat_items.append("runoffImg")
        hourly_feature_lines.append(
            "              'runoff_mm': ee.Number(vals.get('runoff_m_h')).multiply(1000),"
        )

    if has_u:
        hourly_piece_lines += [
            "            var uImg = eraImg.select('u_component_of_wind_10m')",
            "              .rename('u10');",
            "",
        ]
        hourly_cat_items.append("uImg")
        hourly_feature_lines.append(
            "              'u10_ms': ee.Number(vals.get('u10')),"
        )

    if has_v:
        hourly_piece_lines += [
            "            var vImg = eraImg.select('v_component_of_wind_10m')",
            "              .rename('v10');",
            "",
        ]
        hourly_cat_items.append("vImg")
        hourly_feature_lines.append(
            "              'v10_ms': ee.Number(vals.get('v10')),"
        )

    if has_u and has_v:
        hourly_feature_lines.append(
            "              'wind10m_ms': ee.Number(vals.get('u10')).pow(2).add(ee.Number(vals.get('v10')).pow(2)).sqrt(),"
        )

    if has_gust:
        hourly_piece_lines += [
            "            var gustImg = eraImg.select('instantaneous_10m_wind_gust')",
            "              .rename('gust10');",
            "",
        ]
        hourly_cat_items.append("gustImg")
        hourly_feature_lines.append(
            "              'gust10_ms': ee.Number(vals.get('gust10')),"
        )

    if not daily_cat_items and not hourly_cat_items:
        return "// ERRO: nenhuma variável válida foi selecionada."

    daily_cat = ", ".join(daily_cat_items) if daily_cat_items else ""
    hourly_cat = ", ".join(hourly_cat_items) if hourly_cat_items else ""

    def _trim_last_comma(lines_list: List[str]) -> List[str]:
        if not lines_list:
            return lines_list
        lines_copy = lines_list[:]
        last = lines_copy[-1]
        if last.rstrip().endswith(","):
            lines_copy[-1] = last.rstrip()[:-1]
        return lines_copy

    daily_feature_lines = _trim_last_comma(daily_feature_lines)
    hourly_feature_lines = _trim_last_comma(hourly_feature_lines)

    body_lines: List[str] = [
        "var sanitizeName = function(name) {",
        "  return name.replace(/[^0-9a-zA-Z_]+/g, '_');",
        "};",
        "",
        "var pad2 = function(n) {",
        "  return (n < 10 ? '0' : '') + n;",
        "};",
        "",
        "var fileSuffix = ''",
        f"  + startYear + '_' + endYear",
        f"  + '_' + pad2(startMonth) + '_' + pad2(startDay)",
        f"  + '_' + pad2(endMonth) + '_' + pad2(endDay);",
        "",
        "var era5land = ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY')",
        "  .filter(ee.Filter.calendarRange(startYear, endYear, 'year'));",
        "",
        "var era5 = ee.ImageCollection('ECMWF/ERA5/HOURLY')",
        "  .filter(ee.Filter.calendarRange(startYear, endYear, 'year'));",
        "",
        "var computeDoy = function(month, day) {",
        "  var d = ee.Date.fromYMD(2001, month, day);",
        "  return d.getRelative('day', 'year').add(1);",
        "};",
        "",
        "var startDoy = computeDoy(startMonth, startDay);",
        "var endDoy   = computeDoy(endMonth, endDay);",
        "var wrapsYear = startDoy.gt(endDoy);",
        "",
        "var isDayInSeason = function(dayLocal) {",
        "  var doy = dayLocal.getRelative('day', 'year').add(1);",
        "  return ee.Algorithms.If(",
        "    wrapsYear,",
        "    doy.gte(startDoy).or(doy.lte(endDoy)),",
        "    doy.gte(startDoy).and(doy.lte(endDoy))",
        "  );",
        "};",
        "",
    ]

    # DAILY section
    if daily_cat_items:
        body_lines += [
            "// ============================================================",
            "// DAILY (dia local)",
            "// ============================================================",
            "",
            "var makeDailySeries = function(point) {",
            "",
            "  var startDateLocal = ee.Date.fromYMD(startYear, 1, 1, tz);",
            "  var endDateLocalExclusive = ee.Date.fromYMD(endYear + 1, 1, 1, tz);",
            "",
            "  var nDays = endDateLocalExclusive.difference(startDateLocal, 'day');",
            "  var days = ee.List.sequence(0, nDays.subtract(1));",
            "",
            "  var fc = ee.FeatureCollection(",
            "    days.map(function(d) {",
            "      d = ee.Number(d);",
            "",
            "      var dayLocal = startDateLocal.advance(d, 'day');",
            "      var nextLocal = dayLocal.advance(1, 'day');",
            "",
            "      var inSeason = isDayInSeason(dayLocal);",
            "",
            "      return ee.Algorithms.If(",
            "        inSeason,",
            "        (function() {",
            "",
            "          var landDay = era5land.filterDate(dayLocal, nextLocal);",
            "          var era5Day = era5.filterDate(dayLocal, nextLocal);",
            "",
            "          var hasData = landDay.size().gt(0);",
            "",
            "          return ee.Algorithms.If(",
            "            hasData,",
            "            (function() {",
            "",
        ]
        body_lines += daily_agg_lines
        body_lines += [
            f"              var aggImg = ee.Image.cat([{daily_cat}]);",
            "",
            "              var vals = aggImg.reduceRegion({",
            "                reducer: ee.Reducer.mean(),",
            "                geometry: point,",
            "                scale: 11100,",
            "                bestEffort: true",
            "              });",
            "",
            "              var valid = vals.size().gt(0);",
            "",
            "              return ee.Algorithms.If(",
            "                valid,",
            "                ee.Feature(null, {",
            "                  'timezone': tz,",
            "                  'date_local': dayLocal.format('YYYY-MM-dd', tz),",
        ]
        body_lines += daily_feature_lines
        body_lines += [
            "                }),",
            "                null",
            "              );",
            "",
            "            })(),",
            "            null",
            "          );",
            "",
            "        })(),",
            "        null",
            "      );",
            "    })",
            "  );",
            "",
            "  return fc;",
            "};",
            "",
        ]

    # HOURLY section
    if hourly_cat_items:
        body_lines += [
            "// ============================================================",
            "// HOURLY (UTC + local)",
            "// ============================================================",
            "",
            "var makeHourlySeries = function(point) {",
            "",
            "  var startDateLocal = ee.Date.fromYMD(startYear, 1, 1, tz);",
            "  var endDateLocalExclusive = ee.Date.fromYMD(endYear + 1, 1, 1, tz);",
            "",
            "  var nDays = endDateLocalExclusive.difference(startDateLocal, 'day');",
            "  var days = ee.List.sequence(0, nDays.subtract(1));",
            "",
            "  var byDay = days.map(function(d) {",
            "    d = ee.Number(d);",
            "",
            "    var dayLocal = startDateLocal.advance(d, 'day');",
            "    var nextLocal = dayLocal.advance(1, 'day');",
            "",
            "    var inSeason = isDayInSeason(dayLocal);",
            "",
            "    return ee.Algorithms.If(",
            "      inSeason,",
            "      ee.FeatureCollection(",
            "        era5land.filterDate(dayLocal, nextLocal).map(function(img) {",
            "",
            "          var dt = img.date();",
            "          var landImg = ee.Image(era5land.filterDate(dt, dt.advance(1, 'hour')).first());",
            "          var eraImg = ee.Image(era5.filterDate(dt, dt.advance(1, 'hour')).first());",
            "",
        ]
        body_lines += hourly_piece_lines
        body_lines += [
            f"          var aggImg = ee.Image.cat([{hourly_cat}]);",
            "",
            "          var vals = aggImg.reduceRegion({",
            "            reducer: ee.Reducer.mean(),",
            "            geometry: point,",
            "            scale: 11100,",
            "            bestEffort: true",
            "          });",
            "",
            "          return ee.Feature(null, {",
            "            'timezone': tz,",
            "            'datetime_utc': dt.format('YYYY-MM-dd HH:mm:ss', 'UTC'),",
            "            'datetime_local': dt.format('YYYY-MM-dd HH:mm:ss', tz),",
            "            'date_local': dt.format('YYYY-MM-dd', tz),",
            "            'hour_local': ee.Number.parse(dt.format('H', tz)),",
        ]
        body_lines += hourly_feature_lines
        body_lines += [
            "          });",
            "",
            "        })",
            "      ),",
            "      ee.FeatureCollection([])",
            "    );",
            "  });",
            "",
            "  return ee.FeatureCollection(byDay).flatten();",
            "};",
            "",
        ]

    body_lines += [
        "// ============================================================",
        "// EXPORT",
        "// ============================================================",
        "",
        "locations.forEach(function(loc) {",
        "",
        "  var point = ee.Geometry.Point([loc.lon, loc.lat]);",
        "",
    ]

    if daily_cat_items:
        body_lines += [
            "  if (exportMode === 'daily' || exportMode === 'both') {",
            "    var daily = makeDailySeries(point);",
            "    Export.table.toDrive({",
            "      collection: daily,",
            "      description: 'ERA5_daily_' + sanitizeName(loc.name) + '_' + fileSuffix,",
            "      fileFormat: 'CSV'",
            "    });",
            "  }",
            "",
        ]

    if hourly_cat_items:
        body_lines += [
            "  if (exportMode === 'hourly' || exportMode === 'both') {",
            "    var hourly = makeHourlySeries(point);",
            "    Export.table.toDrive({",
            "      collection: hourly,",
            "      description: 'ERA5_hourly_' + sanitizeName(loc.name) + '_' + fileSuffix,",
            "      fileFormat: 'CSV'",
            "    });",
            "  }",
            "",
        ]

    body_lines += [
        "});",
    ]

    lines.extend(body_lines)
    return "\n".join(lines)
