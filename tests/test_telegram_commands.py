import unittest
from unittest.mock import AsyncMock

from telegram import BotCommandScopeAllPrivateChats, BotCommandScopeChat

import telegram_commands


class TelegramCommandsTests(unittest.IsolatedAsyncioTestCase):
    def test_comandos_do_admin_expoem_gestao_completa(self):
        comandos = [comando.command for comando in telegram_commands.obter_comandos_admin()]

        self.assertIn("painel", comandos)
        self.assertIn("link", comandos)
        self.assertIn("upload", comandos)
        self.assertIn("reset", comandos)

    def test_comandos_do_cliente_escondem_gestao(self):
        comandos = [comando.command for comando in telegram_commands.obter_comandos_cliente()]

        self.assertEqual(comandos, ["start", "sair", "ajuda"])
        self.assertNotIn("painel", comandos)
        self.assertNotIn("upload", comandos)
        self.assertNotIn("reset", comandos)

    async def test_configurar_menu_nativo_padrao_define_comandos_privados(self):
        bot = AsyncMock()

        await telegram_commands.configurar_menu_nativo_padrao(bot)

        args, kwargs = bot.set_my_commands.await_args
        comandos = [comando.command for comando in args[0]]

        self.assertEqual(comandos, ["start", "ajuda"])
        self.assertIsInstance(kwargs["scope"], BotCommandScopeAllPrivateChats)
        bot.set_chat_menu_button.assert_awaited_once()

    async def test_sincronizar_comandos_chat_aplica_escopo_do_chat(self):
        bot = AsyncMock()

        await telegram_commands.sincronizar_comandos_chat(bot, 123456, "admin")

        args, kwargs = bot.set_my_commands.await_args
        comandos = [comando.command for comando in args[0]]
        scope = kwargs["scope"]

        self.assertIn("painel", comandos)
        self.assertIn("link", comandos)
        self.assertIsInstance(scope, BotCommandScopeChat)
        self.assertEqual(scope.chat_id, 123456)

    async def test_sincronizar_comandos_existentes_reaplica_admins_e_clientes(self):
        bot = AsyncMock()

        await telegram_commands.sincronizar_comandos_existentes(bot, [10], [20, 30])

        self.assertEqual(bot.set_my_commands.await_count, 3)

        comandos_primeiro = [comando.command for comando in bot.set_my_commands.await_args_list[0].args[0]]
        comandos_segundo = [comando.command for comando in bot.set_my_commands.await_args_list[1].args[0]]
        comandos_terceiro = [comando.command for comando in bot.set_my_commands.await_args_list[2].args[0]]

        self.assertIn("painel", comandos_primeiro)
        self.assertEqual(comandos_segundo, ["start", "sair", "ajuda"])
        self.assertEqual(comandos_terceiro, ["start", "sair", "ajuda"])
