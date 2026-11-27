from dataclasses import dataclass

# Do not change these names once deployed: renaming a bucket or Glue database
# replaces it (new empty bucket, old one retained; Glue table definitions deleted).
# Bucket prefixes are kept to <=32 chars so the account-regional suffix
# (-<account>-<region>-an) fits the 63-char limit in every AWS region.
NAME_PREFIX = "mobile-analytics"

@dataclass
class EnvConfig:
    name: str
    account: str
    region: str

    def resource_name(self, purpose: str, sep: str = "-") -> str:
        return sep.join((NAME_PREFIX.replace("-", sep), purpose, self.name))

ENVS = {
    "dev":  EnvConfig("dev",  "444958704225", "eu-west-1"),
    "uat":  EnvConfig("uat",  "444958704225", "eu-west-1"),
    "prod": EnvConfig("prod", "444958704225", "eu-west-1"),
}
