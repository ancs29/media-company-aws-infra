from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_redshiftserverless as redshift
)
from constructs import Construct

from config import EnvConfig

class ConsumerStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, config: EnvConfig, vpc: ec2.IVpc, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Gold is queried in place with Redshift Spectrum (external schemas over the
        # Glue gold database), not loaded with COPY. The data stays in open formats in
        # S3, readable by Athena/Spark or any other engine, which avoids vendor lock-in,
        # and there is no second copy in Redshift storage to keep in sync with the lake.
        # Minimal role from AWS's Spectrum getting-started guide; to be scoped down later.
        spectrum_role = iam.Role(
            self, "SpectrumRole",
            assumed_by=iam.ServicePrincipal("redshift.amazonaws.com"), # pyright: ignore[reportArgumentType]
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3ReadOnlyAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSGlueConsoleFullAccess")
            ]
        )

        redshift_sg = ec2.SecurityGroup(self, "RedshiftSG", vpc=vpc)

        name = config.resource_name("warehouse")

        namespace = redshift.CfnNamespace(
            self, "RedshiftNamespace",
            namespace_name=name,
            manage_admin_password=True,  # generated and rotated in Secrets Manager
            iam_roles=[spectrum_role.role_arn],
            default_iam_role_arn=spectrum_role.role_arn
        )

        redshift.CfnWorkgroup(
            self, "RedshiftWorkgroup",
            workgroup_name=name,
            namespace_name=namespace.attr_namespace_namespace_name,  # implies the namespace dependency
            subnet_ids=vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED).subnet_ids,
            security_group_ids=[redshift_sg.security_group_id],
            publicly_accessible=False,
            # Route COPY/UNLOAD/Spectrum S3 traffic through the VPC (S3 gateway endpoint)
            enhanced_vpc_routing=True
        )
