"""
Gera código JavaScript para o Google Earth Engine (ERA5-Land + ERA5)
com séries diárias para uma ou várias localizações.

Função principal a usar na app Streamlit:

    build_gee_code_daily(
        start_year: int,
        end_year: int,
        start_month: int,
        start_day: int,
        end_month: int,
        end_day: int,
        locations_text: str,   # "Nome, lon, lat" uma localização por linha
    ) -> str
"""

from typing import List, Dict


def _parse_locations(locations_text: str) -> List[Dict[str, float]]:
    """
    Converte o texto das localizações numa lista de dicionários:
    [{"name": ..., "lon": ..., "lat": ...}, ...]

    Formato esperado por linha:
        Nome, lon, lat
    Exemplo:
        Futrono, -72.4, -40.15
        Lisboa,-9.14,38.70
    """
    locations: List[Dict[str, float]] = []

    for line in locations_text.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            # linha mal formatada, ignorar
            continue

        name, lon_str, lat_str = parts
        try:
            # aceita '.' ou ',' como separador decimal (desde que não crie partes extra)
            lon = float(lon_str.replace(",", "."))
            lat = float(lat_str.replace(",", "."))
            locations.append({"name": name, "lon": lon, "lat": lat})
        except ValueError:
            # se não conseguir converter, ignora a linha
            continue

    return locations


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
    Devolve uma string com o código JavaScript completo para colar no
    Code Editor do Google Earth Engine.

    O código:
      - usa ERA5-Land / ERA5 horário;
      - calcula agregados DIÁRIOS por localização;
      - aplica janela sazonal (pode passar o fim do ano);
      - exporta um CSV por localização para o Google Drive.
    """

    locations = _parse_locations(locations_text)

    if not locations:
        return (
            "// ERRO: nenhuma localização válida encontrada.\n"
            "// Formato esperado (uma por linha): Nome, lon, lat\n"
            "// Exemplo: Futrono, -72.4, -40.15"
        )

    lines: List[str] = []

    # ------------------------------------------------------------------
    # Cabeçalho e parâmetros principais
    # ------------------------------------------------------------------
    lines.append("// -------------------------------------------------------------")
    lines.append("// ERA5-Land + ERA5 – Séries DIÁRIAS por localização")
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

    # ------------------------------------------------------------------
    # Localizações
    # ------------------------------------------------------------------
    lines.append("var locations = [")

    loc_entries: List[str] = []
    for loc in locations:
        name = loc["name"].replace("'", "\\'")
        lon = loc["lon"]
        lat = loc["lat"]
        loc_entries.append(
            f"  {{name: '{name}', lon: {lon}, lat: {lat}}}"
        )

    # juntar entradas, sem vírgula final desnecessária
    for i, entry in enumerate(loc_entries):
        if i < len(loc_entries) - 1:
            lines.append(entry + ",")
        else:
            lines.append(entry)

    lines.append("];")
    lines.append("")

    # ------------------------------------------------------------------
    # Corpo JS fixo (igual ao script validado no GEE)
    # ------------------------------------------------------------------
    body = r"""
// ===== FUNÇÕES BÁSICAS =====

var computeDoy = function(month, day) {
  var d = ee.Date.fromYMD(2001, month, day);
  return d.getRelative('day', 'year').add(1);
};

var startDoy = computeDoy(startMonth, startDay);
var endDoy   = computeDoy(endMonth, endDay);
var wrapsYear = startDoy.gt(endDoy);   // true se a janela passar pelo fim do ano

var sanitizeName = function(name) {
  return name.replace(/[^0-9a-zA-Z_]+/g, '_');
};

// ===== DATASETS (sem filtro sazonal aqui) =====

var era5land = ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY')
  .filter(ee.Filter.calendarRange(startYear, endYear, 'year'));

var era5 = ee.ImageCollection('ECMWF/ERA5/HOURLY')
  .filter(ee.Filter.calendarRange(startYear, endYear, 'year'));

// ===== AGREGAR DIARIAMENTE (APENAS DIAS DENTRO DA JANELA) =====

