import importlib.util
import pathlib
import tempfile
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
        self.assertGreaterEqual(request.call_count, 1)
        self.assertEqual(output["search"]["schools"][0]["schoolfitUrl"], "https://schoolfit.hk/schools/demo-school")
        self.assertEqual(output["recommendation"]["llmBrief"]["topRecommendations"][0]["fitLabel"], "Match")
        self.assertIn("llmBrief", output)

    def test_advisor_search_can_fallback_when_empty_and_fallback_enabled(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "很冷門問題",
            "--fallback-empty",
            "broaden",
            "--format",
            "json",
        ])
        with mock.patch.object(schoolfit_api, "request_json", side_effect=[
            {"search": {"count": 0, "schools": []}, "intent": "search"},
            {"search": {"count": 1, "schools": [{"slug": "fallback-school", "nameZh": "備用學校"}]}, "intent": "search"},
        ]) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].kwargs["params"]["routingMode"], "auto")
        self.assertEqual(request.call_args_list[1].kwargs["params"]["routingMode"], "broad")
        self.assertEqual(output["search"]["schools"][0]["slug"], "fallback-school")

    def test_advisor_search_broad_mode_relaxes_restrictive_filters(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "沙田 Band 1 英文 男女校",
            "--banding",
            "Band 1",
            "--funding-type",
            "資助",
            "--gender",
            "男",
            "--routing-mode",
            "broad",
            "--format",
            "json",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={"search": {"count": 0, "schools": []}}) as request:
            schoolfit_api.run(args)
        params = request.call_args.kwargs["params"]
        self.assertIsNone(params["banding"])
        self.assertIsNone(params["fundingType"])
        self.assertIsNone(params["gender"])
        self.assertIsNone(params["vacancyGrade"])
        self.assertEqual(int(params["pageSize"]), 48)

    def test_advisor_search_precision_mode_preserves_filters(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "沙田 Band 1 英文 男女校",
            "--banding",
            "Band 1",
            "--funding-type",
            "資助",
            "--gender",
            "男",
            "--routing-mode",
            "precision",
            "--format",
            "json",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={"search": {"count": 0, "schools": []}}) as request:
            schoolfit_api.run(args)
        params = request.call_args.kwargs["params"]
        self.assertEqual(params["banding"], "Band 1")
        self.assertEqual(params["fundingType"], "資助")
        self.assertEqual(params["gender"], "男")
        self.assertEqual(int(params["pageSize"]), 24)

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
        self.assertGreaterEqual(request.call_count, 1)
        self.assertIsNone(output["recommendation"])

    def test_advisor_search_audit_data_is_passed(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "中三 名校",
            "--audit-data",
            "--intent",
            "vacancy",
        ])
        payload = {
            "count": 1,
            "schools": [{"slug": "school-a"}],
            "search": {"count": 1, "schools": []},
            "intent": "vacancy",
            "admissionAndVacancy": {
                "vacancies": {"source": {}, "count": 0, "summary": {}, "vacancies": []},
                "audit": {"checkedAt": "2026-05-22T00:00:00.000Z", "vacancy": {}, "admissions": {}},
            },
        }
        with mock.patch.object(schoolfit_api, "request_json", return_value=payload) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_count, 1)
        self.assertTrue(request.call_args.kwargs["params"]["auditData"])
        self.assertTrue(request.call_args.kwargs["params"]["verbose"])
        self.assertEqual(output["admissionAndVacancy"]["audit"]["checkedAt"], "2026-05-22T00:00:00.000Z")

    def test_advisor_search_routes_boarding_query_as_structured_filter(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "小啱搜寄宿制学校",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={"search": {"count": 0, "schools": []}}) as request:
            schoolfit_api.run(args)
        params = request.call_args.kwargs["params"]
        self.assertTrue(params["hasBoarding"])
        self.assertIn("boarding", params["q"])

    def test_advisor_search_auto_audits_time_sensitive_queries(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "中三報名表和截止日期",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={"search": {"count": 0, "schools": []}}) as request:
            schoolfit_api.run(args)
        params = request.call_args.kwargs["params"]
        self.assertEqual(params["intent"], "admissions")
        self.assertTrue(params["auditData"])

    def test_advisor_search_auto_routes_simplified_vacancy_query(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "中三还有学额吗",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={"search": {"count": 0, "schools": []}}) as request:
            schoolfit_api.run(args)
        params = request.call_args.kwargs["params"]
        self.assertEqual(params["intent"], "vacancy")
        self.assertTrue(params["auditData"])
        self.assertTrue(params["verbose"])

    def test_advisor_search_can_disable_auto_audit(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "中三報名表和截止日期",
            "--no-audit-data",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={"search": {"count": 0, "schools": []}}) as request:
            schoolfit_api.run(args)
        self.assertFalse(request.call_args.kwargs["params"]["auditData"])

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

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(
                "os.environ",
                {"SCHOOLFIT_SKILL_CONFIG": str(pathlib.Path(tmpdir) / "skill.json")},
                clear=False,
            ):
                with mock.patch("urllib.request.urlopen", fake_urlopen):
                    data = schoolfit_api.request_json("GET", "https://schoolfit.hk", "/api/schools")
        self.assertEqual(data, {"ok": True})
        self.assertEqual(captured["headers"]["X-schoolfit-skill-code"], "schoolfit-openclaw-v1-reserved")

    def test_custom_skill_code_header_is_sent(self):
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
            return FakeResponse()

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            data = schoolfit_api.request_json(
                "GET",
                "https://schoolfit.hk",
                "/api/schools",
                skill_code="sfhk_custom_code",
                trace_id="sf_trace_1",
            )
        self.assertEqual(data, {"ok": True})
        self.assertEqual(captured["headers"]["X-schoolfit-skill-code"], "sfhk_custom_code")
        self.assertEqual(captured["headers"]["X-schoolfit-skill-trace-id"], "sf_trace_1")
        self.assertEqual(captured["headers"]["X-schoolfit-skill-version"], schoolfit_api.SKILL_VERSION_HEADER_VERSION)

    def test_skill_code_can_appear_after_subcommand(self):
        args = schoolfit_api.build_parser().parse_args([
            "search-schools",
            "--q",
            "沙田",
            "--skill-code",
            "sfhk_after_subcommand",
        ])
        # Isolate the on-disk config so running run() does not read or write the
        # real ~/.schoolfit-hk/skill.json (which made the suite order-dependent).
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(
                "os.environ",
                {"SCHOOLFIT_SKILL_CONFIG": str(pathlib.Path(tmpdir) / "skill.json")},
                clear=False,
            ):
                with mock.patch.object(schoolfit_api, "request_json", side_effect=[
                    {"activationStatus": "active"},
                    {"count": 0, "schools": []},
                ]) as request:
                    schoolfit_api.run(args)
        self.assertEqual(request.call_args_list[-1].kwargs["skill_code"], "sfhk_after_subcommand")

    def test_saved_skill_code_is_used_before_reserved_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = pathlib.Path(tmpdir) / "skill.json"
            env = {
                "SCHOOLFIT_SKILL_CONFIG": str(config_path),
                "SCHOOLFIT_SKILL_CODE": "",
                "SCHOOLFIT_SKILL_API_CODE": "",
            }
            with mock.patch.dict("os.environ", env, clear=False):
                schoolfit_api.save_skill_code("sfhk_saved_code")
                self.assertEqual(schoolfit_api.resolve_skill_code(), "sfhk_saved_code")

    def test_skill_code_precedence_prefers_cli_then_env_then_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = pathlib.Path(tmpdir) / "skill.json"
            with mock.patch.dict("os.environ", {"SCHOOLFIT_SKILL_CONFIG": str(config_path), "SCHOOLFIT_SKILL_CODE": "sfhk_env_code"}, clear=False):
                schoolfit_api.save_skill_code("sfhk_saved_code")
                self.assertEqual(schoolfit_api.resolve_skill_code("sfhk_cli_code"), "sfhk_cli_code")
                self.assertEqual(schoolfit_api.resolve_skill_code(), "sfhk_env_code")

    def test_legacy_skill_api_code_is_after_saved_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = pathlib.Path(tmpdir) / "skill.json"
            env = {
                "SCHOOLFIT_SKILL_CONFIG": str(config_path),
                "SCHOOLFIT_SKILL_CODE": "",
                "SCHOOLFIT_SKILL_API_CODE": "sfhk_legacy_code",
            }
            with mock.patch.dict("os.environ", env, clear=False):
                schoolfit_api.save_skill_code("sfhk_saved_code")
                self.assertEqual(schoolfit_api.resolve_skill_code(), "sfhk_saved_code")

    def test_reserved_fallback_when_no_code_is_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = pathlib.Path(tmpdir) / "missing.json"
            env = {
                "SCHOOLFIT_SKILL_CONFIG": str(config_path),
                "SCHOOLFIT_SKILL_CODE": "",
                "SCHOOLFIT_SKILL_API_CODE": "",
            }
            with mock.patch.dict("os.environ", env, clear=False):
                self.assertEqual(schoolfit_api.resolve_skill_code(), schoolfit_api.SCHOOLFIT_SKILL_CLIENT_CODE)

    def test_activate_prefers_pasted_code_over_reserved_fallback(self):
        args = schoolfit_api.build_parser().parse_args([
            "activate",
            "我的 SchoolFit 授權碼是 sfhk_pasted_code_123456",
        ])
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = pathlib.Path(tmpdir) / "missing.json"
            env = {
                "SCHOOLFIT_SKILL_CONFIG": str(config_path),
                "SCHOOLFIT_SKILL_CODE": "",
                "SCHOOLFIT_SKILL_API_CODE": "",
            }
            with mock.patch.dict("os.environ", env, clear=False):
                with mock.patch.object(schoolfit_api, "request_json", return_value={"activationStatus": "active"}) as request:
                    output = schoolfit_api.run(args)
        self.assertTrue(output["activated"])
        self.assertEqual(request.call_args.kwargs["skill_code"], "sfhk_pasted_code_123456")
        self.assertEqual(output["code"]["display"], "sfhk...3456")

    def test_telemetry_uses_hash_prefix_not_code_display(self):
        code = "sfhk_secret_code_123456"
        payload = schoolfit_api.telemetry_payload("search-schools", "/api/schools", code, "sf_trace", 0, 200)
        self.assertEqual(payload["skillCodeHashPrefix"], schoolfit_api.code_hash_prefix(code))
        self.assertNotIn("sfhk", payload["skillCodeHashPrefix"])
        self.assertNotIn("123456", payload["skillCodeHashPrefix"])

    def test_setup_code_saves_after_activation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = pathlib.Path(tmpdir) / "skill.json"
            with mock.patch.dict("os.environ", {"SCHOOLFIT_SKILL_CONFIG": str(config_path)}, clear=False):
                args = schoolfit_api.build_parser().parse_args(["setup-code", "--code", "sfhk_setup_code"])
                with mock.patch.object(schoolfit_api, "request_json", return_value={"activationStatus": "active"}) as request:
                    output = schoolfit_api.run(args)
                self.assertEqual(output["configPath"], str(config_path))
                self.assertEqual(schoolfit_api.load_saved_skill_code(), "sfhk_setup_code")
                self.assertEqual(request.call_args.kwargs["skill_code"], "sfhk_setup_code")

    def test_telemetry_failure_does_not_raise(self):
        with mock.patch.object(schoolfit_api, "request_json", side_effect=schoolfit_api.SchoolFitError("boom")):
            schoolfit_api.post_telemetry(
                "https://schoolfit.hk",
                {"traceId": "sf_trace", "endpoint": "/api/schools"},
                "sfhk_code",
            )

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

    def test_infer_intent_from_vacancy_synonyms(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "想看沙田区中三空位和插班位",
            "--format",
            "json",
        ])
        self.assertEqual(schoolfit_api.infer_intent(args), "vacancy")

    def test_marketplace_demo_declares_clawhub_first_distribution(self):
        args = schoolfit_api.build_parser().parse_args([
            "marketplace-demo",
            "--format",
            "json",
        ])
        output = schoolfit_api.run(args)
        policy = output["distributionPolicy"]
        self.assertEqual(policy["primaryMarketplace"], "ClawHub")
        self.assertEqual(policy["fallbackOrder"], ["ClawHub", "skills.sh", "GitHub"])
        self.assertIn("clawhub install schoolfit-hk", policy["installCommands"])

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

    def test_deep_compare_include_detail_uses_multiple_detail_requests(self):
        args = schoolfit_api.build_parser().parse_args([
            "deep-compare",
            "a,b,c",
            "--include-detail",
            "--format",
            "json",
        ])
        with mock.patch.object(schoolfit_api, "request_json", side_effect=[
            {"count": 3, "schools": []},
            {"school": {"slug": "a"}},
            {"school": {"slug": "b"}},
            {"school": {"slug": "c"}},
        ]) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_count, 4)
        self.assertEqual(len(output["details"]), 3)

    def test_deep_compare_include_detail_deduplicates_duplicate_ids(self):
        args = schoolfit_api.build_parser().parse_args([
            "deep-compare",
            "a,a,b",
            "--include-detail",
            "--format",
            "json",
        ])
        with mock.patch.object(schoolfit_api, "request_json", side_effect=[
            {"count": 3, "schools": [{"slug": "a"}, {"slug": "a"}, {"slug": "b"}]},
            {"slug": "a"},
            {"slug": "b"},
        ]) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(len(output["details"]), 3)
        self.assertEqual(output["details"][0]["slug"], "a")
        self.assertEqual(output["details"][1]["slug"], "a")
        self.assertEqual(output["details"][2]["slug"], "b")

    def test_search_brief_compact_reduces_payload(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "search-schools",
            "--q",
            "沙田",
            "--brief-level",
            "compact",
            "--format",
            "json",
        ])
        schools = [{"slug": f"school-{idx}", "nameZh": f"學校{idx}", "district": "沙田區"} for idx in range(20)]
        with mock.patch.object(schoolfit_api, "request_json", return_value={"count": 20, "schools": schools}) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(len(output["schools"]), 8)
        self.assertEqual(len(output["llmBrief"]["highlights"]), 5)
        self.assertEqual(request.call_args.kwargs["params"]["pageSize"], 24)

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
        self.assertTrue(request.call_args.kwargs["params"]["verbose"])
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

    def test_parse_parent_request_supports_simplified_chinese(self):
        output = schoolfit_api.parse_parent_request_text("九龙城 Band 1 女校 英文环境 不要直资 想稳阵 初一 用简体回答")
        self.assertEqual(output["responseLanguage"], "zh-Hans")
        self.assertEqual(output["filters"]["district"], "九龍城區")
        self.assertEqual(output["filters"]["banding"], "Band 1")
        self.assertEqual(output["filters"]["gender"], "女校")
        self.assertEqual(output["filters"]["medium"], "英文")
        self.assertFalse(output["recommendationSignals"]["acceptsDss"])
        self.assertEqual(output["recommendationSignals"]["riskPreference"], "conservative")
        self.assertEqual(output["filters"]["vacancyGrade"], "S1")

    def test_parse_parent_request_supports_english(self):
        output = schoolfit_api.parse_parent_request_text(
            "Kowloon City Band 1 girls school English medium no DSS conservative Form 1 answer in English"
        )
        self.assertEqual(output["responseLanguage"], "en")
        self.assertEqual(output["filters"]["district"], "九龍城區")
        self.assertEqual(output["filters"]["banding"], "Band 1")
        self.assertEqual(output["filters"]["gender"], "女校")
        self.assertEqual(output["filters"]["medium"], "英文")
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
        params = request.call_args_list[0].kwargs["params"]
        self.assertEqual(params["district"], "沙田區")
        self.assertEqual(params["banding"], "Band 1")
        self.assertEqual(params["medium"], "英文")
        self.assertEqual(params["gender"], "男女校")

    def test_search_schools_parses_district_and_runs_robust_fallback(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "search-schools",
            "--q",
            "九龍城",
        ])
        primary = {"count": 1, "schools": [{"slug": "partial", "nameZh": "只命中文字", "district": "九龍城區"}]}
        fallback = {
            "count": 3,
            "schools": [
                {"slug": "partial", "nameZh": "只命中文字", "district": "九龍城區"},
                {"slug": "full-a", "nameZh": "完整甲", "district": "九龍城區"},
                {"slug": "other", "nameZh": "其他區", "district": "沙田區"},
            ],
        }
        with mock.patch.object(schoolfit_api, "request_json", side_effect=[primary, fallback]) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.kwargs["params"]["pageSize"], schoolfit_api.ROBUST_SEARCH_PAGE_SIZE)
        self.assertEqual([school["slug"] for school in output["schools"]], ["partial", "full-a"])
        self.assertEqual(output["robustSearch"]["primaryMatchedCount"], 1)
        self.assertEqual(output["robustSearch"]["fallbackMatchedCount"], 2)

    def test_advisor_search_merges_robust_district_fallback(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "advisor-search",
            "--q",
            "九龍城 Band 1 女校",
            "--no-recommend",
        ])
        advisor_payload = {
            "search": {"count": 1, "schools": [{"slug": "partial", "district": "九龍城區", "banding": "Band 1A", "gender": "女校"}]},
            "intent": "search",
            "recommendation": None,
        }
        fallback = {
            "count": 2,
            "schools": [
                {"slug": "partial", "district": "九龍城區", "banding": "Band 1A", "gender": "女校"},
                {"slug": "full-a", "district": "九龍城區", "banding": "Band 1B", "gender": "女校"},
            ],
        }
        with mock.patch.object(schoolfit_api, "request_json", side_effect=[advisor_payload, fallback]):
            output = schoolfit_api.run(args)
        self.assertEqual([school["slug"] for school in output["search"]["schools"]], ["partial", "full-a"])
        self.assertEqual(output["search"]["robustSearch"]["reason"], "advisor_search_district_guard")

    def test_robust_fallback_respects_accepts_dss_false(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "advisor-search",
            "--q",
            "九龍城 Band 1 女校 英文環境 唔要直資",
            "--no-recommend",
        ])
        advisor_payload = {
            "search": {"count": 0, "schools": []},
            "intent": "search",
            "recommendation": None,
        }
        fallback = {
            "count": 2,
            "schools": [
                {"slug": "dss-school", "district": "九龍城區", "banding": "Band 1A", "gender": "女校", "mediumOfInstruction": "英文", "fundingType": "直資"},
                {"slug": "aided-school", "district": "九龍城區", "banding": "Band 1B", "gender": "女校", "mediumOfInstruction": "英文", "fundingType": "資助"},
            ],
        }
        with mock.patch.object(schoolfit_api, "request_json", side_effect=[advisor_payload, fallback]):
            output = schoolfit_api.run(args)
        self.assertEqual([school["slug"] for school in output["search"]["schools"]], ["aided-school"])

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
            "Band 1 英文 男女校",
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
            "Band 1 英文 男女校",
        ])
        empty = {"search": {"count": 0, "schools": []}}
        fallback = {"count": 1, "schools": [{"slug": "demo-a", "nameZh": "示例甲", "mediumOfInstruction": "英文", "banding": "Band 1"}]}
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
                    {"slug": "dss-school", "nameZh": "直資中學", "fundingType": "直資", "mediumOfInstruction": "英文", "banding": "Band 1A"},
                    {"slug": "aided-school", "nameZh": "資助中學", "fundingType": "資助", "mediumOfInstruction": "英文", "banding": "Band 1B"},
                ],
            }
        }
        with mock.patch.object(schoolfit_api, "request_json", return_value=payload):
            output = schoolfit_api.run(args)
        self.assertEqual(output["buckets"]["暫不建議"][0]["school"]["slug"], "dss-school")
        self.assertEqual(output["buckets"]["首選"][0]["school"]["slug"], "aided-school")
        self.assertTrue(output["preferenceWarnings"])

    def test_shortlist_builder_downgrades_chinese_medium_when_english_environment_requested(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "shortlist-builder",
            "--q",
            "九龍城 Band 1 女校 英文環境",
        ])
        payload = {
            "search": {
                "count": 2,
                "schools": [
                    {"slug": "chinese-school", "nameZh": "中文中學", "district": "九龍城區", "mediumOfInstruction": "中文", "banding": "Band 1A"},
                    {"slug": "english-school", "nameZh": "英文中學", "district": "九龍城區", "mediumOfInstruction": "英文", "banding": "Band 1B"},
                ],
            }
        }
        with mock.patch.object(schoolfit_api, "request_json", return_value=payload):
            output = schoolfit_api.run(args)
        self.assertEqual(output["buckets"]["首選"][0]["school"]["slug"], "english-school")
        self.assertEqual(output["buckets"]["暫不建議"][0]["school"]["slug"], "chinese-school")
        self.assertIn("授課語言不符合英文環境偏好", output["buckets"]["暫不建議"][0]["fitRisks"][0])

    def test_shortlist_builder_prefers_same_district_over_nearby(self):
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
                    {"slug": "nearby-school", "nameZh": "鄰近中學", "district": "九龍城區", "mediumOfInstruction": "英文", "banding": "Band 1A"},
                    {"slug": "same-district-school", "nameZh": "同區中學", "district": "沙田區", "mediumOfInstruction": "英文", "banding": "Band 1B"},
                ],
            }
        }
        with mock.patch.object(schoolfit_api, "request_json", return_value=payload):
            output = schoolfit_api.run(args)
        self.assertEqual(output["buckets"]["首選"][0]["school"]["slug"], "same-district-school")
        self.assertIn("目標地區內", output["buckets"]["首選"][0]["rankingRationale"])

    def test_more_school_aliases_resolve_to_full_names(self):
        self.assertEqual(schoolfit_api.resolve_school_query("DGS"), "Diocesan Girls' School")
        self.assertEqual(schoolfit_api.resolve_school_query("HYS"), "Heep Yunn School")
        self.assertEqual(schoolfit_api.resolve_school_query("LSC"), "La Salle College")
        self.assertEqual(schoolfit_api.resolve_school_query("WYHK"), "Wah Yan College Hong Kong")

    def test_self_check_is_public_and_ok(self):
        args = schoolfit_api.build_parser().parse_args(["self-check"])
        with mock.patch.object(schoolfit_api, "request_json") as request:
            output = schoolfit_api.run(args)
        self.assertFalse(request.called)
        self.assertTrue(output["ok"])
        self.assertEqual(output["skillVersion"], schoolfit_api.SKILL_VERSION)
        self.assertIn("version_current", {check["name"] for check in output["checks"]})

    def test_llm_brief_allows_traditional_simplified_and_english_answers(self):
        brief = schoolfit_api.standard_llm_brief("demo", "purpose", [])
        self.assertIn("Traditional Chinese", brief["recommendedTone"])
        self.assertIn("Simplified Chinese", brief["recommendedTone"])
        self.assertIn("English", brief["recommendedTone"])

    def test_parse_parent_request_returns_missing_questions_and_conversation_hint(self):
        output = schoolfit_api.parse_parent_request_text("上次條件只看女校，唔想太谷，近地鐵")
        self.assertIn("continue_previous_filters", output["conversationHints"])
        self.assertIn("校風", output["recommendationSignals"]["priorities"])
        self.assertTrue(output["missingInfoQuestions"])


if __name__ == "__main__":
    unittest.main()
