import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch
import hr_notify as h
from tracker import DeliveryError
CONFIG={'credentials':{'appKey':'SYNTHETIC_ROBOT','appSecret':'SYNTHETIC_SECRET'},'state':{'robot_code':'SYNTHETIC_ROBOT','leader_staff_id':'SYNTHETIC_LEADER'},'source':{'url':h.BASE,'anon_key':'SYNTHETIC_PUBLIC'}}
NOTICE={'kind':'hr_data_updated','version':1,'runId':'11111111-1111-4111-8111-111111111111','claimId':'22222222-2222-4222-8222-222222222222','month':'2026-11','completedAt':'2026-11-08T17:01:00Z','noticeDay':'2026-11-09'}
REPORT={**NOTICE,'kind':'hr_data_sync_report','version':2,'runStatus':'succeeded','coreVerified':True,'historyVerified':True,'verifiedSources':['assign','stars','on','off','promotions'],'historyRecords':1080}
class Api:
 def __init__(self,notice=NOTICE):self.notice=copy.deepcopy(notice);self.calls=[];self.ack_fail=0;self.start_fail=False;self.unknown=0;self.rejected=0
 def call(self,action,**extra):
  self.calls.append((action,extra))
  if action=='status':return {'pending':int(self.notice is not None),'due':0,'unknown':self.unknown,'rejected':self.rejected}
  if action=='claim':n=self.notice;self.notice=None;return {'notice':n}
  if action=='sending':
   if self.start_fail:raise h.NoticeError('unknown sending write')
   return {'sending':True}
  if action=='ack':
   if self.ack_fail:self.ack_fail-=1;raise h.NoticeError('temporary ack failure')
   self.unknown+=int(extra['outcome']=='unknown');self.rejected+=int(extra['outcome']=='rejected');return {'accepted':extra['outcome']=='accepted','recorded':True}
  if action=='release':return {'released':True}
  raise AssertionError(action)
