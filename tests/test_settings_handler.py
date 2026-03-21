"""Testes para handlers/settings.py — pausar, ativar, horário, fallback, editar."""
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from telegram.ext import ConversationHandler

from tests.helpers import make_update, make_context, make_empresa


class DefinirStatusAgenteTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.settings._obter_empresa_admin_ou_responder")
    @patch("handlers.settings.atualizar_empresa", new_callable=AsyncMock)
    async def test_pausar_agente_ativo(self, mock_att, mock_admin):
        from handlers.settings import _definir_status_agente

        mock_admin.return_value = make_empresa(ativo=1)
        update = make_update()
        ctx = make_context()
        await _definir_status_agente(update, ctx, ativo=False)
        mock_att.assert_called_once()
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("pausado", texto.lower())

    @patch("handlers.settings._obter_empresa_admin_ou_responder")
    @patch("handlers.settings.atualizar_empresa", new_callable=AsyncMock)
    async def test_ativar_agente_pausado(self, mock_att, mock_admin):
        from handlers.settings import _definir_status_agente

        mock_admin.return_value = make_empresa(ativo=0)
        update = make_update()
        ctx = make_context()
        await _definir_status_agente(update, ctx, ativo=True)
        mock_att.assert_called_once()
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("ativado", texto.lower())

    @patch("handlers.settings._obter_empresa_admin_ou_responder")
    async def test_ja_ativo_nao_atualiza(self, mock_admin):
        from handlers.settings import _definir_status_agente

        mock_admin.return_value = make_empresa(ativo=1)
        update = make_update()
        ctx = make_context()
        with patch("handlers.settings.atualizar_empresa", new_callable=AsyncMock) as mock_att:
            await _definir_status_agente(update, ctx, ativo=True)
            mock_att.assert_not_called()
        texto = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("já está ativo", texto)

    @patch("handlers.settings._obter_empresa_admin_ou_responder", return_value=None)
    async def test_sem_empresa_retorna(self, mock_admin):
        from handlers.settings import _definir_status_agente

        update = make_update()
        ctx = make_context()
        await _definir_status_agente(update, ctx, ativo=True)
        update.effective_message.reply_text.assert_not_called()


class CmdPausarAtivarTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.settings._definir_status_agente", new_callable=AsyncMock)
    async def test_cmd_pausar(self, mock_def):
        from handlers.settings import cmd_pausar

        update = make_update()
        ctx = make_context()
        await cmd_pausar(update, ctx)
        mock_def.assert_called_once_with(update, ctx, ativo=False)

    @patch("handlers.settings._definir_status_agente", new_callable=AsyncMock)
    async def test_cmd_ativar(self, mock_def):
        from handlers.settings import cmd_ativar

        update = make_update()
        ctx = make_context()
        await cmd_ativar(update, ctx)
        mock_def.assert_called_once_with(update, ctx, ativo=True)


class CmdHorarioTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.settings._obter_empresa_admin_ou_responder", return_value=None)
    async def test_sem_empresa(self, mock_admin):
        from handlers.settings import cmd_horario

        update = make_update()
        ctx = make_context()
        result = await cmd_horario(update, ctx)
        self.assertEqual(result, ConversationHandler.END)

    @patch("handlers.settings._obter_empresa_admin_ou_responder")
    @patch("handlers.settings.atualizar_empresa", new_callable=AsyncMock)
    async def test_com_args_limpar(self, mock_att, mock_admin):
        from handlers.settings import cmd_horario

        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context(args=["limpar"])
        ctx.args = ["limpar"]
        result = await cmd_horario(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        mock_att.assert_called_once()

    @patch("handlers.settings._obter_empresa_admin_ou_responder")
    @patch("handlers.settings.atualizar_empresa", new_callable=AsyncMock)
    async def test_com_args_horario_direto(self, mock_att, mock_admin):
        from handlers.settings import cmd_horario

        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context(args=["Seg", "a", "Sex"])
        ctx.args = ["Seg", "a", "Sex"]
        result = await cmd_horario(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        mock_att.assert_called_once()

    @patch("handlers.settings._obter_empresa_admin_ou_responder")
    async def test_sem_args_pergunta_horario(self, mock_admin):
        from handlers.settings import cmd_horario
        from handlers.common import AGUARDANDO_HORARIO

        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context(args=None)
        ctx.args = None
        result = await cmd_horario(update, ctx)
        self.assertEqual(result, AGUARDANDO_HORARIO)


class ReceberHorarioTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.settings._obter_empresa_admin_ou_responder")
    @patch("handlers.settings.atualizar_empresa", new_callable=AsyncMock)
    async def test_horario_valido(self, mock_att, mock_admin):
        from handlers.settings import receber_horario

        mock_admin.return_value = make_empresa()
        update = make_update("Seg a Sex 9h-18h")
        ctx = make_context()
        result = await receber_horario(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        mock_att.assert_called_once()

    @patch("handlers.settings._obter_empresa_admin_ou_responder", return_value=None)
    async def test_sem_empresa(self, mock_admin):
        from handlers.settings import receber_horario

        update = make_update("Seg a Sex")
        ctx = make_context()
        result = await receber_horario(update, ctx)
        self.assertEqual(result, ConversationHandler.END)


class CmdFallbackTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.settings._obter_empresa_admin_ou_responder")
    @patch("handlers.settings.atualizar_empresa", new_callable=AsyncMock)
    async def test_com_args_limpar(self, mock_att, mock_admin):
        from handlers.settings import cmd_fallback

        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context(args=["limpar"])
        ctx.args = ["limpar"]
        result = await cmd_fallback(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        mock_att.assert_called_once()

    @patch("handlers.settings._obter_empresa_admin_ou_responder")
    async def test_sem_args_pergunta_fallback(self, mock_admin):
        from handlers.settings import cmd_fallback
        from handlers.common import AGUARDANDO_FALLBACK

        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context(args=None)
        ctx.args = None
        result = await cmd_fallback(update, ctx)
        self.assertEqual(result, AGUARDANDO_FALLBACK)


class ReceberFallbackTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.settings._obter_empresa_admin_ou_responder")
    @patch("handlers.settings.atualizar_empresa", new_callable=AsyncMock)
    async def test_fallback_valido(self, mock_att, mock_admin):
        from handlers.settings import receber_fallback

        mock_admin.return_value = make_empresa()
        update = make_update("WhatsApp (11) 99999-9999")
        ctx = make_context()
        result = await receber_fallback(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        mock_att.assert_called_once()


class CmdEditarTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.settings._obter_empresa_admin_ou_responder")
    async def test_mostra_opcoes(self, mock_admin):
        from handlers.settings import cmd_editar
        from handlers.common import EDITANDO_CAMPO

        mock_admin.return_value = make_empresa()
        update = make_update()
        ctx = make_context()
        result = await cmd_editar(update, ctx)
        self.assertEqual(result, EDITANDO_CAMPO)
        self.assertEqual(ctx.user_data["empresa_editar_id"], 1)


class EditarCampoCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelar(self):
        from handlers.settings import editar_campo_callback

        update = make_update(callback_data="editar_cancelar")
        ctx = make_context()
        result = await editar_campo_callback(update, ctx)
        self.assertEqual(result, ConversationHandler.END)

    async def test_campo_invalido(self):
        from handlers.settings import editar_campo_callback

        update = make_update(callback_data="editar_inexistente")
        ctx = make_context()
        result = await editar_campo_callback(update, ctx)
        self.assertEqual(result, ConversationHandler.END)

    async def test_campo_valido(self):
        from handlers.settings import editar_campo_callback
        from handlers.common import EDITANDO_CAMPO

        update = make_update(callback_data="editar_nome")
        ctx = make_context()
        result = await editar_campo_callback(update, ctx)
        self.assertEqual(result, EDITANDO_CAMPO)
        self.assertEqual(ctx.user_data["campo_editando"], "nome")


class ReceberValorEditadoTests(unittest.IsolatedAsyncioTestCase):
    @patch("handlers.settings.atualizar_empresa", new_callable=AsyncMock)
    async def test_atualiza_campo(self, mock_att):
        from handlers.settings import receber_valor_editado

        update = make_update("Novo Nome Corp")
        ctx = make_context(user_data={
            "empresa_editar_id": 1,
            "campo_editando": "nome",
            "campo_editando_nome": "nome da empresa",
        })
        result = await receber_valor_editado(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        mock_att.assert_called_once_with(1, nome="Novo Nome Corp")

    async def test_sem_estado_retorna_erro(self):
        from handlers.settings import receber_valor_editado

        update = make_update("valor")
        ctx = make_context(user_data={})
        result = await receber_valor_editado(update, ctx)
        self.assertEqual(result, ConversationHandler.END)
        self.assertIn("Erro", update.message.reply_text.call_args[0][0])
