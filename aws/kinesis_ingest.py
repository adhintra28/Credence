"""List or download input objects from S3.

Despite the legacy filename, this is S3 ingestion; Kinesis is outside the
batch MVP. Usage: ``python aws/kinesis_ingest.py [s3-key] [destination]``.
"""
import os
import sys
from pathlib import Path

import boto3


def s3_client():
    return boto3.client("s3", region_name=os.getenv("AWS_REGION", "ap-south-1"))


def main() -> None:
    bucket = os.environ["S3_DATA_BUCKET"]
    prefix = os.getenv("S3_INPUT_PREFIX", "raw/")
    key = sys.argv[1] if len(sys.argv) > 1 else None
    if not key:
        for obj in s3_client().list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", []):
            print(obj["Key"])
        return
    destination = Path(sys.argv[2] if len(sys.argv) > 2 else Path("data/raw") / Path(key).name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    s3_client().download_file(bucket, key, str(destination))
    print(f"Downloaded s3://{bucket}/{key} to {destination}")


if __name__ == "__main__":
    main()
