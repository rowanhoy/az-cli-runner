"""Memory benchmark for concurrent Az CLI sessions.

This script measures memory usage when running multiple concurrent
Az CLI sessions. It can be used to determine how many sessions
the service can handle and whether using azure-cli-core directly
(Python API) would reduce memory overhead.

Usage:
    # Test with subprocess-based execution (default)
    python benchmarks/memory_benchmark.py --sessions 10 --mode subprocess

    # Test with azure.cli.core Python API (if installed)
    python benchmarks/memory_benchmark.py --sessions 10 --mode python-sdk

Requirements:
    - psutil (pip install psutil)
    - For python-sdk mode: azure-cli-core
"""

import argparse
import asyncio
import os
import shutil
import sys
import tempfile
import time

try:
    import psutil
except ImportError:
    print("psutil is required: pip install psutil")
    sys.exit(1)


def get_memory_mb() -> float:
    """Get current process memory usage in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


async def simulate_subprocess_session(session_id: int, config_dir: str) -> dict:
    """Simulate a subprocess-based az CLI session.

    Creates an isolated config dir and runs a lightweight az command.
    """
    session_config = os.path.join(config_dir, f"session-{session_id}")
    os.makedirs(session_config, exist_ok=True)

    env = os.environ.copy()
    env["AZURE_CONFIG_DIR"] = session_config

    start = time.monotonic()
    try:
        process = await asyncio.create_subprocess_exec(
            "az",
            "version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        await process.communicate()
        elapsed = time.monotonic() - start
        return {
            "session_id": session_id,
            "elapsed": elapsed,
            "success": process.returncode == 0,
        }
    except FileNotFoundError:
        elapsed = time.monotonic() - start
        return {
            "session_id": session_id,
            "elapsed": elapsed,
            "success": False,
            "error": "az CLI not found",
        }
    finally:
        shutil.rmtree(session_config, ignore_errors=True)


async def simulate_python_sdk_session(session_id: int) -> dict:
    """Simulate an azure-cli-core Python API session.

    Tests if using the Python SDK directly reduces memory overhead
    compared to subprocess execution.
    """
    start = time.monotonic()
    try:
        from azure.cli.core import get_default_cli

        cli = get_default_cli()
        exit_code = cli.invoke(["version"])
        elapsed = time.monotonic() - start
        return {
            "session_id": session_id,
            "elapsed": elapsed,
            "success": exit_code == 0,
        }
    except ImportError:
        return {
            "session_id": session_id,
            "elapsed": 0,
            "success": False,
            "error": "azure-cli-core not installed",
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "session_id": session_id,
            "elapsed": elapsed,
            "success": False,
            "error": str(e),
        }


async def run_benchmark(num_sessions: int, mode: str) -> None:
    """Run the concurrent session benchmark."""
    print(f"\n{'=' * 60}")
    print("Az CLI Runner — Memory Benchmark")
    print(f"Mode: {mode} | Sessions: {num_sessions}")
    print(f"{'=' * 60}\n")

    baseline_mem = get_memory_mb()
    print(f"Baseline memory: {baseline_mem:.1f} MB")

    config_dir = tempfile.mkdtemp(prefix="az-bench-")

    try:
        if mode == "subprocess":
            tasks = [
                simulate_subprocess_session(i, config_dir)
                for i in range(num_sessions)
            ]
        elif mode == "python-sdk":
            tasks = [simulate_python_sdk_session(i) for i in range(num_sessions)]
        else:
            print(f"Unknown mode: {mode}")
            return

        start_time = time.monotonic()
        results = await asyncio.gather(*tasks)
        total_time = time.monotonic() - start_time
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)

    peak_mem = get_memory_mb()
    mem_delta = peak_mem - baseline_mem

    successes = sum(1 for r in results if r["success"])
    failures = sum(1 for r in results if not r["success"])
    avg_time = sum(r["elapsed"] for r in results) / len(results) if results else 0

    print("\nResults:")
    print(f"  Successful sessions: {successes}/{num_sessions}")
    print(f"  Failed sessions:     {failures}/{num_sessions}")
    print(f"  Total wall time:     {total_time:.2f}s")
    print(f"  Avg session time:    {avg_time:.2f}s")
    print(f"  Peak memory:         {peak_mem:.1f} MB")
    print(f"  Memory delta:        {mem_delta:.1f} MB")
    print(f"  Est. per-session:    {mem_delta / max(num_sessions, 1):.1f} MB")

    if failures:
        print("\nFailed sessions:")
        for r in results:
            if not r["success"]:
                print(f"  Session {r['session_id']}: {r.get('error', 'unknown error')}")

    print(f"\n{'=' * 60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark memory usage of concurrent Az CLI sessions"
    )
    parser.add_argument(
        "--sessions",
        type=int,
        default=5,
        help="Number of concurrent sessions to simulate (default: 5)",
    )
    parser.add_argument(
        "--mode",
        choices=["subprocess", "python-sdk"],
        default="subprocess",
        help="Execution mode: 'subprocess' (default) or 'python-sdk'",
    )
    args = parser.parse_args()

    asyncio.run(run_benchmark(args.sessions, args.mode))


if __name__ == "__main__":
    main()
