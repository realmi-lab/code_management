import fs from 'node:fs';
function patch(path,before,after){const s=fs.readFileSync(path,'utf8');if(s.split(before).length!==2)throw new Error('Pinned search persistence contract changed: '+path);fs.writeFileSync(path,s.replace(before,after));}
const page='src/app/search/page.tsx',input='src/components/search/search-input.tsx';
patch(page,'import type { SearchRequest }','import { useSessionState } from "@/lib/use-session-state";\nimport type { DebugSearchResponse } from "@/types";\nimport type { SearchRequest }');
patch(page,'  const searchMutation = useSearch();','  const searchMutation = useSearch();\n  const [savedResult, setSavedResult] = useSessionState<DebugSearchResponse | null>("document-search:result", null);\n  const [pending, setPending] = useSessionState<number | null>("document-search:pending", null);');
patch(page,'    searchMutation.mutate(params);','    setSavedResult(null);\n    setPending(performance.timeOrigin);\n    void searchMutation.mutateAsync(params).then(setSavedResult).catch(() => {}).finally(() => setPending(null));');
patch(page,'searchMutation.data ?? null','searchMutation.data ?? savedResult');
patch(input,'import { useState } from "react";','import { useSessionState } from "@/lib/use-session-state";');
patch(input,'useState("")','useSessionState("document-search:query", "")');
patch(input,'useState<"hybrid" | "vector" | "keyword" | "cascading">("hybrid")','useSessionState<"hybrid" | "vector" | "keyword" | "cascading">("document-search:mode", "hybrid")');
patch(input,'const [useHyde, setUseHyde] = useState(true);','const [useHyde, setUseHyde] = useSessionState("document-search:hyde", true);');
patch(input,'const [useReranking, setUseReranking] = useState(true);','const [useReranking, setUseReranking] = useSessionState("document-search:reranking", true);');
patch(input,'useState(5)','useSessionState("document-search:topk", 5)');

patch(page,'isLoading={searchMutation.isPending}','isLoading={searchMutation.isPending || (pending !== null && typeof window !== "undefined" && pending === performance.timeOrigin)}');
