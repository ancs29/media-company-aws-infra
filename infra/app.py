import aws_cdk as cdk

from stacks.data_stack import DataStack
from stacks.network_stack import NetworkStack
from stacks.streaming_stack import StreamingStack
from stacks.processing_stack import ProcessingStack
from stacks.consumer_stack import ConsumerStack

from config import ENVS

app = cdk.App()
config = ENVS[app.node.try_get_context("env") or "dev"]
env = cdk.Environment(account=config.account, region=config.region)

data_stack = DataStack(
    app, "DataStack",
    config=config,
    env=env
)

network_stack = NetworkStack(
    app, "NetworkStack",
    env=env
)

streaming_stack = StreamingStack(
    app, "StreamingStack",
    unsubscribe_events=data_stack.unsubscribe_events_s3,
    vpc=network_stack.vpc,
    env=env
)

processing_stack = ProcessingStack(
    app, "ProcessingStack",
    config=config,
    vpc=network_stack.vpc,
    scripts=data_stack.scripts_s3,
    landing=data_stack.landing_s3,
    bronze=data_stack.bronze_s3,
    silver=data_stack.silver_s3,
    gold=data_stack.gold_s3,
    env=env
)

consumer_stack = ConsumerStack(
    app, "ConsumerStack",
    config=config,
    vpc=network_stack.vpc,
    env=env
)

app.synth()
