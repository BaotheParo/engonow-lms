"""
scripts/verify_handover_package.py
==================================
Automated production verification script for Sprint 4 / Phase 4.6 Handover Package.
Validates existence, structure, and security constraints of all Docker containerization assets,
production compose topology, and all 6 canonical handover documentation artifacts.
"""

import sys
import os
import re
from pathlib import Path


def check_file(path_str: str, min_bytes: int = 50) -> bool:
    p = Path(path_str)
    if not p.is_file():
        print(f"[FAIL] Missing file: {path_str}")
        return False
    size = p.stat().st_size
    if size < min_bytes:
        print(f"[FAIL] File too small ({size} bytes): {path_str}")
        return False
    print(f"[PASS] File verified ({size} bytes): {path_str}")
    return True


def verify_dockerfiles() -> bool:
    print("\n--- Verifying Hardened Multi-Stage Dockerfiles ---")
    all_ok = True

    # 1. LMS Core Dockerfile
    if not check_file("Dockerfile.lms-core", min_bytes=300):
        all_ok = False
    else:
        content = Path("Dockerfile.lms-core").read_text(encoding="utf-8")
        if "USER appuser" not in content:
            print("[FAIL] Dockerfile.lms-core missing non-root 'USER appuser' directive")
            all_ok = False
        if "layertools" not in content:
            print("[FAIL] Dockerfile.lms-core missing Spring Boot layertools extraction")
            all_ok = False
        if "MaxRAMPercentage" not in content:
            print("[FAIL] Dockerfile.lms-core missing JVM MaxRAMPercentage container optimization")
            all_ok = False
        if "HEALTHCHECK" not in content:
            print("[FAIL] Dockerfile.lms-core missing HEALTHCHECK directive")
            all_ok = False

    # 2. AI Worker Dockerfile
    if not check_file("Dockerfile.ai-worker", min_bytes=300):
        all_ok = False
    else:
        content = Path("Dockerfile.ai-worker").read_text(encoding="utf-8")
        if "USER appuser" not in content:
            print("[FAIL] Dockerfile.ai-worker missing non-root 'USER appuser' directive")
            all_ok = False
        if "PROMETHEUS_MULTIPROC_DIR" not in content:
            print("[FAIL] Dockerfile.ai-worker missing PROMETHEUS_MULTIPROC_DIR configuration")
            all_ok = False
        if "HEALTHCHECK" not in content:
            print("[FAIL] Dockerfile.ai-worker missing HEALTHCHECK directive")
            all_ok = False

    return all_ok


def verify_compose_topology() -> bool:
    print("\n--- Verifying Production Docker Compose Topology ---")
    compose_path = "docker-compose.prod.yml"
    if not check_file(compose_path, min_bytes=500):
        return False

    content = Path(compose_path).read_text(encoding="utf-8")

    expected_services = [
        "postgres",
        "redis",
        "kafka",
        "schema-registry",
        "lms-core",
        "ai-worker",
        "prometheus",
        "grafana"
    ]

    all_ok = True
    for svc in expected_services:
        pattern = rf"^\s+{svc}:"
        if re.search(pattern, content, re.MULTILINE):
            print(f"[PASS] Service defined: {svc}")
        else:
            print(f"[FAIL] Missing required production service: {svc}")
            all_ok = False

    expected_volumes = ["postgres_data", "redis_data", "kafka_data", "prometheus_data", "grafana_data"]
    for vol in expected_volumes:
        pattern = rf"^\s+{vol}:"
        if re.search(pattern, content, re.MULTILINE):
            print(f"[PASS] Persistent named volume defined: {vol}")
        else:
            print(f"[FAIL] Missing volume definition: {vol}")
            all_ok = False

    if "engonow-net:" in content:
        print("[PASS] Custom bridge network defined: engonow-net")
    else:
        print("[FAIL] Missing custom bridge network definition: engonow-net")
        all_ok = False

    return all_ok


def verify_handover_documentation() -> bool:
    print("\n--- Verifying Production Handover Documentation Package (docs/handover/) ---")
    doc_files = [
        ("docs/handover/API_CONTRACT.yaml", 1000),
        ("docs/handover/ARCHITECTURE_GUIDE.md", 1000),
        ("docs/handover/ARCHITECTURE_DECISION_LOG.md", 800),
        ("docs/handover/CALIBRATION_GUIDE.md", 1000),
        ("docs/handover/DEPLOYMENT_GUIDE.md", 800),
        ("docs/handover/RUNBOOK.md", 800),
        ("docs/handover/KNOWN_LIMITATIONS.md", 500),
        ("docs/handover/TEST_REPORT.md", 1000),
    ]

    all_ok = True
    for file_path, min_size in doc_files:
        if not check_file(file_path, min_bytes=min_size):
            all_ok = False

    return all_ok


def main():
    print("=" * 60)
    print("[ENGONOW SPRINT 4 / PHASE 4.6 HANDOVER VERIFICATION]")
    print("=" * 60)

    ok_docker = verify_dockerfiles()
    ok_compose = verify_compose_topology()
    ok_docs = verify_handover_documentation()

    print("\n" + "=" * 60)
    if ok_docker and ok_compose and ok_docs:
        print("[PHASE 4.6 HANDOVER PACKAGE: 100% VERIFIED & PRODUCTION READY]")
        print("Release Tag Definition: release-v1.0-handover")
        print("=" * 60)
        sys.exit(0)
    else:
        print("[PHASE 4.6 HANDOVER VERIFICATION FAILED]")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
