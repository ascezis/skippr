from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class RowItem:
    n: int
    block: str
    phrase: str
    kind: str  # клип / картинка / оригинал / текст
    reference: str = ""
    query: str = ""
    tc: Optional[str] = None
    duration: float = 3.0
    offset: float = 0.0
    priority: str = "B"  # A / B / C
    status: str = "найти"  # найти / скачано / ошибка / пропуск
    notes: str = ""
    file: Optional[str] = None
    row_idx: Optional[int] = None
    raw_dict: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PhraseAnchor:
    n: int
    anchor_start: float
    anchor_end: float
    confidence: float
    method: str  # exact | fuzzy | override | failed


@dataclass
class SidecarData:
    source_in: float
    source_out: float
    useful_in: float
    useful_out: float
    handle_in: float
    handle_out: float
    src_url: str = ""
    src_fps: float = 25.0


@dataclass
class PlanItem:
    n: int
    block: str
    kind: str  # клип / placeholder / ...
    file: Optional[str]
    track: str  # V1 / V2
    timeline_start: float
    timeline_duration: float
    timeline_start_frame: int
    timeline_duration_frame: int
    source_in: float
    source_out: float
    source_in_frame: int
    source_out_frame: int
    speed: float = 1.0
    flags: List[str] = field(default_factory=list)
    phrase: str = ""
    reference: str = ""
