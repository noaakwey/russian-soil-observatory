/* Russian Soil Observatory — geoportal front end.
   Aggregates and the map render immediately; the queryable database is fetched
   only when the SQL tab is first opened, so the landing view stays light. */

'use strict';

/* ------------------------------------------------------------------ i18n */

const STRINGS = {
  ru: {
    'tagline': 'Почвенные наблюдения из «Почвоведения» и Eurasian Soil Science',
    'tab.overview': 'Обзор', 'tab.map': 'Карта', 'tab.props': 'Свойства',
    'tab.quality': 'Качество данных', 'tab.query': 'SQL-запрос', 'tab.about': 'Методика и данные',
    'overview.lede': 'Воспроизводимая база числовых почвенных наблюдений, извлечённых из полнотекстовых публикаций двух корпусов. Каждое значение сохраняет ссылку на исходную ячейку OCR-таблицы, признак достоверности единицы измерения и явно указанную силу пространственной привязки.',
    'overview.insights': 'Пространство, компоненты, время: зональные градиенты, связи свойств и тренды за 20 лет →',
    'overview.report': 'Аудит базы: состав корпуса, качество извлечения, ограничения →',
    'overview.timeline': 'Публикации и наблюдения по годам',
    'overview.timeline.note': 'Год для переводного корпуса восстановлен из идентификатора статьи Pleiades DOI и сверен с Crossref.',
    'overview.categories': 'Наблюдения по группам свойств',
    'overview.spatial': 'Пространственная структура',
    'overview.spatial.note': 'Точки сильно сгруппированы вокруг стационаров и профилей. Это не вероятностная выборка по территории России; статистику нельзя переносить на страну в целом.',
    'map.note': '<strong>Что показано:</strong> только координаты, прямо сообщённые авторами публикаций. Синие точки дополнительно имеют числовые значения, сверенные с исходной OCR-ячейкой. Административные центроиды и региональные геокоды на карту не выводятся. Это не GPS-привязка каждой строки таблицы и не почвенная карта России.',
    'map.layer': 'Слой', 'map.legend.verified': 'с проверенными значениями',
    'map.legend.plain': 'только координата',
    'map.hint': 'Нажмите на точку, чтобы увидеть источник, фрагмент текста с координатой и привязанные измерения.',
    'props.lede': 'Полный спектр распознанных свойств. «Единица доказана» — доля значений, у которых единица напечатана в таблице или получена обратимым преобразованием; остальным единица намеренно не приписывается.',
    'props.sort': 'Сортировка:', 'props.sort.n': 'по числу наблюдений',
    'props.sort.norm': 'по доказанным единицам', 'props.sort.docs': 'по числу публикаций',
    'props.th.property': 'Свойство', 'props.th.category': 'Группа', 'props.th.n': 'Наблюдений',
    'props.th.docs': 'Публикаций', 'props.th.unit': 'Единица доказана',
    'props.th.header': 'Заголовок надёжен', 'props.th.value': 'Значение правдоподобно',
    'props.filter': 'Найти свойство…',
    'props.chart.pick': 'Выберите свойство в таблице выше ↑',
    'props.chart.loading': 'База загружается при первом выборе свойства…',
    'props.chart.ready': 'Выполните запрос — нажмите строку в таблице',
    'props.chart.hist': 'Распределение значений', 'props.chart.depth': 'По глубине',
    'props.chart.lat': 'По широте', 'props.chart.year': 'По годам публикации',
    'chart.empty': 'Недостаточно данных для графика',
    'chart.empty.depth': 'Нет наблюдений с указанной глубиной',
    'chart.empty.lat': 'Нет наблюдений с пространственной привязкой',
    'chart.empty.year': 'Нет наблюдений с известным годом публикации',
    'chart.subtitle': '{n} наблюдений · {docs} публикаций · единица доказана {unit}% · типичная единица «{mode}»',
    'chart.subtitle.raw': '{n} наблюдений · {docs} публикаций · единица доказана лишь {unit}% — график построен по значению как оно напечатано в таблице, без приведения к единой единице',
    'chart.hist.note.metric': 'Значения приведены к «{mode}»; 1-й и 99-й процентили обрезаны, чтобы выбросы OCR не искажали шкалу.',
    'chart.hist.note.raw': 'Единица не доказана — показано напечатанное число без пересчёта. Пунктир — медиана.',
    'chart.depth.note': 'Медиана по интервалам 20 см; показаны интервалы не менее чем с 3 наблюдениями.',
    'chart.lat.note': 'Медиана по полосам 4°; только координаты в границах России (41–82° с.ш.). Наведите точку для деталей.',
    'chart.year.note': 'Число наблюдений в год; только надёжные заголовки и правдоподобные значения.',
    'quality.lede': 'Слой построен из OCR распознанных таблиц, поэтому часть значений неизбежно содержит ошибки распознавания. Они не удаляются, а помечаются: исходная ячейка остаётся доказательством, а решение принимает исследователь.',
    'quality.header': 'Как свойство опознано в заголовке',
    'quality.header.note': '<strong>symbol_embedded</strong> — химический символ найден внутри более длинного заголовка («Thickness of horizons, cm A + B»). Такие значения следует исключать из анализа по умолчанию.',
    'quality.value': 'Физическая правдоподобность значений',
    'quality.value.note': 'Проверка диапазона запускается только там, где единица действительно известна. pH проверяется всегда — он безразмерен.',
    'quality.unit': 'Статус нормализации единиц', 'quality.spatial': 'Сила пространственной привязки',
    'query.lede': 'Вся база наблюдений загружается в браузер и выполняет SQL локально — данные никуда не отправляются. Таблицы: <code>observation</code>, <code>reported_site</code>, <code>verified_measurement</code>, <code>meta</code>.',
    'query.run': 'Выполнить', 'query.ex1': 'Свойства с доказанной единицей', 'query.ex2': 'pH по глубине',
    'query.ex3': 'Тяжёлые металлы по годам', 'query.ex4': 'Только «чистые» данные',
    'query.csv': 'Скачать результат CSV', 'query.loading': 'База загружается при первом запросе.',
    'about.chain': 'Доказательная цепочка',
    'about.chain.text': 'Каждое наблюдение прослеживается до конкретной ячейки:',
    'about.chain.text2': 'Поле <code>evidence_locator</code> хранит номер строки и колонки исходной таблицы, напечатанный заголовок свойства и метку строки.',
    'about.rules': 'Чего эти данные не утверждают',
    'about.rule1': 'Значение со статусом <code>missing_unit</code> не имеет подставленной «по смыслу» единицы.',
    'about.rule2': 'Единственная координата в статье — это контекст документа, а не GPS каждой строки таблицы.',
    'about.rule3': 'pH(H₂O), pH(KCl) и pH без указания метода — три разных показателя.',
    'about.rule4': 'Русский оригинал и его перевод в Eurasian Soil Science не объединены: доказанного соответствия между ними пока нет.',
    'about.rule5': 'Набор точек не является вероятностной выборкой по территории России.',
    'about.downloads': 'Данные для скачивания', 'about.dl.file': 'Файл', 'about.dl.what': 'Что это',
    'about.dl.size': 'Размер', 'about.repro': 'Воспроизведение',
    'about.repro.text': 'Все публикуемые файлы пересобираются из рабочей базы одной командой:',
    'about.license': '<strong>Лицензия.</strong> Составленная база и код — CC BY 4.0. Права на исходные статьи принадлежат их издателям; здесь публикуются извлечённые числовые значения и ссылки на источник.',
    'footer': 'Russian Soil Observatory · воспроизводимая сборка · доказательство: документ → OCR-таблица → строка → ячейка',
    't.observations': 'табличных наблюдений', 't.documents': 'полнотекстовых публикаций',
    't.properties': 'канонических свойств', 't.positions': 'авторских координат',
    't.ready': 'готовы к анализу', 't.tables': 'OCR-таблиц',
    't.note.ready': 'единица доказана, заголовок надёжен, значение правдоподобно',
    't.note.docs': 'Почвоведение + Eurasian Soil Science',
    't.note.positions': 'уникальных положений, сообщённых авторами',
    'f.median': 'медиана до соседа', 'f.within1': 'точек с соседом < 1 км',
    'f.clark': 'индекс Кларка–Эванса', 'f.cells': 'занятых ячеек 5°×5°',
    'f.european': 'в Европейской России', 'f.records': 'координатных записей',
    'f.clark.note': '(< 1 — кластеризация)',
    'm.records': 'координатных записей', 'm.positions': 'уникальных положений',
    'm.verified': 'проверенных измерений', 'm.sites': 'точек с измерениями',
    'legend.docs.ru': 'Почвоведение', 'legend.docs.en': 'Eurasian Soil Science',
    'legend.obs': 'наблюдений',
    'popup.sources': 'Источники', 'popup.evidence': 'Фрагмент с координатой',
    'popup.measurements': 'Проверенные измерения', 'popup.property': 'Свойство',
    'popup.value': 'Значение', 'popup.none': 'Для этой точки пока нет измерения, прошедшего строгую пространственную связь.',
    'popup.records': 'записей с этой координатой', 'popup.year': 'год',
    'sql.rows': 'строк', 'sql.time': 'мс', 'sql.error': 'Ошибка SQL: ',
    'sql.loading': 'Загрузка базы (9,5 МБ)…', 'sql.ready': 'База загружена. Выполните запрос.',
    'sql.truncated': 'показаны первые 1000 строк',
  },
  en: {
    'tagline': 'Soil observations from Pochvovedenie and Eurasian Soil Science',
    'tab.overview': 'Overview', 'tab.map': 'Map', 'tab.props': 'Properties',
    'tab.quality': 'Data quality', 'tab.query': 'SQL query', 'tab.about': 'Method & data',
    'overview.lede': 'A reproducible database of numeric soil observations extracted from the full text of two publication corpora. Every value keeps a pointer to its source OCR table cell, a flag for whether its unit is proven, and an explicit statement of how strong its spatial linkage is.',
    'overview.insights': 'Space, components, time: zonal gradients, property linkages and twenty-year trends →',
    'overview.report': 'Database audit: corpus composition, extraction quality, limitations →',
    'overview.timeline': 'Publications and observations by year',
    'overview.timeline.note': 'For the translated corpus the year is decoded from the Pleiades DOI article identifier and validated against Crossref.',
    'overview.categories': 'Observations by property group',
    'overview.spatial': 'Spatial structure',
    'overview.spatial.note': 'Points are strongly clustered around research stations and profiles. This is not a probability sample of Russian territory; statistics must not be generalised to the country.',
    'map.note': '<strong>What is shown:</strong> only coordinates reported directly by the authors. Blue points additionally carry numeric values re-checked against the source OCR cell. Administrative centroids and regional geocodes are excluded from the map. This is not a GPS fix for every table row, nor a soil map of Russia.',
    'map.layer': 'Layer', 'map.legend.verified': 'with verified values',
    'map.legend.plain': 'coordinate only',
    'map.hint': 'Click a point to see its source, the text fragment carrying the coordinate, and any linked measurements.',
    'props.lede': 'The full spectrum of recognised properties. "Unit proven" is the share of values whose unit is printed in the table or obtained by a reversible conversion; the rest are deliberately left without an assigned unit.',
    'props.sort': 'Sort by:', 'props.sort.n': 'observation count',
    'props.sort.norm': 'proven units', 'props.sort.docs': 'publication count',
    'props.th.property': 'Property', 'props.th.category': 'Group', 'props.th.n': 'Observations',
    'props.th.docs': 'Publications', 'props.th.unit': 'Unit proven',
    'props.th.header': 'Header reliable', 'props.th.value': 'Value plausible',
    'props.filter': 'Find a property…',
    'props.chart.pick': 'Pick a property in the table above ↑',
    'props.chart.loading': 'The database loads on first selection…',
    'props.chart.ready': 'Run a query — click a table row',
    'props.chart.hist': 'Value distribution', 'props.chart.depth': 'By depth',
    'props.chart.lat': 'By latitude', 'props.chart.year': 'By publication year',
    'chart.empty': 'Not enough data for a chart',
    'chart.empty.depth': 'No observations carry a depth',
    'chart.empty.lat': 'No observations carry a spatial reference',
    'chart.empty.year': 'No observations have a known publication year',
    'chart.subtitle': '{n} observations · {docs} publications · unit proven for {unit}% · typical unit "{mode}"',
    'chart.subtitle.raw': '{n} observations · {docs} publications · unit proven for only {unit}% — chart uses the value as printed in the table, not converted to a common unit',
    'chart.hist.note.metric': 'Values converted to "{mode}"; 1st and 99th percentiles clipped so OCR outliers do not flatten the scale.',
    'chart.hist.note.raw': 'Unit not proven — the printed number is shown unconverted. Dashed line is the median.',
    'chart.depth.note': 'Median over 20 cm bins; only bins with 3+ observations are shown.',
    'chart.lat.note': 'Median over 4° bands; coordinates within Russia only (41-82°N). Hover a point for detail.',
    'chart.year.note': 'Observation count per year; trusted headers and plausible values only.',
    'quality.lede': 'The layer is built from OCR-recognised tables, so some values inevitably carry recognition errors. They are not deleted but flagged: the source cell remains as evidence and the researcher decides.',
    'quality.header': 'How the property was recognised in the header',
    'quality.header.note': '<strong>symbol_embedded</strong> — the chemical symbol was found inside a longer header ("Thickness of horizons, cm A + B"). Such values should be excluded from analysis by default.',
    'quality.value': 'Physical plausibility of values',
    'quality.value.note': 'A range check only fires where the unit is actually known. pH is always checked — it is dimensionless.',
    'quality.unit': 'Unit normalization status', 'quality.spatial': 'Strength of spatial linkage',
    'query.lede': 'The whole observation database loads into your browser and runs SQL locally — nothing is sent anywhere. Tables: <code>observation</code>, <code>reported_site</code>, <code>verified_measurement</code>, <code>meta</code>.',
    'query.run': 'Run', 'query.ex1': 'Properties with proven units', 'query.ex2': 'pH by depth',
    'query.ex3': 'Heavy metals by year', 'query.ex4': 'Analysis-ready subset only',
    'query.csv': 'Download result as CSV', 'query.loading': 'The database loads on your first query.',
    'about.chain': 'Chain of evidence',
    'about.chain.text': 'Every observation is traceable to a specific cell:',
    'about.chain.text2': 'The <code>evidence_locator</code> field stores the row and column index of the source table, the printed property header, and the row label.',
    'about.rules': 'What these data do not claim',
    'about.rule1': 'A value with status <code>missing_unit</code> has no unit assigned "by meaning".',
    'about.rule2': 'A single coordinate in an article is document context, not a GPS fix for every table row.',
    'about.rule3': 'pH(H₂O), pH(KCl) and pH with unstated method are three different variables.',
    'about.rule4': 'A Russian original and its Eurasian Soil Science translation are not merged: no proven correspondence between them exists yet.',
    'about.rule5': 'The point set is not a probability sample of Russian territory.',
    'about.downloads': 'Downloads', 'about.dl.file': 'File', 'about.dl.what': 'What it is',
    'about.dl.size': 'Size', 'about.repro': 'Reproducing this build',
    'about.repro.text': 'Every published file is rebuilt from the working database with one sequence:',
    'about.license': '<strong>Licence.</strong> The compiled database and the code are CC BY 4.0. Rights in the source articles remain with their publishers; what is published here are extracted numeric values and pointers to the source.',
    'footer': 'Russian Soil Observatory · reproducible build · evidence: document → OCR table → row → cell',
    't.observations': 'table observations', 't.documents': 'full-text publications',
    't.properties': 'canonical properties', 't.positions': 'author-reported coordinates',
    't.ready': 'analysis-ready', 't.tables': 'OCR tables',
    't.note.ready': 'unit proven, header reliable, value plausible',
    't.note.docs': 'Pochvovedenie + Eurasian Soil Science',
    't.note.positions': 'unique positions reported by authors',
    'f.median': 'median nearest neighbour', 'f.within1': 'points with a neighbour < 1 km',
    'f.clark': 'Clark–Evans index', 'f.cells': 'occupied 5°×5° cells',
    'f.european': 'in European Russia', 'f.records': 'coordinate records',
    'f.clark.note': '(< 1 = clustered)',
    'm.records': 'coordinate records', 'm.positions': 'unique positions',
    'm.verified': 'verified measurements', 'm.sites': 'points with measurements',
    'legend.docs.ru': 'Pochvovedenie', 'legend.docs.en': 'Eurasian Soil Science',
    'legend.obs': 'observations',
    'popup.sources': 'Sources', 'popup.evidence': 'Fragment carrying the coordinate',
    'popup.measurements': 'Verified measurements', 'popup.property': 'Property',
    'popup.value': 'Value', 'popup.none': 'No measurement has passed strict spatial linkage for this point yet.',
    'popup.records': 'records at this coordinate', 'popup.year': 'year',
    'sql.rows': 'rows', 'sql.time': 'ms', 'sql.error': 'SQL error: ',
    'sql.loading': 'Loading database (9.5 MB)…', 'sql.ready': 'Database loaded. Run a query.',
    'sql.truncated': 'first 1000 rows shown',
  },
};

