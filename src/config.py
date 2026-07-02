from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Config:
    raw: dict

    def get(self, path: str, default=None):
        node = self.raw
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


def load_config(path: str = "config.yaml") -> Config:
    p = Path(path)
    data = yaml.safe_load(p.read_text()) if p.exists() else {}
    return Config(raw=data or {})
