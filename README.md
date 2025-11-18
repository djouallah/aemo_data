# Fabric Demo - Australian Electricity Market Data

A ready-to-use solution for ingesting and analyzing Australian electricity market data in Microsoft Fabric.

1. Download the Python Notebook (process_data) from this repo, notice, it is a pure python notebook and does not require spark
2. Import it to Fabric Workspace
3.  click **Run All**

## 📋 Overview

This repository provides an automated data pipeline for the Australian electricity market. Simply download the notebook and run it in your Microsoft Fabric workspace to start collecting and analyzing energy market data.

## 🎯 What You'll Get

- **Automated Data Collection**: Fetch Australian electricity market data automatically
- **Incremental Data Loading**: Loads historical data progressively to handle GitHub API limits and notebook session timeouts
- **Scheduled Updates**: Keep your data fresh with automated daily/5 minutes updates
- **Ready for Analysis**: Data is immediately available for Power BI reports and analysis

## 📊 About the Data

The data comes from the Australian Energy Market Operator (AEMO), covering the National Electricity Market (NEM) across Queensland, New South Wales, Victoria, South Australia, and Tasmania.

The dataset includes:
- **Market Prices**: Electricity spot prices by region
- **Demand Data**: Power consumption patterns
- **Generation Data**: Energy production by source
- **Regional Breakdowns**: Data for each Australian state in the NEM

## 🚀 How to Use (optional)

     Update the following values:
   - **Workspace**: by default it use the current workspace, but you can use any other workspace
   - **Lakehouse**: Your lakehouse name (no spaces)
   - **Schema**: Your schema name (no spaces)
   - **Semantic Model**: the name of your Semantic Model
5. **⚠️ IMPORTANT**: Ensure none of these names contain spaces
   - Use underscores instead: `my_workspace` not `my workspace`

     <img width="1352" height="193" alt="image" src="https://github.com/user-attachments/assets/c26546a7-29e3-49a3-93ba-d73724bc27e3" />

###  Schedule Automatic Updates

To keep your data updated and continue loading historical data:

1. In your Fabric workspace, create a new **Pipeline**
2. Add a **Notebook activity** to the pipeline
3. Select the notebook you uploaded
4. Configure the schedule (recommended: run every hour or daily, or 5 minutes)
   - For initial backfill: First run take around 17 minutes then 7 minutes once completed it will take around 1 minutes to load 5 minutes data
5. **⚠️ IMPORTANT**: Set **Concurrency to 1** in the pipeline settings
   - This ensures only one instance runs at a time
   - Prevents data duplication and conflicts
6. Save and activate the pipeline

### Why Concurrency = 1?

Setting concurrency to 1 means only one copy of the pipeline runs at any time. This is critical because:
- Prevents duplicate data loading
- Avoids conflicts when updating the same data
- Ensures data consistency and accuracy
- Allows the incremental load process to work correctly

  <img width="836" height="257" alt="image" src="https://github.com/user-attachments/assets/4ef043b8-fc33-466e-905b-f246b0819aca" />



## 🔧 Common Use Cases

- **Energy Cost Analysis**: Track and forecast electricity costs
- **Demand Forecasting**: Predict future energy consumption
- **Market Intelligence**: Understand pricing patterns and market dynamics
- **Operational Planning**: Plan energy usage during low-price periods
- **Sustainability Reporting**: Monitor renewable energy generation

## 📚 Helpful Resources

### Microsoft Fabric Documentation
- [Getting Started with Fabric](https://learn.microsoft.com/en-us/fabric/get-started/)
- [Working with Python Notebooks](https://learn.microsoft.com/en-us/fabric/data-engineering/using-python-experience-on-notebook)
- [Creating Data Pipelines](https://learn.microsoft.com/en-us/fabric/data-factory/create-first-pipeline-with-sample-data)

### Main Python packages
- [Duckrun, a simple task runner powered by DuckDB and Delta_rs](https://github.com/djouallah/duckrun)
- [Obstore, Interacting with Onelake Files](https://github.com/developmentseed/obstore)

### Australian Energy Market
- [AEMO Official Website](https://aemo.com.au/)
- [Understanding the NEM](https://aemo.com.au/en/energy-systems/electricity/national-electricity-market-nem)




## 🔧 How It Works

This solution is a simple scheduler that automates data ingestion:

1. **Reads Configuration Files**: The notebook reads SQL and Python files from this GitHub repository
2. **Executes Scripts**: Runs the scripts in sequence to fetch and process Australian electricity market data
3. **Generates Delta Tables**: Automatically creates and updates Delta tables in your Lakehouse
4. **Incremental Processing**: Tracks progress and resumes where it left off on each run

The beauty of this approach is that all your data logic is stored in the GitHub repository as SQL and Python files, while the notebook acts as the orchestration engine that brings it all together, it would be even easier when duckdb add support for writing delta

<img width="1502" height="763" alt="image" src="https://github.com/user-attachments/assets/4f41bb98-637a-4781-a868-c97b317e4e6b" />


## 🔧 How to run Benchmarks

download and run Benchmarks notebook, it will create a new lakehouse, download the data, create a new semantic model and run the test, store the results and run some analysis

<img width="707" height="284" alt="image" src="https://github.com/user-attachments/assets/fc946768-f82b-46d0-82d9-aeab11d0103c" />