var makeDailySeries = function(point) {

  var startDate = ee.Date.fromYMD(startYear, 1, 1);
  var endDate   = ee.Date.fromYMD(endYear, 12, 31);
  var nDays     = endDate.difference(startDate, 'day');

  var days = ee.List.sequence(0, nDays.subtract(1));

  var fc = ee.FeatureCollection(
    days.map(function(d) {
      d = ee.Number(d);
      var day  = startDate.advance(d, 'day');
      var next = day.advance(1, 'day');

      // day-of-year do dia em causa
      var doy = day.getRelative('day', 'year').add(1);

      // esta flag diz se este dia está ou não dentro da janela sazonal
      var inSeason = ee.Algorithms.If(
        wrapsYear,
        // janela que passa pelo fim do ano (ex.: 15 Nov–15 Fev)
        doy.gte(startDoy).or(doy.lte(endDoy)),
        // janela normal (ex.: 1 Jan–2 Jan ou 5 Set–15 Out)
        doy.gte(startDoy).and(doy.lte(endDoy))
      );

      // se o dia não estiver na janela, nem vale a pena processar
      return ee.Algorithms.If(
        inSeason,
        (function() {

          var landDay = era5land.filterDate(day, next);
          var era5Day = era5.filterDate(day, next);

          var hasData = landDay.size().gt(0);

          return ee.Algorithms.If(
            hasData,
            (function() {

              // ----- ERA5-Land: agregados diários -----

              // Precipitação diária: acumulação máxima do dia (m) -> mm
              var precipImg = landDay.select('total_precipitation')
                .max().rename('precip_m');

              var tminImg  = landDay.select('temperature_2m')
                .min().rename('tmin_K');

              var tmaxImg  = landDay.select('temperature_2m')
                .max().rename('tmax_K');

              var tmeanImg = landDay.select('temperature_2m')
                .mean().rename('tmean_K');

              var dewMeanImg = landDay.select('dewpoint_temperature_2m')
                .mean().rename('dewmean_K');

              var soilImg = landDay.select('volumetric_soil_water_layer_1')
                .mean().rename('soilw1');

              var radSumImg = landDay.select('surface_solar_radiation_downwards')
                .sum().rename('rad_Jm2');

              var radMeanImg = landDay.select('surface_solar_radiation_downwards')
                .mean().rename('rad_Jm2_per_h');

              var pevImg = landDay.select('potential_evaporation')
                .sum().rename('pev_m');

              // ----- ERA5: vento médio + rajada máxima -----

              var uMeanImg = era5Day.select('u_component_of_wind_10m')
                .mean().rename('u10');

              var vMeanImg = era5Day.select('v_component_of_wind_10m')
                .mean().rename('v10');

              var gustMaxImg = era5Day.select('instantaneous_10m_wind_gust')
                .max().rename('gust10');

              // Junta tudo numa imagem
              var aggImg = ee.Image.cat([
                precipImg,
                tminImg, tmaxImg, tmeanImg, dewMeanImg,
                soilImg,
                radSumImg, radMeanImg,
                pevImg,
                uMeanImg, vMeanImg, gustMaxImg
              ]);

              // Redução para o ponto
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

                  var precip_mm = ee.Number(vals.get('precip_m')).multiply(1000);
                  var tmin_C    = ee.Number(vals.get('tmin_K')).subtract(273.15);
                  var tmax_C    = ee.Number(vals.get('tmax_K')).subtract(273.15);
                  var tmean_C   = ee.Number(vals.get('tmean_K')).subtract(273.15);
                  var dewmean_C = ee.Number(vals.get('dewmean_K')).subtract(273.15);
                  var soilw1    = vals.get('soilw1');
                  var rad_Jm2   = vals.get('rad_Jm2');
                  var rad_Wm2   = ee.Number(vals.get('rad_Jm2_per_h')).divide(3600);
                  var pev_mm    = ee.Number(vals.get('pev_m')).multiply(1000);
                  var gust_max  = ee.Number(vals.get('gust10'));

                  return ee.Feature(null, {
                    'date': day.format('YYYY-MM-dd'),
                    'precip_mm': precip_mm,
                    'tmin_C': tmin_C,
                    'tmax_C': tmax_C,
                    'tmean_C': tmean_C,
                    'dew2m_mean_C': dewmean_C,
                    'soilw1_mean': soilw1,
                    'rad_Jm2_day': rad_Jm2,
                    'rad_Wm2_mean': rad_Wm2,
                    'pev_mm_day': pev_mm,
                    'wind_mean_ms': windMean,
                    'gust_max_ms': gust_max
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

  // ficamos apenas com os dias em que houve precipitação calculada
  fc = fc.filter(ee.Filter.notNull(['precip_mm']));
  return fc;
};

// ===== EXPORTAR PARA DRIVE =====

locations.forEach(function(loc) {
  var point = ee.Geometry.Point([loc.lon, loc.lat]);
  var daily = makeDailySeries(point);

  Export.table.toDrive({
    collection: daily,
    description: 'ERA5_diario_' + sanitizeName(loc.name)
      + '_' + startYear + '_' + endYear,
    fileFormat: 'CSV'
  });
});
"""
    # remover a primeira linha em branco do bloco raw
    body = body.lstrip("\n")
    lines.append(body)

    return "\n".join(lines)
