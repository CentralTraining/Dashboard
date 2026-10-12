import copy
import unittest

from kpi import KpiSnapshot, KpiSourceError, average, metric, format_trainer_report


def rows(data):
    return [{'key': k, 'value': v, 'updated_at': '2026-10-12T01:00:00Z'} for k, v in data.items()]


def fixture():
    return {
        'config': {'trainers': [{'id': 'a', 'name': 'Trainer A', 'region': 'HUẾ'},
                                {'id': 'b', 'name': 'Trainer B', 'region': 'HUẾ'}]},
        'campaigns': [{'id': 'pg', 'group': 'noibo', 'subtype': 'pgsdev', 'month': '2026-10', 'name': 'Coaching'},
                      {'id': 'ftf', 'group': 'doitac', 'subtype': 'ftf', 'month': '2026-10', 'name': 'FTF'},
                      {'id': 'ws', 'group': 'doitac', 'subtype': 'workshop', 'month': '2026-10', 'name': 'WS'},
                      {'id': 'nb', 'group': 'truyenthong', 'subtype': 'noibo', 'month': '2026-10', 'name': 'Bài NB'},
                      {'id': 'dt', 'group': 'truyenthong', 'subtype': 'doitac', 'month': '2026-10', 'name': 'Bài ĐT'}],
        'records:2026-10': {'a': {'pg01Target': 10, 'pg01Actual': 999, 'pgMoiActual': 999,
                                'pgMoiTarget': 999, 'ftfShopTarget_MWG': 4, 'ftfHrTarget_MWG': 20}},
        'onoffRoster': [{'trainerId': 'a', 'code': '1', 'name': 'PG One', 'status': 'On', 'joinedAt': '2026-10-01'},
                        {'trainerId': 'a', 'code': '2', 'name': 'PG Two', 'status': 'On', 'joinedAt': '2026-10-25'},
                        {'trainerId': 'a', 'code': '3', 'name': 'PG Three', 'status': 'On', 'joinedAt': '2026-09-01'},
                        {'trainerId': 'a', 'code': '4', 'name': 'PG Four', 'status': 'On', 'joinedAt': '2026-10-01', 'devStatusNote': 'THAI SẢN'}],
        'pgs:2026-10': [{'code': '1', 'status': 'Đang làm'}, {'code': '4', 'status': 'Đang làm'}],
        'surveyResponses:2026-10': [{'trainerId': 'a'}, {'trainerId': 'a'}, {'trainerId': 'b'}],
        'surveyResponsesNew:2026-10': [{'trainerId': 'a', 'code': '1'}, {'trainerId': 'a', 'pgName': 'PG One'},
                                      {'trainerId': 'a', 'code': '2'}, {'trainerId': 'a', 'code': '3'}, {'trainerId': 'b', 'code': '1'}],
        'ftfShopList:2026-10': [{'trainerId': 'a', 'channel': 'TGDĐ', 'status': 'DONE', 'hrActual': 7,
                               'hrTarget': 99, 'testPass': 4, 'testTotal': 8, 'aiDone': 0, 'surveyDone': 3}],
        'partnerTrainingTargets:ws': {'HUE': {'sessions': 4, 'students': 20}},
        'partnerTrainingActuals:ws': {'HUẾ': {'sessions': 1, 'students': 10}},
        'wsDoitacParticipants:ws': [{'Khu vực': 'HUẾ', 'Khảo sát': 'Đã làm'}, {'Khu vực': 'HUẾ', 'Khảo sát': 'done'}],
        'shopTrainerMap': [{'trainerId': 'a', 'shopName': 'Shop Huế'}, {'trainerId': 'b', 'shopName': 'Shop B'}],
        'partnerList': [{'code': 'staff1', 'shop': 'Shop Hue'}, {'code': 'staff2', 'shop': 'Shop B'}],
        'mediaTargets:nb': {'a': 2, 'b': 2},
        'mediaResponses:nb': [{'trainerId': 'a'}, {'trainerId': 'a'}, {'trainerId': 'a'}],
        'mediaTargets:dt': {'a': 10, 'b': 10},
        'mediaDoitacEmps:dt': [{'code': 'staff1', 'approved': 3}, {'code': 'staff2', 'approved': 7},
                              {'code': 'unknown', 'approved': 50}, {'code': 'staff1', 'approved': 0}],
    }


class KpiChecks(unittest.TestCase):
    def setUp(self):
        self.data = fixture(); self.s = KpiSnapshot(rows(self.data), '2026-10'); self.a = self.s.trainers[0]

    def test_coaching_uses_live_survey_roster_and_before_day_25(self):
        new, pg01 = self.s.coaching(self.a)
        self.assertEqual((new['actual'], new['target']), (2, 2))
        self.assertEqual((pg01['actual'], pg01['target']), (2, 10))

    def test_pending_target_adjustment_keeps_previous_admin_target(self):
        self.data['pendingTargetAdjustments'] = [{'trainerId': 'a', 'month': '2026-10'}]
        self.assertEqual(KpiSnapshot(rows(self.data), '2026-10').coaching(self.a)[0]['target'], 999)

    def test_vietnam_day_cutoff_and_unassigned_targets(self):
        self.data['onoffRoster'][0]['joinedAt'] = '2026-10-24T20:00:00Z'
        new = KpiSnapshot(rows(self.data), '2026-10').coaching(self.a)[0]
        self.assertIsNone(new['pct'])
        self.assertIsNone(new['remaining'])

    def test_ftf_uses_admin_targets_and_dynamic_survey_target(self):
        m = {x['key']: x for x in self.s.ftf(self.a)}
        self.assertEqual((m['ftfShop:MWG']['actual'], m['ftfShop:MWG']['target']), (1, 4))
        self.assertEqual(m['ftfHr:MWG']['target'], 20)
        self.assertEqual((m['ftfKhaoSat:MWG']['actual'], m['ftfKhaoSat:MWG']['target']), (3, 7))

    def test_workshop_is_shared_region_and_survey_target_is_80_percent(self):
        a = self.s.workshop(self.a); b = self.s.workshop(self.s.trainers[1])
        self.assertEqual(a, b)
        self.assertEqual((a[0]['actual'], a[0]['target'], a[0]['shared_region']), (1, 4, 'HUẾ'))
        self.assertEqual((a[2]['actual'], a[2]['target']), (2, 8))

    def test_media_preserves_campaign_scope_and_partner_shop_assignment(self):
        m = self.s.media(self.a)
        self.assertEqual((m[0]['actual'], m[0]['target']), (3, 2))
        self.assertEqual((m[1]['actual'], m[1]['target']), (3, 10))
        # A finished campaign cannot hide another incomplete campaign in the average.
        self.assertEqual(average(m), 65)

    def test_missing_data_stops_reporting_instead_of_fabricating_zero(self):
        del self.data['surveyResponses:2026-10']
        with self.assertRaisesRegex(KpiSourceError, 'missing_coaching_source'):
            KpiSnapshot(rows(self.data), '2026-10').trainer_report(self.a)

    def test_format_has_three_groups_remaining_shared_scope_and_dashboard_link(self):
        text = format_trainer_report(self.s.trainer_report(self.a), 'https://example.invalid/dashboard/')
        for expected in ('1. Nội bộ', '2. Đối tác', '3. Truyền thông', 'còn 8',
                         'WS dùng chung theo khu vực HUẾ', 'chưa có target', 'https://example.invalid/dashboard/'):
            self.assertIn(expected, text)
        self.assertNotIn('NR-', text)
        self.assertNotIn('Người nhận:', text)


if __name__ == '__main__':
    unittest.main()
