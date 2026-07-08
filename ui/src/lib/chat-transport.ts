import { DefaultChatTransport, isTextUIPart, type UIMessage } from "ai";
import { debugLog } from "./debug-log";
import type { RuntimeSettings } from "../types/chat";

type BackendTransportOptions = {
  getSessionId: () => string | undefined;
  getSettings: () => RuntimeSettings;
};

export function createBackendTransport({ getSessionId, getSettings }: BackendTransportOptions) {
  return new DefaultChatTransport<UIMessage>({
    api: "/completions",
    headers: {},
    fetch: async (_url, init) => {
      const sessionId = getSessionId();
      const settings = getSettings();

      debugLog.log("chat request started", {
        baseUrl: settings.baseUrl,
        hasBody: Boolean(init?.body),
        sessionId,
        model: settings.modelId,
        providerId: settings.providerId,
      });

      if (!sessionId) {
        debugLog.error("session not initialized", { sessionId });
        throw new Error("Session not initialized");
      }

      let messages: UIMessage[] = [];

      if (typeof init?.body === "string") {
        try {
          const originalBody = JSON.parse(init.body) as { messages?: UIMessage[] };
          messages = originalBody.messages ?? [];

          debugLog.log("chat request body parsed", {
            messageCount: messages.length,
          });
        } catch (error) {
          debugLog.error("failed to parse chat request body", { error });
        }
      }

      let latestUserMessage: UIMessage | undefined;

      for (let index = messages.length - 1; index >= 0; index -= 1) {
        if (messages[index]?.role === "user") {
          latestUserMessage = messages[index];
          break;
        }
      }

      const latestText = latestUserMessage?.parts?.find(isTextUIPart);

      const customBody = {
        session_id: sessionId,
        query: latestText?.text ?? "",

        // 后端 ChatRequest 字段名就是 model，不是 model_id
        model: settings.modelId || null,
        provider_id: settings.providerId || null,

        runtime_options: {},
      };

      console.log("[chat payload]", customBody);

      debugLog.log("chat request payload prepared", {
        model: customBody.model,
        providerId: customBody.provider_id,
        queryLength: customBody.query.length,
      });

      const response = await fetch(`${settings.baseUrl}/completions`, {
        ...init,
        headers: {
          ...(init?.headers ?? {}),
          "Content-Type": "application/json",
          "X-From-Source": settings.fromSource,
          "X-User-Id": settings.userId,
          "X-Identity-Type": settings.identityType,
        },
        body: JSON.stringify(customBody),
      });

      debugLog.log("chat response received", {
        status: response.status,
        statusText: response.statusText,
      });

      return response;
    },
  });
}