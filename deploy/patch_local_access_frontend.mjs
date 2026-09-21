// Fail closed against the pinned upstream; preserve the JWT UI for CODE_AUTH_MODE=jwt.
import fs from 'node:fs';
const pending = new Map();
function patch(path, before, after) {
  const text = pending.get(path) ?? fs.readFileSync(path, 'utf8');
  if (text.split(before).length !== 2) throw new Error(`Pinned local access contract changed: ${path}`);
  pending.set(path, text.replace(before, after));
}
const auth='src/lib/auth-context.tsx';
patch(auth,'  isLoading: boolean;','  isLoading: boolean;\n  localMode: boolean;');
patch(auth,'  const [isLoading, setIsLoading] = useState(true);','  const [isLoading, setIsLoading] = useState(true);\n  const [localMode, setLocalMode] = useState(false);');
patch(auth,'    try {\n      const res = await fetch("/api/auth/refresh",','    if (localMode) return null;\n    try {\n      const res = await fetch("/api/auth/refresh",');
patch(auth,'  }, []);\n\n  const fetchMe','  }, [localMode]);\n\n  const fetchMe');
patch(auth,'async (token: string): Promise<User | null>','async (token: string | null): Promise<User | null>');
patch(auth,'headers: { Authorization: `Bearer ${token}` },','headers: token ? { Authorization: `Bearer ${token}` } : {},');
patch(auth,'      const token = await refreshAccessToken();',`      const modeResponse = await fetch("/api/auth/mode").catch(() => null);
      if (!modeResponse?.ok) { setIsLoading(false); return; }
      const mode = await modeResponse.json().catch(() => null);
      if (mode?.mode === "local") {
        setLocalMode(true);
        setAccessToken(null);
        setUser(await fetchMe(null));
        setIsLoading(false);
        return;
      }
      if (mode?.mode !== "jwt") { setIsLoading(false); return; }
      const token = await refreshAccessToken();`);
patch(auth,'    if (accessToken) {','    if (accessToken || localMode) {');
patch(auth,'  }, [accessToken, fetchMe]);','  }, [accessToken, fetchMe, localMode]);');
patch(auth,'  const logout = async () => {','  const logout = async () => {\n    if (localMode) return;');
patch(auth,'        isLoading,','        isLoading,\n        localMode,');
const layout='src/components/layout/auth-layout.tsx';
patch(layout,'const { isAuthenticated, isLoading }','const { isAuthenticated, isLoading, localMode }');
patch(layout,'router.replace("/");','router.replace(localMode ? "/codes" : "/");');
patch(layout,'[isAuthenticated, isLoading, isPublicPath, router]','[isAuthenticated, isLoading, isPublicPath, router, localMode]');
const header='src/components/layout/header.tsx';
patch(header,'const { user, logout }','const { user, logout, localMode }');
patch(header,'{user && (','{user && !localMode && (');
const profile='src/app/settings/profile/page.tsx';
patch(profile,'const { user, refreshUser }','const { user, refreshUser, localMode }');
patch(profile,'  if (!user) return null;','  if (!user) return null;\n  if (localMode) return <p>로그인 없이 사용하는 공용 작업실입니다.</p>;');
const login='src/app/login/page.tsx';
patch(login,'const { login }','const { login, localMode, isLoading }');
patch(login,'  return (','  if (localMode || isLoading) return null;\n\n  return (');
for (const [path,text] of pending) fs.writeFileSync(path,text);
