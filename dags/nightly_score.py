"""Orchestration (Apache Airflow). Install: pip install apache-airflow
Place this repo's dags/ on AIRFLOW__CORE__DAGS_FOLDER, then unpause nightly_score.
"""
try:
    from airflow import DAG
    from airflow.operators.bash import BashOperator
    from datetime import datetime

    with DAG("nightly_score", start_date=datetime(2024, 11, 1),
             schedule="@daily", catchup=False, tags=["predelinq"]) as dag:
        score = BashOperator(task_id="score",
                             bash_command="cd /opt/predelinq && python -m src.scoring.score --scoring-date {{ ds }}")
        policy = BashOperator(task_id="policy",
                              bash_command="cd /opt/predelinq && python -m src.policy.engine --scoring-date {{ ds }}")
        score >> policy
except ImportError:
    print("airflow not installed — DAG inactive until pip install apache-airflow")
