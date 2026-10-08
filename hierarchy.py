"""Organisation hierarchy helpers (Organisation > BU > Client > Process > Location > Team ...).

The hierarchy is data, not code: unit types come from the database, so a
customer can use different levels without any program change."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class Scope:
    """A selection of units the dashboard is looking at."""
    unit_ids: frozenset            # every unit inside the selection (any depth)
    leaf_ids: frozenset            # units without children inside the selection
    anchor_id: str | None          # lowest common ancestor (None = whole organisation)
    filters: tuple = field(default_factory=tuple)   # ((level, name), ...) used to build it
    label: str = "Whole organisation"


class Hierarchy:
    def __init__(self, units: pd.DataFrame, levels: list[str] | None = None):
        self.df = units.set_index("id", drop=False)
        self.parent: dict[str, str | None] = {r.id: r.parent_id for r in units.itertuples()}
        self.children: dict[str, list[str]] = defaultdict(list)
        for uid, pid in self.parent.items():
            if pid:
                self.children[pid].append(uid)
        self.type = dict(zip(units["id"], units["unit_type"]))
        self.name = dict(zip(units["id"], units["name"]))
        self._anc = {uid: self._ancestors(uid) for uid in self.parent}
        self.depth = {uid: len(a) - 1 for uid, a in self._anc.items()}
        if not levels:   # order unit types by their typical depth
            depth_by_type = units.assign(d=units["id"].map(self.depth)).groupby("unit_type")["d"].median()
            levels = list(depth_by_type.sort_values().index)
        self.levels = [lv for lv in levels if lv in set(self.type.values())]
        self.path = {uid: {self.type[a]: self.name[a] for a in anc} for uid, anc in self._anc.items()}
        self.leaves = frozenset(u for u in self.parent if not self.children.get(u))

    def _ancestors(self, uid: str) -> list[str]:
        """The unit itself followed by its parent, grandparent ... (guards against loops)."""
        out, seen, cur = [], set(), uid
        while cur and cur not in seen and cur in self.parent:
            out.append(cur)
            seen.add(cur)
            cur = self.parent[cur]
        return out

    def ancestors(self, uid: str) -> list[str]:
        return self._anc.get(uid, [])

    def options(self, level: str, filters: dict[str, str | None]) -> list[str]:
        """Names available at ``level`` given the filters chosen at the levels above it."""
        names = set()
        for path in self.path.values():          # paths of every unit, so filters below a level also work
            if level in path and all(path.get(lv) == val for lv, val in filters.items() if val and lv != level):
                names.add(path[level])
        return sorted(names)

    def scope(self, filters: dict[str, str | None] | None = None) -> Scope:
        active = tuple((lv, v) for lv, v in (filters or {}).items() if v)
        units = frozenset(uid for uid, path in self.path.items()
                          if all(path.get(lv) == val for lv, val in active))
        leaves = frozenset(u for u in units if u in self.leaves)
        label = " › ".join(v for _, v in active) if active else "Whole organisation"
        return Scope(units, leaves, self.common_ancestor(units) if active else None, active, label)

    def common_ancestor(self, unit_ids) -> str | None:
        unit_ids = list(unit_ids)
        if not unit_ids:
            return None
        common = None
        for uid in unit_ids:
            chain = set(self.ancestors(uid))
            common = chain if common is None else common & chain
            if not common:
                return None
        # the deepest shared ancestor
        return max(common, key=lambda u: self.depth[u])

    def unit_table(self) -> pd.DataFrame:
        rows = []
        for uid in self.parent:
            row = {"id": uid, "unit_type": self.type[uid], "name": self.name[uid],
                   "depth": self.depth[uid], "is_leaf": uid in self.leaves}
            row.update({lv: self.path[uid].get(lv) for lv in self.levels})
            rows.append(row)
        return pd.DataFrame(rows)
