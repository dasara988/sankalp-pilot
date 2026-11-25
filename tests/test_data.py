"""Cleaning and lookups in agent/data.py, against the real extracts."""
import pandas as pd

from agent import data


def test_messy_codes_are_cleaned():
    assert data.clean_stockist(pd.Series([" stk0054 "])).iloc[0] == "STK0054"
    assert data.clean_sku(pd.Series(["PFL-1301"])).iloc[0] == "PFL1301"
    assert data.clean_cnf(pd.Series(["CFN01"])).iloc[0] == "CF-N01"
    assert data.clean_invoice("inv-s02-2510-053444") == "INV/S02/2510/053444"


def test_three_date_formats_parse_to_the_same_day():
    out = data.parse_date(pd.Series(["16-10-2026", "2026-10-16", "16-Oct-2026"]))
    assert out.nunique() == 1 and out.iloc[0] == pd.Timestamp("2026-10-16")


def test_repeated_rows_are_removed():
    t = data.tables()
    assert len(t["sales"]) == 93063        # 93,809 rows, 746 repeats
    assert len(t["claims"]) == 4503        # 4,526 rows, 23 repeats


def test_lookups_return_the_row_and_its_line_number():
    b = data.get_batch("k2440124")
    assert b["sku_code"] == "PFL1401" and b["row_id"] == 413
    assert data.get_stockist("STK0143")["stockist_name"] == "Matrix Medicos"
    assert data.get_claim("CLM-2607-02627")["row_id"] == 4060


def test_unknown_values_are_not_found():
    assert data.get_batch("K23O0830") is None          # letter O, not zero: never corrected
    assert data.get_stockist("") is None
    assert data.get_claim("CLM-2609-99999") is None
