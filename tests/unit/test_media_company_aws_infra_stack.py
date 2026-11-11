import aws_cdk as core
import aws_cdk.assertions as assertions

from media_company_aws_infra.media_company_aws_infra_stack import MediaCompanyAwsInfraStack

# example tests. To run these tests, uncomment this file along with the example
# resource in media_company_aws_infra/media_company_aws_infra_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = MediaCompanyAwsInfraStack(app, "media-company-aws-infra")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
