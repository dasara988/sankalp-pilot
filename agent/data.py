"""Loads the seven CSVs once, cleans them, and answers exact lookups.

No model is used here. Every fact the tool shows comes from these tables, and every
row keeps `row_id`: its line number in the original CSV (the header is line 1), so a
person can open the file and find it.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------- cleaning helpers
def parse_date(s: pd.Series) -> pd.Series:
    """The extracts use three date formats: 01-04-2024, 2024-04-01 and 01-Apr-2024."""
    s = s.astype(str).str.strip()
    out = pd.to_datetime(s, format="%d-%m-%Y", errors="coerce")
    out = out.fillna(pd.to_datetime(s, format="%Y-%m-%d", errors="coerce"))
    out = out.fillna(pd.to_datetime(s, format="%d-%b-%Y", errors="coerce"))
    return out


def parse_num(s: pd.Series) -> pd.Series:
    """Some numbers carry thousands separators, such as '3,615.00'."""
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.strip().replace("", np.nan), errors="coerce")


def clean_stockist(s: pd.Series) -> pd.Series:   # 'stk0054 ' -> 'STK0054'
    return s.astype(str).str.strip().str.upper()


def clean_sku(s: pd.Series) -> pd.Series:        # 'PFL-1301' -> 'PFL1301'
    return s.astype(str).str.strip().str.upper().str.replace("-", "", regex=False)


def clean_cnf(s: pd.Series) -> pd.Series:        # 'CFN01' -> 'CF-N01'
    return s.astype(str).str.strip().str.upper().str.replace(r"^CF-?", "CF-", regex=True)


def clean_batch(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper()


def clean_invoice(value: str) -> str:
    """'INV-S02-2510-053444' and 'inv/s02/2510/053444' both become 'INV/S02/2510/053444'."""
    return str(value or "").strip().upper().replace("-", "/")


def _read(name: str) -> pd.DataFrame:
    df = pd.read_csv(DATA / f"{name}.csv", dtype=str, keep_default_na=False)
    df.insert(0, "row_id", np.arange(2, len(df) + 2))
    return df


def _drop_repeats(df: pd.DataFrame) -> pd.DataFrame:
    """Remove rows that repeat exactly once codes and dates are cleaned (keeps the first)."""
    return df[~df.drop(columns="row_id").duplicated()].copy()


# ---------------------------------------------------------------- load once
@lru_cache(maxsize=1)
def tables() -> dict:
    sku = _read("sku_master")
    sku["sku_code"] = clean_sku(sku.sku_code)
    for c in ["pts_inr", "mrp_inr", "shelf_life_months"]:
        sku[c] = parse_num(sku[c])

    batch = _read("batch_master")
    batch["batch_no"], batch["sku_code"] = clean_batch(batch.batch_no), clean_sku(batch.sku_code)
    batch["mfg_date"], batch["expiry_date"] = parse_date(batch.mfg_date), parse_date(batch.expiry_date)

    stockist = _read("stockist_master")
    stockist["stockist_code"], stockist["cnf_code"] = clean_stockist(stockist.stockist_code), clean_cnf(stockist.cnf_code)

    sales = _read("primary_sales")
    sales["invoice_no"] = sales.invoice_no.map(clean_invoice)
    sales["invoice_date"] = parse_date(sales.invoice_date)
    sales["stockist_code"], sales["sku_code"] = clean_stockist(sales.stockist_code), clean_sku(sales.sku_code)
    sales["cnf_code"], sales["batch_no"] = clean_cnf(sales.cnf_code), clean_batch(sales.batch_no)
    for c in ["ordered_qty", "invoiced_qty", "free_qty", "pts_inr", "net_value_inr"]:
        sales[c] = parse_num(sales[c])
    sales["scheme_code"] = sales.scheme_code.str.strip().replace({"NA": "", "-": ""})
    sales = _drop_repeats(sales)

    stock = _read("cnf_stock_snapshot")
    stock["snapshot_date"], stock["expiry_date"] = parse_date(stock.snapshot_date), parse_date(stock.expiry_date)
    stock["cnf_code"], stock["sku_code"] = clean_cnf(stock.cnf_code), clean_sku(stock.sku_code)
    stock["batch_no"] = clean_batch(stock.batch_no)
    for c in ["qty_on_hand_packs", "avg_monthly_outward_packs"]:
        stock[c] = parse_num(stock[c])
    stock = _drop_repeats(stock)

    claims = _read("expiry_claims")
    claims["claim_no"] = claims.claim_no.str.strip().str.upper()
    for c in ["claim_date", "expiry_date_as_claimed", "credit_note_date"]:
        claims[c] = parse_date(claims[c])
    claims["stockist_code"], claims["sku_code"] = clean_stockist(claims.stockist_code), clean_sku(claims.sku_code)
    claims["cnf_code"], claims["batch_no"] = clean_cnf(claims.cnf_code), clean_batch(claims.batch_no)
    for c in ["qty_claimed", "claim_value_inr", "credit_value_inr"]:
        claims[c] = parse_num(claims[c])
    claims = _drop_repeats(claims)

    emails = pd.read_csv(DATA / "claim_emails.csv", dtype=str, keep_default_na=False)
    return dict(sku=sku, batch=batch, stockist=stockist, sales=sales, stock=stock, claims=claims, emails=emails)


# ---------------------------------------------------------------- lookups (exact, or "not found")
def _row(df: pd.DataFrame) -> dict | None:
    return None if df.empty else df.iloc[0].to_dict()


def get_stockist(code: str) -> dict | None:
    s = tables()["stockist"]
    return _row(s[s.stockist_code == str(code or "").strip().upper()])


def get_batch(batch_no: str) -> dict | None:
    """Batch master joined to the SKU master."""
    t = tables()
    b = t["batch"][t["batch"].batch_no == str(batch_no or "").strip().upper()]
    if b.empty:
        return None
    return b.merge(t["sku"].drop(columns="row_id"), on="sku_code", how="left").iloc[0].to_dict()


def supplies(stockist_code: str, batch_no: str) -> pd.DataFrame:
    """Every invoice line of this batch to this stockist."""
    s = tables()["sales"]
    return s[(s.stockist_code == stockist_code) & (s.batch_no == batch_no)]


def invoice_lines(invoice_no: str) -> pd.DataFrame:
    s = tables()["sales"]
    return s[s.invoice_no == clean_invoice(invoice_no)]


def earlier_claims(stockist_code: str, batch_no: str) -> pd.DataFrame:
    """Claims already in the register for this stockist and batch, still pending or credited."""
    c = tables()["claims"]
    return c[(c.stockist_code == stockist_code) & (c.batch_no == batch_no) & c.status.isin(["Pending", "Credited"])]


def get_claim(claim_no: str) -> dict | None:
    c = tables()["claims"]
    return _row(c[c.claim_no == str(claim_no or "").strip().upper()])


def sample_emails() -> list[dict]:
    e = tables()["emails"].sort_values("email_id")
    return e.to_dict("records")