let lang = (navigator.language || 'ru').startsWith('ru') ? 'ru' : 'en';
const t = (key) => (STRINGS[lang] && STRINGS[lang][key]) || STRINGS.ru[key] || key;
const num = (value) => value == null ? '—' : value.toLocaleString(lang === 'ru' ? 'ru-RU' : 'en-US');
const esc = (value) => String(value ?? '').replace(/[&<>"']/g,
  (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

/* ------------------------------------------------------------- rendering */

let AGG = null;
let MAP_DATA = null;

function bars(rows, options = {}) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  const format = options.format || ((row) => num(row.value));
  return `<div class="bars">${rows.map((row) => `
    <div class="bar-row">
      <span class="name" title="${esc(row.label)}">${esc(row.label)}</span>
      <span class="bar-track"><span class="bar-fill ${row.tone || ''}" style="width:${Math.max(1.5, 100 * row.value / max)}%"></span></span>
      <span class="num">${format(row)}</span>
    </div>`).join('')}</div>`;
}

function renderOverview() {
  const q = AGG.quality;
  const tiles = [
    { value: AGG.observations, label: t('t.observations') },
    { value: q.analysis_ready, label: t('t.ready'), note: t('t.note.ready') },
    { value: AGG.documents.total, label: t('t.documents'), note: t('t.note.docs') },
    { value: AGG.spatial.unique_positions, label: t('t.positions'), note: t('t.note.positions') },
    { value: AGG.properties.length, label: t('t.properties') },
    { value: AGG.ocr_tables, label: t('t.tables') },
  ];
  document.getElementById('overview-tiles').innerHTML = tiles.map((tile) => `
    <div class="tile"><div class="value">${num(tile.value)}</div>
      <div class="label">${esc(tile.label)}</div>
      ${tile.note ? `<div class="note">${esc(tile.note)}</div>` : ''}</div>`).join('');

  // Documents per year, split by corpus — one axis, two stacked segments.
  const years = AGG.documents_per_year.filter((row) => row.year >= 2006);
  const maxDocs = Math.max(...years.map((row) => row.pochvovedenie + row.springer), 1);
  document.getElementById('chart-years').innerHTML = `
    <div class="columns">${years.map((row) => {
      const total = row.pochvovedenie + row.springer;
      const height = 150 * total / maxDocs;
      const share = total ? row.pochvovedenie / total : 0;
      return `<div class="column" title="${row.year}: ${num(total)}">
        ${row.pochvovedenie ? `<span class="stack second" style="height:${Math.max(1, height * share)}px"></span>` : ''}
        <span class="stack" style="height:${Math.max(1, height * (1 - share))}px"></span>
      </div>`;
    }).join('')}</div>
    <div class="ticks">${years.map((row) => `<span>${row.year % 100 === 0 || row.year % 5 === 0 ? row.year : ''}</span>`).join('')}</div>
    <div class="legend">
      <span><i class="swatch" style="background:var(--series-1)"></i>${esc(t('legend.docs.en'))}</span>
      <span><i class="swatch" style="background:var(--series-2)"></i>${esc(t('legend.docs.ru'))}</span>
    </div>`;

  document.getElementById('chart-categories').innerHTML = bars(
    AGG.categories.map((row) => ({ label: row.category, value: row.observations })));

  const s = AGG.spatial;
  document.getElementById('spatial-facts').innerHTML = `
    <dt>${esc(t('f.records'))}</dt><dd>${num(s.coordinate_records)}</dd>
    <dt>${esc(t('f.median'))}</dt><dd>${s.nearest_neighbour_km.median} km</dd>
    <dt>${esc(t('f.within1'))}</dt><dd>${s.share_within_1km}%</dd>
    <dt>${esc(t('f.clark'))}</dt><dd>${s.clark_evans_ratio} <span class="pill">${esc(t('f.clark.note'))}</span></dd>
    <dt>${esc(t('f.cells'))}</dt><dd>${num(s.occupied_5deg_cells)}</dd>
    <dt>${esc(t('f.european'))}</dt><dd>${s.european_share_pct}%</dd>`;
}

function propertyLabel(row) {
  return lang === 'ru' && row.property_ru ? row.property_ru : row.property;
}

function renderProperties() {
  const sort = document.getElementById('prop-sort').value;
  const query = (document.getElementById('prop-filter').value || '').trim().toLowerCase();
  const pct = (part, whole) => whole ? `${Math.round(100 * part / whole)}%` : '—';
  let rows = [...AGG.properties].sort((a, b) => b[sort] - a[sort]);
  if (query) {
    rows = rows.filter((row) =>
      propertyLabel(row).toLowerCase().includes(query)
      || row.property.toLowerCase().includes(query)
      || (row.property_ru || '').toLowerCase().includes(query)
      || (lang === 'ru' && row.category_ru || row.category).toLowerCase().includes(query));
  }
  document.getElementById('prop-count').textContent =
    `${num(rows.length)} / ${num(AGG.properties.length)}`;
  document.querySelector('#props-table tbody').innerHTML = rows.map((row) => `
    <tr data-property-id="${esc(row.property_id)}" aria-selected="${row.property_id === selectedProperty}">
      <td>${esc(propertyLabel(row))}</td>
      <td>${esc(lang === 'ru' && row.category_ru ? row.category_ru : row.category)}</td>
      <td class="num">${num(row.observations)}</td>
      <td class="num">${num(row.documents)}</td>
      <td class="num">${pct(row.normalized, row.observations)}</td>
      <td class="num">${pct(row.header_trusted, row.observations)}</td>
      <td class="num">${pct(row.value_plausible, row.observations)}</td>
    </tr>`).join('');
}

function renderQuality() {
  const q = AGG.quality;
  const total = AGG.observations;
  document.getElementById('quality-tiles').innerHTML = [
    { value: q.unflagged, label: t('t.ready'), note: `${Math.round(100 * q.unflagged / total)}% / ${num(total)}` },
    { value: q.header_match_kind.symbol_embedded || 0, label: 'symbol_embedded' },
    { value: (q.value_plausibility.negative_content || 0) + (q.value_plausibility.out_of_physical_range || 0),
      label: lang === 'ru' ? 'значения вне физического диапазона' : 'values outside physical range' },
    { value: q.normalization_status.missing_unit || 0, label: 'missing_unit' },
  ].map((tile) => `<div class="tile"><div class="value">${num(tile.value)}</div>
      <div class="label">${esc(tile.label)}</div>
      ${tile.note ? `<div class="note">${esc(tile.note)}</div>` : ''}</div>`).join('');

  const toRows = (obj, tones = {}) => Object.entries(obj)
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => ({ label: key, value, tone: tones[key] || '' }));

  document.getElementById('chart-headerkind').innerHTML = bars(
    toRows(q.header_match_kind, { phrase: 'good', symbol_clean: '', symbol_embedded: 'muted' }));
  document.getElementById('chart-plausibility').innerHTML = bars(
    toRows(q.value_plausibility, { ok: 'good' }));
  document.getElementById('chart-normalization').innerHTML = bars(
    toRows(q.normalization_status, { exact: 'good', converted: 'good' }));
  document.getElementById('chart-linkage').innerHTML = bars(
    toRows(q.spatial_linkage, { row_profile_verified: 'good' }));
}

const DOWNLOADS = [
  ['data/full_table_observations.csv', {
    ru: 'Все табличные наблюдения с флагами качества и происхождением',
    en: 'All table observations with quality flags and provenance' }, '80 MB'],
  ['data/observatory.sqlite.gz', {
    ru: 'База для браузера и локального анализа (SQLite, gzip)',
    en: 'Database for the browser and local analysis (SQLite, gzip)' }, '9.5 MB'],
  ['data/aggregates.json', {
    ru: 'Все сводные показатели портала', en: 'Every aggregate the portal quotes' }, '30 KB'],
  ['data/portal_map.json', {
    ru: 'Точки карты с источниками и измерениями', en: 'Map points with sources and measurements' }, '0.8 MB'],
  ['data/reported_sites.csv', {
    ru: 'Все авторские координаты', en: 'All author-reported coordinates' }, '1.2 MB'],
  ['data/normalized_measurements.csv', {
    ru: 'Строгий пространственный слой измерений', en: 'Strict spatial measurement layer' }, '1.1 MB'],
  ['data/profile_descriptions.csv', {
    ru: 'Описания разрезов и профилей', en: 'Profile and pit descriptions' }, '1.1 MB'],
  ['data/property_dictionary_ru_public.csv', {
    ru: 'Словарь свойств и канонических единиц', en: 'Property and canonical-unit dictionary' }, '34 KB'],
  ['data/property_census.csv', {
    ru: 'Перепись всех 101 свойств: охват единицей, глубиной, координатой',
    en: 'Census of all 101 properties: unit, depth and spatial coverage' }, '17 KB'],
  ['data/full_table_observation_audit.json', {
    ru: 'Аудит полноты слоя наблюдений', en: 'Observation layer coverage audit' }, '1 KB'],
  ['data/observation_quality_audit.json', {
    ru: 'Аудит флагов качества', en: 'Quality flag audit' }, '2 KB'],
  ['data/publication_year_audit.json', {
    ru: 'Аудит восстановления года публикации', en: 'Publication year recovery audit' }, '1 KB'],
];

function renderDownloads() {
  document.getElementById('downloads').innerHTML = DOWNLOADS.map(([href, label, size]) => `
    <tr><td><a href="${href}">${esc(href.replace('data/', ''))}</a></td>
        <td style="white-space:normal">${esc(label[lang])}</td>
        <td class="num">${esc(size)}</td></tr>`).join('');
  document.getElementById('generated-at').textContent =
    (lang === 'ru' ? 'Сборка: ' : 'Build: ') + (AGG.generated_at || '');
}

/* ------------------------------------------------------------------- map */

let map = null;
let mapLayer = null;

function popupHtml(point) {
  const sources = point.sources.map((source) => `<li>
      <b>${esc(source.corpus === 'springer' ? 'Eurasian Soil Science' : 'Почвоведение')}</b>
      ${source.year ? ` · ${t('popup.year')} ${source.year}${source.year_confidence === 'submission_year' ? ' ±1' : ''}` : ''}
      ${source.doi ? `<br><a target="_blank" rel="noopener" href="https://doi.org/${esc(source.doi)}">${esc(source.doi)}</a>` : ''}
      ${source.evidence ? `<details><summary>${esc(t('popup.evidence'))}</summary>${esc(source.evidence)}</details>` : ''}
    </li>`).join('');

  const rows = point.measurements.map((m) => `<tr>
      <td>${esc(m.property)}</td>
      <td>${esc(m.value)} ${esc(m.unit || '')}</td>
      <td>${m.doi ? `<a target="_blank" rel="noopener" href="https://doi.org/${esc(m.doi)}">DOI</a>` : ''}</td>
    </tr>`).join('');

  return `<h3>${point.lat.toFixed(5)}° N, ${point.lon.toFixed(5)}° E</h3>
    <p>${point.records} ${esc(t('popup.records'))}</p>
    <h4>${esc(t('popup.sources'))}</h4><ul>${sources}</ul>
    ${rows ? `<h4>${esc(t('popup.measurements'))}</h4>
      <table><thead><tr><th>${esc(t('popup.property'))}</th><th>${esc(t('popup.value'))}</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table>`
      : `<p><em>${esc(t('popup.none'))}</em></p>`}`;
}

function renderMap() {
  if (!MAP_DATA) return;
  if (!map) {
    map = L.map('map', { scrollWheelZoom: true }).setView([60, 80], 3);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18, attribution: '© OpenStreetMap contributors',
    }).addTo(map);
  }
  if (mapLayer) mapLayer.remove();

  const bounds = [];
  mapLayer = L.layerGroup();
  const accent = getComputedStyle(document.documentElement).getPropertyValue('--series-1').trim() || '#2a78d6';
  MAP_DATA.points.forEach((point) => {
    const verified = point.measurements.length > 0;
    const marker = L.circleMarker([point.lat, point.lon], {
      radius: verified ? 7 : 4,
      color: verified ? accent : '#767569',
      weight: 1,
      fillColor: verified ? accent : '#94938a',
      fillOpacity: verified ? 0.85 : 0.6,
    }).bindPopup(() => popupHtml(point), { maxWidth: 470 });
    mapLayer.addLayer(marker);
    bounds.push([point.lat, point.lon]);
  });
  mapLayer.addTo(map);
  if (bounds.length) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 6 });

  const verified = MAP_DATA.points.filter((p) => p.measurements.length).length;
  const values = MAP_DATA.points.reduce((sum, p) => sum + p.measurements.length, 0);
  document.getElementById('map-facts').innerHTML = `
    <dt>${esc(t('m.positions'))}</dt><dd>${num(MAP_DATA.points.length)}</dd>
    <dt>${esc(t('m.records'))}</dt><dd>${num(AGG.spatial.coordinate_records)}</dd>
    <dt>${esc(t('m.sites'))}</dt><dd>${num(verified)}</dd>
    <dt>${esc(t('m.verified'))}</dt><dd>${num(values)}</dd>`;
  setTimeout(() => map.invalidateSize(), 60);
}

