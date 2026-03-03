import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ObjectiveConfig:
    desire_bonus_weight: int = 10
    activation_penalty: int = 1
    lecture_lecture_conflict_penalty: int = 10
    lecture_workshop_conflict_penalty: int = 3
    workshop_workshop_conflict_penalty: int = 1


def load_objective_config(path: Path = None):
    if path is None:
        path = Path(__file__).with_name("objective_config.json")
        
    if not path.exists():
        return ObjectiveConfig()
    
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ObjectiveConfig(
        desire_bonus_weight=int(raw.get("desire_bonus_weight", 10)),
        activation_penalty=int(raw.get("activation_penalty", 1)),
        lecture_lecture_conflict_penalty=int(raw.get("lecture_lecture_conflict_penalty", 10)),
        lecture_workshop_conflict_penalty=int(raw.get("lecture_workshop_conflict_penalty", 3)),
        workshop_workshop_conflict_penalty=int(raw.get("workshop_workshop_conflict_penalty", 1)),
    )
