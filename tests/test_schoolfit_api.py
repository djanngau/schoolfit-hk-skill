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
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
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
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
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
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
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
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
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
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
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
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "application-plan",
            "--school-slugs",
            "sha-tin-methodist-college,ying-wa-girls-school",
            "--deadline-window-days",
            "30",
            "--format",
            "json",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={
            "plan": {
                "deadlineWindowDays": 30,
                "timeline": ["T-30：核對提交清單。"],
            },
            "schools": [
                {
                    "slug": "sha-tin-methodist-college",
                    "nameZh": "沙田中學",
                    "vacancy": {"summary": {"dataMonth": "2026-05"}},
                    "admission": {"summary": {"nextDeadline": "2026-06-01"}},
                    "schoolfitUrl": "https://schoolfit.hk/schools/sha-tin-methodist-college",
                }
            ],
            "checklist": ["確認成績單與申請文件", "核對學校官網截止日"],
            "reminders": [{"school": "沙田中學", "message": "確認面試文具", "deadline": "2026-06-01"}],
        }) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[0], "GET")
        self.assertEqual(request.call_args.args[2], "/api/skill/application-plan")
        self.assertEqual(
            request.call_args.kwargs["params"]["schoolSlugs"],
            "sha-tin-methodist-college,ying-wa-girls-school"
        )
        self.assertIn("schools", output)
        self.assertIn("checklist", output)
        self.assertIn("reminders", output)
        self.assertEqual(output["plan"]["timeline"][0], "T-30：核對提交清單。")

    def test_missing_skill_code_returns_activation_guide(self):
        args = schoolfit_api.build_parser().parse_args([
            "search-schools",
            "--q",
            "沙田",
        ])
        with mock.patch.object(schoolfit_api, "request_json") as request:
            output = schoolfit_api.run(args)
        self.assertFalse(request.called)
        self.assertTrue(output["needsActivation"])
        self.assertEqual(output["activationUrl"], "https://schoolfit.hk/skill-code")

    def test_quick_start_does_not_call_api(self):
        args = schoolfit_api.build_parser().parse_args([
            "quick-start",
            "--format",
            "json",
        ])
        with mock.patch.object(schoolfit_api, "request_json") as request:
            output = schoolfit_api.run(args)
        self.assertFalse(request.called)
        self.assertEqual(output["activationStatus"], "not_required")
        self.assertIn("skill-code", output["steps"][0]["text"])

    def test_parse_parent_request_extracts_local_filters(self):
        args = schoolfit_api.build_parser().parse_args([
            "parse-parent-request",
            "--q",
            "九龍城 Band 1 女校 英文環境 唔要直資 想穩陣 中一",
        ])
        output = schoolfit_api.run(args)
        self.assertEqual(output["filters"]["district"], "九龍城區")
        self.assertEqual(output["filters"]["banding"], "Band 1")
        self.assertEqual(output["filters"]["gender"], "女校")
        self.assertEqual(output["filters"]["medium"], "英文")
        self.assertNotIn("fundingType", output["filters"])
        self.assertFalse(output["recommendationSignals"]["acceptsDss"])
        self.assertEqual(output["recommendationSignals"]["riskPreference"], "conservative")
        self.assertEqual(output["filters"]["vacancyGrade"], "S1")

    def test_advisor_search_applies_parsed_filters(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "advisor-search",
            "--q",
            "沙田 Band 1 英文 男女校 想穩陣",
            "--no-recommend",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={"count": 0, "schools": []}) as request:
            schoolfit_api.run(args)
        params = request.call_args.kwargs["params"]
        self.assertEqual(params["district"], "沙田區")
        self.assertEqual(params["banding"], "Band 1")
        self.assertEqual(params["medium"], "英文")
        self.assertEqual(params["gender"], "男女校")

    def test_privacy_warning_blocks_obvious_pii(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "advisor-search",
            "--q",
            "沙田 Band 1，電話 91234567",
        ])
        with mock.patch.object(schoolfit_api, "request_json") as request:
            output = schoolfit_api.run(args)
        self.assertFalse(request.called)
        self.assertTrue(output["privacyWarning"])
        self.assertEqual(output["detected"][0]["type"], "phone")

    def test_llm_brief_has_facts_only_contract(self):
        output = schoolfit_api.compact_output("search-schools", {"count": 0, "schools": []})
        self.assertTrue(output["llmBrief"]["factsOnly"])
        self.assertIn("doNotInvent", output["llmBrief"])

    def test_resolve_school_searches_by_name(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "resolve-school",
            "--name",
            "SPCC",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={
            "count": 1,
            "schools": [{"slug": "st-pauls-co-educational-college", "nameEn": "St. Paul's Co-educational College"}],
        }) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_args.args[2], "/api/schools")
        self.assertEqual(request.call_args.kwargs["params"]["q"], "St. Paul's Co-educational College")
        self.assertEqual(output["candidates"][0]["slug"], "st-pauls-co-educational-college")

    def test_shortlist_builder_buckets_results(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "shortlist-builder",
            "--q",
            "沙田 Band 1 英文 男女校",
        ])
        payload = {
            "search": {
                "count": 2,
                "schools": [
                    {
                        "slug": "demo-a",
                        "nameZh": "示例甲",
                        "district": "沙田區",
                        "mediumOfInstruction": "英文",
                        "banding": "Band 1A",
                    },
                    {
                        "slug": "demo-b",
                        "nameZh": "示例乙",
                        "district": "沙田區",
                        "mediumOfInstruction": "英文",
                        "banding": "Band 2",
                    },
                ],
            }
        }
        with mock.patch.object(schoolfit_api, "request_json", return_value=payload) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_args.args[2], "/api/skill/search-advisor")
        self.assertEqual(output["buckets"]["首選"][0]["school"]["slug"], "demo-a")
        self.assertIn("rankingRationale", output["buckets"]["首選"][0])

    def test_shortlist_builder_uses_fallback_when_advisor_search_empty(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "shortlist-builder",
            "--q",
            "沙田 Band 1 英文 男女校",
        ])
        empty = {"search": {"count": 0, "schools": []}}
        fallback = {"count": 1, "schools": [{"slug": "demo-a", "nameZh": "示例甲", "banding": "Band 1"}]}
        with mock.patch.object(schoolfit_api, "request_json", side_effect=[empty, fallback]) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.args[2], "/api/schools")
        self.assertIsNone(request.call_args.kwargs["params"]["q"])
        self.assertEqual(output["buckets"]["首選"][0]["school"]["slug"], "demo-a")

    def test_shortlist_builder_respects_reject_dss_preference(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "shortlist-builder",
            "--q",
            "九龍城 Band 1 女校 英文環境 唔要直資",
        ])
        payload = {
            "search": {
                "count": 2,
                "schools": [
                    {"slug": "dss-school", "nameZh": "直資中學", "fundingType": "直資", "banding": "Band 1A"},
                    {"slug": "aided-school", "nameZh": "資助中學", "fundingType": "資助", "banding": "Band 1B"},
                ],
            }
        }
        with mock.patch.object(schoolfit_api, "request_json", return_value=payload):
            output = schoolfit_api.run(args)
        self.assertEqual(output["buckets"]["暫不建議"][0]["school"]["slug"], "dss-school")
        self.assertEqual(output["buckets"]["首選"][0]["school"]["slug"], "aided-school")
        self.assertTrue(output["preferenceWarnings"])

    def test_self_check_is_public_and_ok(self):
        args = schoolfit_api.build_parser().parse_args(["self-check"])
        with mock.patch.object(schoolfit_api, "request_json") as request:
            output = schoolfit_api.run(args)
        self.assertFalse(request.called)
        self.assertTrue(output["ok"])
        self.assertEqual(output["skillVersion"], schoolfit_api.SKILL_VERSION)

    def test_parse_parent_request_returns_missing_questions_and_conversation_hint(self):
        output = schoolfit_api.parse_parent_request_text("上次條件只看女校，唔想太谷，近地鐵")
        self.assertIn("continue_previous_filters", output["conversationHints"])
        self.assertIn("校風", output["recommendationSignals"]["priorities"])
        self.assertTrue(output["missingInfoQuestions"])


if __name__ == "__main__":
    unittest.main()
