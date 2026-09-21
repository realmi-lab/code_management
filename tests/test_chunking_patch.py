"""Execute patched upstream strategy selection with boundary dependencies stubbed."""
import ast
import asyncio
import importlib.util
import shutil
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('chunking_patch', ROOT/'deploy/patch_chunking.py')
PATCH = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(PATCH)
FILES = ['app/tasks/indexing.py','app/services/document/processor.py','app/services/chunking/auto_detect.py','app/services/chunking/recursive.py']

def load_class(path, name, scope):
    node = next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.ClassDef) and n.name==name)
    exec('from __future__ import annotations\n'+ast.unparse(node),scope)
    return scope[name]

class ChunkingPatch(unittest.TestCase):
    def test_configured_values_reach_selected_strategy_and_splitter(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for path in FILES:
                dest=root/path;dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy(ROOT/'upstream/backend'/path,dest)
            last=root/FILES[-1];original=last.read_text()
            last.write_text(original.replace('split_overlap = max(1, split_length // 3)','split_overlap = 1'))
            first=(root/FILES[0]).read_text()
            with self.assertRaisesRegex(RuntimeError,'contract changed'): PATCH.apply(root)
            self.assertEqual((root/FILES[0]).read_text(),first)
            last.write_text(original);PATCH.apply(root)
            captured=[]
            class Splitter:
                def __init__(self,**kwargs):captured.append(kwargs)
                def run(self,documents):return {'documents':documents}
            scope={'DocumentSplitter':Splitter,'Document':types.SimpleNamespace,'Chunk':types.SimpleNamespace}
            recursive=load_class(last,'RecursiveChunking',scope)
            class Header:
                def __init__(self,**kwargs):self.kwargs=kwargs
            scope.update(RecursiveChunking=recursive,SectionHeaderChunking=Header)
            auto=load_class(root/FILES[2],'AutoDetectChunking',scope)
            scope['AutoDetectChunking']=auto
            processor=load_class(root/FILES[1],'DocumentProcessor',scope)
            for strategy in ('recursive','header','auto','sentence','token'):
                obj=processor(None,None,None,chunking_strategy=strategy,chunk_size=680,chunk_overlap=0)._get_chunking_strategy()
                if isinstance(obj,auto):
                    self.assertEqual(obj.detect_strategy({'file_type':'md'}).kwargs,{'chunk_size':680,'chunk_overlap':0})
                    obj=obj.detect_strategy({'file_type':'txt'})
                if isinstance(obj,Header):self.assertEqual(obj.kwargs,{'chunk_size':680,'chunk_overlap':0})
                else:
                    self.assertEqual((obj.chunk_size,obj.chunk_overlap),(680,0))
                    asyncio.run(obj.chunk('Synthetic sentence. '*100))
                    self.assertEqual(captured[-1]['split_overlap'],0)
                    self.assertEqual(captured[-1]['split_length'],4)
            asyncio.run(recursive(680,340).chunk('Synthetic sentence. '*100))
            self.assertEqual(captured[-1]['split_overlap'],2)
            self.assertIn('chunk_size=rag_settings.chunk_size', (root/FILES[0]).read_text())
            self.assertIn('chunk_overlap=rag_settings.chunk_overlap', (root/FILES[0]).read_text())

    @unittest.skipUnless(shutil.which('node'),'Requires Node')
    def test_frontend_legacy_options_are_not_offered_as_implemented(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);dest=root/'src/components/settings/chunking-form.tsx'
            dest.parent.mkdir(parents=True)
            shutil.copy(ROOT/'upstream/frontend/src/components/settings/chunking-form.tsx',dest)
            subprocess.run(['node',str(ROOT/'deploy/patch_chunking_frontend.mjs')],cwd=root,check=True,capture_output=True)
            self.assertIn('value="sentence" disabled',dest.read_text())
            self.assertIn('value="token" disabled',dest.read_text())
            self.assertIn('문장 단위로 근사',dest.read_text())
if __name__=='__main__':unittest.main()
