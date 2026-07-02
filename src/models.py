from dataclasses import dataclass, field, asdict


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: str | None = None


@dataclass
class ActionItem:
    task: str
    owner: str = ""
    due: str = ""


@dataclass
class Minutes:
    title: str
    date: str
    attendees: list[str] = field(default_factory=list)
    summary: str = ""
    key_points: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Minutes":
        d = dict(d)
        d["action_items"] = [ActionItem(**a) for a in d.get("action_items", [])]
        return cls(**d)
