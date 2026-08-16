import errno
import unittest
from unittest.mock import MagicMock, patch

from core import vectorstore


class VectorStoreRecoveryTests(unittest.TestCase):
    def test_eio_reopens_table_and_retries_mutation_once(self):
        stale = MagicMock()
        fresh = MagicMock()
        operation = MagicMock(side_effect=[OSError(errno.EIO, "Input/output error"), None])

        with (
            patch.object(vectorstore, "_table", side_effect=[stale, fresh]) as get_table,
            patch.object(vectorstore, "_write_lock"),
        ):
            vectorstore._mutate(operation)

        self.assertEqual(get_table.call_count, 2)
        get_table.cache_clear.assert_called_once_with()
        self.assertEqual(operation.call_args_list[0].args, (stale,))
        self.assertEqual(operation.call_args_list[1].args, (fresh,))

    def test_non_eio_is_not_retried(self):
        operation = MagicMock(side_effect=OSError(errno.ENOSPC, "No space left"))
        with (
            patch.object(vectorstore, "_table", return_value=MagicMock()) as get_table,
            patch.object(vectorstore, "_write_lock"),
        ):
            with self.assertRaises(OSError):
                vectorstore._mutate(operation)
        get_table.assert_called_once()


if __name__ == "__main__":
    unittest.main()
