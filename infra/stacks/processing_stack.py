from aws_cdk import (
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

        # Minimal shared role; to be replaced with per-job least-privilege roles
        glue_role = iam.Role(
            self, "GlueJobRole",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"), # pyright: ignore[reportArgumentType]
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")]
        )
        scripts.grant_read(glue_role)
        for lake_bucket in (landing, bronze, silver, gold):
            lake_bucket.grant_read_write(glue_role)

        # `name` sets both the Glue job name and its script key (`<name>.py` in the scripts
        # bucket, deployed from infra/glue/). When adding a job, create infra/glue/<name>.py
        # with exactly the same name: synth won't catch a mismatch, the job only fails at run time.
        def job(construct_id: str, name: str, connection: glue.Connection) -> glue.PySparkEtlJob:
            return glue.PySparkEtlJob(
                self, construct_id,
                job_name=config.resource_name(name),
                role=glue_role, # pyright: ignore[reportArgumentType]
                script=glue.Code.from_bucket(scripts, f"{name}.py"),
                glue_version=glue.GlueVersion.V6_0,
                connections=[connection]
            )

        job("ValidateApiJob", "validate_api", egress_connection)  # imaginary APIs (via NAT) -> bronze
        job("ValidateJob", "validate", isolated_connection)       # landing -> bronze
        job("CleanJob", "clean", isolated_connection)             # bronze -> silver
        job("CurateJob", "curate", isolated_connection)           # silver -> gold
