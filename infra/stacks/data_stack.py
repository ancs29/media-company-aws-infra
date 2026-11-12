from aws_cdk import (
    Stack, 
    aws_s3 as s3, 
    aws_glue as glue
)
from constructs import Construct

class DataStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.bronze_s3 = s3.Bucket(self, "BronzeS3")
        self.silver_s3 = s3.Bucket(self, "SilverS3")
        self.gold_s3 = s3.Bucket(self, "GoldS3")
        self.landing_s3 = s3.Bucket(self, "LandingS3", event_bridge_enabled=True)
        self.unsubscribe_events_s3 = s3.Bucket(self, "UnsubscribeS3")

        self.bronze_database = glue.Database(
            self, "BronzeDatabase",
            database_name="bronze",
            location_uri=self.bronze_s3.bucket_arn
        )
        self.silver_database = glue.Database(
            self, "SilverDatabase",
            database_name="silver",
            location_uri=self.silver_s3.bucket_arn
        )
        self.gold_database = glue.Database(
            self, "GoldDatabase",
            database_name="gold",
            location_uri=self.gold_s3.bucket_arn
        )