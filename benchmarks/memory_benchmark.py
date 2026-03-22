"""Memory benchmark for API execution paths.

This script benchmarks the live FastAPI service by calling its execution
endpoints over HTTP while sampling the server process tree's memory usage.

The server should already be running separately when this benchmark starts.
Provide the server PID so memory measurements target the actual app process.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Iterable

import httpx

try:
    import psutil
except ImportError:
    print("psutil is required: pip install psutil")
    sys.exit(1)


DEFAULT_BENCHMARK_COMMAND = "az group list"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
EXECUTE_ENDPOINT = "/execute"


def extract_timing_metrics(payload: dict, prefix: str = "timings") -> dict[str, float]:
    """Flatten nested timing payloads into numeric metrics."""
    metrics: dict[str, float] = {}

    for key, value in payload.items():
        metric_name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            metrics.update(extract_timing_metrics(value, metric_name))
        elif isinstance(value, (int, float)):
            metrics[metric_name] = float(value)

    return metrics


def average(values: Iterable[float]) -> float:
    """Return the arithmetic mean for a sequence of numeric values."""
    value_list = list(values)
    return sum(value_list) / len(value_list) if value_list else 0.0


def get_process_tree_memory_mb(root_pid: int) -> float:
    """Get target process tree memory usage in MB."""
    current_process = psutil.Process(root_pid)
    total_rss = 0

    for process in [current_process, *current_process.children(recursive=True)]:
        try:
            total_rss += process.memory_info().rss
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue

    return total_rss / 1024 / 1024


def resolve_server_pid(server_pid: int | None) -> int:
    """Resolve the server PID from args or environment."""
    if server_pid is not None:
        return server_pid

    env_value = os.environ.get("AZ_CLI_RUNNER_SERVER_PID")
    if env_value:
        return int(env_value)

    raise RuntimeError(
        "server_pid is required. Pass --server-pid or set AZ_CLI_RUNNER_SERVER_PID."
    )


async def call_execute_endpoint(
    client: httpx.AsyncClient,
    endpoint: str,
    command: str,
    subscription_id: str | None,
) -> dict:
    """Call one execution endpoint and capture runtime and payload size."""
    payload = {"command": command}
    if subscription_id:
        payload["subscription_id"] = subscription_id

    start = time.monotonic()
    response = await client.post(endpoint, json=payload)
    elapsed = time.monotonic() - start
    response_size_bytes = len(response.content)

    try:
        response_json = response.json()
    except json.JSONDecodeError:
        return {
            "success": False,
            "elapsed": elapsed,
            "response_size_bytes": response_size_bytes,
            "error": response.text,
        }

    if response.status_code != 200:
        return {
            "success": False,
            "elapsed": elapsed,
            "response_size_bytes": response_size_bytes,
            "error": response_json.get("detail", response.text),
        }

    if not response_json.get("success"):
        return {
            "success": False,
            "elapsed": elapsed,
            "response_size_bytes": response_size_bytes,
            "error": response_json.get("stderr") or "command failed",
        }

    return {
        "success": True,
        "elapsed": elapsed,
        "response_size_bytes": response_size_bytes,
        "timings": response_json.get("timings") or {},
    }


async def track_peak_memory(
    stop_event: asyncio.Event,
    peak_memory_holder: dict[str, float],
    server_pid: int,
    sample_interval: float,
) -> None:
    """Track peak process-tree memory while benchmark tasks are running."""
    while not stop_event.is_set():
        try:
            peak_memory_holder["peak"] = max(
                peak_memory_holder["peak"],
                get_process_tree_memory_mb(server_pid),
            )
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            stop_event.set()
            return

        await asyncio.sleep(sample_interval)


async def run_benchmark(
    num_sessions: int,
    base_url: str,
    server_pid: int,
    command: str,
    subscription_id: str | None,
    sample_interval: float,
    timeout: float,
) -> None:
    """Run the concurrent session benchmark."""
    print(f"\n{'=' * 60}")
    print("Az CLI Runner — Memory Benchmark")
    print(f"Mode: subprocess | Sessions: {num_sessions}")
    print(f"Base URL: {base_url}")
    print(f"Endpoint: {EXECUTE_ENDPOINT}")
    print(f"Server PID: {server_pid}")
    print(f"Command: {command}")
    print(f"{'=' * 60}\n")

    baseline_mem = get_process_tree_memory_mb(server_pid)
    print(f"Baseline memory: {baseline_mem:.1f} MB")

    stop_event = asyncio.Event()
    peak_memory_holder = {"peak": baseline_mem}
    monitor_task = asyncio.create_task(
        track_peak_memory(stop_event, peak_memory_holder, server_pid, sample_interval)
    )

    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout),
        ) as client:
            health_response = await client.get("/health")
            health_response.raise_for_status()

            tasks = [
                call_execute_endpoint(client, EXECUTE_ENDPOINT, command, subscription_id)
                for _ in range(num_sessions)
            ]

            start_time = time.monotonic()
            results = await asyncio.gather(*tasks)
            total_time = time.monotonic() - start_time
    finally:
        stop_event.set()
        await monitor_task

    peak_mem = peak_memory_holder["peak"]
    mem_delta = peak_mem - baseline_mem

    successes = sum(1 for r in results if r["success"])
    failures = sum(1 for r in results if not r["success"])
    avg_time = sum(r["elapsed"] for r in results) / len(results) if results else 0
    avg_response_kb = (
        sum(r.get("response_size_bytes", 0) for r in results) / len(results) / 1024
        if results
        else 0
    )
    flattened_timings = [extract_timing_metrics(result.get("timings", {})) for result in results]
    timing_keys = sorted({key for metrics in flattened_timings for key in metrics})

    print("\nResults:")
    print(f"  Successful sessions: {successes}/{num_sessions}")
    print(f"  Failed sessions:     {failures}/{num_sessions}")
    print(f"  Total wall time:     {total_time:.2f}s")
    print(f"  Avg session time:    {avg_time:.2f}s")
    print(f"  Peak memory:         {peak_mem:.1f} MB")
    print(f"  Memory delta:        {mem_delta:.1f} MB")
    print(f"  Est. per-session:    {mem_delta / max(num_sessions, 1):.1f} MB")
    print(f"  Avg response size:   {avg_response_kb:.1f} KB")

    if timing_keys:
        print("\nAverage timing breakdown:")
        timing_averages = {
            key: average(metrics[key] for metrics in flattened_timings if key in metrics)
            for key in timing_keys
        }
        for timing_key in timing_keys:
            print(f"  {timing_key}: {timing_averages[timing_key]:.2f}s")

        phase_averages = {
            key: value
            for key, value in timing_averages.items()
            if not key.endswith(".total_seconds") and key != "timings.total_seconds"
        }
        if phase_averages:
            slowest_key = max(phase_averages, key=phase_averages.get)
            print(
                f"\nSlowest average phase: {slowest_key} ({phase_averages[slowest_key]:.2f}s)"
            )

    if failures:
        print("\nFailed sessions:")
        for index, result in enumerate(results):
            if not result["success"]:
                print(f"  Session {index}: {result.get('error', 'unknown error')}")

    print(f"\n{'=' * 60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark memory usage of live Az CLI Runner API execution paths"
    )
    parser.add_argument(
        "--sessions",
        type=int,
        default=5,
        help="Number of concurrent sessions to simulate (default: 5)",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the running API server (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--server-pid",
        type=int,
        default=None,
        help="PID of the running API server to sample memory from.",
    )
    parser.add_argument(
        "--command",
        default=DEFAULT_BENCHMARK_COMMAND,
        help=(
            "Azure CLI command to execute for each session "
            f"(default: '{DEFAULT_BENCHMARK_COMMAND}')"
        ),
    )
    parser.add_argument(
        "--subscription-id",
        default=None,
        help="Subscription ID to use. Defaults to DEFAULT_SUBSCRIPTION_ID.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Per-request timeout in seconds (default: 180)",
    )
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=0.1,
        help="Process-tree memory sampling interval in seconds (default: 0.1)",
    )
    args = parser.parse_args()

    asyncio.run(
        run_benchmark(
            args.sessions,
            args.base_url,
            resolve_server_pid(args.server_pid),
            args.command,
            args.subscription_id,
            args.sample_interval,
            args.timeout,
        )
    )


if __name__ == "__main__":
    main()
