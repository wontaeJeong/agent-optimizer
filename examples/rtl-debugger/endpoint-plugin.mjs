// Keep the bundled SDK's streaming/tool handling; customize only its destination.
export default async () => ({
  config: async (config) => {
    const base = process.env.AGENT_OPT_MODEL_BASE_URL;
    if (process.env.AGENT_OPT_MODEL_ENDPOINT) throw new Error("AGENT_OPT_MODEL_ENDPOINT 대신 AGENT_OPT_MODEL_BASE_URL을 사용하세요");
    if (!base) throw new Error("AGENT_OPT_MODEL_BASE_URL을 설정하세요");
    const target = new URL(base);
    if ((target.protocol !== "https:" && !(target.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(target.hostname))) ||
        target.username || target.password || target.search || target.hash ||
        target.pathname.replace(/\/+$/, "").endsWith("/chat/completions")) {
      throw new Error("Model URL must use HTTPS without credentials/query/fragment (HTTP only on loopback)");
    }
    const model = process.env.AGENT_OPT_MODEL_ID ?? "glm5.3-flash";
    if (!model || /\s/.test(model)) throw new Error("AGENT_OPT_MODEL_ID must be a nonempty model identifier");
    const provider = config.provider.compatible;
    config.model = config.small_model = `compatible/${model}`;
    provider.models = { [model]: { name: model, tool_call: true } };
    const options = provider.options;
    options.baseURL = base.replace(/\/+$/, "");
    const expected = options.baseURL + "/chat/completions";
    options.fetch = (url, init) => {
      if (String(url) !== expected) throw new Error("Unexpected model request path");
      return fetch(expected, { ...init, redirect: "error" });
    };
  },
});
