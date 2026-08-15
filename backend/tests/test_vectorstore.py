import unittest
from contextlib import nullcontext
from datetime import timedelta
from unittest.mock import MagicMock, patch

from core import vectorstore


class VectorStoreInitializationTests(unittest.TestCase):
    def tearDown(self):
        vectorstore._table.cache_clear()

    def test_table_initialization_is_idempotent_and_strongly_consistent(self):
        connection = MagicMock()
        table = MagicMock()
        connection.create_table.return_value = table

        with (
            patch.object(vectorstore.lancedb, "connect", return_value=connection) as connect,
            patch.object(vectorstore, "_write_lock", return_value=nullcontext()),
        ):
            vectorstore._table.cache_clear()
            self.assertIs(vectorstore._table(), table)

        connect.assert_called_once_with(
            str(vectorstore.LANCEDB_DIR),
            read_consistency_interval=timedelta(seconds=0),
        )
        connection.create_table.assert_called_once_with(
            vectorstore.TABLE,
            schema=vectorstore.SCHEMA,
            exist_ok=True,
        )

    def test_add_chunks_replaces_matching_ids_before_append(self):
        table = MagicMock()
        rows = [{
            "chunk_id": 7,
            "item_id": 3,
            "subject": "Math",
            "source_label": "Test",
            "text": "Matrices",
        }]

        with (
            patch.object(vectorstore, "_table", return_value=table),
            patch.object(vectorstore, "_write_lock", return_value=nullcontext()),
            patch.object(vectorstore, "embed", return_value=[[0.0] * 384]),
        ):
            vectorstore.add_chunks(rows)

        table.delete.assert_called_once_with("chunk_id IN (7)")
        table.add.assert_called_once_with(rows)

    def test_subject_update_and_delete_use_integer_filters(self):
        table = MagicMock()
        with (
            patch.object(vectorstore, "_table", return_value=table),
            patch.object(vectorstore, "_write_lock", return_value=nullcontext()),
        ):
            vectorstore.update_item_subject(12, "Mathematics")
            vectorstore.delete_chunks([9, 4, 9])

        table.update.assert_called_once_with(
            {"subject": "Mathematics"},
            where="item_id = 12",
        )
        table.delete.assert_called_once_with("chunk_id IN (4, 9)")


if __name__ == "__main__":
    unittest.main()
