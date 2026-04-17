import ast
import glob
import sys

files = glob.glob("jobpipe/**/*.py", recursive=True)
errors = []
for f in files:
    try:
        ast.parse(open(f, encoding="utf-8").read())
    except SyntaxError as e:
        errors.append(f"{f}: {e}")

if errors:
    for e in errors:
        print("FAIL:", e)
    sys.exit(1)
else:
    print(f"OK — {len(files)} files parsed cleanly")
