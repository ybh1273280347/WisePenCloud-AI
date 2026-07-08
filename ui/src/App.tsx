import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import { useChat } from "@ai-sdk/react";
import { debugLog } from "./lib/debug-log";
import { createBackendTransport } from "./lib/chat-transport";
import {
  createSession,
  createWebSearchCredential,
  deleteSession,
  listAvailableModels,
  listSessions,
  listWebSearchCredentials,
  loadHistoryMessages,
  pinSession,
  renameSession,
  setActiveWebSearchCredential,
} from "./lib/backend-client";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { ChatWindow } from "./components/ChatWindow";
import { InputBox } from "./components/InputBox";
import { SettingsDialog } from "./components/SettingsDialog";
import { Sidebar } from "./components/Sidebar";
import { defaultRuntimeSettings } from "./data/runtimeSettings";
import type { ChatAppMessage, ModelOption, RuntimeSettings, SessionSummary, WebSearchCredential } from "./types/chat";

export default function App() {
  const [settings, setSettings] = useState<RuntimeSettings>(defaultRuntimeSettings);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [input, setInput] = useState("");
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [backendSessionId, setBackendSessionId] = useState<string>("");
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
  const [modelLoadError, setModelLoadError] = useState("");
  const [searchCredentials, setSearchCredentials] = useState<WebSearchCredential[]>([]);
  const [searchLoadError, setSearchLoadError] = useState("");
  const [pendingBackendInput, setPendingBackendInput] = useState("");
  const [creatingSessionForSubmit, setCreatingSessionForSubmit] = useState(false);
  const backendSessionIdRef = useRef("");
  const loadedHistorySessionIdRef = useRef("");
  const sentPendingInputRef = useRef("");
  const settingsRef = useRef(settings);

  useEffect(() => {
  settingsRef.current = settings;
}, [settings]);

  const transport = useMemo(() => {
  return createBackendTransport({
    getSessionId: () => backendSessionIdRef.current,
    getSettings: () => settingsRef.current,
  });
}, []);
  const { messages, sendMessage, setMessages, status, stop } = useChat({
    transport,
  });
  const applyHistoryMessages = useEffectEvent((nextMessages: ChatAppMessage[]) => {
    setMessages(nextMessages);
  });
  const applyModelOptions = useEffectEvent((options: ModelOption[]) => {
    setModelOptions(options);

    if (options[0]) {
      setSettings((current) => {
        if (current.modelId) {
          return current;
        }

        return {
          ...current,
          modelId: options[0].modelId,
          providerId: options[0].providerId,
        };
      });
    }
  });
  const bootstrapSession = useEffectEvent(async () => {
    debugLog.log("bootstrap session started", {
      baseUrl: settings.baseUrl,
      userId: settings.userId,
    });
    try {
      // 加载已有 session 列表
      const sessionsResult = await listSessions(settings);
      const sessionList: SessionSummary[] = sessionsResult.list.map((s) => ({
        id: s.id,
        title: s.title,
        updatedAt: s.updated_at,
        preview: "",
        pinned: s.is_pinned,
      }));
      setSessions(sessionList);

      // 如果有已有 session，选择最近的一个；否则创建新 session
      if (sessionList.length > 0) {
        const latestSession = sessionList[0];
        applyBackendSessionId(latestSession.id);
        setActiveSessionId(latestSession.id);
        const history = await loadHistoryMessages(settings, latestSession.id);
        applyHistoryMessages(history.list);
        loadedHistorySessionIdRef.current = latestSession.id;
      } else {
        const session = await createSession(settings);
        applyBackendSessionId(session.id);
        setActiveSessionId(session.id);
        loadedHistorySessionIdRef.current = session.id;
        setSessions([{
          id: session.id,
          title: session.title,
          updatedAt: session.updated_at,
          preview: "",
          pinned: session.is_pinned,
        }]);
      }
    } catch (error) {
      debugLog.error("bootstrap session failed", { error });
    }
  });

  function applySearchCredentials(credentials: WebSearchCredential[]) {
    setSearchCredentials(credentials);

    // 优先找 active 的 custom，其次找 active 的 platform
    const activeCustom = credentials.find((credential) => credential.source === "custom" && credential.is_active);
    const activePlatform = credentials.find((credential) => credential.source === "platform" && credential.is_active);
    const selected = activeCustom ?? activePlatform;

    if (selected) {
      setSettings((current) => {
        if (
          current.searchProvider === selected.provider
          && current.searchSource === selected.source
        ) {
          return current;
        }

        return {
          ...current,
          searchProvider: selected.provider,
          searchSource: selected.source,
        };
      });
    }
  }

  function applyBackendSessionId(sessionId: string) {
    backendSessionIdRef.current = sessionId;
    setBackendSessionId(sessionId);
  }

  useEffect(() => {
    let disposed = false;
    const requestSettings: RuntimeSettings = {
      ...defaultRuntimeSettings,
      baseUrl: settings.baseUrl,
      fromSource: settings.fromSource,
      identityType: settings.identityType,
      userId: settings.userId,
    };

    async function loadRuntimeOptions() {
      setModelLoadError("");
      setSearchLoadError("");

      const [nextModels, nextCredentials] = await Promise.all([
        listAvailableModels(requestSettings),
        listWebSearchCredentials(requestSettings),
      ]);

      if (disposed) {
        return;
      }

      applyModelOptions(nextModels);
      applySearchCredentials(nextCredentials);
    }

    void loadRuntimeOptions().catch((error: unknown) => {
      if (disposed) {
        return;
      }

      const message = error instanceof Error ? error.message : "运行配置加载失败";
      setModelLoadError(message);
      setSearchLoadError(message);
    });

    return () => {
      disposed = true;
    };
  }, [
    settings.baseUrl,
    settings.fromSource,
    settings.identityType,
    settings.userId,
  ]);

  useEffect(() => {
    let disposed = false;

    async function run() {
      try {
        await bootstrapSession();
      } catch (error) {
        if (disposed) return;
        debugLog.error("failed to bootstrap session", { error });
      }
    }

    void run();

    return () => {
      disposed = true;
    };
  }, [
    settings.baseUrl,
    settings.fromSource,
    settings.identityType,
    settings.userId,
  ]);

  // 切换 session 时加载历史消息
  useEffect(() => {
    if (!activeSessionId) {
      return;
    }

    if (activeSessionId === loadedHistorySessionIdRef.current) {
      if (backendSessionIdRef.current !== activeSessionId) {
        applyBackendSessionId(activeSessionId);
      }

      return;
    }

    let disposed = false;
    const targetSessionId = activeSessionId;

    async function loadSessionHistory() {
      try {
        applyBackendSessionId(targetSessionId);
        const history = await loadHistoryMessages(settings, targetSessionId);
        if (disposed) return;
        if (backendSessionIdRef.current !== targetSessionId) return;

        applyHistoryMessages(history.list);
        loadedHistorySessionIdRef.current = targetSessionId;
      } catch (error) {
        if (disposed) return;
        debugLog.error("failed to load session history", { error });
      }
    }

    void loadSessionHistory();

    return () => {
      disposed = true;
    };
  }, [activeSessionId, settings]);

  useEffect(() => {
    backendSessionIdRef.current = backendSessionId;
  }, [backendSessionId]);

  useEffect(() => {
    if (
      !pendingBackendInput
      || !backendSessionId
      || sentPendingInputRef.current === pendingBackendInput
    ) {
      return;
    }

    sentPendingInputRef.current = pendingBackendInput;
    void sendMessage({ text: pendingBackendInput });

    window.setTimeout(() => {
      setPendingBackendInput("");
      sentPendingInputRef.current = "";
    }, 0);
  }, [backendSessionId, pendingBackendInput, sendMessage]);

  async function createBackendSessionForSubmit() {
    if (creatingSessionForSubmit) {
      return;
    }

    setCreatingSessionForSubmit(true);

    try {
      const session = await createSession(settings);
      const nextSession: SessionSummary = {
        id: session.id,
        title: session.title,
        updatedAt: session.updated_at,
        preview: "",
        pinned: session.is_pinned,
      };

      setSessions((current) => {
        if (current.some((item) => item.id === nextSession.id)) {
          return current;
        }

        return [nextSession, ...current];
      });
      setActiveSessionId(session.id);
      applyBackendSessionId(session.id);
    } catch (error) {
      setPendingBackendInput("");
      debugLog.error("failed to create session before submit", { error });
    } finally {
      setCreatingSessionForSubmit(false);
    }
  }

  function handleSubmit() {
    debugLog.log("submit message", {
      hasBackendSession: Boolean(backendSessionId),
      inputLength: input.length,
    });

    if (!input.trim()) {
      return;
    }

    setPendingBackendInput(input);
    setInput("");

    if (!backendSessionId) {
      void createBackendSessionForSubmit();
    }
  }

  async function handleCreateSession() {
    try {
      const session = await createSession(settings);
      const nextSession: SessionSummary = {
        id: session.id,
        title: session.title,
        updatedAt: session.updated_at,
        preview: "",
        pinned: session.is_pinned,
      };

      setSessions((current) => [nextSession, ...current]);
      setActiveSessionId(session.id);
      applyBackendSessionId(session.id);
      loadedHistorySessionIdRef.current = session.id;
      setMessages([]);
    } catch (error) {
      debugLog.error("failed to create session", { error });
    }
  }

  async function handleDeleteSession(sessionId: string) {
    try {
      await deleteSession(settings, sessionId);
      setSessions((current) => current.filter((s) => s.id !== sessionId));
      if (activeSessionId === sessionId) {
        const remaining = sessions.filter((s) => s.id !== sessionId);
        if (remaining.length > 0) {
          setActiveSessionId(remaining[0].id);
        } else {
          setActiveSessionId("");
          applyBackendSessionId("");
          loadedHistorySessionIdRef.current = "";
          setMessages([]);
        }
      }
    } catch (error) {
      debugLog.error("failed to delete session", { error });
    }
  }

  async function handleRenameSession(sessionId: string, newTitle: string) {
    try {
      await renameSession(settings, sessionId, newTitle);
      setSessions((current) =>
        current.map((s) => s.id === sessionId ? { ...s, title: newTitle } : s)
      );
    } catch (error) {
      debugLog.error("failed to rename session", { error });
    }
  }

  async function handlePinSession(sessionId: string, setPin: boolean) {
    try {
      await pinSession(settings, sessionId, setPin);
      setSessions((current) =>
        current.map((s) => s.id === sessionId ? { ...s, pinned: setPin } : s)
      );
    } catch (error) {
      debugLog.error("failed to pin session", { error });
    }
  }

  async function handleDeleteAllSessions() {
    try {
      await Promise.all(sessions.map((s) => deleteSession(settings, s.id)));
      setSessions([]);
      setActiveSessionId("");
      applyBackendSessionId("");
      loadedHistorySessionIdRef.current = "";
      setMessages([]);
    } catch (error) {
      debugLog.error("failed to delete all sessions", { error });
    }
  }

  async function handleCreateCustomSearchCredential(provider: string, apiKey: string) {
    const credential = await createWebSearchCredential(settings, provider, apiKey);
    const credentials = await listWebSearchCredentials(settings);
    applySearchCredentials(credentials);
    return credential;
  }

  async function handleSelectSearchCredential(source: "platform" | "custom", provider: string) {
    const credential = await setActiveWebSearchCredential(settings, source, provider);
    const credentials = await listWebSearchCredentials(settings);
    applySearchCredentials(credentials);
    return credential;
  }

  return (
    <AppErrorBoundary>
      <div className="app-shell h-screen overflow-hidden">
        <div className="relative z-10 flex h-full gap-6 p-3 md:p-5 xl:gap-8 xl:p-6">
          <Sidebar
            activeSessionId={activeSessionId}
            mobileOpen={mobileSidebarOpen}
            onCreateSession={handleCreateSession}
            onDeleteSession={handleDeleteSession}
            onDeleteAllSessions={handleDeleteAllSessions}
            onMobileOpenChange={setMobileSidebarOpen}
            onOpenSettings={() => setSettingsOpen(true)}
            onPinSession={handlePinSession}
            onRenameSession={handleRenameSession}
            onSelectSession={setActiveSessionId}
            sessions={sessions}
          />

          <div className="flex min-h-0 min-w-0 flex-1 justify-center px-3 md:px-8 xl:px-12">
            <div className="flex min-h-0 w-full max-w-[860px] flex-col gap-3 2xl:max-w-[920px]">
              <div className="min-h-0 flex-1">
                <ChatWindow messages={messages as ChatAppMessage[]} status={status} />
              </div>

              <div className="relative shrink-0 pt-2 before:absolute before:inset-x-0 before:-top-8 before:h-8 before:bg-gradient-to-t before:from-[#f7f8fa] before:to-transparent before:content-['']">
                <InputBox
                  modelLoadError={modelLoadError}
                  modelOptions={modelOptions}
                  onChange={setInput}
                  onCreateCustomSearchCredential={handleCreateCustomSearchCredential}
                  onSelectModel={(option) => {
                    setSettings((current) => ({
                      ...current,
                      modelId: option.modelId,
                      providerId: option.providerId,
                    }));
                  }}
                  onSelectSearchCredential={handleSelectSearchCredential}
                  onStop={stop}
                  onSubmit={handleSubmit}
                  searchCredentials={searchCredentials}
                  settings={settings}
                  status={status}
                  value={input}
                />
              </div>
            </div>
          </div>
        </div>

        <SettingsDialog
          modelLoadError={modelLoadError}
          modelOptions={modelOptions}
          onChange={setSettings}
          onCreateCustomSearchCredential={handleCreateCustomSearchCredential}
          onOpenChange={setSettingsOpen}
          onSelectSearchCredential={handleSelectSearchCredential}
          open={settingsOpen}
          searchCredentials={searchCredentials}
          searchLoadError={searchLoadError}
          settings={settings}
        />
      </div>
    </AppErrorBoundary>
  );
}
