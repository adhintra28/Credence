"""AWS: SageMaker training + hosting. UNCOMMENT after backend configured.
TODO:
  - set SAGEMAKER_ROLE = "arn:aws:iam::<acct>:role/<SageMakerExec>" (backend)
  - pip install sagemaker boto3
"""
# import sagemaker
# from sagemaker.sklearn import SKLearn
# SAGEMAKER_ROLE = "TODO-backend"  # e.g. arn:aws:iam::123456789012:role/SageMakerExec
# est = SKLearn(entry_point="src/models/train.py", role=SAGEMAKER_ROLE,
#               instance_type="ml.m5.xlarge", framework_version="1.2-1")
# est.fit({"train": "s3://TODO-backend-bucket/data/processed/"})
# predictor = est.deploy(initial_instance_count=1, instance_type="ml.t2.medium")
# print(predictor.predict(...))
