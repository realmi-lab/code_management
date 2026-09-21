// Build-copy-only changes against exact pinned upstream contracts.
import fs from 'node:fs';
import crypto from 'node:crypto';
const records=[];
function patch(path, changes) {
  const before=fs.readFileSync(path,'utf8'); let after=before;
  for(const [old,next] of changes){if(after.split(old).length!==2)throw new Error(`Pinned experience contract changed: ${path}: ${old.slice(0,60)}`);after=after.replace(old,next);}
  fs.writeFileSync(path,after);records.push({path,before_sha256:hash(before),after_sha256:hash(after)});
}
function hash(s){return crypto.createHash('sha256').update(s).digest('hex');}
patch('src/app/global-error.tsx',[
 ['bg-blue-600 px-4 py-2 text-white hover:bg-blue-700','bg-orange-700 px-4 py-2 text-white hover:bg-orange-800'],
]);
patch('src/app/layout.tsx',[
 ['import "./globals.css";','import "./globals.css";\nimport "@/components/workspace/experience.css";'],
 ['          <AuthLayout>{children}</AuthLayout>','          <AuthLayout>{children}</AuthLayout>\n          <noscript><p style={{ padding: 32 }}>문서와 알림 코드 작업실을 사용하려면 JavaScript를 켜주세요. 로그인과 데이터 조회에 필요합니다.</p></noscript>'],
]);
patch('src/components/layout/app-shell.tsx',[
 ['import { ErrorBoundary } from "@/components/error/error-boundary";','import { ErrorBoundary } from "@/components/error/error-boundary";\nimport { WorkspaceExperience } from "@/components/workspace/experience";'],
 ['          <ErrorBoundary>{children}</ErrorBoundary>','          <div className="workspace-content"><WorkspaceExperience /><ErrorBoundary>{children}</ErrorBoundary></div>'],
]);
patch('src/components/layout/sidebar.tsx',[
 ['} from "lucide-react";','} from "@/components/workspace/solar-icons";'],
 ['<h1 className="text-lg font-bold">UrstoryRAG</h1>','<h1 className="text-lg font-bold">Code Management</h1>'],
 ['<p className="text-xs text-muted-foreground">관리자 콘솔</p>','<p className="text-xs text-muted-foreground">문서와 알림의 작업 공간</p>'],
]);
patch('src/app/settings/reranking/page.tsx',[
 ['      <RerankingForm />', `      <section aria-label="리랭커 실행 안내" className="rounded-xl border p-4 text-sm space-y-2">
        <p className="font-medium">실행 위치: 로컬 · CPU</p>
        <p className="text-muted-foreground">현재 로컬 Docker 구성에서 다운로드된 모델을 실행합니다. 모델 이름은 사용할 모델의 식별자이며, 외부 API 서버 주소가 아닙니다.</p>
        <p className="text-muted-foreground">검색으로 찾은 후보를 질문과 비교해 관련도 순으로 다시 정렬합니다. 리랭커 추론에는 외부 API 키가 필요하지 않으며, 답변 생성 모델의 연결 설정은 별도입니다.</p>
      </section>
      <RerankingForm />`],
]);
fs.writeFileSync('workspace-experience-patches.json',JSON.stringify(records,null,2));
