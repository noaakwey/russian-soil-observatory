# Russian Soil Observatory

Открытая база почвенных наблюдений, извлечённых из полнотекстовых публикаций
российского почвоведения, и геопортал к ней.

**Геопортал:** https://noaakwey.github.io/russian-soil-observatory/
**Научный анализ базы:** [docs/data_audit.md](docs/data_audit.md)

*An open database of soil measurements extracted from the full text of Russian
soil-science publications, with a bilingual (RU/EN) geoportal.*

---

## Что это

| Слой | Объём |
|---|---:|
| Полнотекстовые публикации | 4 180 |
| — «Почвоведение» | 625 |
| — Springer / *Eurasian Soil Science* | 3 555 |
| OCR-таблиц | 12 280 |
| Табличных наблюдений | 62 805 |
| Канонических свойств | 70 |
| Авторских координат | 1 092 (790 уникальных положений) |
| Строгий пространственный слой | 1 239 измерений |

Главный принцип: **никакое числовое значение не пропадает из-за отсутствующей
координаты, но и координата документа не выдаётся за координату каждой строки
таблицы.** Каждое наблюдение хранит ссылку на исходную ячейку OCR-таблицы,
статус доказанности единицы измерения и явно указанную силу пространственной
привязки.

## Данные

Всё, что публикуется, лежит в [`docs/data/`](docs/data/):

| Файл | Что это |
|---|---|
| `full_table_observations.csv` | все 62 805 наблюдений с флагами качества и происхождением |
| `observatory.sqlite.gz` | та же база в SQLite (gzip, 4.9 МБ) — для браузера и локального анализа |
| `aggregates.json` | все сводные показатели портала |
| `portal_map.json` | точки карты с источниками и измерениями |
| `reported_sites.csv` | все координаты, сообщённые авторами |
| `normalized_measurements.csv` | строгий пространственный слой |
| `property_dictionary_ru_public.csv` | словарь свойств и канонических единиц |
| `*_audit.json` | аудиты полноты, качества и восстановления года |

### Как читать флаги качества

Перед количественным анализом фильтруйте по трём полям:

```sql
SELECT * FROM observation
WHERE header_match_kind <> 'symbol_embedded'   -- свойство надёжно опознано
  AND value_plausibility = 'ok'                -- значение физически возможно
  AND normalization_status IN ('exact','converted');  -- единица доказана
-- 19 918 наблюдений из 62 805
```

- `normalization_status = 'missing_unit'` (55.9%) — единицу нельзя доказать по
  напечатанному заголовку. Она **намеренно не подставляется**.
- `header_match_kind = 'symbol_embedded'` (8.8%) — химический символ найден внутри
  более длинного текста заголовка; вероятное ложное срабатывание.
- `spatial_linkage` — сила привязки к координате; `document_single_reported_coordinate`
  означает контекст документа, а не GPS строки таблицы.

## Ограничения

1. Точки сильно кластеризованы (индекс Кларка–Эванса 0.34, ≈ 302 независимых
   локалитета на 790 положений) — это **не вероятностная выборка** по территории России.
2. Русский оригинал и его перевод в *Eurasian Soil Science* не связаны: у переводного
   корпуса нет заголовков и авторов. Верхняя граница возможного двойного учёта — 3.8%.
3. Метка генетического горизонта заполнена лишь у 12 наблюдений; профильный анализ
   возможен только по числовой глубине.
4. Значения получены OCR-распознаванием и содержат ошибки; они помечены, а не удалены.

Подробно — в [научном анализе](docs/data_audit.md).

## Воспроизведение

Требуется рабочая база `russian_soil_observatory.sqlite` (не входит в репозиторий:
1.2 ГБ). Порядок:

```bash
python3 observatory_v1/extract_table_measurement_candidates.py --db DB --replace-existing
python3 observatory_v1/normalize_table_measurement_candidates.py --db DB
python3 observatory_v1/materialize_full_table_observations.py --db DB
python3 observatory_v1/audit_full_table_observations.py --db DB --output docs/data/full_table_observation_audit.json
python3 observatory_v1/flag_observation_quality.py --db DB --output docs/data/observation_quality_audit.json
python3 observatory_v1/infer_springer_publication_year.py --db DB --crossref docs/data/doi_metadata.csv --output docs/data/publication_year_audit.json
python3 docs/scripts/build_portal.py --db DB --output docs/data
python3 docs/scripts/render_markdown.py --input docs/data_audit.md --output docs/data_audit.html
```

> `--replace-existing` пересоздаёт слой кандидатов из `table_cell`. Он не сохраняет
> ручные переклассификации: перед запуском убедитесь, что кандидаты, привязанные к
> проверенным записям `measurement`, будут восстановлены (см. раздел 2.1 анализа).

### Локальный просмотр портала

Портал загружает данные через `fetch()`, поэтому открытие `index.html` как
`file://` не работает — нужен HTTP-сервер:

```bash
cd docs && python3 -m http.server 8777   # http://127.0.0.1:8777/
```

## Лицензия

- Составленная база данных, код и портал — [CC BY 4.0](LICENSE).
- Права на исходные статьи принадлежат их издателям. Здесь публикуются извлечённые
  числовые значения, ссылки на источник и локаторы ячеек.

Портал использует Leaflet (BSD-2-Clause), sql.js (MIT) и тайлы OpenStreetMap
(ODbL) — все библиотеки поставляются локально в `docs/assets/`.
