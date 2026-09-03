"""SQS-triggered worker for specs/008-aws-async-inference.

Thin adapter around the existing, unmodified server/app/services/conditions.py
prediction logic (constitution Principle II: one feature-assembly
implementation, not one per trigger). See aws/SYSTEM_DESIGN.md for the full
design rationale behind every decision below.
"""

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote_plus

import boto3
from fastapi import HTTPException

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Cold-start setup: everything here runs once per warm execution
# environment, not once per message (same "pay once, reuse while warm"
# pattern the model cache already uses in server/app/services/conditions.py).

_secrets_client = boto3.client("secretsmanager")
_dynamodb = boto3.resource("dynamodb")

# The RDS instance's auto-generated Secrets Manager secret only contains
# {"username", "password"} - host/port/dbname aren't secret, so they're
# passed as plain env vars (inference-stack.ts) instead of duplicating them
# into the secret. username/password are URL-encoded defensively even though
# the CDK stack already excludes URL-breaking characters when generating the
# password (belt and suspenders - this must never silently mis-parse a
# connection string). db/connection.py reads DATABASE_URL from os.environ
# lazily, inside get_connection(), so it's enough to set it here before any
# request is processed.
_db_secret = json.loads(_secrets_client.get_secret_value(SecretId=os.environ["DB_CREDENTIALS_SECRET_ARN"])["SecretString"])
_db_user = quote_plus(_db_secret["username"])
_db_password = quote_plus(_db_secret["password"])
os.environ["DATABASE_URL"] = (
    f"postgresql://{_db_user}:{_db_password}@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"
)

# conditions.py's _load_description() now reads the trails table directly
# (server/db/migrations/0004) instead of a local enriched_descriptions/
# JSON file - so unlike the model (still S3-only, see below), there's no
# local-filesystem workaround needed here at all: this Lambda's Postgres
# connection (set up above) already serves both the activity lookup and the
# description lookup. See aws/SYSTEM_DESIGN.md section 6.2 for how this
# replaced an earlier /tmp-cache-from-S3 workaround.
from app.services import conditions as conditions_module  # noqa: E402  (must follow DATABASE_URL setup above)

_predictions_table = _dynamodb.Table(os.environ["PREDICTIONS_TABLE_NAME"])


def _to_dynamodb_item(trail_id: str, date: str, result) -> dict:
    # boto3's DynamoDB resource API rejects native Python floats - Decimal is
    # the required numeric type for put_item. Round-tripping through
    # json.dumps/loads is the simplest correct way to convert every nested
    # float in the Pydantic model's dict form.
    body = json.loads(json.dumps(result.model_dump(by_alias=True)), parse_float=Decimal)
    body["computedAt"] = datetime.now(timezone.utc).isoformat()
    return body


def lambda_handler(event, context):
    batch_item_failures: list[dict] = []

    for record in event["Records"]:
        message_id = record["messageId"]
        try:
            body = json.loads(record["body"])
            trail_id = str(body["trailId"])
            date = body["date"]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("malformed message %s, will not succeed on retry: %s", message_id, exc)
            batch_item_failures.append({"itemIdentifier": message_id})
            continue

        try:
            result = conditions_module.get_trail_conditions(trail_id, date)
            item = _to_dynamodb_item(trail_id, date, result)
            # Unconditional PutItem: overwrites any prior prediction for this
            # (trailId, date) key. Naturally idempotent (FR-006/SC-002) -
            # recomputing the same input produces an equivalent result, so
            # SQS's at-least-once delivery can never produce a conflicting
            # duplicate, only a harmless repeat write.
            _predictions_table.put_item(Item=item)
        except HTTPException as exc:
            # A 4xx here (invalid date, unenriched trail, ...) is a permanent
            # failure - it will fail identically on every retry. Still
            # reported as a batch item failure rather than special-cased,
            # letting SQS's own maxReceiveCount redrive policy carry it to
            # the DLQ - see SYSTEM_DESIGN.md section 6.4 for why this
            # simplification was chosen over a custom immediate-DLQ path.
            logger.error("permanent failure for message %s (trail=%s date=%s): %s", message_id, trail_id, date, exc.detail)
            batch_item_failures.append({"itemIdentifier": message_id})
        except Exception:
            logger.exception("transient failure for message %s (trail=%s date=%s)", message_id, trail_id, date)
            batch_item_failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": batch_item_failures}
