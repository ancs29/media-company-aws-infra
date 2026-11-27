from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_kinesisfirehose as firehose,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs
)
from constructs import Construct

from config import EnvConfig

class StreamingStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, config: EnvConfig, vpc: ec2.Vpc, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- IAM: explicit roles ---------------------------------------------------------
        # Every permission in this stack is listed here. Roles are passed to constructs with
        # without_policy_updates(), so CDK cannot add anything on top. Statements that need
        # a resource created further down are added to these documents once it exists; the
        # documents are only rendered at synth, so they still end up inside the role itself.

        # Deploy-time helper Lambda that CDK adds to switch on EventBridge notifications for
        # the bucket. No log permissions: it reports failures back to CloudFormation directly.
        notifications_handler_policy = iam.PolicyDocument()
        notifications_handler_role = iam.Role(
            self, "BucketNotificationsHandlerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"), # pyright: ignore[reportArgumentType]
            inline_policies={"EnableBucketNotifications": notifications_handler_policy}
        )

        firehose_policy = iam.PolicyDocument()
        firehose_role = iam.Role(
            self, "UnsubscribeFirehoseRole",
            assumed_by=iam.ServicePrincipal("firehose.amazonaws.com"), # pyright: ignore[reportArgumentType]
            inline_policies={"DeliverToS3": firehose_policy}
        )

        lambda_policy = iam.PolicyDocument()
        lambda_role = iam.Role(
            self, "UnsubscribeLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"), # pyright: ignore[reportArgumentType]
            inline_policies={"ReadEventsInVpc": lambda_policy}
        )

        # --- Resources -------------------------------------------------------------------

        # Buffer for the alerting flow only, not part of the lake. EventBridge must be
        # enabled for the rule below to receive its Object Created events.
        unsubscribe_events = s3.Bucket(
            self, "UnsubscribeS3",
            bucket_name_prefix=config.resource_name("unsub"),
            bucket_namespace=s3.BucketNamespace.ACCOUNT_REGIONAL,
            event_bridge_enabled=True,
            notifications_handler_role=notifications_handler_role.without_policy_updates()
        )

        firehose_logs = logs.LogGroup(self, "UnsubscribeFirehoseLogs")
        lambda_logs = logs.LogGroup(self, "UnsubscribeLambdaLogs")

        firehose.DeliveryStream(self, "UnsubscribeStream",
            destination=firehose.S3Bucket(
                unsubscribe_events,
                role=firehose_role.without_policy_updates(),
                logging_config=firehose.EnableLogging(firehose_logs)
            )
        )

        # Created explicitly (CDK would otherwise make one) so the role can be scoped to it
        lambda_sg = ec2.SecurityGroup(self, "UnsubscribeLambdaSG", vpc=vpc)
        lambda_subnets = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED)

        unsubscribe_lambda = _lambda.Function(self, "UnsubscribeLambda",
            runtime=_lambda.Runtime.PYTHON_3_14,
            handler="unsubscribe_event.handler",
            code=_lambda.Code.from_asset("lambda"),
            role=lambda_role.without_policy_updates(),
            vpc=vpc,
            vpc_subnets=lambda_subnets,
            security_groups=[lambda_sg],
            log_group=lambda_logs
        )

        # EventBridge invokes the Lambda through a resource-based permission on the
        # function (created by this target), not through an IAM role
        events.Rule(self, "UnsubscribeBridge",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={"bucket": {"name": [unsubscribe_events.bucket_name]}},
            ),
            targets=[targets.LambdaFunction(unsubscribe_lambda)] # pyright: ignore[reportArgumentType]
        )

        # --- IAM: statements that reference the resources above ---------------------------

        notifications_handler_policy.add_statements(
            iam.PolicyStatement(actions=["s3:PutBucketNotification"], resources=[unsubscribe_events.bucket_arn])
        )

        # The set AWS documents for a Firehose S3 destination
        firehose_policy.add_statements(
            iam.PolicyStatement(
                actions=["s3:GetBucketLocation", "s3:ListBucket", "s3:ListBucketMultipartUploads"],
                resources=[unsubscribe_events.bucket_arn]
            ),
            iam.PolicyStatement(
                actions=["s3:PutObject", "s3:GetObject", "s3:AbortMultipartUpload"],
                resources=[unsubscribe_events.arn_for_objects("*")]
            ),
            # CDK pre-creates the log stream, so writing to it is enough
            iam.PolicyStatement(actions=["logs:PutLogEvents"], resources=[firehose_logs.log_group_arn])
        )

        lambda_policy.add_statements(
            # The handler reads the object named in each event
            iam.PolicyStatement(actions=["s3:GetObject"], resources=[unsubscribe_events.arn_for_objects("*")]),
            # The log group already exists, so no CreateLogGroup
            iam.PolicyStatement(
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[lambda_logs.log_group_arn]
            ),
            # Lambda creates and manages the function's ENIs in the VPC with this role.
            # Describe calls do not support resource-level permissions.
            iam.PolicyStatement(
                actions=["ec2:DescribeNetworkInterfaces", "ec2:DescribeSubnets"],
                resources=["*"]
            ),
            iam.PolicyStatement(
                actions=["ec2:CreateNetworkInterface"],
                resources=[
                    self.format_arn(service="ec2", resource="network-interface", resource_name="*"),
                    self.format_arn(service="ec2", resource="security-group", resource_name=lambda_sg.security_group_id),
                    *[
                        self.format_arn(service="ec2", resource="subnet", resource_name=subnet_id)
                        for subnet_id in vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED).subnet_ids
                    ]
                ]
            ),
            iam.PolicyStatement(
                actions=[
                    "ec2:DeleteNetworkInterface",
                    "ec2:AssignPrivateIpAddresses",
                    "ec2:UnassignPrivateIpAddresses"
                ],
                resources=[self.format_arn(service="ec2", resource="network-interface", resource_name="*")]
            )
        )
