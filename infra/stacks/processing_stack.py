from aws_cdk import (
    ArnFormat,
    Stack,
    aws_ec2 as ec2,
    aws_glue as glue,
    aws_iam as iam,
    aws_s3 as s3
)
from constructs import Construct

from config import EnvConfig

class ProcessingStack(Stack):

    def __init__(
        self, scope: Construct, construct_id: str,
        config: EnvConfig,
        vpc: ec2.IVpc,
        scripts: s3.IBucket,
        landing: s3.IBucket,
        bronze: s3.IBucket,
        silver: s3.IBucket,
        gold: s3.IBucket,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Glue requires a self-referencing all-TCP ingress rule so Spark workers can talk to each other
        glue_sg = ec2.SecurityGroup(self, "GlueSG", vpc=vpc)
        glue_sg.add_ingress_rule(glue_sg, ec2.Port.all_tcp())

        def connection(construct_id: str, subnet_type: ec2.SubnetType) -> glue.Connection:
            return glue.Connection(
                self, construct_id,
                type=glue.ConnectionType.NETWORK,
                network=glue.ConnectionNetwork.vpc(vpc, subnet_type=subnet_type),
                security_groups=[glue_sg]
            )

        isolated_connection = connection("IsolatedConnection", ec2.SubnetType.PRIVATE_ISOLATED)
        egress_connection = connection("EgressConnection", ec2.SubnetType.PRIVATE_WITH_EGRESS)

        # --- IAM: one explicit role per job --------------------------------------------
        # Every permission each job has is listed below. Roles are passed to the jobs with
        # without_policy_updates(), so CDK cannot add anything on top (e.g. its automatic
        # script-read grant, which is why script access is written out here instead).
        # Tables are Iceberg, read and committed through the Glue Data Catalog. They are
        # created outside these jobs, so no role can create or delete tables, and with no
        # s3:DeleteObject the jobs cannot expire snapshots or remove old files.

        def glue_catalog(layer: str) -> list[str]:
            # Glue checks the catalog, database and table ARNs on every table call
            database = config.resource_name(layer, sep="_")  # must match DataStack
            return [
                self.format_arn(service="glue", resource="catalog"),
                self.format_arn(service="glue", resource="database", resource_name=database),
                self.format_arn(service="glue", resource="table", resource_name=f"{database}/*")
            ]

        def read_files(bucket: s3.IBucket) -> list[iam.PolicyStatement]:
            # Raw objects, not tables: listing is needed to find the dumps under a prefix
            return [
                iam.PolicyStatement(actions=["s3:ListBucket"], resources=[bucket.bucket_arn]),
                iam.PolicyStatement(actions=["s3:GetObject"], resources=[bucket.arn_for_objects("*")])
            ]

        def read_tables(bucket: s3.IBucket, layer: str) -> list[iam.PolicyStatement]:
            # Iceberg reads exact file paths from its metadata, so no listing is needed
            return [
                iam.PolicyStatement(actions=["glue:GetDatabase", "glue:GetTable"], resources=glue_catalog(layer)),
                iam.PolicyStatement(actions=["s3:GetObject"], resources=[bucket.arn_for_objects("*")])
            ]

        def write_tables(bucket: s3.IBucket, layer: str) -> list[iam.PolicyStatement]:
            # A commit writes new data and metadata files, reads the current metadata,
            # then points the Glue table at the new metadata.json (UpdateTable). IAM cannot
            # tell a commit apart from a schema change: both are UpdateTable.
            return [
                iam.PolicyStatement(
                    actions=["glue:GetDatabase", "glue:GetTable", "glue:UpdateTable"],
                    resources=glue_catalog(layer)
                ),
                iam.PolicyStatement(actions=["s3:GetObject", "s3:PutObject"], resources=[bucket.arn_for_objects("*")])
            ]

        def job_runtime(name: str, connection: glue.Connection, subnet_type: ec2.SubnetType) -> list[iam.PolicyStatement]:
            # What every job needs to start and run, regardless of the data it touches
            return [
                # Its own script only
                iam.PolicyStatement(actions=["s3:GetObject"], resources=[scripts.arn_for_objects(f"{name}.py")]),
                # Its own VPC connection only
                iam.PolicyStatement(
                    actions=["glue:GetConnection"],
                    resources=[self.format_arn(service="glue", resource="catalog"), connection.connection_arn]
                ),
                # Glue creates ENIs in the connection's subnets with the job's role.
                # Describe calls do not support resource-level permissions.
                iam.PolicyStatement(
                    actions=[
                        "ec2:DescribeNetworkInterfaces",
                        "ec2:DescribeRouteTables",
                        "ec2:DescribeSecurityGroups",
                        "ec2:DescribeSubnets",
                        "ec2:DescribeVpcAttribute",
                        "ec2:DescribeVpcEndpoints"
                    ],
                    resources=["*"]
                ),
                iam.PolicyStatement(
                    actions=["ec2:CreateNetworkInterface"],
                    resources=[
                        self.format_arn(service="ec2", resource="network-interface", resource_name="*"),
                        self.format_arn(service="ec2", resource="security-group", resource_name=glue_sg.security_group_id),
                        *[
                            self.format_arn(service="ec2", resource="subnet", resource_name=subnet_id)
                            for subnet_id in vpc.select_subnets(subnet_type=subnet_type).subnet_ids
                        ]
                    ]
                ),
                iam.PolicyStatement(
                    actions=["ec2:DeleteNetworkInterface"],
                    resources=[self.format_arn(service="ec2", resource="network-interface", resource_name="*")]
                ),
                iam.PolicyStatement(
                    actions=["ec2:CreateTags", "ec2:DeleteTags"],
                    resources=[self.format_arn(service="ec2", resource="network-interface", resource_name="*")],
                    conditions={"ForAllValues:StringEquals": {"aws:TagKeys": ["aws-glue-service-resource"]}}
                ),
                # Driver/executor and continuous logs (enabled by default on the jobs)
                iam.PolicyStatement(
                    actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                    resources=[self.format_arn(
                        service="logs", resource="log-group", resource_name="/aws-glue/jobs/*",
                        arn_format=ArnFormat.COLON_RESOURCE_NAME
                    )]
                ),
                # Job metrics (enabled by default on the jobs); PutMetricData has no
                # resource-level permissions, so it is limited to the Glue namespace instead
                iam.PolicyStatement(
                    actions=["cloudwatch:PutMetricData"],
                    resources=["*"],
                    conditions={"StringEquals": {"cloudwatch:namespace": "Glue"}}
                )
            ]

        # CONSTRAINT: `name` sets both the Glue job name and its script key (`<name>.py` in the scripts
        # bucket, deployed from infra/glue/). When adding a job, create infra/glue/<name>.py
        # with exactly the same name: synth won't catch a mismatch, the job only fails at run time.
        def job(
            construct_id: str, name: str,
            connection: glue.Connection, subnet_type: ec2.SubnetType,
            data_access: list[iam.PolicyStatement]
        ) -> glue.PySparkEtlJob:
            role = iam.Role(
                self, f"{construct_id}Role",
                assumed_by=iam.ServicePrincipal("glue.amazonaws.com"), # pyright: ignore[reportArgumentType]
                inline_policies={
                    "Runtime": iam.PolicyDocument(statements=job_runtime(name, connection, subnet_type)),
                    "DataAccess": iam.PolicyDocument(statements=data_access)
                }
            )
            return glue.PySparkEtlJob(
                self, construct_id,
                job_name=config.resource_name(name),
                role=role.without_policy_updates(), # pyright: ignore[reportArgumentType]
                script=glue.Code.from_bucket(scripts, f"{name}.py"),
                glue_version=glue.GlueVersion.V6_0,
                connections=[connection]
            )

        isolated = ec2.SubnetType.PRIVATE_ISOLATED
        egress = ec2.SubnetType.PRIVATE_WITH_EGRESS

        # Imaginary APIs (via NAT) -> bronze tables. Calling the API needs no IAM.
        job("ValidateApiJob", "validate_api", egress_connection, egress,
            write_tables(bronze, "bronze"))
        # Raw (zipped) dumps in landing, unzipped in memory -> bronze tables
        job("ValidateJob", "validate", isolated_connection, isolated,
            read_files(landing) + write_tables(bronze, "bronze"))
        # Bronze tables -> silver tables
        job("CleanJob", "clean", isolated_connection, isolated,
            read_tables(bronze, "bronze") + write_tables(silver, "silver"))
        # Silver tables -> gold tables
        job("CurateJob", "curate", isolated_connection, isolated,
            read_tables(silver, "silver") + write_tables(gold, "gold"))
        # Gold tables -> aggregated gold tables (write_tables covers reading gold)
        job("AggregateJob", "aggregate", isolated_connection, isolated,
            write_tables(gold, "gold"))
