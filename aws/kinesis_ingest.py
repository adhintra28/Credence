"""AWS: Kinesis streaming ingest (mirrors Kafka path). UNCOMMENT after backend configured.
TODO: STREAM = backend stream name; REGION = backend region.
"""
# import boto3, json
# REGION, STREAM = "TODO-backend-region", "TODO-pre-delinquency-txns"
# kinesis = boto3.client("kinesis", region_name=REGION)
# def put_txn(customer_id, txn_type, amount):
#     kinesis.put_record(StreamName=STREAM, PartitionKey=customer_id,
#                        Data=json.dumps({"customer_id": customer_id, "txn_type": txn_type, "amount": amount}))
