# Журнал восстановления БД — 2026-08-09

## Контрольная точка

- Рабочая БД после строгой материализации: `C:\tmp\rso_rebuild_strict_20260807b.sqlite`, 40,595 строк в `table_observation`.
- Найдена локальная копия до последней строгой материализации: `database/russian_soil_observatory (копия с компьютера GEONINJA) (2).sqlite`, 118,924 строки.
- В старой копии: 4,521 document, 39,756 source_artifact, 302,104 candidate.
- В текущей: 4,862 document, 41,638 source_artifact, 366,485 candidate.
- По candidate_id совпадают все 118,924 старых наблюдения; потеря вызвана не исчезновением исходных кандидатов, а их статусной фильтрацией.
- Только 12,166 observation candidate_id совпадают между старой и текущей материализацией; 106,758 старых строк отсутствуют в текущей.

## Распределение старой копии

- `exact`: 34,988; `converted`: 3,265; `missing_unit`: 77,225; `incompatible`: 3,430; `missing_value`: 16.
- `qa_status`: normalized 37,512; unit_missing 77,216; unit_incompatible 3,430; flagged 749; missing_value 17.
- Старая копия не является безопасной финальной версией: 118,826 из её observation-кандидатов имели status `unreviewed` в старой таблице кандидатов.

## Причина расхождения

В текущей БД старые observation-кандидаты получили status `rejected` вследствие массовой статусной сверки/квартиранизации. Для старых строк текущая очередь показывает: `resolved_reparse` — 85,593, `resolved_accept` — 7,212, `resolved_reject` — 547, без записи очереди — остальные. Поэтому старые строки нельзя возвращать целиком: подтверждённые (`resolved_accept`, с явной единицей) нужно восстановить; `resolved_reparse` и unitless — оставить в ручном разборе до подтверждения.

## Правило восстановления

Не подменять финальную БД старой копией и не возвращать все 118,924 строк. Восстановить в отдельную рабочую копию только старые строки, для которых есть текущий `resolved_accept` или иной явный provenance и есть `exact/converted` единица; затем проверить единицы, координаты, дубли, FK и покрытие. Все остальные сохранить как кандидаты/очередь ручного разбора.

## Следующий шаг

Сделать резерв текущей БД, материализовать подтверждённое множество из старого снимка в новую рабочую копию, затем прогнать полные аудиты. Рабочую синхронизированную БД не перезаписывать до успешной проверки.

## Контрольная точка после агентской сверки

- Рабочая копия: `C:\tmp\rso_recovery_work_20260809.sqlite`.
- В архиве сохранены все 118,924 старые строки; создан отдельный `recovery_manual_queue`.
- Три агента проверили unit/header для basic Springer и русских таблиц; независимый верификатор проверил 2,113 предложений.
- Безопасно принято к materialization: 1,231 candidate_id; исключены 369 переводных дублей, 259 строк без row/profile context и 254 предложения с JSON вместо единицы.
- После materialization: `table_observation=41,826`, все строки имеют numeric/text value, непустую нормализованную единицу и provenance; `integrity_check=ok`, `foreign_key_check=[]`.
- Открыто в ручном контуре: 105,527 старых строк. Они намеренно не входят в `table_observation`; это не потеря, а ожидаемая очередь точечного разбора.
- Проверка unitless C/N следует отдельному правилу: принимается только при явном `C/N` или `C:N` в заголовке, с `unit_inference_status=inferred_from_verified_table_header` и без физической единицы (`1`).

## Контрольная точка после второго текстового прохода

- Второй проход по статье/методике/подписи проверил basic properties, metals/ions/EC и русские таблицы.
- Независимая верификация проверила 2,120 предложений: 1,515 безопасных, 605 удержаны из-за контекста/дубликата/непрямого доказательства.
- В рабочую копию материализовано дополнительно 1,515 строк; всего `table_observation=43,341`.
- `integrity_check=ok`, `foreign_key_check=[]`, пустых нормализованных единиц нет, provenance заполнен у всех строк.
- В ручном контуре осталось `104,012` открытых задач; они не были автоматически перенесены в подтверждённый слой.

## Контрольная точка после третьего прохода

- Третий проход проверил 2,968 candidate-level предложений; независимый агент подтвердил 1,053 и удержал 1,915.
- Материализовано ещё 1,053 строки; рабочая копия содержит `table_observation=44,394`.
- Проверки: `integrity_check=ok`, `foreign_key_check=[]`, `blank_units=0`, provenance отсутствует у 0 строк.
- Открытая manual-очередь: `102,959` строк; она остаётся отдельной и не считается подтверждённым слоем.

## Контрольная точка после четвёртого прохода

- Четвёртый проход проверил крупные Springer-блоки: 11,155 exact/converted кандидатов и 14,530 unit/context кандидатов.
- Безопасно подтверждены агентами: 7,068 и 8,761 соответственно; все candidate-level, с числом, контекстом и прямым unit evidence.
- Материализовано ещё 15,829 строк; `table_observation=60,223`.
- Проверки после записи: `integrity_check=ok`, `foreign_key_check=[]`, `blank_units=0`, provenance отсутствует у 0 строк.
- `unclassified_table_metric` намеренно не материализован: для него сначала требуется восстановить имя свойства, а не только единицу.
- Открытая manual-очередь: `87,130` строк.

