from ledger_etl.util import round2, same_money, to_iso_date


def test_round2_half_up():
    assert round2(1.005) == 1.01
    assert round2(2.004) == 2.00


def test_round2_numeric_strings():
    assert round2("12.345") == 12.35
    assert round2("abc") == 0.0
    assert round2(None) == 0.0


def test_same_money():
    assert same_money(0.1 + 0.2, 0.3)
    assert not same_money(1.11, 1.12)


def test_to_iso_date_variants():
    assert to_iso_date(20210401) == "2021-04-01"
    assert to_iso_date(20210401.0) == "2021-04-01"
    assert to_iso_date("2021/04/01") == "2021-04-01"
    assert to_iso_date(None) is None


if __name__ == "__main__":
    import sys
    import pytest

    # 方便单独试验：python tests/test_xxx.py [-k foo]
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
