"""Tree / hierarchy mixin for todos: subtree, flatten, move."""

from __future__ import annotations

from typing import Any


class _TodoTreeMixin:
    """Mixin providing tree traversal and hierarchy operations
    for the TodoService class."""

    # ── Tree / Hierarchy ────────────────────────────────────────────────

    def get_tree(self, parent_uuid: str | None = None,
                 depth: int = 0, max_depth: int = 10
                 ) -> list[dict[str, Any]]:
        if depth > max_depth:
            return []
        if parent_uuid is None:
            rows = self.db.execute(
                "SELECT * FROM tasks WHERE parent_uuid IS NULL"
                " ORDER BY sort_order, created_at DESC",
            )
        else:
            rows = self.db.execute(
                "SELECT * FROM tasks WHERE parent_uuid = ?"
                " ORDER BY sort_order, created_at DESC",
                (parent_uuid,),
            )
        result = []
        for row in rows:
            children = self.get_tree(row["uuid"], depth + 1, max_depth)
            item = dict(row)
            item["children"] = children
            item["_computed_priority"] = self._compute_priority(item)
            result.append(item)
        return result

    def flatten_tree(self, parent_uuid: str | None = None
                     ) -> list[dict[str, Any]]:
        flat: list[dict[str, Any]] = []

        def _walk(pid: str | None, depth: int) -> None:
            if pid is None:
                rows = self.db.execute(
                    "SELECT * FROM tasks WHERE parent_uuid IS NULL"
                    " ORDER BY sort_order, created_at DESC",
                )
            else:
                rows = self.db.execute(
                    "SELECT * FROM tasks WHERE parent_uuid = ?"
                    " ORDER BY sort_order, created_at DESC",
                    (pid,),
                )
            for row in rows:
                has_children = bool(
                    self.db.execute_one(
                        "SELECT 1 FROM tasks WHERE parent_uuid = ? LIMIT 1",
                        (row["uuid"],),
                    )
                )
                item = dict(row)
                item["_depth"] = depth
                item["_has_children"] = has_children
                item["_computed_priority"] = self._compute_priority(item)
                flat.append(item)
                if has_children:
                    _walk(row["uuid"], depth + 1)

        _walk(parent_uuid, 0)
        return self._attach_labels(flat)

    def get_with_children(self, uuid_: str) -> dict[str, Any] | None:
        todo = self.get(uuid_)
        if not todo:
            return None
        todo["children"] = self.get_tree(uuid_, depth=1)
        todo["_computed_priority"] = self._compute_priority(todo)
        todo["labels"] = self._tag_svc().get_tags_for("todo", uuid_)
        return todo

    def move_as_child(self, uuid_: str, parent_uuid_: str | None) -> None:
        self.update(uuid_, {"parent_uuid": parent_uuid_})
