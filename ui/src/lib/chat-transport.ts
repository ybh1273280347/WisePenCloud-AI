import { DefaultChatTransport, isTextUIPart, type UIMessage } from "ai";
import { debugLog } from "./debug-log";
import type { RuntimeSettings } from "../types/chat";

type BackendTransportOptions = {
  getSessionId: () => string | undefined;
  settings: RuntimeSettings;
};

export function createBackendTransport({ getSessionId, settings }: BackendTransportOptions) {
  debugLog.log("create backend transport", {
    baseUrl: settings.baseUrl,
    modelId: settings.modelId,
    providerId: settings.providerId,
  });

  return new DefaultChatTransport<UIMessage>({
    api: `${settings.baseUrl}/completions`,
    headers: {
      "X-From-Source": settings.fromSource,
      "X-User-Id": settings.userId,
      "X-Identity-Type": settings.identityType,
    },
    fetch: async (url, init) => {
      const sessionId = getSessionId();
      debugLog.log("chat request started", {
        url: url.toString(),
        hasBody: Boolean(init?.body),
        sessionId,
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
          debugLog.log("chat request body parsed", { messageCount: messages.length });
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
        model: settings.modelId || undefined,
        provider_id: settings.providerId || undefined,
      };

      debugLog.log("chat request payload prepared", {
        model: customBody.model,
        providerId: customBody.provider_id,
        queryLength: customBody.query.length,
      });

      const response = await fetch(url, {
        ...init,
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
