from ledger_etl.project_map import UNKNOWN, load_project_map, match_project


def test_load_default(env):
    pmap = load_project_map(env.map_path)
    assert pmap["A01"] == "A项目"
    assert pmap["B01"] == "B项目"


def test_match_hit_and_miss(env):
    pmap = load_project_map(env.map_path)
    assert match_project("A01#支付货款-甲公司", pmap) == "A项目"
    assert match_project("完全不含编码的摘要", pmap) == UNKNOWN


if __name__ == "__main__":
    import sys
    import pytest

    # 方便单独试验：python tests/test_xxx.py [-k foo]
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
