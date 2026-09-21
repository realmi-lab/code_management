"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import "./workspace.css";

/** Original AuthLayout/AuthProvider remain the sole source of login identity. */
export default function CodesPage() {
  const { accessToken, refreshAccessToken, localMode } = useAuth();
  const frame = useRef<HTMLIFrameElement>(null);
  const [error, setError] = useState("");
  const send = useCallback((token: string | null) => {
    frame.current?.contentWindow?.postMessage({ type: "catalog-auth", token, local: localMode }, window.location.origin);
  }, [localMode]);
  useEffect(() => {
    let active = true;
    const listener = async (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== frame.current?.contentWindow) return;
      if (event.data?.type === "catalog-ready") send(accessToken);
      if (event.data?.type === "catalog-refresh") {
        if (localMode) { send(null); return; }
        const token = await refreshAccessToken();
        if (active) { send(token); if (!token) setError("로그인이 만료되었습니다. 다시 로그인해주세요."); }
      }
    };
    window.addEventListener("message", listener); send(accessToken);
    return () => { active = false; window.removeEventListener("message", listener); };
  }, [accessToken, refreshAccessToken, send, localMode]);
  return <section aria-label="알림 코드 관리" className="codes-shell">
    {error && <p role="alert">{error}</p>}
    <iframe ref={frame} src="/api/code-catalog/ui/index.html" title="알림 코드 대화 작업실"
      allow="clipboard-write" onLoad={() => send(accessToken)}
      className="codes-frame" />
  </section>;
}
