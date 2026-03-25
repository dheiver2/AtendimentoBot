"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const {
  clearLocalAuthSession,
  normalizeInboundMessageType,
  rememberSentMessage,
  shouldDownloadInboundMedia,
  shouldIgnoreMessage,
} = require("../scripts/whatsapp_bridge_helpers");

test("trata interactive com texto como chat", () => {
  assert.equal(normalizeInboundMessageType("interactive", "Ola"), "chat");
});

test("so tenta baixar midia para tipos suportados", () => {
  assert.equal(shouldDownloadInboundMedia("document"), true);
  assert.equal(shouldDownloadInboundMedia("image"), true);
  assert.equal(shouldDownloadInboundMedia("interactive"), false);
  assert.equal(shouldDownloadInboundMedia("audio"), false);
});

test("permite mensagem recebida normalmente", async () => {
  const shouldIgnore = await shouldIgnoreMessage(
    {
      fromMe: false,
      from: "5511999999999@c.us",
    },
    { _serialized: "5511888888888@c.us" },
    new Map(),
  );

  assert.equal(shouldIgnore, false);
});

test("ignora resposta enviada pelo proprio bot no autochat", async () => {
  const sentMessageIds = new Map();
  rememberSentMessage(sentMessageIds, { id: { _serialized: "ABC123" } }, 1_000);

  const shouldIgnore = await shouldIgnoreMessage(
    {
      fromMe: true,
      id: { _serialized: "ABC123" },
      from: "5511999999999@c.us",
      getChat: async () => ({ id: { _serialized: "5511999999999@c.us" } }),
    },
    { _serialized: "5511999999999@c.us" },
    sentMessageIds,
    1_500,
  );

  assert.equal(shouldIgnore, true);
});

test("permite mensagem manual no chat com o proprio numero", async () => {
  const shouldIgnore = await shouldIgnoreMessage(
    {
      fromMe: true,
      id: { _serialized: "SELF123" },
      from: "5511999999999@c.us",
      getChat: async () => ({ id: { _serialized: "5511999999999@c.us" } }),
    },
    { _serialized: "5511999999999@c.us" },
    new Map(),
  );

  assert.equal(shouldIgnore, false);
});

test("continua ignorando mensagem enviada para outro contato", async () => {
  const shouldIgnore = await shouldIgnoreMessage(
    {
      fromMe: true,
      id: { _serialized: "OUT123" },
      from: "5511777777777@c.us",
      to: "5511777777777@c.us",
      getChat: async () => ({ id: { _serialized: "5511777777777@c.us" } }),
    },
    { _serialized: "5511999999999@c.us" },
    new Map(),
  );

  assert.equal(shouldIgnore, true);
});

test("limpa apenas a sessao LocalAuth do clientId atual", () => {
  const calls = [];
  const fsMock = {
    rmSync(target, options) {
      calls.push({ target, options });
    },
  };

  const sessionPath = clearLocalAuthSession("/tmp/whatsapp", "atendimento-bot", fsMock);

  assert.equal(sessionPath, path.join("/tmp/whatsapp", "session-atendimento-bot"));
  assert.deepEqual(calls, [
    {
      target: path.join("/tmp/whatsapp", "session-atendimento-bot"),
      options: { recursive: true, force: true },
    },
  ]);
});

test("nao tenta limpar sessao quando o diretorio base nao foi definido", () => {
  const calls = [];
  const fsMock = {
    rmSync(target, options) {
      calls.push({ target, options });
    },
  };

  const sessionPath = clearLocalAuthSession("", "atendimento-bot", fsMock);

  assert.equal(sessionPath, "");
  assert.deepEqual(calls, []);
});
