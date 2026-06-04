import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock
from io import StringIO
from contextlib import redirect_stdout


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

    def test_advisor_search_preserves_decision_briefs_parent_question_and_api_source_ledger(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "九龍城 Band 1 女校",
            "--include-decision-brief",
            "--format",
            "json",
        ])
        payload = {
            "search": {"count": 1, "schools": [{"slug": "school-a", "nameZh": "甲中學"}]},
            "intent": "search",
            "decisionBriefs": [{
                "school": {"slug": "school-a", "nameZh": "甲中學"},
                "links": {"decisionBriefApiUrl": "https://schoolfit.hk/api/skill/schools/school-a/decision-brief"},
            }],
            "parentQuestion": {
                "language": "zh-Hant",
                "detectedSignals": {"district": "九龍城區", "banding": "Band 1", "gender": "女校"},
                "answerStrategy": {
                    "primaryIntent": "recommend",
                    "rankedCriteria": ["地區與通勤可行性", "教學語言"],
                    "responseShape": "shortlist",
                    "missingInfo": ["孩子最近呈分"],
                },
                "quality": {"specificity": "high", "confidence": "high", "warnings": []},
            },
            "llmBrief": {
                "answerBlueprint": {
                    "lead": "先按九龍城 Band 1 女校收窄。",
                    "evidenceOrder": ["地區與通勤可行性", "教學語言"],
                    "missingInfo": ["孩子最近呈分"],
                    "responseShape": "shortlist",
                }
            },
            "sourceLedger": {"officialFacts": [{"name": "SchoolFit HK API"}], "assumptions": ["compact api"]},
        }
        with mock.patch.object(schoolfit_api, "request_json", return_value=payload) as request:
            output = schoolfit_api.run(args)
        advisor_params = request.call_args_list[0].kwargs["params"]
        self.assertTrue(advisor_params["includeDecisionBrief"])
        self.assertEqual(output["decisionBriefs"][0]["school"]["slug"], "school-a")
        self.assertEqual(output["parentQuestion"]["answerStrategy"]["responseShape"], "shortlist")
        self.assertEqual(output["llmBrief"]["answerBlueprint"]["lead"], "先按九龍城 Band 1 女校收窄。")
        self.assertEqual(output["sourceLedger"]["assumptions"], ["compact api"])
        self.assertIn("decision-brief", output["nextActions"][-1])

    def test_advisor_search_supports_no_dss_and_flag_has_vacancy(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "沙田 Band 1 英文校",
            "--no-dss",
            "--has-vacancy",
            "--format",
            "json",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={"search": {"count": 0, "schools": []}}) as request:
            schoolfit_api.run(args)
        params = request.call_args_list[0].kwargs["params"]
        self.assertFalse(params["acceptsDss"])
        self.assertTrue(params["hasVacancy"])

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
        self.assertIsNone(request.call_args.kwargs["params"]["verbose"])
        self.assertEqual(output["admissionAndVacancy"]["audit"]["checkedAt"], "2026-05-22T00:00:00.000Z")

    def test_advisor_search_verbose_can_request_full_payload(self):
        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "中三 名校",
            "--intent",
            "vacancy",
            "--verbose",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={"search": {"count": 0, "schools": []}}) as request:
            schoolfit_api.run(args)
        self.assertTrue(request.call_args.kwargs["params"]["verbose"])

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
        self.assertIsNone(params["verbose"])

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

    def test_school_relationships_command_calls_skill_endpoint(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "school-relationships",
            "--type",
            "through-train",
            "--q",
            "基道",
            "--matched-only",
            "--page-size",
            "5",
            "--format",
            "json",
        ])
        payload = {
            "count": 1,
            "relationships": [{
                "id": "r1",
                "type": "through_train",
                "typeLabel": "一條龍",
                "primary": {"slug": "primary-a", "nameZh": "甲小學"},
                "secondary": {"slug": "secondary-a", "nameZh": "甲中學"},
                "sourceLabel": "EDB 官方名單",
                "confidence": "high",
            }],
            "sourcePolicy": ["關係不等於保證錄取。"],
            "schoolfitUrl": "https://schoolfit.hk/school-relationships?type=through_train&q=%E5%9F%BA%E9%81%93",
        }
        with mock.patch.object(schoolfit_api, "request_json", return_value=payload) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_args.args[2], "/api/skill/school-relationships")
        params = request.call_args.kwargs["params"]
        self.assertEqual(params["type"], "through_train")
        self.assertEqual(params["q"], "基道")
        self.assertTrue(params["matchedOnly"])
        self.assertEqual(params["pageSize"], 5)
        self.assertEqual(output["relationships"][0]["type"], "through_train")
        self.assertIn("primary-secondary school relationships", output["llmBrief"]["purpose"])
        self.assertEqual(output["llmBrief"]["facts"]["relationships"][0]["id"], "r1")

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

    def test_parse_common_hk_school_questions_routes_to_expected_database(self):
        cases = [
            ("secondary", "升中自行可以報幾多間？多報會點？"),
            ("secondary", "Band 1B 沙田男仔，自行兩間應該點揀？"),
            ("secondary", "統一派位甲部乙部有咩分別？跨區搏 Band 1 得唔得？"),
            ("secondary", "九龍城 Band 1 女校 英文環境 唔要直資 想穩陣"),
            ("secondary", "中一派位 Banding 係咪官方公開？可以查我小朋友 band 嗎？"),
            ("secondary", "想叩門，111 對升中有冇用？要準備咩文件？"),
            ("secondary", "非華語學生想找英文中學，有冇支援？"),
            ("secondary", "搬屋去沙田會唔會影響升中校網？"),
            ("primary", "小一自行分配學位係咪只可以揀一間？"),
            ("primary", "小一統一派位甲部可以跨區揀幾間？乙部點填？"),
            ("primary", "41校網 vs 34校網，小學點揀？"),
            ("primary", "九龍城小學 英文環境 通勤短 資助優先"),
            ("primary", "小一叩門 111 係咩意思？"),
            ("primary", "跨境學童小一派位校網點處理？"),
            ("kindergarten", "K1 幾歲報名？細B應唔應該遲一年？"),
            ("kindergarten", "PN 同 K1 有咩分別？幾時開始申請？"),
            ("kindergarten", "荃灣幼稚園 K1 全日制 學券 學費唔太高"),
            ("kindergarten", "幼稚園收生安排要唔要註冊證？"),
            ("kindergarten", "N班面試常問咩？家長要點準備？"),
            ("international", "港島國際學校 IB A-Level 學費 申請"),
            ("international", "國際學校 debenture 債券係咪一定要買？"),
            ("international", "ESF 同私立國際學校 waiting list 點樣排？"),
            ("international", "外籍家庭剛搬香港，小朋友插班 Year 7 點申請？"),
            ("international", "國際學校英文評估和面試通常考咩？"),
            ("postsecondary", "JUPAS 本科同 HD 副學士點揀？"),
            ("postsecondary", "DSE 18分，想讀護理，有咩專上選項？"),
            ("postsecondary", "副學士升大學銜接風險大唔大？"),
            ("postsecondary", "E-APP 係咩？同 JUPAS 有咩分別？"),
            ("secondary", "La Salle College 係咪專上院校？幫我查男校"),
            ("postsecondary", "香港 College top-up degree 有咩選擇？"),
        ]
        for expected, query in cases:
            with self.subTest(query=query):
                output = schoolfit_api.parse_parent_request_text(query)
                self.assertEqual(output["filters"].get("level"), expected)

    def test_allocation_places_are_not_treated_as_vacancy_queries(self):
        output = schoolfit_api.parse_parent_request_text("小一自行分配學位係咪只可以揀一間？")
        self.assertNotIn("vacancy", output["intentHints"])
        self.assertNotIn("hasVacancy", output["filters"])

        args = schoolfit_api.build_parser().parse_args([
            "advisor-search",
            "--q",
            "小一自行分配學位係咪只可以揀一間？",
            "--format",
            "json",
        ])
        self.assertNotEqual(schoolfit_api.infer_intent(args), "vacancy")

    def test_vacancy_edge_phrases_route_without_allocation_false_positives(self):
        vacancy_cases = [
            ("secondary", "女校今年仲收唔收插班？有位先睇"),
            ("primary", "小學無位都可以交申請嗎？"),
            ("kindergarten", "N班有無位？"),
            ("kindergarten", "幼稚園冇位可否排後補"),
            ("international", "Woodland Pre-schools 有冇 PN vacancy"),
        ]
        for expected_level, query in vacancy_cases:
            with self.subTest(query=query):
                output = schoolfit_api.parse_parent_request_text(query)
                self.assertEqual(output["filters"].get("level"), expected_level)
                self.assertIn("vacancy", output["intentHints"])
                self.assertTrue(output["filters"].get("hasVacancy"))

        non_vacancy_cases = [
            ("primary", "兄姊分對小一學位有幫助嗎？"),
            ("secondary", "自行分配學位面試要準備咩？"),
            ("postsecondary", "degree places available through JUPAS 是不是學額？"),
            ("postsecondary", "副學位 vacancy 和 waiting list 是院校自己處理嗎？"),
        ]
        for expected_level, query in non_vacancy_cases:
            with self.subTest(query=query):
                output = schoolfit_api.parse_parent_request_text(query)
                self.assertEqual(output["filters"].get("level"), expected_level)
                self.assertNotIn("vacancy", output["intentHints"])
                self.assertNotIn("hasVacancy", output["filters"])

    def test_advisor_search_filters_cross_level_recommendations(self):
        payload = {
            "query": "N班面試常問咩？",
            "filters": {"level": "kindergarten"},
            "search": {"count": 0, "schools": []},
            "recommendation": {
                "summary": "demo",
                "buckets": [
                    {
                        "title": "Reach 進取選擇",
                        "schools": [
                            {
                                "school": {
                                    "slug": "st-pauls-college",
                                    "nameZh": "聖保羅書院",
                                    "level": "secondary",
                                },
                                "fitLabel": "Reach",
                                "decisionBrief": "wrong level",
                            }
                        ],
                    }
                ],
            },
        }
        output = schoolfit_api.compact_advisor_search(payload)
        self.assertIsNone(output["recommendation"])
        self.assertTrue(any("跨資料庫階段" in note for note in output["notes"]))
        self.assertEqual(output["llmBrief"]["recommendationHighlights"], [])

    def test_parse_expanded_hk_school_questions_routes_to_expected_database(self):
        cases = [
            ("secondary", "Band 2A 女仔，想九龍城英中，有冇穩陣選擇？"),
            ("secondary", "升中自行兩間應該一間進取一間穩陣嗎？"),
            ("secondary", "中一統一派位乙部點排頭五志願？"),
            ("secondary", "呈分試之後先知 Band 嗎？點樣用來選校？"),
            ("secondary", "DGS 同 HY 邊間更適合 Band 1 女仔？"),
            ("secondary", "Queen's College 係男校定男女校？"),
            ("secondary", "想查 St. Paul's College 中一申請"),
            ("secondary", "沙田官立中學有冇 S2 插班位？"),
            ("secondary", "Band 3 學生想找校風好、唔太谷的中學"),
            ("secondary", "中學直資同資助有咩分別？學費影響大嗎？"),
            ("primary", "小一自行計分 15 分有機會嗎？"),
            ("primary", "小一甲部跨區填三間會唔會影響乙部？"),
            ("primary", "12校網女仔小學，重視英文同升中"),
            ("primary", "港島區小學，唔想太谷，校風好"),
            ("primary", "小二插班九龍塘小學，有冇學位？"),
            ("primary", "私立小學和直資小學有咩分別？"),
            ("primary", "小一註冊證同自行結果有咩關係？"),
            ("primary", "34校網男仔，想資助小學"),
            ("primary", "小學升中派位同小學校網有冇關係？"),
            ("primary", "P3 transfer to English primary school in Kowloon City"),
            ("kindergarten", "細B K1 應該做大B嗎？"),
            ("kindergarten", "K1 註冊證幾時申請？"),
            ("kindergarten", "PN班要唔要面試？"),
            ("kindergarten", "N 班同幼兒班係咪同一樣？"),
            ("kindergarten", "學券幼稚園同私立幼稚園點揀？"),
            ("kindergarten", "全日制幼稚園 荃灣 有學券 學費低"),
            ("kindergarten", "K2 插班港島幼稚園有位嗎？"),
            ("kindergarten", "幼稚園非華語支援 NCS 有冇資料？"),
            ("kindergarten", "K3 想轉校，會唔會影響小一？"),
            ("kindergarten", "pre nursery interview questions in Hong Kong"),
            ("international", "ESF Year 1 申請 waiting list 要等幾耐？"),
            ("international", "Year 7 插班 IB school 港島"),
            ("international", "A-Level 國際學校 新界 學費上限 20萬"),
            ("international", "debenture 同 capital levy 有咩分別？"),
            ("international", "外籍 passport 對國際學校入學有優先嗎？"),
            ("international", "Which Hong Kong international schools offer boarding?"),
            ("international", "AP curriculum international school in Hong Kong"),
            ("international", "想由本地小學轉國際學校 Year 6"),
            ("international", "國際學校 SEN support and EAL support"),
            ("international", "ISF Academy 係國際學校嗎？"),
            ("postsecondary", "DSE 20分 JUPAS nursing 有咩選擇？"),
            ("postsecondary", "HD 同 Associate Degree 升大學邊個好？"),
            ("postsecondary", "E-APP 報名截止日期係幾時？"),
            ("postsecondary", "自資學士同 UGC 學位有咩分別？"),
            ("postsecondary", "IVE Higher Diploma 銜接 top-up degree"),
            ("postsecondary", "HKCC 副學士升 HKU 機會"),
            ("postsecondary", "SSSDP nursing physiotherapy 適合 DSE 幾分？"),
            ("postsecondary", "Non-JUPAS applicant with overseas qualification"),
            ("postsecondary", "VTC higher diploma design programmes"),
            ("postsecondary", "想讀幼兒教育高級文憑，有咩院校？"),
        ]
        for expected, query in cases:
            with self.subTest(query=query):
                output = schoolfit_api.parse_parent_request_text(query)
                self.assertEqual(output["filters"].get("level"), expected)

    def test_parse_high_ambiguity_school_questions_routes_to_expected_database(self):
        cases = [
            ("secondary", "自行分配兩個 choice 次序會唔會畀學校知？"),
            ("secondary", "直屬小學升直屬中學是否一定收？"),
            ("secondary", "聯繫中學位係咩？小六點部署？"),
            ("secondary", "S4 轉校想讀英文班"),
            ("secondary", "banding reference for St Mark School"),
            ("primary", "自行分配 sibling 兄姊分點計？"),
            ("primary", "統一派位甲一乙一都填同一間有用嗎？"),
            ("primary", "primary school with IB PYP in Hong Kong"),
            ("kindergarten", "K1 waiting list 點跟進？"),
            ("international", "Harrow Hong Kong boarding fees"),
            ("international", "Kellett School capital levy"),
            ("international", "AP school Hong Kong Grade 10 transfer"),
            ("international", "IB school with through-train primary secondary"),
            ("postsecondary", "overseas qualification apply HK university"),
            ("postsecondary", "副學位學費資助 NMTSS"),
        ]
        for expected, query in cases:
            with self.subTest(query=query):
                output = schoolfit_api.parse_parent_request_text(query)
                self.assertEqual(output["filters"].get("level"), expected)

    def test_linked_secondary_school_place_is_not_treated_as_vacancy(self):
        output = schoolfit_api.parse_parent_request_text("聯繫中學位係咩？小六點部署？")
        self.assertEqual(output["filters"].get("level"), "secondary")
        self.assertNotIn("vacancy", output["intentHints"])
        self.assertNotIn("hasVacancy", output["filters"])

    def test_parse_additional_realistic_school_questions_routes_to_expected_database(self):
        cases = [
            ("secondary", "自行分配面試會問時事嗎？"),
            ("secondary", "中學學位分配辦法和小一派位有咩不同？"),
            ("secondary", "小六呈分後升中選校策略"),
            ("primary", "私小 waiting list 點跟進？"),
            ("primary", "小學 IB PYP 和本地課程分別"),
            ("primary", "本地小學轉國際學校前應否先讀私小？"),
            ("international", "GSIS German stream application"),
            ("international", "HKIS American curriculum application"),
            ("international", "Malvern College Hong Kong boarding?"),
            ("international", "Nord Anglia Hong Kong fees"),
            ("international", "international kindergarten to international primary"),
            ("postsecondary", "CityU SCOPE top up"),
            ("postsecondary", "HD internship and articulation"),
        ]
        for expected, query in cases:
            with self.subTest(query=query):
                output = schoolfit_api.parse_parent_request_text(query)
                self.assertEqual(output["filters"].get("level"), expected)

    def test_parse_named_school_and_program_questions_routes_to_expected_database(self):
        cases = [
            ("secondary", "Heep Yunn 自行面試點準備？"),
            ("secondary", "小六操行 B 會影響中學自行嗎？"),
            ("secondary", "DSE 成績不是很好想轉直資中學"),
            ("primary", "Maryknoll Convent School Primary Section 小一"),
            ("primary", "津小有沒有學費？"),
            ("primary", "小六呈分前轉小學風險"),
            ("kindergarten", "幼兒班 N1 兩歲半可以嗎？"),
            ("international", "Discovery College fees"),
            ("international", "American School Hong Kong AP curriculum"),
            ("international", "Malvern College Pre-School Hong Kong"),
            ("international", "Shrewsbury Year 3 application"),
            ("postsecondary", "HSUHK undergraduate admission score"),
        ]
        for expected, query in cases:
            with self.subTest(query=query):
                output = schoolfit_api.parse_parent_request_text(query)
                self.assertEqual(output["filters"].get("level"), expected)

    def test_parse_section_and_institution_name_questions_routes_to_expected_database(self):
        cases = [
            ("secondary", "嘉諾撒聖瑪利書院是否女校？"),
            ("primary", "Diocesan Boys School Primary Division"),
            ("primary", "Diocesan Girls Junior School application"),
            ("kindergarten", "Think International Kindergarten"),
            ("international", "Wycombe Abbey School Hong Kong"),
            ("international", "Mount Kelly School Hong Kong"),
            ("postsecondary", "CityU data science undergraduate"),
            ("postsecondary", "Chu Hai College undergraduate"),
            ("postsecondary", "Savannah College Hong Kong admission"),
            ("postsecondary", "Elder Academy diploma?"),
        ]
        for expected, query in cases:
            with self.subTest(query=query):
                output = schoolfit_api.parse_parent_request_text(query)
                self.assertEqual(output["filters"].get("level"), expected)

    def test_parse_long_tail_school_and_institution_names_routes_to_expected_database(self):
        cases = [
            ("secondary", "St Francis Xavier College banding"),
            ("secondary", "中六轉校重讀 DSE 可行嗎？"),
            ("secondary", "F1 admission for returnee student"),
            ("kindergarten", "K3 primary school placement support"),
            ("kindergarten", "kindergarten to DSS primary preparation"),
            ("international", "DBIS school fees Hong Kong"),
            ("international", "Invictus School Hong Kong fees"),
            ("international", "Woodland Pre-Schools international kindergarten"),
            ("international", "Delia School of Canada admission"),
            ("postsecondary", "HKU SPACE Po Leung Kuk Stanley Ho Community College"),
            ("postsecondary", "PolyU HKCC year 2 admission"),
            ("postsecondary", "HKCC articulation to PolyU"),
            ("postsecondary", "CUHK School of Continuing and Professional Studies"),
            ("postsecondary", "HKU SPACE Community College nursing"),
            ("postsecondary", "VTC Youth College diploma"),
            ("postsecondary", "International Culinary Institute Hong Kong"),
            ("postsecondary", "Caritas Institute of Higher Education nursing"),
            ("postsecondary", "OUHK LiPACE programme"),
        ]
        for expected, query in cases:
            with self.subTest(query=query):
                output = schoolfit_api.parse_parent_request_text(query)
                self.assertEqual(output["filters"].get("level"), expected)

    def test_parse_common_parent_question_defaults_routes_to_expected_database(self):
        cases = [
            ("secondary", "學校 Banding 是官方資料嗎？"),
            ("secondary", "Banding 係咪官方公開？"),
            ("secondary", "升中統一派位乙部頭五志願點排？"),
            ("primary", "35校網 vs 62校網點揀？"),
            ("secondary", "自行面試通常問咩問題？"),
            ("international", "外籍 passport 有入學優先嗎？"),
            ("postsecondary", "海外學歷申請香港大學"),
        ]
        for expected, query in cases:
            with self.subTest(query=query):
                output = schoolfit_api.parse_parent_request_text(query)
                self.assertEqual(output["filters"].get("level"), expected)

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

    def test_school_levels_is_public_and_lists_all_databases(self):
        args = schoolfit_api.build_parser().parse_args([
            "school-levels",
            "--format",
            "json",
        ])
        output = schoolfit_api.run(args)
        levels = output["coverage"]["levels"]
        self.assertEqual([item["level"] for item in levels], list(schoolfit_api.SCHOOL_LEVELS))
        self.assertEqual(output["coverage"]["total"], sum(schoolfit_api.SCHOOL_LEVEL_COUNTS.values()))
        self.assertEqual(output["activationStatus"], "not_required")

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
        self.assertIsNone(request.call_args.kwargs["params"]["verbose"])
        self.assertEqual(output["school"]["slug"], "sha-tin-methodist-college")
        self.assertEqual(output["school"]["schoolfitUrl"], "https://schoolfit.hk/schools/sha-tin-methodist-college")
        self.assertIn("sourceLedger", output)

    def test_decision_brief_uses_skill_decision_endpoint_and_can_be_verbose(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "decision-brief",
            "sha-tin-methodist-college",
            "--verbose",
            "--format",
            "json",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={
            "sourceLedger": {"officialFacts": [], "assumptions": ["api"]},
            "school": {"slug": "sha-tin-methodist-college", "nameZh": "沙田中學"},
            "vacancy": {"summary": {"dataMonth": "2026-05"}, "count": 0},
            "admission": {"summary": {"nextDeadline": "2026-06-01"}, "count": 0},
        }) as request:
            output = schoolfit_api.run(args)
        self.assertEqual(request.call_args.args[2], "/api/skill/schools/sha-tin-methodist-college/decision-brief")
        self.assertTrue(request.call_args.kwargs["params"]["verbose"])
        self.assertEqual(output["school"]["slug"], "sha-tin-methodist-college")
        self.assertEqual(output["sourceLedger"]["assumptions"], ["api"])

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
        self.assertEqual(output["activationUrlPolicy"]["canonicalUrl"], "https://schoolfit.hk/skill-code")

    def test_activation_url_is_canonicalized_when_suffix_is_added(self):
        decorated_urls = [
            "https://schoolfit.hk/skill-code?utm_source=agent",
            "https://schoolfit.hk/skill-code#openclaw",
            "https://schoolfit.hk/skill-code/sfhk_extra",
            "https://schoolfit.hk/skill-code?next=/missing#x",
        ]
        for url in decorated_urls:
            with self.subTest(url=url):
                self.assertEqual(
                    schoolfit_api.canonical_activation_url(url),
                    "https://schoolfit.hk/skill-code",
                )

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
        self.assertEqual(output["activationUrlPolicy"]["canonicalUrl"], "https://schoolfit.hk/skill-code")
        self.assertIn("/skill-code", output["steps"][0]["note"])
        self.assertIn("friendlyOpening", output)
        self.assertEqual(output["interactionStyle"]["tone"], "warm, concise, parent-friendly, and evidence-conscious")

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

    def test_parse_parent_request_detects_school_levels(self):
        cases = [
            ("九龍城 小學 英文環境", "primary"),
            ("荃灣幼稚園 K1", "kindergarten"),
            ("港島 國際學校 IB A-Level", "international"),
            ("JUPAS HD 副學士 銜接 專上", "postsecondary"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                output = schoolfit_api.parse_parent_request_text(text)
                self.assertEqual(output["filters"]["level"], expected)
                self.assertEqual(output["recommendationSignals"]["level"], expected)

    def test_parse_parent_request_detects_region_without_fake_district(self):
        output = schoolfit_api.parse_parent_request_text("港島 國際學校 IB A-Level")
        self.assertEqual(output["filters"]["level"], "international")
        self.assertEqual(output["filters"]["region"], "港島")
        self.assertNotIn("district", output["filters"])
        self.assertNotIn("主要想看哪個區", "\n".join(output["missingInfoQuestions"]))
        self.assertIn("friendlySummary", output)
        self.assertIn("friendlyFollowUp", output)
        self.assertIn("國際學校資料庫", "\n".join(output["friendlySummary"]))

    def test_parse_parent_request_markdown_is_parent_friendly(self):
        output = schoolfit_api.parse_parent_request_text("港島 國際學校 IB A-Level")
        buffer = StringIO()
        with redirect_stdout(buffer):
            schoolfit_api.print_markdown("parse-parent-request", output)
        rendered = buffer.getvalue()
        self.assertIn("我先幫你整理到這裡", rendered)
        self.assertIn("資料庫: 國際學校資料庫", rendered)
        self.assertIn("不用提供姓名", rendered)
        self.assertNotIn("zh-Hant", rendered)
        self.assertNotIn("資料庫名稱", rendered)

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

    def test_advisor_search_applies_parsed_primary_level(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "advisor-search",
            "--q",
            "九龍城 小學 英文環境",
            "--no-recommend",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={"search": {"count": 0, "schools": []}}) as request:
            schoolfit_api.run(args)
        params = request.call_args_list[0].kwargs["params"]
        self.assertEqual(params["level"], "primary")
        self.assertEqual(params["district"], "九龍城區")
        self.assertEqual(params["medium"], "英文")

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
        self.assertIn("decision-brief", output["nextActions"][0])

    def test_vacancies_accepts_flag_style_has_vacancy(self):
        args = schoolfit_api.build_parser().parse_args([
            "--skill-code",
            "schoolfit-openclaw-v1-reserved",
            "vacancies",
            "--grade",
            "S1",
            "--has-vacancy",
        ])
        with mock.patch.object(schoolfit_api, "request_json", return_value={"count": 0, "vacancies": []}) as request:
            schoolfit_api.run(args)
        self.assertTrue(request.call_args.kwargs["params"]["hasVacancy"])

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
