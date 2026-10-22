import sys
from core.maid.maid_selfevolve import propose_patch, request_self_reload
task, marker = sys.argv[1], sys.argv[2]
code = open('core/maid/maid_common.py').read() + "\n# " + marker + "\n"
print(propose_patch(task, [{'path': 'core/maid/maid_common.py', 'content': code}], marker)[:120])
print(request_self_reload(task, marker, 'e2e test')[:80])
