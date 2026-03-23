"""
test_humphi.py - Debug version
"""
import sys
import traceback

print("=== HUMPHI DEBUG ===")
print(f"Python: {sys.version}")

# Step 1 - check uiautomation
try:
    import uiautomation as auto
    print("[OK] uiautomation imported")
except Exception as e:
    print(f"[FAIL] uiautomation: {e}")
    input("Press Enter to exit...")
    sys.exit()

# Step 2 - list all open windows
print("\n=== OPEN WINDOWS ===")
try:
    desktop = auto.GetRootControl()
    windows = []
    for win in desktop.GetChildren():
        if win.Name and win.Name not in ("", "Program Manager"):
            print(f"  [{win.ControlTypeName}] '{win.Name}'")
            windows.append(win)
    print(f"Total: {len(windows)} windows")
except Exception as e:
    print(f"[FAIL] listing windows: {e}")
    traceback.print_exc()

# Step 3 - pick first real window and dump its tree
print("\n=== TESTING FILTER ON FIRST WINDOW ===")
try:
    target = None
    for win in windows:
        # skip taskbar and system windows
        if win.Name and win.Name not in ("Windows Input Experience", "Windows Shell Experience Host"):
            target = win
            break

    if target:
        print(f"Testing on: '{target.Name}'")

        # dump raw tree first
        print("\n--- Raw tree (depth 2) ---")
        def dump(ctrl, depth=0, max_d=2):
            if depth > max_d: return
            indent = "  " * depth
            print(f"{indent}[{ctrl.ControlTypeName}] '{ctrl.Name}' id='{ctrl.AutomationId}' enabled={ctrl.IsEnabled}")
            try:
                for child in ctrl.GetChildren():
                    dump(child, depth+1, max_d)
            except: pass
        dump(target)

        # now test filter
        print("\n--- After Humphi filter ---")
        from humphi.filter import filter_and_compress
        from humphi.logger import HumphiLogger
        logger = HumphiLogger()
        result = filter_and_compress(target, "test task", logger)
        print(f"Raw nodes: {result.raw_node_count}")
        print(f"Filtered: {result.filtered_count}")
        print(f"DSL:\n{result.dsl_payload}")

except Exception as e:
    print(f"[FAIL] {e}")
    traceback.print_exc()

# Step 4 - now run the real agent
print("\n=== HUMPHI AI ===")
print("Type your task. Type 'quit' to exit.\n")

try:
    from humphi.agent import HumphiAgent
    agent = HumphiAgent()

    while True:
        task = input("Task > ").strip()
        if not task:
            continue
        if task.lower() in ("quit", "exit", "q"):
            break
        agent.run(task)

except Exception as e:
    print(f"[FAIL] agent error: {e}")
    traceback.print_exc()

input("\nPress Enter to exit...")
