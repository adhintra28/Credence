# AWS wiring — ALL COMMENTED until you configure backend (no credentials in repo).
# Each file below is a ready-to-uncomment template mapped to your AWS stack.

# 1) ML Platform (SageMaker training + hosting) .... see aws/sagemaker_train_deploy.py
# 2) Streaming (Kinesis real-time ingestion) ........ see aws/kinesis_ingest.py
# 3) Feature Store (SageMaker Feature Store) ....... see aws/sagemaker_feature_store.py
# 4) Database (Redshift historical analysis) ....... see aws/redshift.py
# 5) Real-time DB (DynamoDB risk scores) ........... see aws/dynamodb_scores.py
# 6) Notifications (SNS interventions) ............. see aws/sns_notify.py
# 7) Dashboard (QuickSight) ........................ see aws/quicksight_README.md
#
# TODO (backend checklist):
#  [ ] `aws configure` (region, keys) or IAM role
#  [ ] Fill TODOs in each file (role ARNs, stream names, table names, topic ARNs)
#  [ ] `pip install boto3 sagemaker`
#  [ ] Uncomment + test one service at a time; batch CSV pipeline keeps working regardless.
