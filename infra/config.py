from dataclasses import dataclass

@dataclass
class EnvConfig:
    name: str
    account: str
    region: str

ENVS = {
    "dev":  EnvConfig("dev",  "444958704225", "eu-west-1"),
    "uat":  EnvConfig("uat",  "444958704225", "eu-west-1"),
    "prod": EnvConfig("prod", "444958704225", "eu-west-1"),
}
