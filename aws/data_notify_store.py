"""Read one customer risk record from DynamoDB.

Set AWS_REGION and DYNAMODB_RISK_SCORES_TABLE, then run this script with an
optional customer ID. Credentials use the standard boto3 chain.
"""
import os
import sys

import boto3


def get_risk_score(customer_id: str) -> dict | None:
    table_name = os.environ["DYNAMODB_RISK_SCORES_TABLE"]
    region = os.getenv("AWS_REGION", "ap-south-1")
    table = boto3.resource("dynamodb", region_name=region).Table(table_name)
    return table.get_item(Key={"customer_id": customer_id}).get("Item")


if __name__ == "__main__":
    customer_id = sys.argv[1] if len(sys.argv) > 1 else "CUST001"
    item = get_risk_score(customer_id)
    print(item if item else f"No risk score found for {customer_id}")
