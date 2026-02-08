import pandas as pd
import plotly.express as px
import requests

# ----------------------------
# 1) Load your main dataset + geojson
# ----------------------------
df = pd.read_csv("planet.csv")

counties_geojson = requests.get(
    "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
).json()

# ----------------------------
# 2) Load county_flip.csv and build a clean FIPS lookup table
# ----------------------------
flip = pd.read_csv("county_flip.csv", header=None, dtype=str, skiprows=4)
flip = flip.rename(columns={0:"sumlev", 1:"state_fips", 2:"county_fips", 6:"area_name"})

# state names (sumlev 040)
states = flip[flip["sumlev"] == "040"][["state_fips", "area_name"]].copy()
states = states.rename(columns={"area_name": "State"})

# county-equivalents (sumlev 050)
counties = flip[flip["sumlev"] == "050"][["state_fips", "county_fips", "area_name"]].copy()
counties["fips"] = counties["state_fips"].str.zfill(2) + counties["county_fips"].str.zfill(3)

# attach state name
counties = counties.merge(states, on="state_fips", how="left")

# ---- IMPORTANT CLEANING ORDER (fixes Juneau) ----
counties["County"] = counties["area_name"]

counties["County"] = counties["County"].str.replace(" County", "", regex=False)
counties["County"] = counties["County"].str.replace(" Parish", "", regex=False)

# Remove the LONG phrase FIRST (otherwise Borough removal breaks it)
counties["County"] = counties["County"].str.replace(" City and Borough", "", regex=False)
counties["County"] = counties["County"].str.replace(" City and", "", regex=False)

counties["County"] = counties["County"].str.replace(" Borough", "", regex=False)
counties["County"] = counties["County"].str.replace(" Census Area", "", regex=False)
counties["County"] = counties["County"].str.replace(" Municipality", "", regex=False)
counties["County"] = counties["County"].str.replace(" Municipio", "", regex=False)

# ----------------------------
# 3) Create merge keys (beginner-friendly normalization)
# ----------------------------

# Fix one known typo in your dataset (if it exists)
df.loc[(df["State"] == "Virginia") & (df["County"] == "Charles"), "County"] = "Charles City"

# Make simple keys: lower + strip
df["State_key"] = df["State"].str.strip().str.lower()
df["County_key"] = df["County"].str.strip().str.lower()

counties["State_key"] = counties["State"].str.strip().str.lower()
counties["County_key"] = counties["County"].str.strip().str.lower()

# Handle "(City)" in your dataset: "Baltimore (City)" -> "baltimore city"
df["County_key"] = df["County_key"].str.replace("(city)", " city", regex=False)

# Saint/Sainte standardization
df["County_key"] = df["County_key"].str.replace("saint ", "st ", regex=False)
counties["County_key"] = counties["County_key"].str.replace("saint ", "st ", regex=False)

df["County_key"] = df["County_key"].str.replace("sainte ", "ste ", regex=False)
counties["County_key"] = counties["County_key"].str.replace("sainte ", "ste ", regex=False)

# Final cleanup: remove punctuation + normalize spaces
df["County_key"] = df["County_key"].str.replace(".", "", regex=False)
counties["County_key"] = counties["County_key"].str.replace(".", "", regex=False)

df["County_key"] = df["County_key"].str.replace("'", "", regex=False).str.replace(",", "", regex=False)
counties["County_key"] = counties["County_key"].str.replace("'", "", regex=False).str.replace(",", "", regex=False)

df["County_key"] = df["County_key"].str.replace("-", " ", regex=False)
counties["County_key"] = counties["County_key"].str.replace("-", " ", regex=False)

# Make accented characters not matter (Doña -> Dona)
df["County_key"] = df["County_key"].str.replace("doña", "dona", regex=False)
counties["County_key"] = counties["County_key"].str.replace("doña", "dona", regex=False)

# Normalize double spaces
df["County_key"] = df["County_key"].str.replace("  ", " ", regex=False).str.strip()
counties["County_key"] = counties["County_key"].str.replace("  ", " ", regex=False).str.strip()

# ----------------------------
# 4) Merge to get FIPS
# ----------------------------
df_map = df.merge(
    counties[["State_key", "County_key", "fips"]],
    on=["State_key", "County_key"],
    how="left"
)

print("Total rows:", len(df_map))
print("Missing fips (before filtering non-US regions):", df_map["fips"].isna().sum())

# Filter out places that do not appear on Plotly's US counties map
df_map = df_map[
    ~df_map["State"].isin(["Puerto Rico", "Virgin Islands", "Country Of Mexico"])
].copy()

print("Missing fips (after filtering non-US regions):", df_map["fips"].isna().sum())

# If anything is still missing, show them:
print(df_map[df_map["fips"].isna()][["State", "County"]].sort_values(["State","County"]))

# ----------------------------
# 5) Compute bad air days
# ----------------------------
df_map["bad_air_days"] = (
    df_map["Unhealthy Days"]
    + df_map["Very Unhealthy Days"]
    + df_map["Hazardous Days"]
    + df_map["Unhealthy for Sensitive Groups Days"]
)

# ----------------------------
# 6) Bin it
# ----------------------------
df_map["bad_air_bin"] = pd.cut(
    df_map["bad_air_days"],
    bins=[-1, 0, 5, 15, 30, 1000],
    labels=["0", "1–5", "6–15", "16–30", "30+"]
)

# ----------------------------
# 7) County map (keep hover)
# ----------------------------
df_map["county_label"] = df_map["County"] + ", " + df_map["State"]

bin_order = ["0", "1–5", "6–15", "16–30", "30+"]

color_map = {
    "0":    "#41ab5d",
    "1–5":  "#a1d99b",
    "6–15": "#fec44f",
    "16–30":"#fe9929",
    "30+":  "#cc4c02"
}

fig = px.choropleth(
    df_map,
    geojson=counties_geojson,
    locations="fips",
    featureidkey="id",
    color="bad_air_bin",
    scope="usa",
    category_orders={"bad_air_bin": bin_order},
    color_discrete_map=color_map,
    hover_name="county_label",
    hover_data={
        "State": True,
        "County": True,
        "bad_air_days": True,
        "bad_air_bin": False,
        "fips": False
    }
)

fig.update_traces(marker_line_width=0.2)
fig.update_geos(subunitcolor="black", subunitwidth=1.1, showlakes=False)
fig.update_layout(
    legend_title_text="Unhealthy / Hazardous Air Days",
    margin=dict(l=0, r=0, t=30, b=0)
)
fig.show()

# ----------------------------
# 8) State totals (SUM) — overall burden
# ----------------------------
state_sum = df_map.groupby("State", as_index=False)["bad_air_days"].sum()
state_sum = state_sum.sort_values("bad_air_days", ascending=False)

fig = px.bar(
    state_sum.head(10),
    x="bad_air_days",
    y="State",
    orientation="h",
    title="Top 10 States with the Most Total Unhealthy/Hazardous Air Days (sum across counties)"
)
fig.update_layout(yaxis=dict(autorange="reversed"))
fig.show()

# ----------------------------
# 9) State averages (MEAN) — average severity per county
# ----------------------------
state_avg = df_map.groupby("State", as_index=False)["bad_air_days"].mean()
state_avg = state_avg.sort_values("bad_air_days", ascending=False)

fig = px.bar(
    state_avg.head(10),
    x="bad_air_days",
    y="State",
    orientation="h",
    title="Top 10 States by Average Unhealthy/Hazardous Air Days per County",
    labels={"bad_air_days": "Average days (per county)"}
)
fig.update_layout(yaxis=dict(autorange="reversed"))
fig.show()