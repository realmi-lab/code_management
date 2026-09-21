"""Tracked fail-closed local access patch; never edits the verified upstream checkout."""
import ast
import hashlib
import json
from pathlib import Path
import sys


def apply(root: Path):
    edits = []
    outputs = {}

    def replace(path, old, new):
        original = outputs.get(path, (root / path).read_text())
        if original.count(old) != 1:
            raise RuntimeError(f"Upstream contract changed: {path}")
        output = original.replace(old, new)
        ast.parse(output)
        outputs[path] = output

    replace("app/dependencies.py", '    if credentials is None:\n',
            '    from code_agent.local_access import auth_mode, local_user\n'
            '    if auth_mode() == "local":\n'
            '        return await local_user(db)\n\n'
            '    if credentials is None:\n')
    replace("app/main.py", '    count = await session.scalar(select(func.count(User.id)))\n',
            '    from code_agent.local_access import auth_mode, ensure_local_user\n'
            '    if auth_mode() == "local":\n'
            '        await ensure_local_user(session)\n'
            '        return\n'
            '    count = await session.scalar(select(func.count(User.id)))\n')
    replace("app/api/auth.py", 'router = APIRouter(prefix="/auth", tags=["auth"])',
            'from code_agent.local_access import auth_mode, auth_route_guard\n\n'
            'router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(auth_route_guard)])\n\n'
            '@router.get("/mode")\n'
            'async def get_auth_mode():\n'
            '    return {"mode": auth_mode()}')
    for path, output in outputs.items():
        target = root / path
        original = target.read_text()
        edits.append({"path": path, "before_sha256": hashlib.sha256(original.encode()).hexdigest(),
                      "after_sha256": hashlib.sha256(output.encode()).hexdigest()})
        target.write_text(output)
    (root / "local-access-patches.json").write_text(json.dumps(edits, indent=2))
    return edits


if __name__ == "__main__":
    apply(Path(sys.argv[1] if len(sys.argv) > 1 else "/app"))
