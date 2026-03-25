"""Testes para a montagem dos handlers do bot."""
import unittest
import warnings

from telegram.warnings import PTBUserWarning


class HandlerFactoryTests(unittest.TestCase):
    def test_get_handlers_nao_emite_warning_known_do_ptb(self):
        from handlers import get_handlers

        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            handlers = get_handlers()

        self.assertTrue(handlers)
        ptb_warnings = [warning for warning in captured if issubclass(warning.category, PTBUserWarning)]
        self.assertEqual(
            ptb_warnings,
            [],
            msg=[str(warning.message) for warning in ptb_warnings],
        )
