"""Todo service class — assembled from focused mixin modules.

See individual sub-modules for implementation details:
    - todo_crud.py: CRUD hooks, search/list, labels, dependencies, attachments, priority
    - todo_tree.py: tree/flat hierarchy operations
    - todo_template.py: template CRUD
    - todo_export_import.py: markdown export/import
"""

from __future__ import annotations

from typing import Any

from lighterbird.core.crud import CRUDService
from lighterbird.todo.services.todo_crud import _TodoCrudMixin
from lighterbird.todo.services.todo_export_import import _TodoExportImportMixin
from lighterbird.todo.services.todo_template import _TodoTemplateMixin
from lighterbird.todo.services.todo_tree import _TodoTreeMixin


class TodoService(
    _TodoCrudMixin,
    _TodoTreeMixin,
    _TodoTemplateMixin,
    _TodoExportImportMixin,
    CRUDService,
):
    """CRUD service for tasks with priority formulas, labels,
    subtask hierarchy, dependencies, attachments, and templates."""

    def __init__(self, db):
        super().__init__(db, "tasks")

    def update(self, pk: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update a todo, intercepting ``_tags`` for label management."""
        data = dict(data)
        tags = data.pop("_tags", None)
        result = super().update(pk, data)
        if tags is not None and result is not None:
            # Remove existing labels, then add new ones
            current = self.db.execute(
                "SELECT label_name FROM todo_labels WHERE todo_uuid = ?",
                (pk,),
            )
            for row in current:
                self.db.execute(
                    "DELETE FROM todo_labels WHERE todo_uuid = ? AND label_name = ?",
                    (pk, row["label_name"]),
                )
            for tag_name in tags:
                self.add_label(pk, tag_name)
        return result
