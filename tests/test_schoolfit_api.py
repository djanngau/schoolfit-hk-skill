import importlib.util
import pathlib
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "skills" / "schoolfit-hk" / "scripts" / "schoolfit_api.py"
spec = importlib.util.spec_from_file_location("schoolfit_api", SCRIPT)
schoolfit_api = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(schoolfit_api)


class SchoolFitApiTests(unittest.TestCase):
    def test_rejects_non_schoolfit_host(self):
        with self.assertRaises(schoolfit_api.SchoolFitError):
            schoolfit_api.validate_base_url("https://example.com")

    def test_rejects_plain_http(self):
        with self.assertRaises(schoolfit_api.SchoolFitError):
            schoolfit_api.validate_base_url("http://schoolfit.hk")

    def test_make_url_only_allows_api_paths(self):
        with self.assertRaises(schoolfit_api.SchoolFitError):
            schoolfit_api.make_url("https://schoolfit.hk", "/admin")

    def test_compare_limits_ids_to_four(self):
        args = schoolfit_api.build_parser().parse_args([
            "compare",
            "a,b,c,d,e",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={"count": 4, "schools": []}) as request:
            schoolfit_api.run(args)
        _, _, path = request.call_args.args
        self.assertEqual(path, "/api/compare")
        self.assertEqual(request.call_args.kwargs["params"]["ids"], ["a", "b", "c", "d"])

    def test_format_can_appear_after_subcommand(self):
        args = schoolfit_api.build_parser().parse_args([
            "search-schools",
            "--q",
            "沙田",
            "--format",
            "markdown",
        ])
        self.assertEqual(args.format, "markdown")

    def test_advisor_search_calls_search_and_recommend_when_profile_is_present(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "沙田英文中學",
            "--district",
            "沙田區",
            "--banding",
            "Band 1",
            "--page-size",
            "3",
        ])
        search_payload = {
            "search": {
                "count": 1,
                "schools": [{
                    "id": "chsc-1",
                    "slug": "demo-school",
                    "nameZh": "示例中學",
                    "nameEn": "Demo College",
                    "district": "沙田區",
                    "fundingType": "資助",
                    "gender": "男女校",
                    "mediumOfInstruction": "英文",
                    "banding": "Band 1B",
                    "vacancySummary": {"dataMonth": "2026-05"},
                    "admissionNoticeSummary": {"noticeCount": 0},
                }],
            }
        }
        recommend_payload = {
            "summary": "demo",
            "buckets": [{
                "title": "Match 主力選擇",
                "schools": [{
                    "school": {"slug": "demo-school", "nameZh": "示例中學"},
                    "fitLabel": "Match",
                    "decisionBrief": "可作主力選擇。",
                }],
            }],
        }
        with mock.patch.object(schoolfit_api, "request_json", return_value={
            **search_payload,
            "intent": "recommend",
            "recommendation": recommend_payload,
            "compare": None,
            "schoolDetail": None,
            "admissionAndVacancy": None,
        }) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(output["search"]["schools"][0]["schoolfitUrl"], "https://schoolfit.hk/schools/demo-school")
        self.assertEqual(output["recommendation"]["llmBrief"]["topRecommendations"][0]["fitLabel"], "Match")
        self.assertIn("llmBrief", output)

    def test_advisor_search_can_skip_recommendation(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "沙田",
            "--no-recommend",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={"count": 0, "schools": []}) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_count, 1)
        self.assertIsNone(output["recommendation"])

    def test_reserved_client_code_header_is_sent(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return b'{"ok": true}'

        captured = {}

        def fake_urlopen(req, timeout):
            captured["headers"] = dict(req.header_items())
            captured["timeout"] = timeout
            return FakeResponse()

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            data = schoolfit_api.request_json("GET", "https://schoolfit.hk", "/api/schools")
        self.assertEqual(data, {"ok": True})
        self.assertEqual(captured["headers"]["X-schoolfit-skill-code"], "schoolfit-openclaw-v1-reserved")

    def test_infer_intent_from_prompt(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "幫我比較 沙田 Band 1 男女校",
            "--district",
            "沙田區",
            "--no-recommend",
            "--format",
            "json",
        ])
        self.assertEqual(schoolfit_api.infer_intent(args), "compare")

    def test_deep_compare_limits_ids_to_four(self):
        args = schoolfit_api.build_parser().parse_args([
            "deep-compare",
            "a,b,c,d,e",
            "--format",
            "json",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={"count": 4, "schools": []}) as request:
            schoolfit_api.run(args)
        _, _, path = request.call_args.args
        self.assertEqual(path, "/api/compare")
        self.assertEqual(request.call_args.kwargs["params"]["ids"], ["a", "b", "c", "d"])

    def test_school_report_builds_checklist_and_ledger(self):
        args = schoolfit_api.build_parser().parse_args([
            "school-report",
            "sha-tin-methodist-college",
            "--format",
            "json",
        ])
        school_payload = {
            "school": {
                "id": "school-1",
                "slug": "sha-tin-methodist-college",
                "nameZh": "沙田中學",
                "banding": "Band 1",
            },
            "vacancy": {
                "source": {"sourceName": "SchoolFit"},
                "count": 1,
                "vacancies": [],
                "summary": {"dataMonth": "2026-05"},
                "caveat": "x",
            },
            "admission": {
                "source": {"sourceName": "SchoolFit"},
                "count": 0,
                "notices": [],
                "summary": {"nextDeadline": "2026-06-01"},
                "caveat": "y",
            },
        }
        with mock.patch.object(schoolfit_api, "request_json", side_effect=[
            school_payload,
        ]) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(output["school"]["slug"], "sha-tin-methodist-college")
        self.assertEqual(output["school"]["schoolfitUrl"], "https://schoolfit.hk/schools/sha-tin-methodist-college")
        self.assertIn("sourceLedger", output)

    def test_application_plan_contains_timeline(self):
        args = schoolfit_api.build_parser().parse_args([
            "application-plan",
            "--school-slugs",
            "sha-tin-methodist-college,ying-wa-girls-school",
            "--deadline-window-days",
            "30",
            "--format",
            "json",
        ])
        with mock.patch.object(schoolfit_api, "request_json", side_effect=[
            {
                "id": "s1",
                "slug": "sha-tin-methodist-college",
                "nameZh": "沙田中學",
            },
            {"count": 0, "vacancies": []},
            {"count": 0, "notices": []},
            {
                "id": "s2",
                "slug": "ying-wa-girls-school",
                "nameZh": "英華女書院",
            },
            {"count": 0, "vacancies": []},
            {"count": 0, "notices": []},
        ]) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_count, 6)
        self.assertIn("items", output)
        self.assertTrue(any("申請" in item for item in output["items"]))
        self.assertEqual(output["plan"]["timeline"][0], "T-45：完成每校初篩（申請條件、校風、通勤、Band 參考）。")


if __name__ == "__main__":
    unittest.main()
