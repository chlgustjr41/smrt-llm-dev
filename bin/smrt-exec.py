#!/usr/bin/env python3
"""CLI shim: delegate to smrt_agent.sandbox.exec."""
import sys
import os

# Allow running from repo root without installing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "src"))

from smrt_agent.sandbox.exec import get_docker_client, run_in_sandbox, SMRT_NETWORK  # noqa: F401

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SMRT sandbox exec helper")
    parser.add_argument("--image", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    container = run_in_sandbox(
        container_name=args.name,
        image=args.image,
        command=args.command,
    )
    print(f"Started container: {container.id}")
