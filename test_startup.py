import sys
import traceback

sys.path.insert(0, ".")

try:
    from services.api.main import app
    print("SUCCESS: app imported")
except Exception as e:
    print("FAILED TO IMPORT APP")
    traceback.print_exc()
