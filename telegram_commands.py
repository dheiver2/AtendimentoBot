"""Comandos nativos do Telegram por perfil de usuário."""

from typing import Literal

from telegram import (
    Bot,
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    MenuButtonCommands,
)


PerfilComando = Literal["admin", "cliente", "padrao"]


def obter_comandos_padrao() -> list[BotCommand]:
    """Comandos exibidos para chats privados ainda sem papel definido."""
    return [
        BotCommand("start", "Iniciar atendimento ou configuração"),
        BotCommand("ajuda", "Ver ajuda rápida"),
    ]


def obter_comandos_cliente() -> list[BotCommand]:
    """Comandos exibidos para clientes vinculados por link."""
    return [
        BotCommand("start", "Abrir o atendimento"),
        BotCommand("sair", "Sair deste atendimento"),
        BotCommand("ajuda", "Ver ajuda rápida"),
    ]


def obter_comandos_admin() -> list[BotCommand]:
    """Comandos exibidos para o admin que gerencia o atendimento."""
    return [
        BotCommand("start", "Iniciar atendimento ou configuração"),
        BotCommand("painel", "Abrir o painel principal"),
        BotCommand("link", "Gerar o link dos clientes"),
        BotCommand("upload", "Enviar novos documentos"),
        BotCommand("imagem", "Atualizar a imagem do agente"),
        BotCommand("pausar", "Pausar o agente"),
        BotCommand("ativar", "Ativar o agente"),
        BotCommand("horario", "Definir horário de atendimento"),
        BotCommand("fallback", "Definir contato humano"),
        BotCommand("faq", "Gerenciar perguntas frequentes"),
        BotCommand("documentos", "Gerenciar a base de conhecimento"),
        BotCommand("editar", "Editar a configuração do agente"),
        BotCommand("status", "Ver o status atual"),
        BotCommand("reset", "Reconfigurar do zero"),
        BotCommand("ajuda", "Ver ajuda rápida"),
    ]


def obter_comandos_por_perfil(perfil: PerfilComando) -> list[BotCommand]:
    """Resolve a lista de comandos conforme o papel do usuário."""
    if perfil == "admin":
        return obter_comandos_admin()
    if perfil == "cliente":
        return obter_comandos_cliente()
    return obter_comandos_padrao()


async def configurar_menu_nativo_padrao(bot: Bot):
    """Configura o menu padrão do bot para chats privados."""
    await bot.set_my_commands(
        obter_comandos_padrao(),
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def sincronizar_comandos_chat(bot: Bot, chat_id: int, perfil: PerfilComando):
    """Sobrescreve o menu de comandos de um chat privado conforme o perfil."""
    await bot.set_my_commands(
        obter_comandos_por_perfil(perfil),
        scope=BotCommandScopeChat(chat_id),
    )


async def sincronizar_comandos_existentes(
    bot: Bot,
    admin_chat_ids: list[int],
    cliente_chat_ids: list[int],
):
    """Reaplica os menus corretos para chats já cadastrados no banco."""
    for chat_id in admin_chat_ids:
        await sincronizar_comandos_chat(bot, chat_id, "admin")

    for chat_id in cliente_chat_ids:
        await sincronizar_comandos_chat(bot, chat_id, "cliente")
