# AWS: QuickSight dashboard. UNCOMMENT / configure after backend ready.
# TODO (backend):
#  1. Point Redshift (aws/data_notify_store.py) as QuickSight dataset (SPICE refresh daily).
#  2. Recreate Dash views: risk mix donut, score histogram, alerts table, drift.
#  3. Row-level security: bank role = all customers; customer role = own customer_id.
# Local Dash (src/dashboard/risk_dashboard.py) remains the dev equivalent.
