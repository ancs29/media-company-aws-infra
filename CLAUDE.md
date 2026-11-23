# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

AWS CDK (Python) app provisioning a media company's data platform: a medallion data lake (landing → bronze → silver → gold S3 buckets + Glue databases), a VPC, and a streaming pipeline for subscriber unsubscribe events. See [README.md](README.md) for the full resource inventory.

**This is a portfolio project, not a production system.** The stacks will never be deployed to AWS. The goal is to implement an architecture the author designed and to demonstrate an understanding of AWS for a realistic scenario: a media company that needs a lakehouse for analytics. Keep this in mind when working here:

- Judge correctness with `cdk synth` and unit tests, not deployment. Don't suggest `cdk deploy`, real account setup or cost and operations work beyond what the design itself needs.
- The repo is infrastructure only. There are no Spark/Glue jobs, transformation code or real data, and their absence is intentional. Don't treat it as a gap to fill unless asked.
- Design choices should still be sound and defensible, because the infrastructure is what's being shown.
- Implement only the minimal viable solution for what was explicitly asked: no extras such as error handling. Suggest any further additions after implementing, and build nothing extra without the author's approval.

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

- **Entry point & wiring**: [infra/app.py](infra/app.py) builds three stacks — `DataStack`, `NetworkStack`, `StreamingStack`. `StreamingStack` receives the unsubscribe bucket from `DataStack` and the VPC from `NetworkStack` as constructor arguments; this creates the cross-stack dependencies (deploy order: Data + Network, then Streaming). Cross-stack sharing follows this pattern: expose resources as `self.<attr>` on the producing stack and pass them into the consumer's `__init__`.
- **Environments**: [infra/config.py](infra/config.py) maps `dev`/`uat`/`prod` to `EnvConfig(account, region)`; chosen via the `env` CDK context key, defaulting to `dev`. All three currently point at the same account/region.
- **Imports are relative to `infra/`**, not the repo root (`from stacks.data_stack import ...`, `from config import ENVS`). Tests that import stacks need `infra/` on `sys.path` (or run with it as CWD).
- **Lambda code path is CWD-relative**: `StreamingStack` uses `_lambda.Code.from_asset("lambda")`, which resolves to `infra/lambda/` only when synth runs from `infra/`. Handler modules live in [infra/lambda/](infra/lambda/) and are referenced as `<module>.handler`.
- **Streaming flow**: Firehose `UnsubscribeStream` → `UnsubscribeS3` bucket → EventBridge rule (S3 `Object Created`, filtered by bucket name) → `UnsubscribeLambda`. The Lambda runs in `PRIVATE_ISOLATED` subnets with no internet; it reaches S3 only via the VPC's S3 gateway endpoint, so any other AWS service it needs will require an additional VPC interface endpoint.
- EventBridge S3 events only fire for buckets with `event_bridge_enabled=True` (currently set on `LandingS3`).
- `cdk.json` sets `@aws-cdk/core:defaultCrossStackReferences` to `"weak"`.

## Current state

- [tests/unit/test_media_company_aws_infra_stack.py](tests/unit/test_media_company_aws_infra_stack.py) is leftover CDK template boilerplate importing a non-existent `infra.stack` module, so `pytest` fails at collection. New tests should use `aws_cdk.assertions.Template.from_stack` against the real stacks.
- The unsubscribe Lambda handler is a placeholder.
