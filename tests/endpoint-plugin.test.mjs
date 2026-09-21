import assert from "node:assert/strict";
import test from "node:test";
import plugin from "../examples/rtl-debugger/endpoint-plugin.mjs";

test("exact endpoint preserves streamed request, tool body and cancellation", async () => {
  const original = { ...process.env };
  const originalFetch = globalThis.fetch;
  try {
    delete process.env.MODEL_BASE_URL;
    process.env.MODEL_ENDPOINT = "https://example.invalid/v1/chat/completion";
    process.env.MODEL_ID = "dynamic-model";
    let observed;
    globalThis.fetch = async (...args) => { observed = args; return new Response("data: [DONE]\n\n"); };
    const config = { provider: { compatible: { options: {} } } };
    await (await plugin()).config(config);
    assert.equal(config.model, "compatible/dynamic-model");
    assert.ok(config.provider.compatible.models["dynamic-model"]);
    const options = config.provider.compatible.options;
    const init = { body: '{"stream":true,"tools":[]}', signal: new AbortController().signal };
    const reply = await options.fetch(options.baseURL + "/chat/completions", init);
    assert.equal(observed[0], "https://example.invalid/v1/chat/completion");
    assert.equal(observed[1].body, init.body);
    assert.equal(observed[1].signal, init.signal);
    assert.equal(observed[1].redirect, "error");
    assert.equal(await reply.text(), "data: [DONE]\n\n");
    assert.throws(() => options.fetch("https://another.invalid", init));
    process.env.MODEL_BASE_URL = "https://ambiguous.invalid/v1";
    await assert.rejects((await plugin()).config(config));
  } finally {
    process.env = original;
    globalThis.fetch = originalFetch;
  }
});
