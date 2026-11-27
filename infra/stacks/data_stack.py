from aws_cdk import (
    Stack,
    aws_s3 as s3,
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
        self.unsubscribe_events_s3 = bucket("UnsubscribeS3", "unsub", event_bridge_enabled=True)
        self.scripts_s3 = bucket("ScriptsS3", "scripts")

        s3_deployment.BucketDeployment(
            self, "GlueScriptsDeployment",
            sources=[s3_deployment.Source.asset("glue")],
            destination_bucket=self.scripts_s3
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
