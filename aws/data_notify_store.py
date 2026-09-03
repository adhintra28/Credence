"""AWS: SageMaker Feature Store + Redshift + DynamoDB + SNS. UNCOMMENT after backend configured.
TODO: set FEATURE_GROUP, REDSHIFT cluster/db, DYNAMO_TABLE, SNS_TOPIC_ARN from backend.
"""
# import boto3
# REGION = "TODO-backend-region"
# FEATURE_GROUP = "TODO-predelinq-features"   # SageMaker Feature Store: offline (S3) + online
# DYNAMO_TABLE = "TODO-risk_scores"           # DynamoDB: PK=customer_id, SK=scoring_date
# SNS_TOPIC_ARN = "TODO-arn:aws:sns:...:risk-alerts"  # SNS: fan-out per tier
# REDSHIFT = {"cluster": "TODO-rs-predelinq", "db": "TODO-predelinq", "table": "features"}
#
# def save_score(customer_id, scoring_date, score, tier, reasons):
#     boto3.resource("dynamodb", region_name=REGION).Table(DYNAMO_TABLE).put_item(
#         Item={"customer_id": customer_id, "scoring_date": scoring_date,
#               "score": str(score), "tier": tier, "reasons": reasons})
#
# def notify(phone_or_email, message):
#     boto3.client("sns", region_name=REGION).publish(TopicArn=SNS_TOPIC_ARN, Message=message)
#     # Redshift historical analysis: COPY processed parquet -> staging, then model SQL there.
