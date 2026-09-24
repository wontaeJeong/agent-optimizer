// Keep the bundled SDK's streaming/tool handling; customize only its destination.
export default async () => ({
  config: async (config) => {
    const endpoint = process.env.AGENT_OPT_MODEL_ENDPOINT;
    const base = process.env.AGENT_OPT_MODEL_BASE_URL;
    if (Boolean(endpoint) === Boolean(base)) throw new Error("Set exactly one of AGENT_OPT_MODEL_ENDPOINT or AGENT_OPT_MODEL_BASE_URL");
    const target = new URL(endpoint || base);
    if ((target.protocol !== "https:" && !(target.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(target.hostname))) ||
        target.username || target.password || target.search || target.hash) {
      throw new Error("Model URL must use HTTPS without credentials/query/fragment (HTTP only on loopback)");
    }
    const model = process.env.AGENT_OPT_MODEL_ID ?? "glm5.3-flash";
    if (!model || /\s/.test(model)) throw new Error("AGENT_OPT_MODEL_ID must be a nonempty model identifier");
    const provider = config.provider.compatible;
    config.model = config.small_model = `compatible/${model}`;
    provider.models = { [model]: { name: model, tool_call: true } };
    const options = provider.options;
    options.baseURL = (base || "https://configured-endpoint.invalid/v1").replace(/\/$/, "");
    const expected = options.baseURL + "/chat/completions";
    options.fetch = (url, init) => {
      if (String(url) !== expected) throw new Error("Unexpected model request path");
      return fetch(endpoint || expected, { ...init, redirect: "error" });
    };
  },
});