/* ------------------------------------------------------------------- SQL */

const EXAMPLES = [
  `-- Properties whose unit is actually proven, most abundant first
SELECT property, property_ru, category,
       COUNT(*)                                   AS observations,
       ROUND(AVG(value_normalized), 3)            AS mean_value,
       unit_normalized
FROM observation
WHERE normalization_status IN ('exact','converted')
  AND value_plausibility = 'ok'
GROUP BY property, property_ru, category, unit_normalized
ORDER BY observations DESC
LIMIT 40;`,
  `-- pH against sampling depth, using only trustworthy cells
SELECT CAST(depth_top_cm / 10 AS INT) * 10 AS depth_from_cm,
       COUNT(*)                            AS n,
       ROUND(AVG(value_raw), 2)            AS mean_pH,
       ROUND(MIN(value_raw), 2)            AS min_pH,
       ROUND(MAX(value_raw), 2)            AS max_pH
FROM observation
-- NB: LIKE 'ph_%' would also match physical_clay — '_' is a wildcard.
WHERE property_id IN ('ph_h2o','ph_kcl','ph_unspecified')
  AND depth_top_cm IS NOT NULL AND depth_top_cm < 200
  AND value_plausibility = 'ok'
GROUP BY depth_from_cm
ORDER BY depth_from_cm;`,
  `-- Share of heavy-metal observations over time
SELECT publication_year AS year,
       COUNT(*)                                                        AS observations,
       SUM(category IN ('microelement','contaminant'))                 AS metals,
       ROUND(100.0 * SUM(category IN ('microelement','contaminant')) / COUNT(*), 1) AS pct_metals
FROM observation
WHERE publication_year IS NOT NULL
GROUP BY year
HAVING observations > 200
ORDER BY year;`,
  `-- The analysis-ready subset: proven unit, reliable header, plausible value
SELECT category, property, COUNT(*) AS n
FROM observation
WHERE header_match_kind <> 'symbol_embedded'
  AND value_plausibility = 'ok'
  AND normalization_status IN ('exact','converted')
GROUP BY category, property
ORDER BY n DESC;`,
];

