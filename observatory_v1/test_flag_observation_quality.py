from flag_observation_quality import plausibility


def test_unclassified_metric_uses_proven_unit_ranges():
    assert plausibility('unclassified_table_metric', 'unclassified', 10001, 'cm', 'exact')[0] == 'out_of_physical_range'
    assert plausibility('unclassified_table_metric', 'unclassified', 101, '%', 'exact')[0] == 'out_of_physical_range'
    assert plausibility('unclassified_table_metric', 'unclassified', 100, 'mg/kg', 'exact')[0] == 'ok'


def test_unclassified_metric_does_not_judge_missing_units():
    assert plausibility('unclassified_table_metric', 'unclassified', 10_000_000, None, 'missing_unit')[0] == 'ok'
