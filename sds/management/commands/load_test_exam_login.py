import csv
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from django.core.management.base import BaseCommand, CommandError


@dataclass
class ScenarioResult:
    username: str
    ok: bool
    status_code: int
    login_ms: int
    my_tests_ms: int
    launch_ms: int
    error: str = ""


class Command(BaseCommand):
    help = "Load test the exam login path with real test credentials."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default="http://localhost:8000")
        parser.add_argument("--credentials", required=True, help="CSV with username,password,role[,launch_url].")
        parser.add_argument("--students", type=int, default=100)
        parser.add_argument("--workers", type=int, default=20)
        parser.add_argument("--timeout", type=int, default=15)

    def handle(self, *args, **options):
        credentials = self._load_credentials(options["credentials"], options["students"])
        if not credentials:
            raise CommandError("No credentials found.")

        base_url = options["base_url"].rstrip("/") + "/"
        timeout = options["timeout"]
        results = []
        started_at = time.perf_counter()

        with ThreadPoolExecutor(max_workers=options["workers"]) as executor:
            futures = [
                executor.submit(self._run_student_scenario, base_url, row, timeout)
                for row in credentials
            ]
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                status = "OK" if result.ok else "FAIL"
                self.stdout.write(
                    f"{status} {result.username} login={result.login_ms}ms "
                    f"my_tests={result.my_tests_ms}ms launch={result.launch_ms}ms "
                    f"status={result.status_code} {result.error}"
                )

        elapsed = int((time.perf_counter() - started_at) * 1000)
        ok_results = [result for result in results if result.ok]
        self.stdout.write("")
        self.stdout.write(f"Students simulated: {len(results)}")
        self.stdout.write(f"Successful scenarios: {len(ok_results)}")
        self.stdout.write(f"Failed scenarios: {len(results) - len(ok_results)}")
        self.stdout.write(f"Total wall time: {elapsed}ms")

        for label, values in {
            "login": [result.login_ms for result in ok_results],
            "my_tests": [result.my_tests_ms for result in ok_results],
            "launch": [result.launch_ms for result in ok_results if result.launch_ms],
        }.items():
            if values:
                self.stdout.write(
                    f"{label} avg={int(statistics.mean(values))}ms "
                    f"p95={self._percentile(values, 95)}ms max={max(values)}ms"
                )

    def _load_credentials(self, path, limit):
        with open(path, newline="", encoding="utf-8") as credentials_file:
            rows = list(csv.DictReader(credentials_file))
        required = {"username", "password"}
        missing = required - set(rows[0].keys() if rows else [])
        if missing:
            raise CommandError(f"Credentials CSV is missing columns: {', '.join(sorted(missing))}")
        return rows[:limit]

    def _run_student_scenario(self, base_url, row, timeout):
        session = requests.Session()
        username = (row.get("username") or "").strip()
        role = (row.get("role") or "Student").strip() or "Student"
        launch_url = (row.get("launch_url") or "").strip()

        try:
            login_url = urljoin(base_url, "/")
            login_page = session.get(login_url, timeout=timeout)
            csrf_token = session.cookies.get("csrftoken", "")

            started = time.perf_counter()
            login_response = session.post(
                login_url,
                data={
                    "username": username,
                    "password": row.get("password") or "",
                    "role": role,
                    "csrfmiddlewaretoken": csrf_token,
                },
                headers={"Referer": login_url, "X-CSRFToken": csrf_token},
                allow_redirects=True,
                timeout=timeout,
            )
            login_ms = int((time.perf_counter() - started) * 1000)

            started = time.perf_counter()
            my_tests_response = session.get(urljoin(base_url, "/my-tests/"), timeout=timeout)
            my_tests_ms = int((time.perf_counter() - started) * 1000)

            launch_ms = 0
            if launch_url:
                started = time.perf_counter()
                launch_response = session.get(urljoin(base_url, launch_url), timeout=timeout)
                launch_ms = int((time.perf_counter() - started) * 1000)
                status_code = launch_response.status_code
            else:
                status_code = my_tests_response.status_code

            ok = (
                login_page.status_code == 200
                and login_response.status_code < 400
                and my_tests_response.status_code == 200
                and status_code < 400
            )
            return ScenarioResult(username, ok, status_code, login_ms, my_tests_ms, launch_ms)
        except requests.RequestException as exc:
            return ScenarioResult(username, False, 0, 0, 0, 0, str(exc))

    def _percentile(self, values, percentile):
        ordered = sorted(values)
        index = min(len(ordered) - 1, int(round((percentile / 100) * (len(ordered) - 1))))
        return ordered[index]