## Контрольная точка после дедупликации и mapping unclassified

- Mapping-агент однозначно сопоставил 354 `unclassified_table_metric` строки с существующими properties; они материализованы вместе с unit evidence.
- После четвертого раунда и mapping слой достиг `60,577`, затем удалены 134 явных OCR namespace-дубля и 4 точных дубля одной RCSI-ячейки.
- Финальный текущий счёт рабочей копии: `table_observation=60,436`.
- Дедупликационный аудит по ключу document/artifact/row/column/property/value/unit/row-label/horizon: `0` групп с повтором.
- Проверки: `integrity_check=ok`, `foreign_key_check=[]`, `blank_units=0`, provenance отсутствует у 0 строк.
- Открытая manual-очередь после возврата дублей в ручной контур: `86,910` строк.

## Контрольная точка после пятого прохода

- Раунд 5 дал 4,543 применимых к legacy archive строк из больших provenance/unit/physical блоков; остальные safe-кандидаты относились к новым кандидатным слоям либо не имели legacy observation-строки и не были смешаны с восстановлением.
- После materialization и повторной дедупликации: `table_observation=64,893`.
- Все повторные namespace-дубли удалены из materialized слоя и сохранены в archive/manual provenance.
- Проверки: `integrity_check=ok`, `foreign_key_check=[]`, `blank_units=0`, provenance отсутствует у 0 строк, semantic duplicate groups=0.
- Открытая manual-очередь: `82,453` строк.

## Контрольная точка после шестого прохода

- Шестой проход проверил 39,579 unclassified-кандидатов (202 mapped), 23,411 остаточных unit-кандидатов (1,946 safe) и 76,587 provenance-кандидатов без новых safe-строк.
- Materialized дополнительно 2,148 строк; после удаления 51 namespace-дубля текущий слой: `table_observation=66,990`.
- Контроль: `integrity_check=ok`, `foreign_key_check=[]`, `blank_units=0`, provenance отсутствует у 0 строк, semantic duplicate groups=0.
- Открытая manual-очередь: `80,356` строк; оставшиеся строки не имеют достаточного source-grounded доказательства для подтверждённого слоя.
## 2026-08-09 — mandatory text review of missing units

The previous closure treated `unit_missing` as a withholding reason too early. Per the user's rule, absence of a unit in a table header is not sufficient for rejection: the article's full OCR/text, methods, table captions, and surrounding text must be checked manually. A separate queue was created in `C:\tmp\rso_recovery_work_20260809.sqlite` as `recovery_text_unit_review`.

Scope: all 58,011 archived observations with `current_present=0` and `normalization_status='missing_unit'`; 1,270 documents, 1,856 artifacts. 56,016 queue rows have a usable linked extraction text. No rows were added to `table_observation` at this stage. Three agents were assigned disjoint rowid partitions for candidate-level evidence review.

The three partitions produced 58,011/58,011 candidate decisions. Independent verification reviewed all 38,476 initial ACCEPT proposals: 29,020 remained acceptable and 9,456 were rejected. After exact namespace deduplication, 28,042 new text-unit observations were retained; the full working table contains 95,215 observations, with no blank units, no foreign-key violations, and no exact duplicate keys. All 58,011 queue rows now have an explicit text-review outcome (`resolved_accept`, `reviewed_text_no_direct_unit`, or `reviewed_duplicate`).

The independent coordinate audit examined 11,169 observations from 556 documents and generated 3,311 unambiguous observation-to-site actions. Those actions were applied with `document_single_reported_coordinate` or `document_multiple_reported_coordinates` according to the document's reported-coordinate cardinality. A residual audit queue remains for multi-site documents where a row-level site cannot be selected safely; it is not silently assigned to a guessed point. Confirmed document links remain 625 `translation_of` and 341 `same_study`.

Translation deduplication then removed 106 English Springer observations identified as exact counterparts of Russian observations in 117 confirmed translation matches; Russian observations were retained as canonical, and provenance/review statuses were updated. Final working count after this pass: 95,109 observations. The final integrity checks remain clean: no blank units, no foreign-key violations, no exact duplicate keys, and no open manual queue rows.

Residual coordinate review added 70 explicit single-coordinate sites/links for 1,949 observations and filled 58 explicit profile/site coordinates from a second mismatch audit. The residual 1,002 observations belong to 27 multi-coordinate or otherwise ambiguous documents; they remain without guessed row-level site assignments, with the ambiguity documented in `C:\tmp\coord_residual_single.md` and `C:\tmp\coord_residual_mismatch.md`. Current coordinate quality counters: 2,416 observations still lack a row site despite a document coordinate candidate, and 2,332 reference sites still lack lat/lon; these are intentionally unresolved ambiguity/reference gaps, not silently geocoded.
