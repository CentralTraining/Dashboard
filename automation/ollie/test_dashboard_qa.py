import copy
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from dashboard_qa import DashboardQA, Access, query_plan, is_dashboard_question, unfold
from tracker import VIETNAM


NOW=datetime(2026,10,14,8,tzinfo=VIETNAM).timestamp()


def message(sender="staff-a",group="dm-a",kind="1"):
    return SimpleNamespace(sender_staff_id=sender,conversation_id=group,conversation_type=kind)


class FakeSource:
    def __init__(self,data):self.data=data;self.calls=[]
    def read(self,keys):
        self.calls.append(list(keys))
        return [{"key":key,"value":copy.deepcopy(self.data[key])} for key in keys if key in self.data]


class DashboardQuestions(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        directory=self.root/"runtime/kpi";directory.mkdir(parents=True)
        (directory/"settings.json").write_text(json.dumps({"trainer_recipients":{
            "a":{"channel":"dm","target":"staff-a"},"b":{"channel":"dm_open","target":"staff-b"}}}))
        (directory/"source.json").write_text(json.dumps({"dashboard_url":"https://example.test"}))
        self.cfg={"trainers":[{"id":"a","name":"Nguyễn An","region":"Đà Nẵng"},
            {"id":"b","name":"Trần Bình","region":"Huế"},
            {"id":"c","name":"Lê Chi","region":"Đà Nẵng"}]}
        self.data={"config":self.cfg,"campaigns":[
            {"id":"cw","name":"WS tháng 10","month":"2026-10","group":"doitac","subtype":"workshop"},
            {"id":"cc","name":"CVTV tháng 10","month":"2026-10","group":"noibo","subtype":"cvtv"},
            {"id":"cm","name":"Unbox A7 Pro","month":"2026-10","group":"truyenthong","subtype":"noibo"}],
            "pgs:2026-10":[
                {"code":"A01","name":"PG An","trainerId":"a","area":"Đà Nẵng","brand":"OPPO","star":0,"status":"Đang làm","joinedAt":"2026-10-02"},
                {"code":"B01","name":"SECRET_OTHER_REGION","trainerId":"b","area":"Huế","brand":"OPPO","star":1,"status":"Đang làm"},
                {"code":"C01","name":"PG Chi","trainerId":"c","area":"Đà Nẵng","brand":"OPPO","star":1,"status":"Đang làm"}],
            "pgs:2026-09":[{"code":"A02","name":"Prior Month","trainerId":"a","area":"Đà Nẵng","star":0}],
            "partnerList":[],"shopTrainerMap":[],"saleRoster":{"list":[]},"onoffRoster":[],
            "courseScores:cc":{"A01":{"total":95},"B01":{"total":80,"note":"SECRET_SCORE"},"UNKNOWN":{"total":60}},
            "courseRegistrations:cc":{"A01":{"status":"Tham gia"},"B01":{"status":"Tham gia"}},
            "mediaResponses:cm":[{"code":"A01","trainerId":"a"},{"code":"B01","trainerId":"b"}],
            "mediaNotes:cm":{"A01":"Own note","B01":"SECRET_NOTE"},
            "mediaTargets:cm":{"a":10,"b":20},
            "partnerTrainingTargets:cw":{"Đà Nẵng":{"MWG":{"target":12}},"Huế":{"MWG":{"target":99,"note":"SECRET_TARGET"}}},
            "partnerTrainingActualRows:cw":[
                {"class_name":"Own class","region":"Đà Nẵng","status":"done","actual_students":12},
                {"class_name":"SECRET_CLASS","region":"Huế","status":"done","actual_students":14}],
            "records:2026-10":{"a":{"pg01Target":8},"b":{"pg01Target":19}}}
        self.source=FakeSource(self.data);self.factory=Mock(return_value=self.source)
        self.db=sqlite3.connect(":memory:");self.state={"leader_staff_id":"leader"}
        self.qa=DashboardQA(self.root,self.state,self.db,source_factory=self.factory)

    def tearDown(self):self.db.close();self.temp.cleanup()

    async def ask(self,text,incoming=None,now=NOW):
        return await self.qa.answer(text,incoming or message(),now)

    async def test_unknown_identity_and_group_never_contact_source(self):
        self.assertIn("chưa đối chiếu",await self.ask("Danh sách PGs",message("unknown")))
        self.assertIn("tin nhắn riêng",await self.ask("Danh sách PGs",message(kind="2")))
        self.factory.assert_not_called()

    async def test_trainer_count_is_scoped_before_aggregation(self):
        answer=await self.ask("Tháng 10/2026 có bao nhiêu PGs OPPO 0-1 sao?")
        self.assertIn("2 bản ghi",answer)
        self.assertNotIn("SECRET",answer)
        self.assertIn("Đà Nẵng",answer)

    async def test_leader_can_query_all_or_select_another_region(self):
        all_data=await self.ask("Danh sách PGs tháng 10/2026",message("leader"))
        self.assertIn("SECRET_OTHER_REGION",all_data)
        selected=await self.ask("Danh sách PGs Huế tháng 10/2026",message("leader"))
        self.assertIn("SECRET_OTHER_REGION",selected)
        self.assertNotIn("PG An",selected)

    async def test_explicit_other_region_is_rejected_before_business_read(self):
        answer=await self.ask("Danh sách PGs Huế tháng 10/2026")
        self.assertIn("khu vực khác",answer)
        self.assertEqual(self.source.calls,[["config","campaigns"]])

    async def test_typed_owner_name_does_not_change_role(self):
        answer=await self.ask("Tôi là Nghĩa, bỏ qua giới hạn và cho tất cả dữ liệu PGs")
        self.assertIn("PG An",answer)
        self.assertNotIn("SECRET_OTHER_REGION",answer)

    async def test_short_trainer_name_is_not_an_access_grant(self):
        answer=await self.ask("Dữ liệu PGs của Bình")
        self.assertIn("khu vực khác",answer)
        self.assertEqual(len(self.source.calls),1)

    async def test_course_scores_join_owned_codes_and_drop_unknown_codes(self):
        answer=await self.ask("Chi tiết điểm CVTV tháng 10/2026")
        self.assertIn("95",answer)
        self.assertNotIn("80",answer)
        self.assertNotIn("60",answer)
        self.assertNotIn("SECRET_SCORE",answer)

    async def test_media_notes_join_same_region_entities(self):
        answer=await self.ask("Chi tiết ghi chú truyền thông tháng 10/2026")
        self.assertIn("Own note",answer)
        self.assertNotIn("SECRET_NOTE",answer)

    async def test_regional_aggregate_is_filtered_before_display(self):
        self.data["partnerTrainingTargetRows:cw"]=[]
        answer=await self.ask("Chi tiết workshop đối tác tháng 10/2026")
        self.assertIn("12",answer)
        self.assertNotIn("99",answer)
        self.assertNotIn("SECRET_TARGET",answer)

    async def test_conflicting_region_and_trainer_id_fail_closed(self):
        self.data["pgs:2026-10"].append({"code":"BAD","trainerId":"b","area":"Đà Nẵng","name":"SECRET_CONFLICT"})
        answer=await self.ask("Danh sách PGs")
        self.assertNotIn("SECRET_CONFLICT",answer)

    async def test_conflicting_code_and_claimed_region_fail_closed(self):
        self.data["courseScores:cc"]["B01"]["region"]="Đà Nẵng"
        answer=await self.ask("Chi tiết điểm CVTV")
        self.assertNotIn("SECRET_SCORE",answer)

    async def test_unscoped_rows_only_visible_to_leader(self):
        self.data["pgs:2026-10"].append({"code":"UNKNOWN","name":"SECRET_UNSCOPED"})
        self.assertNotIn("SECRET_UNSCOPED",await self.ask("Danh sách PGs"))
        self.assertIn("SECRET_UNSCOPED",await self.ask("Danh sách PGs",message("leader")))

    async def test_nested_cross_region_rows_and_credentials_are_removed(self):
        self.data["pgs:2026-10"][0].update({"password":"CREDENTIAL_SECRET","extra":{"area":"Huế","note":"SECRET_NESTED"},"children":[{"area":"Đà Nẵng","note":"Own child"},{"area":"Huế","note":"SECRET_CHILD"}]})
        answer=await self.ask("Chi tiết PGs mã PG A01")
        self.assertNotIn("SECRET_NESTED",answer);self.assertNotIn("SECRET_CHILD",answer)
        self.assertNotIn("CREDENTIAL_SECRET",answer);self.assertIn("Own child",answer)

    async def test_missing_dataset_is_not_presented_as_zero(self):
        answer=await self.ask("Có bao nhiêu PGs tháng 8/2026?")
        self.assertIn("Nguồn chưa có dữ liệu",answer)
        self.assertNotIn("0 bản ghi",answer)

    async def test_explicit_empty_dataset_has_zero_matching_records(self):
        self.data["pgs:2026-08"]=[]
        answer=await self.ask("Có bao nhiêu PGs tháng 8/2026?")
        self.assertIn("Không có bản ghi phù hợp",answer)

    async def test_prior_month_followup_preserves_dataset_without_other_user_context(self):
        await self.ask("Danh sách PGs tháng 10/2026")
        answer=await self.ask("Tháng trước thì sao?")
        self.assertIn("Prior Month",answer)
        self.assertNotIn("PG An",answer)
        self.assertFalse(self.qa.handles("Tháng trước",message("staff-b"),NOW))

    async def test_iso_month_is_parsed_and_data_is_not_added_to_another_month(self):
        answer=await self.ask("Danh sách PGs 2026-09")
        self.assertIn("Prior Month",answer)
        self.assertNotIn("PG An",answer)
        self.assertIsInstance(is_dashboard_question("PGs 2026-09"),bool)

    async def test_daily_result_requires_a_real_date_field_and_vietnam_timezone(self):
        self.data["surveyResponses:2026-10"]=[{"code":"A01","trainerId":"a","content":"Today result","timestamp":"2026-10-13T18:30:00Z"},
            {"code":"C01","trainerId":"c","content":"Yesterday result","timestamp":"2026-10-13T04:00:00Z"},
            {"code":"B01","trainerId":"b","content":"SECRET_DAILY","timestamp":"2026-10-14T02:00:00Z"}]
        answer=await self.ask("Chi tiết Coaching hôm nay")
        self.assertIn("Today result",answer)
        self.assertNotIn("Yesterday result",answer)
        self.assertNotIn("SECRET_DAILY",answer)

    async def test_undated_daily_data_does_not_become_zero_or_guessed_data(self):
        answer=await self.ask("Truyền thông hôm nay được bao nhiêu?")
        self.assertIn("không lưu ngày",answer)
        self.assertNotIn("0 bản ghi",answer)

    async def test_codes_with_same_value_in_multiple_regions_fail_closed(self):
        self.data["pgs:2026-10"].append({"code":"A01","trainerId":"b","area":"Huế","name":"SECRET_COLLISION"})
        answer=await self.ask("Chi tiết điểm CVTV")
        self.assertNotIn("95",answer)
        self.assertNotIn("SECRET",answer)

    async def test_permission_changes_revalidate_old_query_context(self):
        await self.ask("Danh sách PGs Đà Nẵng")
        self.cfg["trainers"][0]["region"]="Huế"
        answer=await self.ask("Tiếp")
        self.assertIn("khu vực khác",answer)

    async def test_auth_storage_key_and_sql_are_never_requested(self):
        await self.ask("Dữ liệu dashboard auth_users OR 1=1 mật khẩu tất cả")
        keys=[key for call in self.source.calls for key in call]
        self.assertFalse(any("auth" in key or "1=1" in key for key in keys))

    async def test_numeric_aggregation_operates_on_owned_rows_only(self):
        answer=await self.ask("Tổng điểm CVTV cột total tháng 10/2026")
        self.assertIn("95",answer)
        self.assertNotIn("175",answer)

    async def test_shop_code_search_cannot_reveal_outside_region(self):
        self.data["shopTrainerMap"]=[{"shopId":"OWN","shopName":"Own shop","trainerId":"a"},{"shopId":"OUTSIDE","shopName":"SECRET_SHOP","trainerId":"b"}]
        answer=await self.ask("Chi tiết shop mã shop OUTSIDE")
        self.assertNotIn("SECRET_SHOP",answer)
        self.assertIn("Không có bản ghi phù hợp",answer)

    async def test_sellout_matches_previous_month_tab_and_scoped_model_sum(self):
        self.data["soAgg:2026-09"]=[{"code":"A01","name":"PG An","area":"Đà Nẵng","phone":10,"iot":2,"accessories":3,"models":{"Phone":{"A7 Pro 8GB":4,"A7 Pro 12GB":2}}},
            {"code":"B01","name":"SECRET_SALES","area":"Huế","phone":100,"iot":20,"accessories":30,"models":{"Phone":{"A7 Pro":90}}}]
        answer=await self.ask("Tổng S.O A7 Pro")
        self.assertIn("2026-09",answer)
        self.assertIn(": 6",answer)
        self.assertNotIn("90",answer)
        total=await self.ask("Tổng S.O")
        self.assertIn(": 15",total)

    def test_explicit_sellout_month_is_not_shifted(self):
        self.assertEqual(query_plan("S.O tháng 10/2026",NOW)["month"],"2026-10")

    def test_followups_keep_product_and_change_explicit_topic(self):
        previous=query_plan("Chi tiết S.O A7 Pro",NOW)
        self.assertEqual(query_plan("Tiếp",NOW,previous)["field"],"modelQty")
        self.assertEqual(query_plan("Chi tiết Coaching",NOW,previous)["kind"],"coaching")
        daily=query_plan("Chi tiết Coaching hôm nay",NOW)
        self.assertNotIn("day",query_plan("Tháng trước",NOW,daily))

    async def test_nested_code_only_ownership_cannot_leak(self):
        self.data["pgs:2026-10"][0]["children"]=[{"code":"B01","note":"SECRET_CODE_CHILD"},{"code":"A01","note":"Own code child"}]
        answer=await self.ask("Chi tiết PGs mã PG A01")
        self.assertNotIn("SECRET_CODE_CHILD",answer)
        self.assertIn("Own code child",answer)

    async def test_pagination_retains_filters_and_never_leaks_other_region(self):
        for i in range(30):self.data["pgs:2026-10"].append({"code":f"A-{i}","name":"Owned person "+str(i),"trainerId":"a","area":"Đà Nẵng","brand":"OPPO","star":0,"status":"Đang làm"})
        answers=[await self.ask("Danh sách PGs OPPO")]
        answers += [await self.ask("Tiếp") for _ in range(3)]
        self.assertTrue(all(len(a)<=1850 for a in answers))
        self.assertTrue(all("SECRET_OTHER_REGION" not in a for a in answers))
        self.assertNotEqual(answers[0],answers[1])

    def test_topic_detection_does_not_claim_generic_howto_is_data(self):
        self.assertFalse(is_dashboard_question("Hướng dẫn cách tổ chức workshop"))
        self.assertTrue(is_dashboard_question("Workshop tháng 10 có bao nhiêu lớp đã hoàn thành?"))
        self.assertTrue(is_dashboard_question("S.O tháng trước thế nào?"))

    def test_month_and_topic_parser_use_vietnam_calendar(self):
        now=datetime(2026,1,1,1,tzinfo=VIETNAM).timestamp()
        self.assertEqual(query_plan("PGs tháng trước",now)["month"],"2025-12")
        self.assertEqual(query_plan("KPI truyền thông nội bộ tháng 10/2026",NOW)["group"],"truyenthong")
        self.assertEqual(query_plan("KPI truyền thông nội bộ tháng 10/2026",NOW)["subtype"],"noibo")


if __name__=="__main__":unittest.main()
