from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_redshiftserverless as redshift,
    aws_s3 as s3
)
from constructs import Construct

from config import EnvConfig

class ConsumerStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, config: EnvConfig, vpc: ec2.IVpc, gold: s3.IBucket, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Gold is queried in place with Redshift Spectrum (external schemas over the
        # Glue gold database), not loaded with COPY. The data stays in open formats in
        # S3, readable by Athena/Spark or any other engine, which avoids vendor lock-in,
        # and there is no second copy in Redshift storage to keep in sync with the lake.
        # Read-only access to the gold layer and nothing else.
        # Must match the gold database name in DataStack.
        gold_database = config.resource_name("gold", sep="_")
        spectrum_role = iam.Role(
            self, "SpectrumRole",
            assumed_by=iam.ServicePrincipal("redshift.amazonaws.com"), # pyright: ignore[reportArgumentType]
            inline_policies={
                "SpectrumGoldReadOnly": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["s3:GetBucketLocation", "s3:ListBucket"],
                        resources=[gold.bucket_arn]
                    ),
                    iam.PolicyStatement(
                        actions=["s3:GetObject"],
                        resources=[gold.arn_for_objects("*")]
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "glue:GetDatabase",
                            "glue:GetTable",
                            "glue:GetTables",
                            "glue:GetPartition",
                            "glue:GetPartitions",
                            "glue:BatchGetPartition"
                        ],
                        resources=[
                            self.format_arn(service="glue", resource="catalog"),
                            self.format_arn(service="glue", resource="database", resource_name=gold_database),
                            self.format_arn(service="glue", resource="table", resource_name=f"{gold_database}/*")
                        ]
                    )
                ])
            }
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
