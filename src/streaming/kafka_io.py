"""Stream Processing (Apache Kafka — Open-Source Stack). Install: pip install kafka-python
Requires local Kafka (docker). Guarded: batch pipeline does not need this.
"""
TOPIC_IN = "txns"
TOPIC_OUT = "risk_alerts"


def produce_example():
    # from kafka import KafkaProducer
    # import json
    # p = KafkaProducer(bootstrap_servers="localhost:9092",
    #                   value_serializer=lambda v: json.dumps(v).encode())
    # p.send(TOPIC_IN, {"customer_id": "C000001", "txn_type": "salary_credit", "amount": 50000})
    # p.flush()
    raise NotImplementedError("Start Kafka locally, uncomment code, then produce.")


def consume_and_score():
    # from kafka import KafkaConsumer
    # wire consumer -> build_snapshot(window) -> production.pkl -> TOPIC_OUT
    # See src/scoring/score.py for batch equivalent logic to mirror per-event.
    raise NotImplementedError("Mirror src/scoring/score.py per-event here once Kafka is up.")
