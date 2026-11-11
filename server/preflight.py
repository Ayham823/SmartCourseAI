"""Offline, secret-safe configuration checks: python -m server.preflight."""
import argparse
import json
import math
import os
from urllib.parse import urlsplit

from server.config import is_placeholder


def configuration_report(environ=None):
    values = os.environ if environ is None else environ
    checks = []
    for name in ("DATABASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"):
        value = values.get(name, "").strip()
        status = "configured"
        if not value:
            status = "missing"
        elif is_placeholder(value):
            status = "placeholder"
        elif name == "DATABASE_URL":
            try:
                parsed = urlsplit(value)
                valid = parsed.scheme in {"postgres", "postgresql"} and parsed.hostname and parsed.path.strip("/")
                if parsed.port is not None and not 1 <= parsed.port <= 65535:
                    valid = False
                if not valid:
                    status = "invalid"
            except ValueError:
                status = "invalid"
        checks.append({"setting": name, "status": status})

    # Numeric options must parse as finite values. Provider bounds are clamped
    # by get_llm; application integer bounds are validated at Flask startup.
    numeric = {
        "PORT": (int, 1, 65535),
        "MAX_MESSAGE_LENGTH": (int, 1, 100000),
        "MEMORY_MESSAGES": (int, 1, 30),
        "LLM_MAX_TOKENS": (int, None, None),
        "LLM_TIMEOUT_SECONDS": (float, None, None),
        "LLM_MAX_RETRIES": (int, None, None),
        "RAG_MIN_SIMILARITY": (float, -1, 1),
    }
    for name, (cast, minimum, maximum) in numeric.items():
        if name not in values:
            continue
        try:
            number = cast(values[name])
            valid = math.isfinite(number) and (minimum is None or minimum <= number <= maximum)
        except (TypeError, ValueError, OverflowError):
            valid = False
        checks.append({"setting": name, "status": "configured" if valid else "invalid"})
    return {
        "ready": all(check["status"] == "configured" for check in checks),
        "scope": "configuration_only",
        "database_verified": False,
        "provider_verified": False,
        "checks": checks,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print safe structured results; never print setting values.")
    args = parser.parse_args(argv)
    report = configuration_report()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Local configuration: " + ("ready" if report["ready"] else "needs attention"))
        for check in report["checks"]:
            print(f"{check['setting']}: {check['status']}")
        print("Offline check only. Database connectivity, API authentication, model access and generation were not tested.")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
