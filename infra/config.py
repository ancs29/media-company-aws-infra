from dataclasses import dataclass

@dataclass
class EnvConfig:
    account: str
    region: str

ENVS = {
    "dev":  EnvConfig("444958704225", "eu-west-1"),
    "uat":  EnvConfig("444958704225", "eu-west-1"),
    "prod": EnvConfig("444958704225", "eu-west-1"),
}