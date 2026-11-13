import aws_cdk as cdk

from stacks.data_stack import DataStack
from stacks.network_stack import NetworkStack
from stacks.streaming_stack import StreamingStack

from config import ENVS

app = cdk.App()
env_name = app.node.try_get_context("env") or "dev"
config = ENVS[env_name]

data_stack = DataStack(
    app, "DataStack",
    env=cdk.Environment(account=config.account, region=config.region)
)

network_stack = NetworkStack(
    app, "NetworkStack",
    env=cdk.Environment(account=config.account, region=config.region)
)

streaming_stack = StreamingStack(
    app, "StreamingStack",
    landing=data_stack.landing_s3,
    vpc=network_stack.vpc,
    env=cdk.Environment(account=config.account, region=config.region)
)

app.synth()
