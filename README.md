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
| Полнотекстовые публикации | 4 521 |
| — «Почвоведение» | 966 |
| — Springer / *Eurasian Soil Science* | 3 555 |
| OCR-таблиц | 13 358 |
| Табличных наблюдений | 106 839 |
| Канонических свойств | 101 |
| Публикаций, давших наблюдения | 1 430 |
| Авторских координат | 1 092 (790 уникальных положений) |
| Строгий пространственный слой | 1 239 измерений |

**Архивная копия базы данных** депонирована на Zenodo:
[10.5281/zenodo.21777711](https://doi.org/10.5281/zenodo.21777711) (CC BY 4.0).

Главный принцип: **никакое числовое значение не пропадает из-за отсутствующей
координаты, но и координата документа не выдаётся за координату каждой строки
таблицы.** Каждое наблюдение хранит ссылку на исходную ячейку OCR-таблицы,
статус доказанности единицы измерения и явно указанную силу пространственной
привязки.

## Данные

Всё, что публикуется, лежит в [`docs/data/`](docs/data/):

| Файл | Что это |
|---|---|
| `full_table_observations.csv` | все 106 839 наблюдений с флагами качества и происхождением |
| `observatory.sqlite.gz` | та же база в SQLite (gzip, ~9.4 МБ) — для браузера и локального анализа |
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
  AND metric = 1;                              -- единица доказана, не предположена
-- 51 626 наблюдений из 106 839
```

- `metric` — единица определена для каждого наблюдения без исключения, но с
  разной силой; `metric = 1` означает `confidence IN ('high','medium')` в
  исходной базе (`observation_unit_inference`): `high` — напечатана в
  заголовке колонки (25.4%); `medium` — надёжно выведена из контекста статьи,
  подписи к таблице или соседних колонок (27.6%). Оставшиеся 47.0%
  (`metric = 0`, `confidence = 'low'`) — предположение, обычно каноническая
  единица показателя по умолчанию, а не то, что напечатано в статье; полный
  метод и уровень уверенности по каждому наблюдению — в
  `full_table_observations.csv` (столбцы `unit_confidence`, `unit_method`).
- `header_match_kind = 'symbol_embedded'` (5.2%) — химический символ найден внутри
  более длинного текста заголовка; вероятное ложное срабатывание.
- `spatial_linkage` — сила привязки к координате; `document_single_reported_coordinate`
  означает контекст документа, а не GPS строки таблицы.

## Ограничения

1. Точки сильно кластеризованы (индекс Кларка–Эванса 0.34, ≈ 302 независимых
   локалитета на 790 положений) — это **не вероятностная выборка** по территории России.
2. Для 626 пар статей установлено соответствие «русский оригинал ↔ перевод»
   (`document_links.csv`) — 608 подтверждено разбором печатной библиографической
   ссылки Springer на источник (журнал, год, номер, страницы), 18 дополнительно
   статусом candidate по отпечатку числовых значений таблиц; документы не
   объединяются. 146 из 201 статьи «Почвоведение», давшей наблюдения, входят в
   подтверждённые пары. Остаточная верхняя граница двойного учёта — 1.4%
   (1532 наблюдения в 39 статьях «Почвоведение», не сопоставленных ни одной парой).
3. Метка генетического горизонта заполнена у 17 401 наблюдения (16.3%) —
   достаточно для укрупнённого сравнения по горизонтам A/B/C; более детальный
   профильный анализ по-прежнему опирается в основном на числовую глубину.
4. Значения получены OCR-распознаванием и содержат ошибки; они помечены, а не удалены.

Подробно — в [аудите базы](docs/data_audit.md) и
[пространственно-временном анализе](docs/insights.md).

## Воспроизведение

Требуется рабочая база `russian_soil_observatory.sqlite` (не входит в репозиторий:
1.3 ГБ). Порядок:

```bash
pip install pandas numpy scipy matplotlib statsmodels

# каталог свойств и извлечение
python3 observatory_v1/seed_additional_properties.py --db DB
python3 observatory_v1/extract_table_measurement_candidates.py --db DB --additive
python3 observatory_v1/repair_total_npk_word_boundary.py --db DB
python3 observatory_v1/extract_table_measurement_candidates.py --db DB --additive
python3 observatory_v1/normalize_table_measurement_candidates.py --db DB
python3 observatory_v1/materialize_full_table_observations.py --db DB
python3 observatory_v1/audit_full_table_observations.py --db DB --output docs/data/full_table_observation_audit.json
python3 observatory_v1/flag_observation_quality.py --db DB --output docs/data/observation_quality_audit.json

# датировка, пространственная привязка, связь оригинал/перевод
python3 observatory_v1/infer_springer_publication_year.py --db DB --crossref docs/data/doi_metadata.csv --output docs/data/publication_year_audit.json
python3 observatory_v1/infer_document_study_region.py --db DB
python3 observatory_v1/infer_document_precise_coordinates.py --db DB
python3 observatory_v1/merge_spatial_layers.py --db DB
python3 observatory_v1/link_springer_translations.py --db DB

# сборка портала, анализа и отчётов
python3 docs/scripts/build_portal.py --db DB --output docs/data
python3 docs/scripts/build_insight_analysis.py --db DB --output docs/figures
python3 docs/scripts/build_manuscript_analysis.py --db DB --tables docs/tables --figures docs/figures --output docs/tables/manuscript_analysis.json
python3 docs/scripts/render_markdown.py --input docs/data_audit.md --output docs/data_audit.html
python3 docs/scripts/render_markdown.py --input docs/insights.md --output docs/insights.html
```

> `--additive` заполняет только ячейки без кандидата и никогда не переписывает
> существующую строку. Режим `--replace-existing` пересоздаёт слой целиком и
> **не сохраняет ручные переклассификации** — используйте его только при
> сознательной полной пересборке (см. раздел 2.1 аудита).

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