class NoticeTests(unittest.TestCase):
 def sender(self):return Mock(access_token=Mock(return_value='SYNTHETIC_TOKEN'),send=Mock(return_value='SYNTHETIC_RECEIPT'))
 def test_verify_does_not_claim_or_send(self):
  api=Api();s=self.sender();r=h.run(CONFIG,api=api,sender=s);self.assertTrue(r['ready']);s.send.assert_not_called();self.assertEqual([c[0] for c in api.calls],['status'])
 def test_no_due_event_sends_nothing(self):
  s=self.sender();r=h.run(CONFIG,True,Api(None),s);self.assertEqual(r['accepted'],0);s.send.assert_not_called()
 def test_only_leader_dm_after_durable_sending(self):
  api=Api();s=self.sender();s.send.side_effect=lambda *a:self.assertEqual(api.calls[-1][0],'sending') or 'SYNTHETIC_RECEIPT';r=h.run(CONFIG,True,api,s);self.assertEqual(r['accepted'],1);a=s.send.call_args.args;self.assertEqual(a[:2],('dm','SYNTHETIC_LEADER'));self.assertIn('Đã cập nhật Data HR mới thành công',a[2]);self.assertIn('00:01 ngày 09/11/2026',a[2]);self.assertEqual(r['group'],0)
 def test_provider_unknown_not_resent(self):
  api=Api();s=self.sender();s.send.side_effect=DeliveryError('uncertain',ambiguous=True);r=h.run(CONFIG,True,api,s);self.assertEqual(r['unknown'],1);self.assertEqual(s.send.call_count,1);self.assertEqual([c[1]['outcome'] for c in api.calls if c[0]=='ack'],['unknown'])
 def test_missing_receipt_is_unknown(self):
  s=self.sender();s.send.return_value='';r=h.run(CONFIG,True,Api(),s);self.assertEqual(r['accepted'],0);self.assertEqual(r['unknown'],1)
 def test_rejection_is_not_accepted(self):
  s=self.sender();s.send.side_effect=DeliveryError('invalid_recipient');r=h.run(CONFIG,True,Api(),s);self.assertEqual(r['rejected'],1);self.assertEqual(r['accepted'],0)
 def test_retry_only_receipt_not_message(self):
  api=Api();api.ack_fail=1;s=self.sender();r=h.run(CONFIG,True,api,s);self.assertEqual(r['accepted'],1);self.assertEqual(s.send.call_count,1);self.assertEqual(len([c for c in api.calls if c[0]=='ack']),2)
 def test_unknown_sending_write_stops_before_http(self):
  api=Api();api.start_fail=True;s=self.sender()
  with self.assertRaises(h.NoticeError):h.run(CONFIG,True,api,s)
  s.send.assert_not_called()
 def test_bot_auth_fail_releases_before_sending(self):
  api=Api();s=self.sender();s.access_token.side_effect=DeliveryError('bad_token')
  with self.assertRaises(h.NoticeError):h.run(CONFIG,True,api,s)
  self.assertEqual(api.calls[-1][0],'release');s.send.assert_not_called()
 def test_invalid_proof_never_sends(self):
  for field,value in [('kind','fake'),('version',0),('runId','bad'),('month','2026-99'),('completedAt','2026-11-09')]:
   s=self.sender()
   with self.assertRaises(h.NoticeError):h.run(CONFIG,True,Api({**NOTICE,field:value}),s)
   s.send.assert_not_called()
 def test_configuration_rejects_other_robot_or_source(self):
  for section,field,value in [('source','url','https://evil.test'),('state','robot_code','OTHER'),('state','leader_staff_id','')]:
   c=copy.deepcopy(CONFIG);c[section][field]=value
   with self.assertRaises(h.NoticeError):h.configuration(json.dumps(c))
 def test_cli_error_never_prints_sensitive_exception(self):
  with patch.object(h,'run',side_effect=ValueError('SYNTHETIC_SECRET')),patch.object(h,'configuration',return_value=CONFIG),patch('sys.argv',['hr_notify.py']),redirect_stdout(io.StringIO()) as out:self.assertEqual(h.main(),1)
  self.assertNotIn('SYNTHETIC_SECRET',out.getvalue());self.assertIn('ValueError',out.getvalue())
 def test_old_uncertainty_does_not_fail_today(self):
  api=Api(None);original=api.call
  def call(action,**extra):
   if action=='status':return {'pending':0,'due':0,'unknown':7,'rejected':1,'unresolved':0}
   return original(action,**extra)
  api.call=call;r=h.run(CONFIG,True,api,self.sender());self.assertEqual(r['unresolved'],0)
 def test_real_sender_uses_one_private_recipient(self):
  s=h.DingTalkSender(CONFIG['credentials'],{'robot_code':CONFIG['state']['robot_code']});s.token='SYNTHETIC_TOKEN';s.token_until=10**12;r=Mock(ok=True,status_code=200);r.json.return_value={'processQueryKey':'SYNTHETIC_RECEIPT'}
  with patch('tracker.requests.post',return_value=r) as post:self.assertEqual(s.send('dm','SYNTHETIC_LEADER',h.message(NOTICE)),'SYNTHETIC_RECEIPT')
  a,k=post.call_args;self.assertTrue(a[0].endswith('/oToMessages/batchSend'));self.assertEqual(k['json']['userIds'],['SYNTHETIC_LEADER']);self.assertNotIn('openConversationId',k['json'])
 def test_five_source_success_requires_extra_proof(self):
  text=h.message(REPORT);self.assertIn('đủ 5 tab',text);self.assertIn('LÊN SAO',text)
  api=Api(REPORT);s=self.sender();r=h.run(CONFIG,True,api,s);self.assertEqual(r['accepted'],1);self.assertEqual(s.send.call_args.args[:2],('dm','SYNTHETIC_LEADER'))
 def test_core_only_is_partial_not_five_source_success(self):
  notice={**REPORT,'historyVerified':False,'historyRecords':None,'verifiedSources':['assign','stars','on','off']};text=h.message(notice)
  self.assertIn('4 nguồn',text);self.assertIn('LÊN SAO chưa',text);self.assertNotIn('đủ 5 tab',text);self.assertNotIn('mới thành công',text)
 def test_failed_and_uncertain_report_no_false_success(self):
  for status in ['failed','uncertain']:
   notice={**REPORT,'runStatus':status,'coreVerified':False,'historyVerified':False,'historyRecords':None,'verifiedSources':[]};text=h.message(notice)
   self.assertNotIn('thành công',text);self.assertIn('Data → Nhân sự → Nội bộ',text)
   s=self.sender();self.assertEqual(h.run(CONFIG,True,Api(notice),s)['accepted'],1);self.assertEqual(s.send.call_args.args[0],'dm')
 def test_inconsistent_extra_evidence_never_sends(self):
  cases=[{'coreVerified':False},{'historyVerified':'true'},{'historyRecords':0},{'historyRecords':True},{'historyRecords':60001},{'verifiedSources':['promotions']},{'runStatus':'running'}]
  for change in cases:
   s=self.sender()
   with self.assertRaises(h.NoticeError):h.run(CONFIG,True,Api({**REPORT,**change}),s)
   s.send.assert_not_called()
 def test_unknown_five_source_notice_is_never_resent(self):
  s=self.sender();s.send.side_effect=DeliveryError('unknown',ambiguous=True);r=h.run(CONFIG,True,Api(REPORT),s);self.assertEqual(r['unknown'],1);self.assertEqual(s.send.call_count,1)
if __name__=='__main__':unittest.main()
