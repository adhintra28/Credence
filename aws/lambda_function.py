"""S3-triggered publisher for batch risk scores and policy-approved alerts.

Lambda variables: DYNAMODB_RISK_SCORES_TABLE, SNS_ALERT_TOPIC_ARN, and
Trigger only ``outputs/risk_scores_*.csv`` and ``outputs/alerts_*.csv``. The
Lambda role needs S3 read, DynamoDB PutItem, and SNS Publish permissions.
"""
import csv
import io
import json
import os
from decimal import Decimal
from urllib.parse import unquote_plus

import boto3

REGION = os.getenv("AWS_REGION", "ap-south-1")
s3 = boto3.client("s3", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)
sns = boto3.client("sns", region_name=REGION)


def lambda_handler(event, context):
    table = dynamodb.Table(os.environ["DYNAMODB_RISK_SCORES_TABLE"])
    topic_arn = os.environ["SNS_ALERT_TOPIC_ARN"]
    processed = notified = 0
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        if not key.startswith("outputs/") or not key.endswith(".csv"):
            continue
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8-sig")
        for row in csv.DictReader(io.StringIO(body)):
            if key.startswith("outputs/alerts_"):
                sns.publish(TopicArn=topic_arn, Subject="Pre-delinquency policy alert",
                            Message=row.get("message") or json.dumps(row))
                notified += 1
                continue
            if not key.startswith("outputs/risk_scores_"):
                continue
            score = Decimal(str(row["score"]))
            try:
                reasons = json.loads(row.get("reasons", "[]"))
            except json.JSONDecodeError:
                reasons = []
            item = {"customer_id": row["customer_id"], "scoring_date": row["scoring_date"],
                    "risk_score": score, "risk_level": row.get("tier", "Green"),
                    "top_reason": row.get("top_reason") or (reasons[0] if reasons else ""),
                    "reasons": reasons, "model_version": row.get("model", "")}
            table.put_item(Item=item)
            processed += 1
    return {"statusCode": 200, "body": json.dumps({"processed": processed, "notified": notified})}
