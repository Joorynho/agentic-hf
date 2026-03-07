#!/usr/bin/env python
"""Verify Phase 2.6 deployment setup — comprehensive integration check."""
import subprocess
import sys
from pathlib import Path

def check_file_exists(path: str, name: str) -> bool:
    """Check if a file exists."""
    if Path(path).exists():
        print(f"  [OK] {name}: {path}")
        return True
    else:
        print(f"  [FAIL] {name}: {path} NOT FOUND")
        return False

def check_python_imports() -> bool:
    """Check critical Python imports."""
    try:
        import sys
        from pathlib import Path
        # Ensure we can import from src
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        from src.web.server import create_app, ConnectionManager, EventBusListener
        from src.core.bus.event_bus import EventBus
        from src.mission_control.session_manager import SessionManager
        print("  [OK] All Python imports successful")
        return True
    except Exception as e:
        print(f"  [FAIL] Python imports: {e}")
        return False

def check_web_app_creation() -> bool:
    """Check if FastAPI app can be created."""
    try:
        import sys
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        from src.web.server import create_app
        app = create_app()
        # Verify endpoints exist
        endpoints = [route.path for route in app.routes]
        critical_endpoints = ["/health", "/api/session", "/api/pods", "/ws"]
        found = [ep in endpoints for ep in critical_endpoints]
        if all(found):
            print(f"  [OK] FastAPI app created with {len(endpoints)} endpoints")
            return True
        else:
            missing = [ep for ep, found in zip(critical_endpoints, found) if not found]
            print(f"  [FAIL] Missing endpoints: {missing}")
            return False
    except Exception as e:
        print(f"  [FAIL] FastAPI app creation: {e}")
        return False

def check_session_manager_web_support() -> bool:
    """Check SessionManager has web server support."""
    try:
        import sys
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        from src.mission_control.session_manager import SessionManager
        import inspect

        # Check __init__ has enable_web_server
        sig = inspect.signature(SessionManager.__init__)
        if 'enable_web_server' not in sig.parameters:
            print("  [FAIL] SessionManager missing enable_web_server parameter")
            return False

        # Check methods exist
        if not hasattr(SessionManager, '_start_web_server'):
            print("  [FAIL] SessionManager missing _start_web_server method")
            return False

        if not hasattr(SessionManager, '_update_web_state'):
            print("  [FAIL] SessionManager missing _update_web_state method")
            return False

        print("  [OK] SessionManager has web server support")
        return True
    except Exception as e:
        print(f"  [FAIL] SessionManager check: {e}")
        return False

def check_tests_pass() -> bool:
    """Run web dashboard tests."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest",
             "tests/integration/test_web_dashboard_e2e.py",
             "-v", "--tb=short", "-q"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            # Extract test count
            output = result.stdout + result.stderr
            if "passed" in output:
                print(f"  [OK] Web dashboard tests passed")
                return True
            else:
                print(f"  [FAIL] Tests may have failed")
                return False
        else:
            print(f"  [FAIL] Tests failed with return code {result.returncode}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  [FAIL] Tests timed out")
        return False
    except Exception as e:
        print(f"  [FAIL] Test execution: {e}")
        return False

def check_docker_files() -> bool:
    """Check Docker deployment files."""
    docker_files = {
        "Dockerfile": "Multi-stage Docker build",
        "docker-compose.yml": "Docker Compose config",
        ".dockerignore": "Docker ignore patterns",
    }

    all_present = True
    for filename, description in docker_files.items():
        if check_file_exists(filename, description):
            pass
        else:
            all_present = False

    return all_present

def check_env_files() -> bool:
    """Check environment configuration files."""
    env_files = {
        ".env.example": "Backend env template",
        "web/.env.example": "Frontend env template",
    }

    all_present = True
    for filename, description in env_files.items():
        if check_file_exists(filename, description):
            pass
        else:
            all_present = False

    return all_present

def check_documentation() -> bool:
    """Check documentation files."""
    docs = {
        "README.md": "Main documentation",
        "CLAUDE.md": "Development guidelines",
    }

    all_present = True
    for filename, description in docs.items():
        if check_file_exists(filename, description):
            pass
        else:
            all_present = False

    return all_present

def main():
    """Run all verification checks."""
    print("\n" + "="*70)
    print("Phase 2.6 Deployment Verification")
    print("="*70)

    checks = [
        ("Critical Files", [
            ("Backend web server", "src/web/server.py"),
            ("Web __init__", "src/web/__init__.py"),
            ("Web tests", "tests/integration/test_web_dashboard_e2e.py"),
            ("React config", "web/vite.config.ts"),
            ("React package.json", "web/package.json"),
        ]),
        ("Python Imports", [
            ("Python imports", check_python_imports),
        ]),
        ("FastAPI Integration", [
            ("Web app creation", check_web_app_creation),
        ]),
        ("SessionManager Integration", [
            ("Web server support", check_session_manager_web_support),
        ]),
        ("Docker Deployment", [
            ("Docker files", check_docker_files),
        ]),
        ("Configuration", [
            ("Environment files", check_env_files),
        ]),
        ("Documentation", [
            ("Documentation", check_documentation),
        ]),
        ("Testing", [
            ("Web dashboard tests", check_tests_pass),
        ]),
    ]

    total_checks = 0
    passed_checks = 0

    for category_name, category_checks in checks:
        print(f"\n{category_name}:")
        for check_name, check_fn in category_checks:
            total_checks += 1
            if callable(check_fn):
                # Function-based check
                if check_fn():
                    passed_checks += 1
            else:
                # File existence check
                if check_file_exists(check_fn, check_name):
                    passed_checks += 1

    # Summary
    print(f"\n" + "="*70)
    print(f"Results: {passed_checks}/{total_checks} checks passed")
    print("="*70)

    if passed_checks == total_checks:
        print("\nSUCCESS: Phase 2.6 deployment setup is complete!")
        print("\nNext steps:")
        print("1. Configure .env with Alpaca credentials")
        print("2. Build React: cd web && npm run build && cd ..")
        print("3. Start FastAPI: python -m uvicorn src.web.server:app --port 8000")
        print("4. Open http://localhost:8000 in your browser")
        return 0
    else:
        print(f"\nFAILURE: {total_checks - passed_checks} checks failed")
        print("Review the failures above and fix issues.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
