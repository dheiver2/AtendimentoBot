"""Testes do fluxo conversacional do WhatsApp."""
import os
import unittest
from unittest.mock import AsyncMock, patch

from tests.helpers import make_empresa


class WhatsAppFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from whatsapp_flow import _sessions

        _sessions.clear()

    async def test_start_novo_usuario_inicia_onboarding(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                actions = await processar_mensagem_whatsapp(
                    sender="5511999999999@c.us",
                    text="/start",
                    message_type="chat",
                    is_owner_chat=True,
                    resolve_default_company=AsyncMock(return_value=None),
                )

        self.assertEqual(len(actions), 1)
        self.assertIn("nome da sua empresa", actions[0]["text"].lower())

    async def test_start_owner_chat_com_token_nao_vira_cliente(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                with patch("whatsapp_flow.obter_empresa_por_link_token", new_callable=AsyncMock) as mock_link:
                    with patch("whatsapp_flow.vincular_cliente_empresa", new_callable=AsyncMock) as mock_bind:
                        actions = await processar_mensagem_whatsapp(
                            sender="5511999999999@c.us",
                            text="/start abc123",
                            message_type="chat",
                            is_owner_chat=True,
                            resolve_default_company=AsyncMock(return_value=None),
                        )

        mock_link.assert_not_awaited()
        mock_bind.assert_not_awaited()
        self.assertIn("nao entra pelo link do cliente", actions[0]["text"].lower())
        self.assertIn("nome da sua empresa", actions[0]["text"].lower())

    async def test_start_numero_autorizado_por_lista_inicia_onboarding_sem_owner_chat(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        with patch.dict(os.environ, {"WHATSAPP_ADMIN_NUMBERS": "5511888888888"}, clear=False):
            with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
                with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                    actions = await processar_mensagem_whatsapp(
                        sender="5511888888888@c.us",
                        text="/start",
                        message_type="chat",
                        resolve_default_company=AsyncMock(return_value=None),
                    )

        self.assertEqual(len(actions), 1)
        self.assertIn("nome da sua empresa", actions[0]["text"].lower())

    async def test_start_cliente_existente_numero_autorizado_reabre_atendimento(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        empresa = make_empresa(nome="Acme")
        with patch.dict(os.environ, {"WHATSAPP_ADMIN_NUMBERS": "5511888888888"}, clear=False):
            with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
                with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=empresa):
                    with patch(
                        "whatsapp_flow._make_welcome_actions",
                        return_value=[{"type": "text", "text": "bem-vindo Acme"}],
                    ) as mock_welcome:
                        actions = await processar_mensagem_whatsapp(
                            sender="5511888888888@c.us",
                            text="/start",
                            message_type="chat",
                            resolve_default_company=AsyncMock(return_value=None),
                        )

        mock_welcome.assert_called_once_with(empresa, unittest.mock.ANY)
        self.assertEqual(actions, [{"type": "text", "text": "bem-vindo Acme"}])

    async def test_start_cliente_existente_owner_chat_reabre_atendimento(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        empresa = make_empresa(nome="Acme")
        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=empresa):
                with patch(
                    "whatsapp_flow._make_welcome_actions",
                    return_value=[{"type": "text", "text": "bem-vindo owner"}],
                ) as mock_welcome:
                    actions = await processar_mensagem_whatsapp(
                        sender="5511999999999@c.us",
                        text="/start",
                        message_type="chat",
                        is_owner_chat=True,
                        resolve_default_company=AsyncMock(return_value=None),
                    )

        mock_welcome.assert_called_once_with(empresa, unittest.mock.ANY)
        self.assertEqual(actions, [{"type": "text", "text": "bem-vindo owner"}])

    async def test_start_owner_chat_com_lista_configurada_pode_usar_token_cliente(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        with patch.dict(os.environ, {"WHATSAPP_ADMIN_NUMBERS": "5511888888888"}, clear=False):
            with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
                with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                    with patch(
                        "whatsapp_flow.obter_empresa_por_link_token",
                        new_callable=AsyncMock,
                        return_value=make_empresa(link_token="abc123"),
                    ):
                        with patch(
                            "whatsapp_flow.vincular_cliente_empresa",
                            new_callable=AsyncMock,
                        ) as mock_bind:
                            with patch(
                                "whatsapp_flow._make_welcome_actions",
                                return_value=[{"type": "text", "text": "bem-vindo"}],
                            ):
                                actions = await processar_mensagem_whatsapp(
                                    sender="5511999999999@c.us",
                                    text="/start abc123",
                                    message_type="chat",
                                    is_owner_chat=True,
                                    resolve_default_company=AsyncMock(return_value=None),
                                )

        mock_bind.assert_awaited_once_with(1, -5511999999999)
        self.assertEqual(actions, [{"type": "text", "text": "bem-vindo"}])

    async def test_onboarding_completo_cria_empresa(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                with patch("whatsapp_flow.criar_empresa", new_callable=AsyncMock, return_value=7) as mock_create:
                    with patch("whatsapp_flow.atualizar_empresa", new_callable=AsyncMock) as mock_update:
                        await processar_mensagem_whatsapp(
                            sender="5511999999999@c.us",
                            text="/start",
                            message_type="chat",
                            is_owner_chat=True,
                            resolve_default_company=AsyncMock(return_value=None),
                        )
                        await processar_mensagem_whatsapp(
                            sender="5511999999999@c.us",
                            text="Acme",
                            message_type="chat",
                            is_owner_chat=True,
                            resolve_default_company=AsyncMock(return_value=None),
                        )
                        await processar_mensagem_whatsapp(
                            sender="5511999999999@c.us",
                            text="Ana",
                            message_type="chat",
                            is_owner_chat=True,
                            resolve_default_company=AsyncMock(return_value=None),
                        )
                        await processar_mensagem_whatsapp(
                            sender="5511999999999@c.us",
                            text="Ola! Como posso ajudar?",
                            message_type="chat",
                            is_owner_chat=True,
                            resolve_default_company=AsyncMock(return_value=None),
                        )
                        await processar_mensagem_whatsapp(
                            sender="5511999999999@c.us",
                            text="/pular",
                            message_type="chat",
                            is_owner_chat=True,
                            resolve_default_company=AsyncMock(return_value=None),
                        )
                        actions = await processar_mensagem_whatsapp(
                            sender="5511999999999@c.us",
                            text="/confirmar",
                            message_type="chat",
                            is_owner_chat=True,
                            resolve_default_company=AsyncMock(return_value=None),
                        )

        mock_create.assert_awaited_once_with("Acme", -5511999999999)
        mock_update.assert_awaited_once_with(
            7,
            nome_bot="Ana",
            saudacao="Ola! Como posso ajudar?",
            instrucoes=(
                "Você é um assistente de atendimento ao cliente. "
                "Responda de forma educada e profissional."
            ),
        )
        self.assertIn("empresa cadastrada com sucesso", actions[0]["text"].lower())

    async def test_start_com_token_vincula_cliente(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                with patch(
                    "whatsapp_flow.obter_empresa_por_link_token",
                    new_callable=AsyncMock,
                    return_value=make_empresa(link_token="abc123"),
                ):
                    with patch("whatsapp_flow.vincular_cliente_empresa", new_callable=AsyncMock) as mock_bind:
                        with patch(
                            "whatsapp_flow._make_welcome_actions",
                            return_value=[{"type": "text", "text": "bem-vindo"}],
                        ) as mock_welcome:
                            actions = await processar_mensagem_whatsapp(
                                sender="5511999999999@c.us",
                                text="/start abc123",
                                message_type="chat",
                                resolve_default_company=AsyncMock(return_value=None),
                            )

        mock_bind.assert_awaited_once_with(1, -5511999999999)
        mock_welcome.assert_called_once()
        self.assertEqual(actions, [{"type": "text", "text": "bem-vindo"}])

    async def test_start_com_link_admin_vincula_admin(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        empresa = make_empresa(nome="AdminCorp", admin_link_token="adm123")
        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                with patch(
                    "whatsapp_flow.obter_empresa_por_admin_link_token",
                    new_callable=AsyncMock,
                    return_value=empresa,
                ):
                    with patch("whatsapp_flow.adicionar_admin_empresa", new_callable=AsyncMock) as mock_add_admin:
                        actions = await processar_mensagem_whatsapp(
                            sender="5511888888888@c.us",
                            text="/start admin_adm123",
                            message_type="chat",
                            resolve_default_company=AsyncMock(return_value=None),
                        )

        mock_add_admin.assert_awaited_once_with(1, -5511888888888)
        self.assertIn("acesso de admin", actions[0]["text"].lower())
        self.assertIn("admincorp", actions[0]["text"].lower())

    async def test_registrar_externo_nao_inicia_onboarding_admin(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                actions = await processar_mensagem_whatsapp(
                    sender="5511888888888@c.us",
                    text="/registrar",
                    message_type="chat",
                    resolve_default_company=AsyncMock(return_value=None),
                )

        self.assertIn("so podem ser feitos por um numero autorizado como admin", actions[0]["text"].lower())
        self.assertNotIn("qual e o nome da sua empresa", actions[0]["text"].lower())

    async def test_cliente_vinculado_nao_pode_usar_link(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch(
                "whatsapp_flow.obter_empresa_do_cliente",
                new_callable=AsyncMock,
                return_value=make_empresa(nome="Acme"),
            ):
                actions = await processar_mensagem_whatsapp(
                    sender="5511888888888@c.us",
                    text="/link",
                    message_type="chat",
                    resolve_default_company=AsyncMock(return_value=None),
                )

        self.assertIn("exclusivo do admin", actions[0]["text"].lower())
        self.assertIn("apenas para conversar", actions[0]["text"].lower())

    async def test_cliente_vinculado_nao_acessa_comandos_de_gestao(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        comandos = [
            "/registrar",
            "/link",
            "/painel",
            "/status",
            "/pausar",
            "/ativar",
            "/horario",
            "/fallback",
            "/faq",
            "/documentos",
            "/upload",
            "/imagem",
            "/editar",
            "/reset",
        ]

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch(
                "whatsapp_flow.obter_empresa_do_cliente",
                new_callable=AsyncMock,
                return_value=make_empresa(nome="Acme"),
            ):
                for comando in comandos:
                    with self.subTest(comando=comando):
                        actions = await processar_mensagem_whatsapp(
                            sender="5511888888888@c.us",
                            text=comando,
                            message_type="chat",
                            resolve_default_company=AsyncMock(return_value=None),
                        )

                        self.assertEqual(len(actions), 1)
                        self.assertIn("admin", actions[0]["text"].lower())
                        self.assertIn("apenas para conversar", actions[0]["text"].lower())

    async def test_documento_direto_admin_processa_upload(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        empresa = make_empresa()
        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=empresa):
            with patch("whatsapp_flow.listar_documentos", new_callable=AsyncMock, return_value=[]):
                with patch("whatsapp_flow.processar_documento", return_value=["c1", "c2"]) as mock_process:
                    with patch("whatsapp_flow.registrar_documento", new_callable=AsyncMock) as mock_register:
                        with patch("whatsapp_flow.adicionar_documentos") as mock_add:
                            actions = await processar_mensagem_whatsapp(
                                sender="5511999999999@c.us",
                                text="",
                                message_type="document",
                                file_name="manual.pdf",
                                mime_type="application/pdf",
                                media_bytes=b"pdf-data",
                                resolve_default_company=AsyncMock(return_value=None),
                            )

        mock_process.assert_called_once_with(1, "manual.pdf", b"pdf-data")
        mock_register.assert_awaited_once_with(1, "manual.pdf")
        mock_add.assert_called_once_with(1, ["c1", "c2"], {"arquivo": "manual.pdf"})
        self.assertIn("processado com sucesso", actions[0]["text"].lower())

    async def test_texto_do_numero_conectado_sem_empresa_inicia_onboarding_automaticamente(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                actions = await processar_mensagem_whatsapp(
                    sender="5511999999999@c.us",
                    text="Oi",
                    message_type="chat",
                    is_owner_chat=True,
                    resolve_default_company=AsyncMock(return_value=None),
                )

        self.assertEqual(len(actions), 1)
        self.assertIn("nome da sua empresa", actions[0]["text"].lower())

    async def test_texto_owner_chat_com_lista_configurada_sem_autorizacao_nao_inicia_onboarding(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        empresas = [
            make_empresa(empresa_id=1, nome="Acme"),
            make_empresa(empresa_id=2, nome="Beta"),
        ]
        with patch.dict(os.environ, {"WHATSAPP_ADMIN_NUMBERS": "5511888888888"}, clear=False):
            with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
                with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                    with patch("whatsapp_flow.obter_empresa_do_usuario", new_callable=AsyncMock, return_value=None):
                        with patch("whatsapp_flow.listar_empresas", new_callable=AsyncMock, return_value=empresas):
                            actions = await processar_mensagem_whatsapp(
                                sender="5511999999999@c.us",
                                text="Oi",
                                message_type="chat",
                                is_owner_chat=True,
                                resolve_default_company=AsyncMock(return_value=None),
                            )

        self.assertEqual(len(actions), 1)
        self.assertIn("qual empresa deseja atendimento", actions[0]["text"].lower())

    async def test_cliente_externo_texto_auto_vincula_empresa_padrao(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        empresa = make_empresa()
        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                with patch("whatsapp_flow.obter_empresa_do_usuario", new_callable=AsyncMock, return_value=None):
                    with patch("whatsapp_flow.vincular_cliente_empresa", new_callable=AsyncMock) as mock_bind:
                        with patch(
                            "whatsapp_flow.processar_pergunta",
                            new_callable=AsyncMock,
                            return_value="Resposta automatica",
                        ) as mock_process:
                            actions = await processar_mensagem_whatsapp(
                                sender="5511888888888@c.us",
                                text="Quero atendimento",
                                message_type="chat",
                                resolve_default_company=AsyncMock(return_value=empresa),
                            )

        mock_bind.assert_awaited_once_with(1, -5511888888888)
        mock_process.assert_awaited_once()
        self.assertEqual(actions, [{"type": "text", "text": "Resposta automatica"}])

    async def test_cliente_externo_com_varias_empresas_recebe_seletor(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        empresas = [
            make_empresa(empresa_id=1, nome="Acme"),
            make_empresa(empresa_id=2, nome="Beta"),
        ]
        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                with patch("whatsapp_flow.obter_empresa_do_usuario", new_callable=AsyncMock, return_value=None):
                    with patch("whatsapp_flow.listar_empresas", new_callable=AsyncMock, return_value=empresas):
                        actions = await processar_mensagem_whatsapp(
                            sender="5511888888888@c.us",
                            text="Quero atendimento",
                            message_type="chat",
                            resolve_default_company=AsyncMock(return_value=None),
                        )

        self.assertEqual(len(actions), 1)
        self.assertIn("qual empresa deseja atendimento", actions[0]["text"].lower())
        self.assertIn("1. Acme", actions[0]["text"])
        self.assertIn("2. Beta", actions[0]["text"])
        self.assertIn("parte do nome", actions[0]["text"].lower())

    async def test_selecao_empresa_vincula_cliente_e_continua_mensagem_pendente(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        empresas = [
            make_empresa(empresa_id=1, nome="Acme"),
            make_empresa(empresa_id=2, nome="Beta"),
        ]
        resolve_default_company = AsyncMock(return_value=None)

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                with patch(
                    "whatsapp_flow.obter_empresa_do_usuario",
                    new_callable=AsyncMock,
                    side_effect=[None, make_empresa(empresa_id=2, nome="Beta")],
                ):
                    with patch("whatsapp_flow.listar_empresas", new_callable=AsyncMock, return_value=empresas):
                        await processar_mensagem_whatsapp(
                            sender="5511888888888@c.us",
                            text="Quero atendimento",
                            message_type="chat",
                            resolve_default_company=resolve_default_company,
                        )

                    with patch("whatsapp_flow.obter_empresa_por_id", new_callable=AsyncMock, return_value=empresas[1]):
                        with patch("whatsapp_flow.vincular_cliente_empresa", new_callable=AsyncMock) as mock_bind:
                            with patch(
                                "whatsapp_flow._make_welcome_actions",
                                return_value=[{"type": "text", "text": "bem-vindo"}],
                            ):
                                with patch(
                                    "whatsapp_flow.processar_pergunta",
                                    new_callable=AsyncMock,
                                    return_value="Resposta Beta",
                                ):
                                    actions = await processar_mensagem_whatsapp(
                                        sender="5511888888888@c.us",
                                        text="2",
                                        message_type="chat",
                                        resolve_default_company=resolve_default_company,
                                    )

        mock_bind.assert_awaited_once_with(2, -5511888888888)
        self.assertEqual(
            actions,
            [
                {"type": "text", "text": "bem-vindo"},
                {"type": "text", "text": "Resposta Beta"},
            ],
        )

    async def test_selecao_empresa_aceita_nome_parcial_em_frase(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        empresas = [
            make_empresa(empresa_id=1, nome="Acme"),
            make_empresa(empresa_id=2, nome="Clinica Saude e Vida"),
        ]
        resolve_default_company = AsyncMock(return_value=None)

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                with patch(
                    "whatsapp_flow.obter_empresa_do_usuario",
                    new_callable=AsyncMock,
                    side_effect=[None, make_empresa(empresa_id=2, nome="Clinica Saude e Vida")],
                ):
                    with patch("whatsapp_flow.listar_empresas", new_callable=AsyncMock, return_value=empresas):
                        await processar_mensagem_whatsapp(
                            sender="5511888888888@c.us",
                            text="Quero atendimento",
                            message_type="chat",
                            resolve_default_company=resolve_default_company,
                        )

                    with patch("whatsapp_flow.obter_empresa_por_id", new_callable=AsyncMock, return_value=empresas[1]):
                        with patch("whatsapp_flow.vincular_cliente_empresa", new_callable=AsyncMock) as mock_bind:
                            with patch(
                                "whatsapp_flow._make_welcome_actions",
                                return_value=[{"type": "text", "text": "bem-vindo clinica"}],
                            ):
                                with patch(
                                    "whatsapp_flow.processar_pergunta",
                                    new_callable=AsyncMock,
                                    return_value="Resposta Clinica",
                                ):
                                    actions = await processar_mensagem_whatsapp(
                                        sender="5511888888888@c.us",
                                        text="quero falar com a clinica saude",
                                        message_type="chat",
                                        resolve_default_company=resolve_default_company,
                                    )

        mock_bind.assert_awaited_once_with(2, -5511888888888)
        self.assertEqual(
            actions,
            [
                {"type": "text", "text": "bem-vindo clinica"},
                {"type": "text", "text": "Resposta Clinica"},
            ],
        )

    async def test_selecao_empresa_usa_template_como_pista_semantica(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        empresas = [
            make_empresa(empresa_id=1, nome="Vida Plena", instruction_template_key="clinica"),
            make_empresa(empresa_id=2, nome="Casa Aurora", instruction_template_key="restaurante"),
        ]
        resolve_default_company = AsyncMock(return_value=None)

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                with patch(
                    "whatsapp_flow.obter_empresa_do_usuario",
                    new_callable=AsyncMock,
                    side_effect=[None, make_empresa(empresa_id=1, nome="Vida Plena", instruction_template_key="clinica")],
                ):
                    with patch("whatsapp_flow.listar_empresas", new_callable=AsyncMock, return_value=empresas):
                        await processar_mensagem_whatsapp(
                            sender="5511888888888@c.us",
                            text="Preciso de atendimento",
                            message_type="chat",
                            resolve_default_company=resolve_default_company,
                        )

                    with patch("whatsapp_flow.obter_empresa_por_id", new_callable=AsyncMock, return_value=empresas[0]):
                        with patch("whatsapp_flow.vincular_cliente_empresa", new_callable=AsyncMock) as mock_bind:
                            with patch(
                                "whatsapp_flow._make_welcome_actions",
                                return_value=[{"type": "text", "text": "bem-vindo vida plena"}],
                            ):
                                with patch(
                                    "whatsapp_flow.processar_pergunta",
                                    new_callable=AsyncMock,
                                    return_value="Resposta Vida Plena",
                                ):
                                    actions = await processar_mensagem_whatsapp(
                                        sender="5511888888888@c.us",
                                        text="clinica",
                                        message_type="chat",
                                        resolve_default_company=resolve_default_company,
                                    )

        mock_bind.assert_awaited_once_with(1, -5511888888888)
        self.assertEqual(
            actions,
            [
                {"type": "text", "text": "bem-vindo vida plena"},
                {"type": "text", "text": "Resposta Vida Plena"},
            ],
        )

    async def test_cmd_empresas_cliente_vinculado_reabre_seletor(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        empresas = [
            make_empresa(empresa_id=1, nome="Acme"),
            make_empresa(empresa_id=2, nome="Beta"),
        ]
        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.listar_empresas", new_callable=AsyncMock, return_value=empresas):
                actions = await processar_mensagem_whatsapp(
                    sender="5511888888888@c.us",
                    text="/empresas",
                    message_type="chat",
                    resolve_default_company=AsyncMock(return_value=None),
                )

        self.assertEqual(len(actions), 1)
        self.assertIn("qual empresa deseja atendimento", actions[0]["text"].lower())

    async def test_start_externo_sem_token_nao_inicia_onboarding(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=None):
            with patch("whatsapp_flow.obter_empresa_do_cliente", new_callable=AsyncMock, return_value=None):
                with patch("whatsapp_flow.listar_empresas", new_callable=AsyncMock, return_value=[]):
                    actions = await processar_mensagem_whatsapp(
                        sender="5511888888888@c.us",
                        text="/start",
                        message_type="chat",
                        resolve_default_company=AsyncMock(return_value=None),
                    )

        self.assertIn("nao foi vinculado", actions[0]["text"].lower())
        self.assertNotIn("nome da sua empresa", actions[0]["text"].lower())

    async def test_link_admin_retorna_instrucao_com_share_link(self):
        from whatsapp_flow import processar_mensagem_whatsapp

        empresa = make_empresa(link_token="abc123", admin_link_token="adm123")
        with patch("whatsapp_flow.obter_empresa_por_admin", new_callable=AsyncMock, return_value=empresa):
            actions = await processar_mensagem_whatsapp(
                sender="5511999999999@c.us",
                text="/link",
                message_type="chat",
                resolve_default_company=AsyncMock(return_value=None),
                share_link_builder=lambda command: f"https://wa.me/5511999999999?text={command}",
        )

        self.assertIn("/start abc123", actions[0]["text"])
        self.assertIn("/start admin_adm123", actions[0]["text"])
        self.assertIn("Link do cliente", actions[0]["text"])
        self.assertIn("Link do admin", actions[0]["text"])
        self.assertIn("Mensagem pronta para encaminhar ao cliente", actions[0]["text"])
        self.assertIn("Mensagem pronta para encaminhar ao admin", actions[0]["text"])
        self.assertIn("Para falar com o atendimento de Acme Corp", actions[0]["text"])
        self.assertIn("Para administrar o atendimento de Acme Corp", actions[0]["text"])
