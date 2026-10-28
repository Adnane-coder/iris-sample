"""Inspect and export pandapower standard transformer types."""
from importlib.metadata import version
from pathlib import Path

import pandas as pd
import pandapower as pp

net = pp.create_empty_network()
df = pp.available_std_types(net, "trafo")
df.index.name = "std_type"
df = df.reset_index()

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)

print("pandapower version:", version("pandapower"))
print("rows:", len(df))
print("columns:", list(df.columns))
print()
cols = [c for c in ["std_type", "sn_mva", "vn_hv_kv", "vn_lv_kv", "vk_percent", "vkr_percent", "vector_group"] if c in df.columns]
print(df[cols].sort_values(["vn_hv_kv", "sn_mva"]).to_string(index=False))

out = Path("data/raw/transformer_specs")
out.mkdir(parents=True, exist_ok=True)
df.to_csv(out / "pandapower_trafo_std_types_raw.csv", index=False)
print("\nsaved:", out / "pandapower_trafo_std_types_raw.csv")
