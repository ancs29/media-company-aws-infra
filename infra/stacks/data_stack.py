from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_glue as glue
)
from constructs import Construct

from config import EnvConfig

# Do not change these names once deployed: renaming a bucket or Glue database
# replaces it (new empty bucket, old one retained; Glue table definitions deleted).
# Bucket prefixes are kept to <=32 chars so the account-regional suffix
# (-<account>-<region>-an) fits the 63-char limit in every AWS region.
NAME_PREFIX = "mobile-analytics"

class DataStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, config: EnvConfig, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        def bucket(construct_id: str, purpose: str, **bucket_kwargs) -> s3.Bucket:
            return s3.Bucket(
                self, construct_id,
                bucket_name_prefix=f"{NAME_PREFIX}-{purpose}-{config.name}",
                bucket_namespace=s3.BucketNamespace.ACCOUNT_REGIONAL,
                **bucket_kwargs
            )

        self.bronze_s3 = bucket("BronzeS3", "bronze")
        self.silver_s3 = bucket("SilverS3", "silver")
        self.gold_s3 = bucket("GoldS3", "gold")
        self.landing_s3 = bucket("LandingS3", "landing")
        self.unsubscribe_events_s3 = bucket("UnsubscribeS3", "unsub", event_bridge_enabled=True)

        glue_prefix = NAME_PREFIX.replace("-", "_")

        self.bronze_database = glue.Database(
            self, "BronzeDatabase",
            database_name=f"{glue_prefix}_bronze_{config.name}",
            location_uri=self.bronze_s3.s3_url_for_object()
        )
        self.silver_database = glue.Database(
            self, "SilverDatabase",
            database_name=f"{glue_prefix}_silver_{config.name}",
            location_uri=self.silver_s3.s3_url_for_object()
        )
        self.gold_database = glue.Database(
            self, "GoldDatabase",
            database_name=f"{glue_prefix}_gold_{config.name}",
            location_uri=self.gold_s3.s3_url_for_object()
        )
