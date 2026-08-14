import os
import pandas as pd

from paths import DATASETS_DIR

path = os.path.join(DATASETS_DIR, "explore", "top_100_ontario_trails.json")

df = pd.read_json(path)
df = df[["ID", "slug"]]
df["url"] = df["slug"].apply(lambda x: "https://www.alltrails.com/" + x)
print(df.head())