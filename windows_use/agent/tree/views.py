from dataclasses import dataclass,field
from typing import TYPE_CHECKING, Optional,Any
import json

WARNING_MESSAGE="The desktop UI services are temporarily unavailable. Please wait a few seconds and continue."
EMPTY_MESSAGE="No elements found"

if TYPE_CHECKING:
    from windows_use.uia.core import Rect

# ── Humphi AI compression settings ───────────────────────────────────────────
# Controls how aggressively we compress the UI tree before sending to Groq.
# Groq free tier limit is 6000 TPM. Original output was 11,644 tokens.
# With compression we target under 2000 tokens leaving room for system prompt.

HUMPHI_MAX_INTERACTIVE = 40   # max interactive elements to send
HUMPHI_MAX_SCROLLABLE  = 10   # max scrollable elements to send
HUMPHI_MAX_NAME_LEN    = 35   # truncate long element names
HUMPHI_STRIP_METADATA  = True # strip metadata JSON entirely (saves ~60% tokens)

# Metadata keys worth keeping — everything else stripped
HUMPHI_KEEP_META_KEYS  = {"value", "is_focused", "shortcut"}


def _compress_name(name: str) -> str:
    """Truncate long names and strip whitespace."""
    name = " ".join(name.split())  # collapse whitespace
    if len(name) > HUMPHI_MAX_NAME_LEN:
        return name[:HUMPHI_MAX_NAME_LEN] + "…"
    return name


def _compress_meta(metadata: dict) -> str:
    """Keep only useful metadata keys, strip the rest."""
    if HUMPHI_STRIP_METADATA:
        # Only keep keys that actually help the LLM decide what to do
        slim = {k: v for k, v in metadata.items()
                if k in HUMPHI_KEEP_META_KEYS and v not in (None, "", False, {})}
        if not slim:
            return "{}"
        return json.dumps(slim, separators=(',', ':'))
    return json.dumps(metadata)


@dataclass
class TreeState:
    status:bool=True
    root_node:Optional['TreeElementNode']=None
    dom_node:Optional['ScrollElementNode']=None
    interactive_nodes:list['TreeElementNode']|None=field(default_factory=list)
    scrollable_nodes:list['ScrollElementNode']|None=field(default_factory=list)
    dom_informative_nodes:list['TextElementNode']|None=field(default_factory=list)

    def interactive_elements_to_string(self) -> str:
        if not self.status:
            return WARNING_MESSAGE
        if not self.interactive_nodes:
            return EMPTY_MESSAGE

        # ── Humphi: compress before sending to Groq ───────────────────────
        nodes = self.interactive_nodes[:HUMPHI_MAX_INTERACTIVE]
        total = len(self.interactive_nodes)
        trimmed = total - len(nodes)

        # Compressed header — fewer words = fewer tokens
        header = "#|win|type|name|xy|meta"
        rows = [header]

        for idx, node in enumerate(nodes):
            name = _compress_name(node.name or "")
            # Strip window name if it matches the control type — redundant noise
            win = _compress_name(node.window_name or "")[:20]
            ctype = node.control_type or ""
            coords = node.center.to_string()
            meta = _compress_meta(node.metadata)

            # Skip completely empty/unnamed non-button elements
            if not name and ctype not in ("Button", "MenuItem", "Hyperlink"):
                continue

            row = f"{idx}|{win}|{ctype}|{name}|{coords}|{meta}"
            rows.append(row)

        result = "\n".join(rows)

        if trimmed > 0:
            result += f"\n[+{trimmed} more elements not shown]"

        return result

    def scrollable_elements_to_string(self) -> str:
        if not self.status:
            return WARNING_MESSAGE
        if not self.scrollable_nodes:
            return EMPTY_MESSAGE

        # ── Humphi: compress scrollable elements ──────────────────────────
        nodes = self.scrollable_nodes[:HUMPHI_MAX_SCROLLABLE]
        base_index = len(self.interactive_nodes) if self.interactive_nodes else 0

        header = "#|win|type|name|xy|meta"
        rows = [header]

        for idx, node in enumerate(nodes):
            name = _compress_name(node.name or "")
            win = _compress_name(node.window_name or "")[:20]
            ctype = node.control_type or ""
            coords = node.center.to_string()
            meta = _compress_meta(node.metadata)
            row = f"{base_index + idx}|{win}|{ctype}|{name}|{coords}|{meta}"
            rows.append(row)

        return "\n".join(rows)


@dataclass
class BoundingBox:
    left:int
    top:int
    right:int
    bottom:int
    width:int
    height:int

    @classmethod
    def from_bounding_rectangle(cls,bounding_rectangle:'Rect')->'BoundingBox':
        return cls(
            left=bounding_rectangle.left,
            top=bounding_rectangle.top,
            right=bounding_rectangle.right,
            bottom=bounding_rectangle.bottom,
            width=bounding_rectangle.width(),
            height=bounding_rectangle.height()
        )

    def get_center(self)->'Center':
        return Center(x=self.left+self.width//2,y=self.top+self.height//2)

    def xywh_to_string(self):
        return f'({self.left},{self.top},{self.width},{self.height})'
    
    def xyxy_to_string(self):
        x1,y1,x2,y2=self.convert_xywh_to_xyxy()
        return f'({x1},{y1},{x2},{y2})'
    
    def convert_xywh_to_xyxy(self)->tuple[int,int,int,int]:
        x1,y1=self.left,self.top
        x2,y2=self.left+self.width,self.top+self.height
        return x1,y1,x2,y2

@dataclass
class Center:
    x:int
    y:int

    def to_string(self)->str:
        return f'({self.x},{self.y})'

@dataclass
class TreeElementNode:
    bounding_box: BoundingBox
    center: Center
    name: str=''
    control_type: str=''
    window_name: str=''
    metadata:dict[str,Any]=field(default_factory=dict)

    def update_from_node(self,node:'TreeElementNode'):
        self.name=node.name
        self.control_type=node.control_type
        self.window_name=node.window_name
        self.value=node.value
        self.shortcut=node.shortcut
        self.bounding_box=node.bounding_box
        self.center=node.center
        self.metadata=node.metadata

    def to_row(self, index: int):
        return [index, self.window_name, self.control_type, self.name, self.center.to_string()]

@dataclass
class ScrollElementNode:
    name: str
    control_type: str
    window_name: str
    bounding_box: BoundingBox
    center: Center
    metadata:dict[str,Any]=field(default_factory=dict)

    def to_row(self, index: int, base_index: int):
        return [
            base_index + index,
            self.window_name,
            self.control_type,
            self.name,
            self.center.to_string(),
            json.dumps(self.metadata)
        ]

@dataclass
class TextElementNode:
    text:str

ElementNode=TreeElementNode|ScrollElementNode|TextElementNode