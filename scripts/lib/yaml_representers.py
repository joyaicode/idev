"""A str subclass whose yaml dump is a literal block (`|`).

yaml.safe_dump renders a multi-line str as a single-quoted scalar with folded
newlines. Consumers that re-read the file (line-anchored regexes over
report.raw, grep over lesson text) see one long line instead of the lines the
writer wrote. Registering one representer on the Dumper is the standard way
to opt a specific string into block style without changing how every other
string in the file is quoted.
"""
import yaml


class LiteralString(str):
    """A str that dumps as `|` (keep newlines) instead of a folded scalar."""


def _literal_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="|")


_Dumper = type("LiteralDumper", (yaml.SafeDumper,), {})
_Dumper.add_representer(LiteralString, _literal_representer)


def dump(data):
    """safe_dump, but LiteralString values keep their newlines."""
    return yaml.dump(
        data, Dumper=_Dumper, allow_unicode=True, sort_keys=False, default_flow_style=False
    )
