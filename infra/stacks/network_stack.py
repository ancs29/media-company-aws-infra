from aws_cdk import (
    Stack,
    aws_ec2 as ec2
)
from constructs import Construct

class NetworkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = ec2.Vpc(self, "MediaCompanyVPC",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=3, 
            nat_gateways=1, # One NAT gateway to save money, trading off fault tolerance
            subnet_configuration=[
                ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                ec2.SubnetConfiguration(name="private_egress", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=24),
                ec2.SubnetConfiguration(name="private_isolated", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24)
            ]
        )

        self.vpc.add_gateway_endpoint("S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3
        )

        # Glue jobs in isolated subnets have no NAT, so they reach the Glue API
        # (Data Catalog) through this endpoint. Only one private-DNS endpoint per
        # service is allowed in a VPC, so it lives here as shared infrastructure.
        self.vpc.add_interface_endpoint("GlueEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.GLUE,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            private_dns_enabled=True
        )

        self.vpc.add_flow_log("FlowLog")