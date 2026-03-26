"""Testes para a montagem dos handlers do bot."""
import unittest
import warnings

from telegram.ext import CommandHandler, ConversationHandler
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

    def test_empresas_global_fica_apos_conversation_handlers(self):
        from handlers import get_handlers

        handlers = get_handlers()
        ultimo_conversation = max(
            indice for indice, handler in enumerate(handlers) if isinstance(handler, ConversationHandler)
        )
        indice_empresas = next(
            indice
            for indice, handler in enumerate(handlers)
            if isinstance(handler, CommandHandler) and "empresas" in getattr(handler, "commands", ())
        )

        self.assertGreater(indice_empresas, ultimo_conversation)

    def test_todos_conversation_handlers_aceitam_empresas_como_fallback(self):
        from handlers import get_handlers

        handlers = get_handlers()
        conversation_handlers = [
            handler for handler in handlers if isinstance(handler, ConversationHandler)
        ]

        self.assertTrue(conversation_handlers)
        for handler in conversation_handlers:
            comandos_fallback = {
                comando
                for fallback in handler.fallbacks
                if isinstance(fallback, CommandHandler)
                for comando in getattr(fallback, "commands", ())
            }
            self.assertIn("empresas", comandos_fallback)
