from scripts.wp07_candidate import ROOT, config_schema, migration


def test_wp07_manifest_inputs_match_candidate_contract():
    assert migration() == {
        "root": "0001_initial",
        "head": "0010_wp06_governance",
        "revision_count": 10,
    }
    assert config_schema() == 1
    assert (ROOT / "contracts" / "openapi.json").is_file()


def test_manifest_inputs_are_literal_and_linear():
    assert migration()["head"] == "0010_wp06_governance"
    assert config_schema() == 1
