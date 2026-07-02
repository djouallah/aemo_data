# fabric_demo — Australian Electricity Market Data Archive

A raw data archive for the Australian electricity market (AEMO / NEM).  
This repo contains **only data** — daily zip files from AEMO, automatically downloaded by the CI workflow every day at 7 AM Brisbane time (21:00 UTC). No transformations, no semantic models, no notebooks.

## Data

`data/archive/<year>/` — daily zip files from [AEMO Daily Reports](https://nemweb.com.au/Reports/Current/Daily_Reports/), organized by year.  
Coverage: Queensland, New South Wales, Victoria, South Australia, Tasmania.

## Transformation repos

If you want to transform this data into Delta / Iceberg / DWH tables on Microsoft Fabric, see:

| Repo | Storage format | Tool |
|------|---------------|------|
| [dbt_fabric_python_delta](https://github.com/djouallah/dbt_fabric_python_delta) | Delta Lake | [duckrun](https://github.com/djouallah/duckrun) |
| [dbt_fabric_python_iceberg](https://github.com/djouallah/dbt_fabric_python_iceberg) | Apache Iceberg | dbt-duckdb |
| [dbt_fabric_python_dwh](https://github.com/djouallah/dbt_fabric_python_dwh) | Delta Lake (Fabric DWH) | Fabric DWH adapter |
| [dbt_fabric_python_ducklake](https://github.com/djouallah/dbt_fabric_python_ducklake) | DuckLake | dbt-duckdb |

## CI

`.github/workflows/download-files.yml` runs daily, fetches new zip files from AEMO, skips any already present, and commits them to `data/archive/`.