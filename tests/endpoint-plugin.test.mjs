import assert from "node:assert/strict";
import test from "node:test";
import plugin from "../examples/rtl-debugger/endpoint-plugin.mjs";

test("base URL preserves streamed request, tool body and cancellation", async () => {
  const original = { ...process.env };
  const originalFetch = globalThis.fetch;
  try {
    delete process.env.AGENT_OPT_MODEL_ENDPOINT;
    process.env.AGENT_OPT_MODEL_BASE_URL = "https://example.invalid/v1";
    process.env.AGENT_OPT_MODEL_ID = "dynamic-model";
    let observed;
    globalThis.fetch = async (...args) => { observed = args; return new Response("data: [DONE]\n\n"); };
    const config = { provider: { compatible: { options: {} } } };
    await (await plugin()).config(config);
    assert.equal(config.model, "compatible/dynamic-model");
    assert.ok(config.provider.compatible.models["dynamic-model"]);
    const options = config.provider.compatible.options;
    const init = { body: '{"stream":true,"tools":[]}', signal: new AbortController().signal };
    const reply = await options.fetch(options.baseURL + "/chat/completions", init);
    assert.equal(observed[0], "https://example.invalid/v1/chat/completions");
    assert.equal(observed[1].body, init.body);
    assert.equal(observed[1].signal, init.signal);
    assert.equal(observed[1].redirect, "error");
    assert.equal(await reply.text(), "data: [DONE]\n\n");
    assert.throws(() => options.fetch("https://another.invalid", init));
    process.env.AGENT_OPT_MODEL_BASE_URL = "https://example.invalid/v1///";
    await (await plugin()).config(config);
    await config.provider.compatible.options.fetch("https://example.invalid/v1/chat/completions", init);
    assert.equal(observed[0], "https://example.invalid/v1/chat/completions");
    process.env.AGENT_OPT_MODEL_ENDPOINT = "https://ambiguous.invalid/v1/chat/completions";
    await assert.rejects((await plugin()).config(config), /AGENT_OPT_MODEL_BASE_URL/);
    delete process.env.AGENT_OPT_MODEL_BASE_URL;
    await assert.rejects((await plugin()).config(config), /AGENT_OPT_MODEL_ENDPOINT 대신 AGENT_OPT_MODEL_BASE_URL/);
  } finally {
    process.env = original;
    globalThis.fetch = originalFetch;
  }
});

test("OpenAI GPT-5 uses max_completion_tokens without changing other provider requests", async () => {
  const original = { ...process.env };
  const originalFetch = globalThis.fetch;
  try {
    delete process.env.AGENT_OPT_MODEL_ENDPOINT;
    const requests = [];
    globalThis.fetch = async (...args) => {
      requests.push(args);
      return new Response("data: [DONE]\n\n");
    };
    const config = { provider: { compatible: { options: {} } } };
    const signal = new AbortController().signal;
    const headers = { Authorization: "Bearer fixture-token" };
    const body = JSON.stringify({ model: "gpt-5-mini", max_tokens: 200,
      reasoning_effort: "none", stream: true,
      tools: [{ type: "function", function: { name: "ping" } }] });

    process.env.AGENT_OPT_MODEL_BASE_URL = "https://api.openai.com/v1";
    process.env.AGENT_OPT_MODEL_ID = "gpt-5-mini";
    await (await plugin()).config(config);
    await config.provider.compatible.options.fetch("https://api.openai.com/v1/chat/completions",
      { body, headers, signal });
    const forwarded = JSON.parse(requests[0][1].body);
    assert.equal(forwarded.max_completion_tokens, 200);
    assert.equal(Object.hasOwn(forwarded, "max_tokens"), false);
    assert.equal(forwarded.reasoning_effort, "none");
    assert.deepEqual(forwarded.tools, JSON.parse(body).tools);
    assert.equal(forwarded.stream, true);
    assert.equal(requests[0][1].headers, headers);
    assert.equal(requests[0][1].signal, signal);
    assert.equal(requests[0][1].redirect, "error");

    process.env.AGENT_OPT_MODEL_BASE_URL = "https://example.invalid/v1";
    await (await plugin()).config(config);
    await config.provider.compatible.options.fetch("https://example.invalid/v1/chat/completions",
      { body });
    assert.equal(requests[1][1].body, body);

    process.env.AGENT_OPT_MODEL_BASE_URL = "https://api.openai.com/v1";
    process.env.AGENT_OPT_MODEL_ID = "gpt-4.1-mini";
    await (await plugin()).config(config);
    await config.provider.compatible.options.fetch("https://api.openai.com/v1/chat/completions",
      { body });
    assert.equal(requests[2][1].body, body);

    process.env.AGENT_OPT_MODEL_ID = "gpt-5-mini";
    await (await plugin()).config(config);
    const lowEffort = JSON.stringify({ max_tokens: 200, reasoning_effort: "low" });
    await config.provider.compatible.options.fetch("https://api.openai.com/v1/chat/completions",
      { body: lowEffort });
    assert.equal(JSON.parse(requests[3][1].body).reasoning_effort, "low");

    const toolRequest = JSON.stringify({ max_tokens: 200, reasoning_effort: "medium",
      tools: [{ type: "function", function: { name: "ping" } }] });
    await config.provider.compatible.options.fetch("https://api.openai.com/v1/chat/completions",
      { body: toolRequest });
    assert.equal(JSON.parse(requests[4][1].body).reasoning_effort, "none");
  } finally {
    process.env = original;
    globalThis.fetch = originalFetch;
  }
});
