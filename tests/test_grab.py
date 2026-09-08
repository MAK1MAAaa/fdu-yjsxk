from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta
import json
import unittest
from unittest.mock import Mock, mock_open, patch

import requests

from fdu_yjsxk import client, cookies, errors, logging as file_logging, runner, settings


FULL = "教学班容量已满或退选的课程席暂未释放。（#6qz9u）"
CACHE = "数据缓存中，请先暂停选退课操作。13:00:00将重新开放。"
TOKEN = "a" * 32
COOKIE = "JSESSIONID=test-session; _WEU=test-only"
COURSES = [
    {"name": "温旭", "bjdm": "2026202701GEIP40015.11", "lx": "7", "bqmc": "1"},
    {"name": "徐志宏", "bjdm": "2026202701GEIP40017.04", "lx": "7", "bqmc": "1"},
]


def response(body=None, status=200, headers=None, text=None) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result.headers.update(headers or {})
    result.encoding = "utf-8"
    result._content = (text if text is not None else json.dumps(body)).encode()
    return result


class GrabberTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = datetime(2026, 9, 7, 13, 0, 0)
        self.elapsed = 0.0
        self.sleeps: list[float] = []
        owner = self

        class TestDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return owner.clock

        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("fdu_yjsxk.runner.dt.datetime", TestDatetime))
        self.stack.enter_context(patch("fdu_yjsxk.runner.time.monotonic", lambda: self.elapsed))
        self.stack.enter_context(patch("fdu_yjsxk.runner.time.sleep", self.advance))
        self.logger = self.stack.enter_context(patch("fdu_yjsxk.runner.log"))
        self.http_logger = self.stack.enter_context(patch("fdu_yjsxk.client.log"))
        self.stack.enter_context(patch("fdu_yjsxk.cookies.log"))
        self.stack.enter_context(patch(
            "requests.sessions.Session.request",
            side_effect=AssertionError("Offline tests must not send HTTP requests"),
        ))
        self.cfg = {
            "target": "example.invalid",
            "start_time": "2026-09-07 12:59:56",
            "end_time": "2026-09-07 13:00:10",
            "homepage_refresh_secs": 1.0,
            "cookie_refresh_secs": 240,
            "request_interval": 0.8,
            "round_interval": 0,
            "poll_interval": 0.6,
            "poll_max": 2,
            "http_timeout": 12,
            "full_max_tries": 0,
            "serial_mode": True,
            "courses": deepcopy(COURSES),
        }
        self.gr = client.Grabber(self.cfg, COOKIE)
        self.addCleanup(self.gr.session.close)
        self.gr.session.get = Mock(return_value=response(
            text=f'<input id="csrfToken" value="{TOKEN}">'
        ))

    def advance(self, seconds: float) -> None:
        self.assertGreater(seconds, 0)
        self.sleeps.append(seconds)
        self.elapsed += seconds
        self.clock += timedelta(seconds=seconds)

    def run_local(self) -> tuple[int, Mock]:
        with patch("fdu_yjsxk.runner.obtain_cookie", return_value=COOKIE) as obtain:
            with patch("fdu_yjsxk.runner.Grabber", return_value=self.gr):
                code = runner.run(self.cfg, start_now=True)
        return code, obtain

    def test_homepage_refresh_is_throttled(self) -> None:
        self.assertEqual(self.gr.ensure_token(), TOKEN)
        self.advance(0.5)
        self.gr.ensure_token()
        self.assertEqual(self.gr.session.get.call_count, 1)
        self.advance(0.5)
        self.gr.ensure_token()
        self.assertEqual(self.gr.session.get.call_count, 2)

    def test_cookie_change_invalidates_token(self) -> None:
        self.gr.ensure_token()
        self.assertTrue(self.gr.set_cookie("JSESSIONID=replaced"))
        self.assertIsNone(self.gr.token)
        self.assertEqual(self.gr.last_homepage_ts, float("-inf"))

    def test_cookie_jar_preserves_server_update_on_unchanged_browser_cookie(self) -> None:
        self.gr.session.cookies.set(
            "JSESSIONID", "server-renewed", domain="example.invalid", path="/"
        )
        self.assertFalse(self.gr.set_cookie(COOKIE))
        req = self.gr.session.prepare_request(requests.Request(
            "GET", self.gr.base, headers=self.gr._headers()
        ))
        self.assertIn("JSESSIONID=server-renewed", req.headers["Cookie"])
        self.assertNotIn("JSESSIONID=test-session", req.headers["Cookie"])

    def test_full_zero_keeps_every_course_pending(self) -> None:
        pending, done = deepcopy(COURSES), []
        for _ in range(25):
            runner.handle_result(pending[0], 0, FULL, done, pending, self.gr)
        self.assertEqual(pending, COURSES)
        self.assertEqual(done, [])
        self.assertEqual(self.gr.full_tries[COURSES[0]["bjdm"]], 25)

    def test_full_limit_removes_only_exhausted_course_and_is_not_success(self) -> None:
        self.cfg["full_max_tries"] = 2
        pending, done = deepcopy(COURSES), []
        first = pending[0]
        runner.handle_result(first, 0, "其他拒绝原因", done, pending, self.gr)
        self.assertEqual(self.gr.full_tries[first["bjdm"]], 0)
        for _ in range(2):
            runner.handle_result(first, 0, FULL, done, pending, self.gr)
        self.assertEqual(pending, [COURSES[1]])
        self.assertEqual(self.gr.exhausted, [first])
        self.assertEqual(done, [])

    def test_full_limit_exit_code_is_not_success(self) -> None:
        self.cfg["full_max_tries"] = 1
        self.gr.submit = Mock(return_value=(False, FULL))
        code, _ = self.run_local()
        self.assertEqual(code, 1)
        self.assertEqual(len(self.gr.exhausted), 2)

    def test_cache_pause_waits_until_release_and_restarts_first_priority(self) -> None:
        self.clock = datetime(2026, 9, 7, 12, 59, 56)
        release = datetime(2026, 9, 7, 13, 0)
        self.cfg["full_max_tries"] = 1
        attempts = []

        def submit(course):
            attempts.append((course["bjdm"], self.clock))
            return False, CACHE if self.clock < release else FULL

        self.gr.submit = Mock(side_effect=submit)
        self.run_local()
        self.assertEqual(len(attempts), 3)
        self.assertEqual(attempts[0][0], COURSES[0]["bjdm"])
        self.assertEqual(attempts[1], (COURSES[0]["bjdm"], release))
        self.assertEqual(attempts[2][0], COURSES[1]["bjdm"])
        self.assertTrue(all(at >= release for _, at in attempts[1:]))
        self.assertEqual(self.gr.session.get.call_count, 1)

    def test_cache_release_skips_slow_homepage_request(self) -> None:
        self.clock = datetime(2026, 9, 7, 12, 59, 56)
        release = datetime(2026, 9, 7, 13, 0)
        self.cfg["full_max_tries"] = 1
        attempts = []

        def homepage(*args, **kwargs):
            self.advance(1.2)
            return response(text=f'<input id="csrfToken" value="{TOKEN}">')

        def submit(course):
            attempts.append((course["bjdm"], self.clock))
            return False, CACHE if self.clock < release else FULL

        self.gr.session.get.side_effect = homepage
        self.gr.submit = Mock(side_effect=submit)
        self.run_local()
        self.assertEqual(attempts[1], (COURSES[0]["bjdm"], release))
        self.assertEqual(self.gr.session.get.call_count, 1)

    def test_repeated_cache_preserves_token_cookie_and_request_interval(self) -> None:
        self.cfg["full_max_tries"] = 1
        self.cfg["cookie_refresh_secs"] = 0.1
        self.gr.submit = Mock(side_effect=[
            (False, CACHE), (False, CACHE), (False, FULL), (False, FULL),
        ])
        _, obtain = self.run_local()
        obtain.assert_called_once()
        self.assertEqual(self.gr.session.get.call_count, 1)
        self.assertEqual(self.gr.token, TOKEN)
        self.assertEqual(self.sleeps, [0.8] * 4)
        self.assertEqual(
            [call.args[0]["bjdm"] for call in self.gr.submit.call_args_list],
            [COURSES[0]["bjdm"]] * 3 + [COURSES[1]["bjdm"]],
        )

    def test_routine_refresh_resumes_after_release_guard(self) -> None:
        self.cfg["courses"] = [deepcopy(COURSES[0])]
        refresh_times = []

        def homepage(*args, **kwargs):
            refresh_times.append(self.clock)
            return response(text=f'<input id="csrfToken" value="{TOKEN}">')

        self.gr.session.get.side_effect = homepage
        self.gr.submit = Mock(side_effect=lambda _: (
            False, CACHE if self.elapsed == 0 else FULL,
        ))
        self.run_local()
        self.assertGreater(len(refresh_times), 1)
        guard_end = datetime(2026, 9, 7, 13, 0, 5, 800000)
        self.assertTrue(all(at >= guard_end for at in refresh_times[1:]))

    def test_scheduled_start_prewarms_before_release_and_preserves_priority(self) -> None:
        self.clock = datetime(2026, 9, 7, 12, 59, 0)
        self.cfg["full_max_tries"] = 1
        refresh_times, submit_times = [], []

        def homepage(*args, **kwargs):
            refresh_times.append(self.clock)
            self.advance(0.2)
            return response(text=f'<input id="csrfToken" value="{TOKEN}">')

        def submit(course):
            submit_times.append((course["bjdm"], self.clock))
            return False, FULL

        self.gr.session.get.side_effect = homepage
        self.gr.submit = Mock(side_effect=submit)
        with patch("fdu_yjsxk.runner.obtain_cookie", return_value=COOKIE):
            with patch("fdu_yjsxk.runner.Grabber", return_value=self.gr):
                runner.run(self.cfg, start_now=False)
        self.assertEqual(refresh_times, [
            datetime(2026, 9, 7, 12, 59, 0), datetime(2026, 9, 7, 12, 59, 36),
        ])
        self.assertEqual(submit_times[0], (
            COURSES[0]["bjdm"], datetime(2026, 9, 7, 12, 59, 56),
        ))
        self.assertEqual([course for course, _ in submit_times],
                         [course["bjdm"] for course in COURSES])

    def test_last_five_seconds_do_not_start_cookie_or_homepage_refresh(self) -> None:
        target = self.clock + timedelta(seconds=4)
        with patch("fdu_yjsxk.runner.obtain_cookie") as obtain:
            runner.prepare_and_wait(target, "测试等待", self.gr, self.cfg, 0.1)
        obtain.assert_not_called()
        self.gr.session.get.assert_not_called()
        self.assertEqual(self.clock, target)

    def test_slow_cookie_read_rechecks_guard_before_homepage(self) -> None:
        target = self.clock + timedelta(seconds=20)

        def slow_cookie(_):
            self.advance(16)
            return COOKIE

        with patch("fdu_yjsxk.runner.obtain_cookie", side_effect=slow_cookie):
            runner.prepare_and_wait(target, "测试等待", self.gr, self.cfg, 240)
        self.gr.session.get.assert_not_called()
        self.assertEqual(self.clock, target)

    def test_prewarm_http_timeout_is_clipped_before_guard(self) -> None:
        with patch("fdu_yjsxk.runner.obtain_cookie", return_value=COOKIE):
            runner.prepare_and_wait(
                self.clock + timedelta(seconds=7), "测试等待", self.gr, self.cfg, 240,
            )
        self.assertEqual(self.gr.session.get.call_args.kwargs["timeout"], 2)

    def test_missing_token_is_refreshed_even_during_release_guard(self) -> None:
        self.cfg["courses"] = [deepcopy(COURSES[0])]
        self.cfg["full_max_tries"] = 1

        def submit(_):
            if self.elapsed == 0:
                self.gr.token = None
                return False, CACHE
            self.assertEqual(self.gr.token, TOKEN)
            return False, FULL

        self.gr.submit = Mock(side_effect=submit)
        self.run_local()
        self.assertEqual(self.gr.session.get.call_count, 2)

    def test_auth_failure_is_recovered_even_during_release_guard(self) -> None:
        self.cfg["courses"] = [deepcopy(COURSES[0])]
        self.cfg["full_max_tries"] = 1
        self.gr.submit = Mock(side_effect=[
            (False, CACHE), errors.CookieError("csrfToken 失效"), (False, FULL),
        ])
        _, obtain = self.run_local()
        self.assertEqual(self.gr.session.get.call_count, 2)
        self.assertEqual(obtain.call_count, 2)

    def test_prewarm_auth_failure_invalidates_old_token(self) -> None:
        self.gr.token = TOKEN
        self.gr.session.get.return_value = response(status=403)
        with patch("fdu_yjsxk.runner.obtain_cookie", return_value=COOKIE):
            runner.prepare_and_wait(
                self.clock + timedelta(seconds=20), "测试等待", self.gr, self.cfg, 240,
            )
        self.assertIsNone(self.gr.token)

    def test_wait_is_clipped_to_deadline(self) -> None:
        self.gr.deadline = self.clock + timedelta(seconds=3)
        runner.prepare_and_wait(
            self.clock + timedelta(seconds=20), "测试等待", self.gr, self.cfg, 240,
        )
        self.assertEqual(self.clock, self.gr.deadline)
        with self.assertRaises(errors.DeadlineReached):
            self.gr.check_deadline()

    def test_http_logs_distinguish_call_and_response_without_credentials(self) -> None:
        self.gr.token = TOKEN

        def post(*args, **kwargs):
            self.http_logger.assert_called_once_with("提交选课 / 温旭：开始请求")
            self.advance(1.25)
            return response({"code": 1, "msg": "private-xid"})

        self.gr.session.post = Mock(side_effect=post)
        self.assertEqual(self.gr.submit(COURSES[0]), (True, "private-xid"))
        messages = [call.args[0] for call in self.http_logger.call_args_list]
        self.assertIn("收到响应 HTTP 200，耗时 1250.0ms", messages[-1])
        self.assertTrue(all(secret not in "\n".join(messages)
                            for secret in (TOKEN, COOKIE, "private-xid")))

    def test_http_exception_logs_elapsed_time_without_exception_payload(self) -> None:
        def post(*args, **kwargs):
            self.advance(0.5)
            raise requests.ConnectionError(COOKIE)

        self.gr.session.post = Mock(side_effect=post)
        with self.assertRaises(errors.TransientError):
            self.gr.submit(COURSES[0])
        messages = [call.args[0] for call in self.http_logger.call_args_list]
        self.assertIn("请求异常 ConnectionError，耗时 500.0ms", messages[-1])
        self.assertNotIn(COOKIE, "\n".join(messages))

    def test_terminal_and_file_logs_have_milliseconds(self) -> None:
        self.clock = self.clock.replace(microsecond=123456)
        with patch("builtins.open", mock_open()) as opened:
            with patch("builtins.print") as printed:
                file_logging.log("测试")
        printed.assert_called_once_with("[13:00:00.123] 测试", flush=True)
        opened().write.assert_called_once_with("[2026-09-07 13:00:00.123] 测试\n")

    def test_late_cache_message_retries_soon_not_tomorrow(self) -> None:
        self.clock = datetime(2026, 9, 7, 13, 0, 3)
        resume = runner.cache_resume_at(self.clock, 0.8)
        self.assertEqual(resume - self.clock, timedelta(seconds=0.8))

    def test_round_zero_has_no_thirty_second_gap(self) -> None:
        self.gr.submit = Mock(return_value=(False, FULL))
        self.run_local()
        self.assertGreater(self.gr.submit.call_count, 8)
        self.assertTrue(all(delay <= 0.8 for delay in self.sleeps))

    def test_deadline_stops_mid_round_before_next_submit(self) -> None:
        self.gr.deadline = self.clock + timedelta(seconds=0.5)
        self.gr.submit = Mock(return_value=(False, FULL))
        with self.assertRaises(errors.DeadlineReached):
            runner.run_serial(self.gr, deepcopy(COURSES), [], 0.8)
        self.assertEqual(self.gr.submit.call_count, 1)
        self.assertEqual(self.sleeps, [0.5])

    def test_request_timeout_is_bounded_by_deadline(self) -> None:
        self.gr.deadline = self.clock + timedelta(seconds=0.25)
        self.assertEqual(self.gr.request_timeout(), 0.25)
        self.advance(0.25)
        with self.assertRaises(errors.DeadlineReached):
            self.gr.request_timeout()

    def test_expired_config_does_not_read_cookie_or_send_requests(self) -> None:
        self.clock = datetime(2026, 9, 7, 14, 0)
        code, obtain = self.run_local()
        self.assertEqual(code, 1)
        obtain.assert_not_called()
        self.gr.session.get.assert_not_called()

    def test_unknown_second_course_resumes_same_xid_before_other_submissions(self) -> None:
        pending, done = deepcopy(COURSES), []
        self.gr.submit = Mock(side_effect=[(False, FULL), (True, "test-xid")])
        self.gr.poll_result = Mock(side_effect=[(None, "结果尚未返回"), (1, "选课成功")])
        runner.run_serial(self.gr, pending, done, 0.8)
        runner.run_serial(self.gr, pending, done, 0.8)
        self.assertEqual(self.gr.submit.call_count, 2)
        self.assertEqual([c.args for c in self.gr.poll_result.call_args_list],
                         [("test-xid",), ("test-xid",)])
        self.assertEqual(done, ["徐志宏"])
        self.assertEqual(pending, [COURSES[0]])
        self.assertEqual(self.gr.inflight, {})

    def test_inflight_round_does_not_refresh_homepage(self) -> None:
        self.cfg["courses"] = [deepcopy(COURSES[0])]
        self.gr.submit = Mock(return_value=(True, "test-xid"))
        self.gr.poll_result = Mock(side_effect=[
            (None, "结果尚未返回"), (None, "结果尚未返回"), (1, "选课成功")
        ])
        self.run_local()
        self.assertEqual(self.gr.session.get.call_count, 1)
        self.gr.submit.assert_called_once()

    def test_http_503_recovers_without_rereading_browser_cookie(self) -> None:
        self.cfg["courses"] = [deepcopy(COURSES[0])]
        self.cfg["full_max_tries"] = 3
        good = response(text=f'<input id="csrfToken" value="{TOKEN}">')
        self.gr.session.get.side_effect = [good, response(status=503), good]
        self.gr.submit = Mock(return_value=(False, FULL))
        _, obtain = self.run_local()
        obtain.assert_called_once()
        self.assertIn(1, self.sleeps)
        self.assertEqual(self.gr.submit.call_count, 3)

    def test_proxy_timeout_is_transient_not_cookie_error(self) -> None:
        self.gr.session.get.side_effect = requests.ConnectionError("proxy timed out")
        with self.assertRaises(errors.TransientError):
            self.gr.refresh_token()

    def test_retry_after_is_honored(self) -> None:
        with self.assertRaises(errors.TransientError) as error:
            self.gr.check_response(response(status=429, headers={"Retry-After": "7"}))
        self.assertEqual(error.exception.retry_after, 7)

    def test_invalid_submit_response_is_not_accepted(self) -> None:
        for body in ([], {}, {"code": 1, "msg": ""}, {"code": None, "msg": "x"}):
            with self.subTest(body=body):
                self.gr.session.post = Mock(return_value=response(body))
                with self.assertRaises(errors.TransientError):
                    self.gr.submit(COURSES[0])

    def test_polling_recovers_from_timeout_and_returns_final_result(self) -> None:
        self.gr.session.post = Mock(side_effect=[
            requests.ConnectionError("read timeout"),
            response({"msg": json.dumps({"code": 1, "msg": "选课成功"})}),
        ])
        self.assertEqual(self.gr.poll_result("test-xid"), (1, "选课成功"))
        self.assertEqual(self.gr.session.post.call_count, 2)
        self.assertIn("取得最终结果：成功", self.http_logger.call_args.args[0])

    def test_invalid_poll_body_remains_unknown(self) -> None:
        self.gr.session.post = Mock(return_value=response({"msg": "[]"}))
        code, _ = self.gr.poll_result("test-xid")
        self.assertIsNone(code)

    def test_auto_cookie_fallback_only_when_browser_read_fails(self) -> None:
        with patch("fdu_yjsxk.cookies.cookie_from_browser", return_value=(None, "暂不可读")):
            with patch("fdu_yjsxk.cookies.cookie_from_file", return_value=(COOKIE, None)) as fallback:
                self.assertEqual(cookies.obtain_cookie({"cookie_source": "auto"}), COOKIE)
                fallback.assert_called_once()

    def test_invalid_intervals_fail_before_requests(self) -> None:
        for key, value in (
            ("request_interval", 0), ("homepage_refresh_secs", -1),
            ("cookie_refresh_secs", float("nan")), ("full_max_tries", -1),
            ("poll_max", 0), ("round_interval", float("inf")),
        ):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    settings.validate_config({**self.cfg, key: value})


if __name__ == "__main__":
    unittest.main()
