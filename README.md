# Customer Engagement & Product Utilization Analytics

## Run it
1. Install Python 3.10+
2. `pip install -r requirements.txt`
3. Keep `app.py`, `analytics.py` and `European_Bank.xlsx` in the same folder
4. `streamlit run app.py`

You can also upload a different dataset (xlsx or csv) from the sidebar.

## Files
- `app.py`        Streamlit dashboard (5 tabs: engagement, products, high-value disengaged, retention strength, data quality)
- `analytics.py`  Validation, engagement profiles, KPIs, Relationship Strength Index
- `European_Bank.xlsx`  Dataset (10,000 customers)

## Deploy free
Push the folder to GitHub and deploy on share.streamlit.io (main file: app.py).
