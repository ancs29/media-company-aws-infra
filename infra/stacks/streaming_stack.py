from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_ec2 as ec2,
    aws_kinesisfirehose as firehose,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs
)
from constructs import Construct

class StreamingStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, unsubscribe_events: s3.IBucket, vpc: ec2.Vpc, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        firehose_logs = logs.LogGroup(self, "UnsubscribeFirehoseLogs")
        lambda_logs = logs.LogGroup(self, "UnsubscribeLambdaLogs")

        firehose.DeliveryStream(self, "UnsubscribeStream",
            destination=firehose.S3Bucket(
                unsubscribe_events,
                logging_config=firehose.EnableLogging(firehose_logs)
            )
        )

        unsubscribe_lambda = _lambda.Function(self, "UnsubscribeLambda",
            runtime=_lambda.Runtime.PYTHON_3_14,
            handler="unsubscribe_event.handler",
            code=_lambda.Code.from_asset("lambda"),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            log_group=lambda_logs
        )

        events.Rule(self, "UnsubscribeBridge",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={"bucket": {"name": [unsubscribe_events.bucket_name]}},
            ),
            targets=[targets.LambdaFunction(unsubscribe_lambda)] # pyright: ignore[reportArgumentType]
        )

        unsubscribe_events.grant_read(unsubscribe_lambda)