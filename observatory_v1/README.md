# observatory_v1 — extraction pipeline

Provenance-first pipeline behind the Russian Soil Observatory. Core rules that
every stage obeys:

- OCR/table output is **evidence, not an observation**: it enters `extraction`
  before it can create a site, profile, horizon or measurement.
- A translation and its original stay separate `document` rows; `document_link`
  is used only after a relationship is actually checked.
- Operational `site` rows must be Russian (`country_code = 'RU'`) and carry a
  spatial-confidence class.
- `profile`, `horizon`, `sample` and `laboratory_analysis` stay separate: a
  sample label or a method is never discarded when a result is normalized.
- Every accepted measurement leads back to an artifact and its extraction record.

## Воспроизводимый пайплайн (верхний уровень)

Запускается в этом порядке и полностью пересобирает публикуемый слой из
`table_cell` — матриц OCR-таблиц:

| Скрипт | Что делает |
|---|---|
| `extract_table_measurement_candidates.py` | находит числовые ячейки под распознанным заголовком свойства |
| `normalize_table_measurement_candidates.py` | приводит единицы там, где преобразование обратимо |
| `materialize_full_table_observations.py` | строит `table_observation` со статусом пространственной привязки |
| `audit_full_table_observations.py` | проверяет, что не потеряна ни одна ячейка |
| `flag_observation_quality.py` | помечает ненадёжные заголовки и физически невозможные значения |
| `infer_springer_publication_year.py` | восстанавливает год публикации из Pleiades DOI |
| `export_analysis_package.py` | выгружает CSV-пакет |

Вспомогательные модули верхнего уровня — не запускаются напрямую:
`table_property_patterns.py` (шаблоны заголовков и LaTeX-нормализация),
`property_catalog.py`, `method_catalog.py` (канонические словари),
`normalize_measurement_candidates.py` (преобразование единиц),
`ingest_pochvovedenie_text.py` (шаблоны глубин и горизонтов).

`schema.sql` — полная схема рабочей базы.
`v_ready_measurements` — единственное представление, готовое к прямому использованию.

> **Осторожно:** `extract_table_measurement_candidates.py --replace-existing`
> пересоздаёт слой кандидатов и **не сохраняет ручные переклассификации**.
> Порядок сохраняющей пересборки — раздел 2.1 в [`../docs/data_audit.md`](../docs/data_audit.md).

## `archive/` — история сборки корпуса

126 скриптов, которыми корпус собирался и курировался: загрузка PDF и OCR,
извлечение координат из текста, карт и таблиц, геокодирование по внешней
границе РФ, слияние дубликатов профилей, десятки аудитов и ручные
переклассификации отдельных статей (`reclassify_*`, `stage_vanchikova_*`).

Они сохранены не для повторного запуска, а как доказательная линия: часть
записей в базе существует именно потому, что человек принял по ним решение, и
эти решения задокументированы здесь. Многие скрипты рассчитывают на исходные
PDF и промежуточные CSV, которых нет в репозитории.
