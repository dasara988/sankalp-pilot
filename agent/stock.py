"""Stock health by C&F: plain code, no model.

Answers three questions for the supply chain team, at the latest month-end snapshot:
  1. Which C&F is short and which is long (months of cover, SKUs at zero)?
  2. Which SKUs sit short at one C&F while another holds more than 2 months? (stock in the wrong place)
  3. Is each C&F picking the oldest batch first (FEFO), and how much stock is below 60% shelf life?
"""
from functools import lru_cache

import pandas as pd

import config
from agent.data import tables


@lru_cache(maxsize=1)
def stock_health() -> dict:
    t = tables()
    stock, sku, sales = t["stock"], t["sku"], t["sales"]
    pts = sku.set_index("sku_code").pts_inr
    shelf = sku.set_index("sku_code").shelf_life_months
    names = sku.set_index("sku_code").product_description
    city = stock.groupby("cnf_code").cnf_city.first()
    latest = stock.snapshot_date.max()

    # Several rows per C&F and batch are storage locations: sum them.
    by_sku = stock.groupby(["snapshot_date", "cnf_code", "sku_code"]).agg(
        qty=("qty_on_hand_packs", "sum"), out=("avg_monthly_outward_packs", "max")).reset_index()
    now = by_sku[by_sku.snapshot_date == latest].copy()
    now["value"], now["out_value"] = now.qty * now.sku_code.map(pts), now.out * now.sku_code.map(pts)
    now["cover"] = now.qty / now.out.where(now.out > 0)

    # FEFO: share of dispatch value picked from a newer batch while an older, pickable batch
    # sat in stock at both the start and the end of the month (SC-AGR-CF-003 cl 6.3)
    held = stock[stock.batch_no != ""].groupby(["snapshot_date", "cnf_code", "sku_code", "batch_no", "expiry_date"]) \
        .qty_on_hand_packs.sum().reset_index()
    held = held[held.qty_on_hand_packs > 0]
    snaps = sorted(held.snapshot_date.unique())[-4:]          # last three months
    s = sales[sales.batch_no != ""].merge(t["batch"][["batch_no", "expiry_date"]], on="batch_no")
    s["value"] = (s.invoiced_qty + s.free_qty) * s.pts_inr
    picks = []
    for a, b in zip(snaps[:-1], snaps[1:]):
        both = held[held.snapshot_date == a].merge(held[held.snapshot_date == b],
                                                   on=["cnf_code", "sku_code", "batch_no", "expiry_date"])
        both = both[(both.expiry_date - b).dt.days > 60]
        oldest = both.groupby(["cnf_code", "sku_code"]).expiry_date.min().rename("oldest").reset_index()
        w = s[(s.invoice_date > a) & (s.invoice_date <= b)].merge(oldest, on=["cnf_code", "sku_code"])
        w["off"] = w.expiry_date > w.oldest
        picks.append(w)
    picks = pd.concat(picks)

    # Shelf life left on stock held now (CO-POL-014 s7.1)
    h = held[held.snapshot_date == latest].copy()
    h["share_left"] = (h.expiry_date - latest).dt.days / (h.sku_code.map(shelf) * 30.44)
    h["value"] = h.qty_on_hand_packs * h.sku_code.map(pts)
    aged = h[h.share_left < config.MIN_SHELF_LIFE_SHARE]

    cfas = []
    for cnf, g in now.groupby("cnf_code"):
        p = picks[picks.cnf_code == cnf]
        cfas.append({
            "cnf_code": cnf, "city": city.get(cnf, ""),
            "stock_cr": round(g.value.sum() / 1e7, 2),
            "cover_months": round(g.value.sum() / g.out_value.sum(), 2),
            "skus_at_zero": int((g.qty <= 0).sum()),
            "above_target_cr": round(((g.qty - config.TARGET_COVER_MONTHS * g.out).clip(lower=0) * g.sku_code.map(pts)).sum() / 1e7, 2),
            "below_target_cr": round(((config.TARGET_COVER_MONTHS * g.out - g.qty).clip(lower=0) * g.sku_code.map(pts)).sum() / 1e7, 2),
            "off_fefo_pct": round(float(p.loc[p.off, "value"].sum() / p.value.sum() * 100), 1) if len(p) else 0.0,
            "aged_lakh": round(aged[aged.cnf_code == cnf].value.sum() / 1e5, 1),
        })

    wrong_place = []
    for sku_code, g in now.groupby("sku_code"):
        short, long_ = g[g.cover < 0.5], g[g.cover > config.TARGET_COVER_MONTHS]
        if len(short) and len(long_):
            need = int((config.TARGET_COVER_MONTHS * short.out - short.qty).clip(lower=0).sum())
            spare = int((long_.qty - config.TARGET_COVER_MONTHS * long_.out).sum())
            wrong_place.append({"sku_code": sku_code, "product": names.get(sku_code, ""),
                                "short_at": ", ".join(short.cnf_code), "long_at": ", ".join(long_.cnf_code),
                                "packs_to_move": min(need, spare)})

    top_aged = aged.sort_values("value", ascending=False).head(10)
    return {
        "as_of": latest.strftime("%d %b %Y"),
        "fefo_months": f"{pd.Timestamp(snaps[0]).strftime('%b %Y')} to {pd.Timestamp(snaps[-1]).strftime('%b %Y')}",
        "national_cover_months": round(now.value.sum() / now.out_value.sum(), 2),
        "cfas": sorted(cfas, key=lambda c: c["cnf_code"]),
        "wrong_place": sorted(wrong_place, key=lambda r: -r["packs_to_move"]),
        "aged_lots": [{"cnf_code": r.cnf_code, "sku_code": r.sku_code, "product": names.get(r.sku_code, ""),
                       "batch_no": r.batch_no, "expiry": r.expiry_date.strftime("%d %b %Y"),
                       "packs": int(r.qty_on_hand_packs), "shelf_life_left_pct": round(r.share_left * 100),
                       "value_lakh": round(r.value / 1e5, 2)} for r in top_aged.itertuples()],
    }