let db = null;
let loading = null;
let lastResult = null;
let selectedProperty = null;

async function loadDatabase() {
  if (db) return db;
  if (loading) return loading;
  const status = document.getElementById('sql-status');
  status.classList.remove('error');
  status.textContent = t('sql.loading');

  loading = (async () => {
    const [SQL, buffer] = await Promise.all([
      sqlJsReady.then(() => initSqlJs({ locateFile: (file) => `assets/${file}` })),
      (async () => {
        const response = await fetch('data/observatory.sqlite.gz');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        // The database ships gzipped (33 MB → 4.9 MB); browsers inflate it natively.
        if (typeof DecompressionStream === 'function') {
          const stream = response.body.pipeThrough(new DecompressionStream('gzip'));
          return new Uint8Array(await new Response(stream).arrayBuffer());
        }
        throw new Error('DecompressionStream unsupported');
      })(),
    ]);
    db = new SQL.Database(buffer);
    status.textContent = t('sql.ready');
    return db;
  })();
  return loading;
}

function renderResult(result, elapsed) {
  const head = document.querySelector('#sql-result thead');
  const body = document.querySelector('#sql-result tbody');
  if (!result) { head.innerHTML = ''; body.innerHTML = ''; return; }
  const rows = result.values.slice(0, 1000);
  head.innerHTML = `<tr>${result.columns.map((c) => `<th>${esc(c)}</th>`).join('')}</tr>`;
  body.innerHTML = rows.map((row) => `<tr>${row.map((cell) =>
    `<td class="${typeof cell === 'number' ? 'num' : ''}">${esc(cell)}</td>`).join('')}</tr>`).join('');
  const truncated = result.values.length > 1000 ? ` · ${t('sql.truncated')}` : '';
  document.getElementById('sql-status').textContent =
    `${num(result.values.length)} ${t('sql.rows')} · ${elapsed} ${t('sql.time')}${truncated}`;
}

