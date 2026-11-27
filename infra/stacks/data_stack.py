from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_assets as s3_assets,
    aws_s3_deployment as s3_deployment,
    aws_glue as glue
)
from constructs import Construct

from config import EnvConfig

class DataStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, config: EnvConfig, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        def bucket(construct_id: str, purpose: str, **bucket_kwargs) -> s3.Bucket:
            return s3.Bucket(
                self, construct_id,
                bucket_name_prefix=config.resource_name(purpose),
                bucket_namespace=s3.BucketNamespace.ACCOUNT_REGIONAL,
                **bucket_kwargs
            )

        self.bronze_s3 = bucket("BronzeS3", "bronze")
        self.silver_s3 = bucket("SilverS3", "silver")
        self.gold_s3 = bucket("GoldS3", "gold")
        self.landing_s3 = bucket("LandingS3", "landing")
        self.scripts_s3 = bucket("ScriptsS3", "scripts")

        # Glue scripts: CDK zips infra/glue/ into its bootstrap assets bucket at synth, and
        # at deploy time a CDK helper Lambda copies the zip, unzips it and syncs the files
        # into the scripts bucket, deleting scripts no longer in infra/glue/ (prune).
        glue_scripts = s3_assets.Asset(self, "GlueScriptsAsset", path="glue")

        # Passed with without_policy_updates() so CDK cannot add its broader default grants.
        # No log permissions: the helper reports failures back to CloudFormation directly.
        scripts_deployment_role = iam.Role(
            self, "GlueScriptsDeploymentRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"), # pyright: ignore[reportArgumentType]
            inline_policies={"DeployGlueScripts": iam.PolicyDocument(statements=[
                # Download this deployment's zip only
                iam.PolicyStatement(
                    actions=["s3:GetObject"],
                    resources=[glue_scripts.bucket.arn_for_objects(glue_scripts.s3_object_key)]
                ),
                # Sync: list what is there, upload new or changed scripts, delete removed ones
                iam.PolicyStatement(actions=["s3:ListBucket"], resources=[self.scripts_s3.bucket_arn]),
                iam.PolicyStatement(
                    actions=["s3:PutObject", "s3:DeleteObject"],
                    resources=[self.scripts_s3.arn_for_objects("*")]
                )
            ])}
        )

        s3_deployment.BucketDeployment(
            self, "GlueScriptsDeployment",
            sources=[s3_deployment.Source.bucket(glue_scripts.bucket, glue_scripts.s3_object_key)],
            destination_bucket=self.scripts_s3,
            role=scripts_deployment_role.without_policy_updates()
        )

        self.bronze_database = glue.Database(
            self, "BronzeDatabase",
            database_name=config.resource_name("bronze", sep="_"),
            location_uri=self.bronze_s3.s3_url_for_object()
        )
        self.silver_database = glue.Database(
            self, "SilverDatabase",
            database_name=config.resource_name("silver", sep="_"),
            location_uri=self.silver_s3.s3_url_for_object()
        )
        self.gold_database = glue.Database(
            self, "GoldDatabase",
            database_name=config.resource_name("gold", sep="_"),
            location_uri=self.gold_s3.s3_url_for_object()
        )
