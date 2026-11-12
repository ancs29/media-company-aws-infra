from aws_cdk import (
    Stack,
    aws_ec2 as ec2
)
from constructs import Construct

class NetworkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = ec2.Vpc(self, "MediaCompanyVPC",
            max_azs=3, 
            nat_gateways=1 # One NAT gateway to save money, trading off fault tolerance
        )

        self.vpc.add_gateway_endpoint("S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3
        )

        self.vpc.add_flow_log("FlowLog")