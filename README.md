# Media Company AWS Infrastructure

AWS CDK (Python) app that provisions the data platform for a media company: a medallion-style data lake (landing → bronze → silver → gold), the networking it runs in, Glue processing jobs, a private Redshift Serverless warehouse, and a streaming pipeline for subscriber "unsubscribe" events.

## Architecture

The app deploys five stacks, defined in [infra/stacks/](infra/stacks/) and wired together in [infra/app.py](infra/app.py).

### `DataStack` — [data_stack.py](infra/stacks/data_stack.py)

| Resource | Purpose |
| --- | --- |
| `LandingS3` bucket | Raw drop zone for incoming files |
| `BronzeS3` / `SilverS3` / `GoldS3` buckets | Medallion data lake layers |
| `ScriptsS3` bucket | Glue job scripts, deployed from [infra/glue/](infra/glue/) (placeholders) |
| Glue databases `bronze`, `silver`, `gold` | Data catalog databases, one per lake layer |

### `NetworkStack` — [network_stack.py](infra/stacks/network_stack.py)

- VPC `10.0.0.0/16` across up to 3 AZs, with a `/24` subnet per AZ for each tier:
  - `public`
  - `private_egress` (outbound internet through NAT)
  - `private_isolated` (no internet access)
- A single NAT gateway, which saves cost but is not fault tolerant across AZs.
- An S3 gateway endpoint, so isolated subnets can still reach S3.
- A Glue interface endpoint (private DNS) in the isolated subnets, so Glue jobs there can reach the Glue API and Data Catalog.
- VPC flow logs.

### `StreamingStack` — [streaming_stack.py](infra/stacks/streaming_stack.py)

Depends on `NetworkStack` (the VPC).

```
Firehose (UnsubscribeStream) ──▶ UnsubscribeS3 ──(Object Created)──▶ EventBridge rule ──▶ UnsubscribeLambda
```

- **`UnsubscribeS3` bucket** holds the unsubscribe events delivered by Firehose. It is the only bucket with EventBridge notifications enabled.
- **Firehose delivery stream** writes unsubscribe events to `UnsubscribeS3`, logging to its own CloudWatch log group.
- **EventBridge rule** matches S3 `Object Created` events on the unsubscribe bucket.
- **Lambda** (`python3.14`, code in [infra/lambda/](infra/lambda/)) runs in the isolated subnets and has read access to the unsubscribe bucket. The handler in [unsubscribe_event.py](infra/lambda/unsubscribe_event.py) is currently a placeholder.
- **IAM**: explicit roles for Firehose, the Lambda and CDK's bucket-notifications helper, passed with `without_policy_updates()`.

### `ProcessingStack` — [processing_stack.py](infra/stacks/processing_stack.py)

Depends on `DataStack` (lake and scripts buckets) and `NetworkStack` (the VPC).

| Job | Glue connection | Flow |
| --- | --- | --- |
| `validate_api` | egress subnet (NAT) | external APIs → bronze |
| `validate` | isolated subnet | landing → bronze |
| `clean` | isolated subnet | bronze → silver |
| `curate` | isolated subnet | silver → gold |
| `aggregate` | isolated subnet | gold → gold |

- All five are PySpark ETL jobs (Glue 6.0) running placeholder scripts.
- Two `NETWORK` Glue connections share one security group with the self-referencing all-TCP rule Spark needs.
- One explicit IAM role per job, passed with `without_policy_updates()`, with access only to the buckets and Glue databases its flow needs (Iceberg tables, no table creation or deletion).

### `ConsumerStack` — [consumer_stack.py](infra/stacks/consumer_stack.py)

Depends on `DataStack` (gold bucket) and `NetworkStack` (the VPC).

- Redshift Serverless namespace and workgroup, private (`publicly_accessible=False`) in the isolated subnets, with enhanced VPC routing.
- Admin password managed by Redshift in Secrets Manager.
- Gold is queried in place with Redshift Spectrum through an associated IAM role with read-only access to the gold bucket and gold Glue database.

## Project layout

```
.
├── infra/
│   ├── app.py              # CDK entry point: builds the five stacks
│   ├── cdk.json            # CDK config (run cdk commands from this folder)
│   ├── config.py           # Per-environment account/region settings
│   ├── glue/               # Glue job scripts (placeholders)
│   ├── lambda/             # Lambda function source code
│   └── stacks/             # Stack definitions
├── tests/unit/             # Unit tests (pytest + CDK assertions)
├── requirements.txt        # CDK runtime dependencies
└── requirements-dev.txt    # Test dependencies
```

## Prerequisites

- Python 3.x with `venv`
- Node.js and the AWS CDK CLI: `npm install -g aws-cdk`
- AWS credentials for the target account (for example `aws configure` or `AWS_PROFILE`)
- The target account/region bootstrapped once: `cdk bootstrap`

## Setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

## Environments

Environments are defined in [infra/config.py](infra/config.py) as `dev`, `uat` and `prod`, each with an AWS account and region. Choose one with the `env` context value. If you don't pass one, `dev` is used:

```bash
cdk deploy --all -c env=uat
```

To add an environment, add an entry to `ENVS` in `config.py`.

## Usage

Run all CDK commands from the `infra/` directory, because that's where `cdk.json` is:

```bash
cd infra
cdk ls                       # list stacks
cdk synth                    # generate CloudFormation templates
cdk diff -c env=dev          # compare with what's deployed
cdk deploy --all -c env=dev  # deploy all stacks
cdk destroy --all -c env=dev # tear down
```

CDK deploys the stacks in dependency order: `DataStack` and `NetworkStack` first, then `StreamingStack`, `ProcessingStack` and `ConsumerStack`.

## Tests

```bash
pytest
```

> **Note:** [tests/unit/test_media_company_aws_infra_stack.py](tests/unit/test_media_company_aws_infra_stack.py) is still the CDK template example and imports a module (`infra.stack`) that no longer exists. Replace it with tests for the current stacks.
