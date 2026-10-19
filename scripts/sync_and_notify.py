"""Run one local sync and email a digest only when new jobs are added."""
from scripts.auto_runner import run_cycle

if __name__ == "__main__":
    run_cycle()
