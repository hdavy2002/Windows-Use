import ast
with open("main_humphi.py", encoding="utf-8") as f:
    ast.parse(f.read())
print(f"OK — {sum(1 for _ in open('main_humphi.py',encoding='utf-8'))} lines")