async function runQuery() {
  const button = document.getElementById('sql-run');
  const status = document.getElementById('sql-status');
  button.disabled = true;
  try {
    await loadDatabase();
    const started = performance.now();
    const results = db.exec(document.getElementById('sql-input').value);
    const elapsed = Math.round(performance.now() - started);
    lastResult = results.length ? results[results.length - 1] : null;
    status.classList.remove('error');
    renderResult(lastResult, elapsed);
    if (!lastResult) status.textContent = 'OK';
  } catch (error) {
    status.classList.add('error');
    status.textContent = t('sql.error') + error.message;
  } finally {
    button.disabled = false;
  }
}

function downloadCsv() {
  if (!lastResult) return;
  const quote = (cell) => {
    const text = cell == null ? '' : String(cell);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const csv = [lastResult.columns.join(','),
    ...lastResult.values.map((row) => row.map(quote).join(','))].join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = Object.assign(document.createElement('a'), { href: url, download: 'query_result.csv' });
  link.click();
  URL.revokeObjectURL(url);
}

/* -------------------------------------------------------- property charts
   A small vanilla-SVG chart kit: no charting library is vendored, so every
   render function below builds its own <svg> tree.  All four charts for a
   property are computed live from the in-browser database — nothing is
   precomputed at build time — because with 101 properties, precomputing a
   histogram + depth profile + latitude profile + year trend for each would
   dwarf the JSON payloads the landing page needs to stay light. */

const SVGNS = 'http://www.w3.org/2000/svg';

function svgNode(tag, attrs) {
  const el = document.createElementNS(SVGNS, tag);
  for (const key in attrs) el.setAttribute(key, attrs[key]);
  return el;
}

function withTitle(el, text) {
  const title = svgNode('title', {});
  title.textContent = text;
  el.appendChild(title);
  return el;
}

function fmtNum(value) {
  if (value == null || Number.isNaN(value)) return '';
  const abs = Math.abs(value);
  const digits = abs >= 1000 ? 0 : abs >= 100 ? 1 : abs >= 1 ? 2 : 4;
  return value.toLocaleString(lang === 'ru' ? 'ru-RU' : 'en-US', { maximumFractionDigits: digits });
}

function fillTemplate(template, vars) {
  return template.replace(/\{(\w+)\}/g, (_, key) => vars[key] ?? '');
}

function median(sortedValues) {
  return sortedValues.length ? sortedValues[Math.floor((sortedValues.length - 1) / 2)] : null;
}

function emptyChart(container, message) {
  container.innerHTML = `<div class="chart-empty">${esc(message)}</div>`;
}

const CHART_W = 340;
const CHART_H = 176;

/** Bars over p1-p99 of ``values`` so a handful of OCR-corrupted numbers
 * cannot flatten the whole histogram onto one bin. */
function renderHistogram(container, values, unitLabel) {
  if (values.length < 3) return emptyChart(container, t('chart.empty'));
  const sorted = [...values].sort((a, b) => a - b);
  const lo = sorted[Math.floor(0.01 * (sorted.length - 1))];
  const hi = sorted[Math.ceil(0.99 * (sorted.length - 1))];
  const span = hi - lo || Math.abs(hi) || 1;
  const clipped = values.filter((v) => v >= lo && v <= hi);
  const binCount = Math.min(20, Math.max(6, Math.round(Math.sqrt(clipped.length))));
  const bins = new Array(binCount).fill(0);
  clipped.forEach((v) => {
    let index = Math.floor(((v - lo) / span) * binCount);
    if (index >= binCount) index = binCount - 1;
    if (index < 0) index = 0;
    bins[index]++;
  });
  const maxCount = Math.max(...bins, 1);
  const margin = { top: 8, right: 8, bottom: 20, left: 8 };
  const innerW = CHART_W - margin.left - margin.right;
  const innerH = CHART_H - margin.top - margin.bottom;
  const barW = innerW / binCount;
  const svg = svgNode('svg', { viewBox: `0 0 ${CHART_W} ${CHART_H}`, class: 'chart-svg' });

  bins.forEach((count, i) => {
    if (!count) return;
    const h = innerH * count / maxCount;
    const bar = svgNode('rect', {
      class: 'bar', x: (margin.left + i * barW + 0.5).toFixed(1),
      y: (margin.top + innerH - h).toFixed(1), width: Math.max(0.5, barW - 1).toFixed(1),
      height: h.toFixed(1), rx: 1.5,
    });
    const binLo = lo + span * i / binCount, binHi = lo + span * (i + 1) / binCount;
    withTitle(bar, `${fmtNum(binLo)}–${fmtNum(binHi)} ${unitLabel}: ${count}`);
    svg.appendChild(bar);
  });

  const med = median(sorted);
  const medX = margin.left + innerW * Math.min(1, Math.max(0, (med - lo) / span));
  svg.appendChild(svgNode('line', {
    class: 'median-line', x1: medX.toFixed(1), x2: medX.toFixed(1),
    y1: margin.top, y2: margin.top + innerH,
  }));

  [[lo, 'start', margin.left], [hi, 'end', margin.left + innerW]].forEach(([val, anchor, x]) => {
    const label = svgNode('text', {
      class: 'tick-label', x: x.toFixed(1), y: CHART_H - 5, 'text-anchor': anchor,
    });
    label.textContent = fmtNum(val);
    svg.appendChild(label);
  });
  const medLabel = svgNode('text', { class: 'tick-label', x: medX.toFixed(1), y: margin.top - 1, 'text-anchor': 'middle' });
  medLabel.textContent = fmtNum(med);
  svg.appendChild(medLabel);

  container.innerHTML = '';
  container.appendChild(svg);
}

/** Simple categorical bars, used for the per-year observation count. */
function renderBars(container, items) {
  if (items.length < 2) return emptyChart(container, t('chart.empty.year'));
  const margin = { top: 8, right: 8, bottom: 20, left: 8 };
  const innerW = CHART_W - margin.left - margin.right;
  const innerH = CHART_H - margin.top - margin.bottom;
  const maxV = Math.max(...items.map((d) => d.value), 1);
  const barW = innerW / items.length;
  const svg = svgNode('svg', { viewBox: `0 0 ${CHART_W} ${CHART_H}`, class: 'chart-svg' });

  items.forEach((d, i) => {
    const h = innerH * d.value / maxV;
    const bar = svgNode('rect', {
      class: 'bar', x: (margin.left + i * barW + 0.5).toFixed(1),
      y: (margin.top + innerH - h).toFixed(1), width: Math.max(0.5, barW - 1).toFixed(1),
      height: h.toFixed(1), rx: 1.5,
    });
    withTitle(bar, `${d.label}: ${num(d.value)}`);
    svg.appendChild(bar);
  });

  const showEvery = Math.max(1, Math.ceil(items.length / 9));
  items.forEach((d, i) => {
    if (i % showEvery !== 0 && i !== items.length - 1) return;
    const x = margin.left + i * barW + barW / 2;
    const label = svgNode('text', { class: 'tick-label', x: x.toFixed(1), y: CHART_H - 5, 'text-anchor': 'middle' });
    label.textContent = d.label;
    svg.appendChild(label);
  });

  container.innerHTML = '';
  container.appendChild(svg);
}

/** Median-per-band line+dots, oriented vertically: depth grows downward,
 * latitude grows upward (north at the top, matching the map). */
function renderProfile(container, points, opts) {
  if (points.length < 2) return emptyChart(container, opts.emptyText);
  const margin = { top: 10, right: 14, bottom: 8, left: 40 };
  const innerW = CHART_W - margin.left - margin.right;
  const innerH = CHART_H - margin.top - margin.bottom;
  const ys = points.map((p) => p.y);
  const xs = points.map((p) => p.value);
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const xMin = Math.min(0, ...xs), xMax = Math.max(...xs) * 1.06 || 1;
  const yPos = (y) => {
    const frac = (y - yMin) / (yMax - yMin || 1);
    return margin.top + innerH * (opts.topIsMin ? frac : 1 - frac);
  };
  const xPos = (x) => margin.left + innerW * (x - xMin) / (xMax - xMin || 1);

  const svg = svgNode('svg', { viewBox: `0 0 ${CHART_W} ${CHART_H}`, class: 'chart-svg' });
  if (xMin < 0) {
    const zeroX = xPos(0);
    svg.appendChild(svgNode('line', { class: 'gridline', x1: zeroX.toFixed(1), x2: zeroX.toFixed(1), y1: margin.top, y2: margin.top + innerH }));
  }
  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${xPos(p.value).toFixed(1)},${yPos(p.y).toFixed(1)}`).join(' ');
  svg.appendChild(svgNode('path', { class: 'line', d: path }));
  points.forEach((p) => {
    const dot = svgNode('circle', { class: 'dot', cx: xPos(p.value).toFixed(1), cy: yPos(p.y).toFixed(1), r: 3 });
    withTitle(dot, `${opts.yFormat(p.y)}: ${fmtNum(p.value)} ${opts.unitLabel || ''} (n=${p.n})`);
    svg.appendChild(dot);
  });
  svg.appendChild(svgNode('line', { class: 'axis', x1: margin.left, x2: margin.left, y1: margin.top, y2: margin.top + innerH }));

  const labelPoints = points.length <= 4 ? points : [points[0], points[Math.floor(points.length / 2)], points[points.length - 1]];
  labelPoints.forEach((p) => {
    const label = svgNode('text', { class: 'tick-label', x: 2, y: (yPos(p.y) + 3).toFixed(1) });
    label.textContent = opts.yFormat(p.y);
    svg.appendChild(label);
  });

  container.innerHTML = '';
  container.appendChild(svg);
}

/** Fetch a property's four chart datasets from the in-browser database.
 * Whether the histogram/profile use ``value_normalized`` (converted, proven
 * unit) or ``value_raw`` (printed, unconverted) depends on how much of the
 * property's own layer has a proven unit: below 30% the converted subset is
 * too small and too self-selected to represent the property honestly. */
async function fetchPropertyCharts(pid, useMetric) {
  const valueExpr = useMetric ? 'value_normalized' : 'value_raw';
  const metricFilter = useMetric ? 'AND metric=1' : '';

  const values = db.exec(`
    SELECT ${valueExpr} FROM observation
    WHERE property_id=? AND trusted=1 ${metricFilter} AND ${valueExpr} IS NOT NULL`,
    [pid])[0]?.values.map((r) => r[0]) || [];

  const depthRows = db.exec(`
    SELECT depth_top_cm, ${valueExpr} FROM observation
    WHERE property_id=? AND trusted=1 ${metricFilter}
      AND depth_top_cm IS NOT NULL AND depth_top_cm < 200 AND ${valueExpr} IS NOT NULL`,
    [pid])[0]?.values || [];

  const latRows = db.exec(`
    SELECT context_latitude, ${valueExpr} FROM observation
    WHERE property_id=? AND trusted=1 ${metricFilter}
      AND context_latitude BETWEEN 41 AND 82 AND ${valueExpr} IS NOT NULL`,
    [pid])[0]?.values || [];

  const yearRows = db.exec(`
    SELECT publication_year, COUNT(*) FROM observation
    WHERE property_id=? AND trusted=1 AND publication_year IS NOT NULL
    GROUP BY publication_year ORDER BY publication_year`,
    [pid])[0]?.values || [];

  return { values, depthRows, latRows, yearRows };
}

function binMedian(rows, keyFn, binSize, minCount, domain) {
  const buckets = new Map();
  rows.forEach(([key, value]) => {
    if (domain && (key < domain[0] || key > domain[1])) return;
    const bin = binKeyOf(key, binSize);
    if (!buckets.has(bin)) buckets.set(bin, []);
    buckets.get(bin).push(value);
  });
  const points = [];
  for (const [bin, vals] of buckets) {
    if (vals.length < minCount) continue;
    const sorted = [...vals].sort((a, b) => a - b);
    points.push({ y: keyFn(bin), value: median(sorted), n: vals.length });
  }
  return points.sort((a, b) => a.y - b.y);
}

function binKeyOf(value, binSize) {
  return Math.floor(value / binSize) * binSize;
}

let chartCache = new Map();

async function selectProperty(pid) {
  selectedProperty = pid;
  document.querySelectorAll('#props-table tbody tr').forEach((row) =>
    row.setAttribute('aria-selected', String(row.dataset.propertyId === pid)));

  const meta = AGG.properties.find((row) => row.property_id === pid);
  if (!meta) return;
  document.getElementById('chart-title').textContent = propertyLabel(meta);
  const status = document.getElementById('chart-status');
  status.textContent = t('props.chart.loading');

  const unitPct = meta.observations ? Math.round(100 * meta.normalized / meta.observations) : 0;
  const useMetric = unitPct >= 30 && !!meta.unit_mode;
  document.getElementById('chart-subtitle').textContent = fillTemplate(
    t(useMetric ? 'chart.subtitle' : 'chart.subtitle.raw'),
    { n: num(meta.observations), docs: num(meta.documents), unit: unitPct, mode: meta.unit_mode || '' });

  try {
    await loadDatabase();
    status.textContent = '';
    let data = chartCache.get(pid + (useMetric ? ':m' : ':r'));
    if (!data) {
      data = await fetchPropertyCharts(pid, useMetric);
      chartCache.set(pid + (useMetric ? ':m' : ':r'), data);
    }
    renderPropertyCharts(meta, data, useMetric);
  } catch (error) {
    status.classList.add('error');
    status.textContent = t('sql.error') + error.message;
  }
}

function renderPropertyCharts(meta, data, useMetric) {
  const unitLabel = useMetric ? (meta.unit_mode || '') : t('props.th.value');

  document.getElementById('chart-hist-note').textContent =
    t(useMetric ? 'chart.hist.note.metric' : 'chart.hist.note.raw').replace('{mode}', meta.unit_mode || '');
  renderHistogram(document.getElementById('chart-hist'), data.values, unitLabel);

  document.getElementById('chart-depth-note').textContent = t('chart.depth.note');
  const depthPoints = binMedian(data.depthRows, (bin) => bin + 10, 20, 3);
  renderProfile(document.getElementById('chart-depth'), depthPoints, {
    topIsMin: true, emptyText: t('chart.empty.depth'), unitLabel,
    yFormat: (y) => `${Math.round(y)} ${lang === 'ru' ? 'см' : 'cm'}`,
  });

  document.getElementById('chart-lat-note').textContent = t('chart.lat.note');
  const latPoints = binMedian(data.latRows, (bin) => bin + 2, 4, 3, [41, 82]);
  renderProfile(document.getElementById('chart-lat'), latPoints, {
    topIsMin: false, emptyText: t('chart.empty.lat'), unitLabel,
    yFormat: (y) => `${Math.round(y)}°`,
  });

  document.getElementById('chart-year-note').textContent = t('chart.year.note');
  renderBars(document.getElementById('chart-year'),
    data.yearRows.map(([year, count]) => ({ label: String(year), value: count })));
}

/* ------------------------------------------------------------------ shell */

function applyLanguage() {
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-i18n]').forEach((node) => {
    const value = t(node.dataset.i18n);
    if (/<[a-z]/i.test(value)) node.innerHTML = value; else node.textContent = value;
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach((node) => {
    node.placeholder = t(node.dataset.i18nPlaceholder);
  });
  document.getElementById('lang-ru').setAttribute('aria-pressed', String(lang === 'ru'));
  document.getElementById('lang-en').setAttribute('aria-pressed', String(lang === 'en'));
  if (AGG) { renderOverview(); renderProperties(); renderQuality(); renderDownloads(); }
  if (MAP_DATA && map) renderMap();
  if (selectedProperty) selectProperty(selectedProperty);
}

function selectTab(name) {
  document.querySelectorAll('.tabs button').forEach((button) =>
    button.setAttribute('aria-selected', String(button.dataset.panel === name)));
  document.querySelectorAll('.panel').forEach((panel) =>
    panel.hidden = panel.id !== `panel-${name}`);
  if (name === 'map') {
    if (!MAP_DATA) {
      fetch('data/portal_map.json').then((r) => r.json()).then((data) => {
        MAP_DATA = data; renderMap();
      });
    } else { renderMap(); }
  }
  if (name === 'query' && !db) loadDatabase().catch((error) => {
    const status = document.getElementById('sql-status');
    status.classList.add('error');
    status.textContent = t('sql.error') + error.message;
  });
  if (name === 'props' && !selectedProperty && AGG?.properties?.length) {
    selectProperty(AGG.properties[0].property_id);
  }
}

function applyTheme(theme) {
  if (theme) document.documentElement.setAttribute('data-theme', theme);
  else document.documentElement.removeAttribute('data-theme');
  document.getElementById('theme-light').setAttribute('aria-pressed', String(theme === 'light'));
  document.getElementById('theme-dark').setAttribute('aria-pressed', String(theme === 'dark'));
  try { theme ? localStorage.setItem('rso-theme', theme) : localStorage.removeItem('rso-theme'); } catch (_) {}
  if (MAP_DATA && map) renderMap();
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('lang-ru').onclick = () => { lang = 'ru'; applyLanguage(); };
  document.getElementById('lang-en').onclick = () => { lang = 'en'; applyLanguage(); };
  document.getElementById('theme-light').onclick = () =>
    applyTheme(document.documentElement.getAttribute('data-theme') === 'light' ? null : 'light');
  document.getElementById('theme-dark').onclick = () =>
    applyTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? null : 'dark');
  try {
    const saved = localStorage.getItem('rso-theme');
    if (saved) applyTheme(saved);
  } catch (_) {}

  document.querySelectorAll('.tabs button').forEach((button) => {
    button.onclick = () => selectTab(button.dataset.panel);
  });
  document.getElementById('prop-sort').onchange = renderProperties;
  document.getElementById('prop-filter').oninput = renderProperties;
  document.querySelector('#props-table tbody').addEventListener('click', (event) => {
    const row = event.target.closest('tr[data-property-id]');
    if (row) selectProperty(row.dataset.propertyId);
  });
  document.getElementById('sql-run').onclick = runQuery;
  document.getElementById('sql-csv').onclick = downloadCsv;
  document.querySelectorAll('[data-example]').forEach((button) => {
    button.onclick = () => {
      document.getElementById('sql-input').value = EXAMPLES[Number(button.dataset.example)];
      runQuery();
    };
  });
  document.getElementById('sql-input').value = EXAMPLES[0];

  fetch('data/aggregates.json')
    .then((response) => response.json())
    .then((data) => {
      AGG = data;
      applyLanguage();
      if (location.hash.replace('#', '') === 'props') selectTab('props');
    })
    .catch((error) => {
      document.getElementById('overview-tiles').innerHTML =
        `<div class="callout warn">Не удалось загрузить aggregates.json: ${esc(error.message)}</div>`;
    });
});

/* sql.js is loaded lazily so the landing page does not pay for the wasm.  The
   promise is awaited before the first query, otherwise a fast click on the SQL
   tab reaches ``initSqlJs`` before the script has defined it. */
const sqlJsReady = new Promise((resolve, reject) => {
  const script = document.createElement('script');
  script.src = 'assets/sql-wasm.js';
  script.onload = resolve;
  script.onerror = () => reject(new Error('assets/sql-wasm.js failed to load'));
  document.head.appendChild(script);
});
