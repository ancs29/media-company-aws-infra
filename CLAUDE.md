# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

AWS CDK (Python) app provisioning a media company's data platform: a medallion data lake (landing → bronze → silver → gold S3 buckets + Glue databases), a VPC, Glue processing jobs, a private Redshift Serverless warehouse, and a streaming pipeline for subscriber unsubscribe events. See [README.md](README.md) for the full resource inventory.

**This is a portfolio project, not a production system.** The stacks will never be deployed to AWS. The goal is to implement an architecture the author designed and to demonstrate an understanding of AWS for a realistic scenario: a media company that needs a lakehouse for analytics. Keep this in mind when working here:

- Judge correctness with `cdk synth` and unit tests, not deployment. Don't suggest `cdk deploy`, real account setup or cost and operations work beyond what the design itself needs.
- The repo is infrastructure only. There are no Spark/Glue jobs, transformation code or real data, and their absence is intentional. Don't treat it as a gap to fill unless asked.
- Design choices should still be sound and defensible, because the infrastructure is what's being shown.
- Implement only the minimal viable solution for what was explicitly asked: no extras such as error handling. Suggest any further additions after implementing, and build nothing extra without the author's approval.

## Original problem statement

This is the brief the project started from. Some details have since changed, and it may be rewritten later. Treat it as a loose guideline for design decisions and don't enforce it rigidly: this is a portfolio project whose purpose is learning.

> A media company operating in the US, EU and Asia Pacific needs an analytics platform for their mobile application. The platform must be able to process approximately 2 GB daily, including semi-structured and unstructured data, from snapshots of its Postgres database, APIs, and a landing S3 bucket containing raw business events. It will be consumed by BI teams across the three regions, who should only be able to see personally-identifying data from their region. Teams also want live alerts for users who unsubscribe, to follow up with them.
>
> The platform must be simple enough for three full time data engineers across the business to manage. The business wants to avoid vendor lock-in, minimise costs, and maximise security, and wants AWS as their cloud provider.

## Commands

Setup (from repo root):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

All `cdk` commands must run from `infra/` (that's where `cdk.json` lives, and `app.py` is launched as `python3 app.py` from there):

```bash
cd infra
cdk synth                     # synthesize all stacks (dev by default)
cdk diff -c env=uat           # select environment via -c env=<dev|uat|prod>
cdk deploy --all -c env=dev
cdk synth StreamingStack      # single stack
```

Tests (from repo root): `pytest`, single test: `pytest tests/unit/<file>.py::<test_name>`.

## Architecture notes

- **Entry point & wiring**: [infra/app.py](infra/app.py) builds five stacks — `DataStack`, `NetworkStack`, `StreamingStack`, `ProcessingStack` (Glue jobs), `ConsumerStack` (Redshift Serverless). The last three receive the VPC from `NetworkStack` as a constructor argument, and `ProcessingStack`/`ConsumerStack` also receive buckets from `DataStack`; this creates the cross-stack dependencies (deploy order: Data + Network, then the rest). Cross-stack sharing follows this pattern: expose resources as `self.<attr>` on the producing stack and pass them into the consumer's `__init__`.
- **Environments**: [infra/config.py](infra/config.py) maps `dev`/`uat`/`prod` to `EnvConfig(account, region)`; chosen via the `env` CDK context key, defaulting to `dev`. All three currently point at the same account/region.
- **Imports are relative to `infra/`**, not the repo root (`from stacks.data_stack import ...`, `from config import ENVS`). Tests that import stacks need `infra/` on `sys.path` (or run with it as CWD).
- **Asset paths are CWD-relative**: `StreamingStack` uses `_lambda.Code.from_asset("lambda")` and `DataStack` deploys `Source.asset("glue")` to the scripts bucket; these resolve to `infra/lambda/` and `infra/glue/` only when synth runs from `infra/`. Handler modules are referenced as `<module>.handler`; Glue jobs reference `<job>.py` in the scripts bucket.
- **Streaming flow**: Firehose `UnsubscribeStream` → `UnsubscribeS3` bucket → EventBridge rule (S3 `Object Created`, filtered by bucket name) → `UnsubscribeLambda`. The Lambda runs in `PRIVATE_ISOLATED` subnets with no internet; it reaches S3 only via the VPC's S3 gateway endpoint, so any other AWS service it needs will require an additional VPC interface endpoint (a Glue endpoint already exists in `NetworkStack`).
- **Glue networking**: jobs attach via `NETWORK` connections (`validate_api` in an egress subnet using the NAT; the rest in an isolated subnet using the S3 gateway and Glue interface endpoints). The shared Glue SG needs its self-referencing all-TCP rule.
- **Redshift**: Serverless, private in the isolated subnets with enhanced VPC routing; gold is read via Spectrum (no COPY). IAM roles and SGs in `ProcessingStack`/`ConsumerStack` are deliberately minimal placeholders.
- EventBridge S3 events only fire for buckets with `event_bridge_enabled=True` (currently set on `UnsubscribeS3`).
- `cdk.json` sets `@aws-cdk/core:defaultCrossStackReferences` to `"weak"`.

## Current state

- [tests/unit/test_media_company_aws_infra_stack.py](tests/unit/test_media_company_aws_infra_stack.py) is leftover CDK template boilerplate importing a non-existent `infra.stack` module, so `pytest` fails at collection. New tests should use `aws_cdk.assertions.Template.from_stack` against the real stacks.
- The unsubscribe Lambda handler and the Glue job scripts are placeholders.
- Without AWS credentials, `cdk synth` reports an error for `NetworkStack`'s availability-zone lookup but still writes templates using dummy AZs.
