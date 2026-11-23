# Media Company AWS Infrastructure

AWS CDK (Python) app that provisions the data platform for a media company: a medallion-style data lake (landing → bronze → silver → gold), the networking it runs in, and a streaming pipeline for subscriber "unsubscribe" events.

## Architecture

The app deploys three stacks, defined in [infra/stacks/](infra/stacks/) and wired together in [infra/app.py](infra/app.py).

### `DataStack` — [data_stack.py](infra/stacks/data_stack.py)

| Resource | Purpose |
| --- | --- |
| `LandingS3` bucket | Raw drop zone for incoming files (EventBridge notifications enabled) |
| `BronzeS3` / `SilverS3` / `GoldS3` buckets | Medallion data lake layers |
| `UnsubscribeS3` bucket | Destination for unsubscribe events delivered by Firehose |
| Glue databases `bronze`, `silver`, `gold` | Data catalog databases, one per lake layer |

### `NetworkStack` — [network_stack.py](infra/stacks/network_stack.py)

- VPC `10.0.0.0/16` across up to 3 AZs, with a `/24` subnet per AZ for each tier:
  - `public`
  - `private_egress` (outbound internet through NAT)
  - `private_isolated` (no internet access)
- A single NAT gateway, which saves cost but is not fault tolerant across AZs.
- An S3 gateway endpoint, so isolated subnets can still reach S3.
- VPC flow logs.

### `StreamingStack` — [streaming_stack.py](infra/stacks/streaming_stack.py)

Depends on `DataStack` (the unsubscribe bucket) and `NetworkStack` (the VPC).

```
Firehose (UnsubscribeStream) ──▶ UnsubscribeS3 ──(Object Created)──▶ EventBridge rule ──▶ UnsubscribeLambda
```

- **Firehose delivery stream** writes unsubscribe events to `UnsubscribeS3`, logging to its own CloudWatch log group.
- **EventBridge rule** matches S3 `Object Created` events on the unsubscribe bucket.
- **Lambda** (`python3.14`, code in [infra/lambda/](infra/lambda/)) runs in the isolated subnets and has read access to the unsubscribe bucket. The handler in [unsubscribe_event.py](infra/lambda/unsubscribe_event.py) is currently a placeholder.

## Project layout

```
.
├── infra/
│   ├── app.py              # CDK entry point: builds the three stacks
│   ├── cdk.json            # CDK config (run cdk commands from this folder)
│   ├── config.py           # Per-environment account/region settings
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

CDK deploys the stacks in dependency order: `DataStack` and `NetworkStack` first, then `StreamingStack`.

## Tests

```bash
pytest
```

> **Note:** [tests/unit/test_media_company_aws_infra_stack.py](tests/unit/test_media_company_aws_infra_stack.py) is still the CDK template example and imports a module (`infra.stack`) that no longer exists. Replace it with tests for the current stacks.
