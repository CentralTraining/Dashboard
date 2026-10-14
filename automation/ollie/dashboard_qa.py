"""Read-only dashboard questions with mandatory account/region projection.

Neither query planning nor rendering sends dashboard values to a model. Storage
keys come from the inspected website's business-data registry, never from a
user-supplied key, URL, SQL expression or a generated program.
"""
import asyncio
import copy
import json
import math
import re
import time
import unicodedata
from calendar import monthrange
from datetime import datetime, timedelta
from pathlib import Path

from kpi import KpiSourceError, SupabaseKpiSource, normalize, format_team_report, format_trainer_report, date_vietnam
from tracker import VIETNAM, folded


REGISTRY = {
    "employees": ("Nhân sự PGs", "month", ("pgs",)),
    "onoff": ("Nhân sự On/Off", "global", ("onoffRoster",)),
    "shops": ("Shop và phân công", "global", ("shopTrainerMap",)),
    "brand_shops": ("Nhân sự các hãng theo shop", "month", ("brandShopList",)),
    "partners": ("Nhân sự đối tác", "global", ("partnerList",)),
    "sales": ("Nhân sự Sale", "global", ("saleRoster",)),
    "sellout": ("S.O", "month", ("soAgg",)),
    "coaching_reg": ("Đăng ký Coaching", "month", ("coachingReg",)),
    "coaching": ("Kết quả Coaching PGs 0★/1★", "month", ("surveyResponses",)),
    "coaching_new": ("Kết quả Coaching PGs mới", "month", ("surveyResponsesNew",)),
    "ftf": ("FTF đối tác", "month", ("ftfShopList",)),
    "media": ("Truyền thông", "campaign", ("mediaResponses", "mediaDoitacEmps", "mediaTargets", "mediaNotes")),
    "workshop": ("Workshop", "campaign", ("workshopTargetRows", "workshopActualRows", "partnerTrainingTargetRows", "partnerTrainingActualRows", "partnerTrainingTargets", "partnerTrainingActuals", "partnerTrainingNotes", "wsDoitacParticipants")),
    "courses": ("Đào tạo CVTV / PGs 3★", "campaign", ("courseRegistrations", "courseScores", "courseSurveyResponses")),
    "frequency": ("Test Online / Tư vấn AI", "campaign", ("frequencyProgress", "aiCheckProgress", "saleTestOnline", "saleAi")),
    "pending": ("Đề nghị chờ duyệt", "global", ("pendingPgStatusRequests", "pendingTargetAdjustments")),
    "records": ("Chỉ số / Target đã lưu", "month", ("records",)),
    "campaigns": ("Chiến dịch", "metadata", ()),
    "trainers": ("Trainer và khu vực", "metadata", ()),
}
TRAINER_FIELDS = ("trainerId", "trainer_id", "Trainer ID")
REGION_FIELDS = ("region", "area", "Khu vực", "khu_vuc", "oppo_area")
CODE_FIELDS = ("code", "pgCode", "Mã NV", "Mã PG", "pg_code")
SHOP_FIELDS = ("shopId", "shopCode", "storeId", "shop", "shopName", "storeName")
SECRET_FIELDS = {"password", "passwordhash", "salt", "secret", "clientsecret", "apikey", "anonkey", "authorization", "token", "accesstoken", "refreshtoken", "session", "credentials"}
LABELS = {"name":"Tên", "code":"Mã", "area":"Khu vực", "region":"Khu vực", "brand":"Hãng", "channel":"Kênh", "shop":"Shop", "shopName":"Shop", "storeName":"Shop", "status":"Trạng thái", "star":"Sao", "joinedAt":"Ngày vào", "offDate":"Ngày Off", "sale":"Sale", "saleName":"Sale", "province":"Tỉnh/TP", "district":"Quận/huyện", "phone":"Điện thoại", "email":"Email", "registeredAt":"Ngày đăng ký", "trainerName":"Trainer", "pgName":"PG", "className":"Lớp", "class_name":"Lớp", "expectedStudents":"Target học viên", "actualStudents":"Học viên thực tế", "target_students":"Target học viên", "actual_students":"Học viên thực tế", "theory":"Điểm lý thuyết", "consult":"Điểm tư vấn", "total":"Tổng", "note":"Ghi chú", "approved":"Đã duyệt", "target":"Target", "done":"Hoàn thành"}


def norm(value):
    return normalize(value)


def has_words(text, phrase):
    return bool(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text))


def is_dashboard_question(text):
    q = folded(text)
    if re.search(r"(?:la gi|huong dan|cach (?:lam|to chuc|coaching))", q) and not any(x in q for x in ("bao nhieu", "danh sach", "tien do", "so lieu", "du lieu")):
        return False
    terms = ("kpi", "target", "dashboard", "dasboard", "tien do", "chi so", "nhan su", "pg", "pgs", "on/off", "on off", "onoff", "bien dong", "ftf", "workshop", "ws", "coaching", "truyen thong", "sellout", "sell out", "s.o", "shop", "cvtv", "khoa hoc", "diem cuoi khoa", "3 sao", "khao sat", "test online", "tu van ai", "cho duyet", "chien dich", "du lieu", "doanh so", "ban duoc", "so luong ban")
    return any(has_words(q, word) for word in terms)


def parse_month(text, now):
    current = datetime.fromtimestamp(now, VIETNAM)
    q = folded(text)
    iso=re.search(r"\b(20\d{2})-(0?[1-9]|1[0-2])\b",q)
    if iso:return f"{int(iso[1]):04}-{int(iso[2]):02}"
    if "thang truoc" in q:
        return (current.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    found = re.search(r"(?<!\d)(0?[1-9]|1[0-2])\s*[/.-]\s*(20\d{2})(?!\d)", q)
    if not found:
        found = re.search(r"thang\s*(0?[1-9]|1[0-2])(?:\s*(?:nam|[/.-])\s*(20\d{2}))?\b", q)
    if found:
        return f"{int(found[2] or current.year):04}-{int(found[1]):02}"
    if re.search(r"thang\s*(?:0|1[3-9]|[2-9]\d)\b", q):
        raise ValueError("Tháng cần từ 1 đến 12. Bạn ghi ví dụ ‘tháng 10/2026’ nhé.")
    return current.strftime("%Y-%m")


def infer_kind(text):
    q = folded(text)
    if "cho duyet" in q or "de nghi" in q: return "pending"
    if "chien dich" in q and not any(x in q for x in ("target", "kpi", "tien do", "truyen thong")): return "campaigns"
    if "target" in q and "da luu" in q: return "records"
    if any(x in q for x in ("kpi", "target", "tien do", "chi so", "con thieu")): return "kpi"
    if "s.o" in q or "sellout" in q or "sell out" in q or "doanh so" in q or "ban duoc" in q or "so luong ban" in q: return "sellout"
    if "on/off" in q or "on off" in q or "onoff" in q or "bien dong" in q: return "onoff"
    if "cvtv" in q or "khoa hoc" in q or "diem cuoi khoa" in q or "pgs 3" in q: return "courses"
    if "test online" in q or "tu van ai" in q: return "frequency"
    if "truyen thong" in q and not any(x in q for x in ("kpi", "tien do", "con thieu", "target")): return "media"
    if "workshop" in q or has_words(q, "ws"): return "workshop"
    if "coaching" in q and not any(x in q for x in ("kpi", "tien do", "target", "con thieu")):
        if "dang ky" in q: return "coaching_reg"
        return "coaching_new" if "moi" in q else "coaching"
    if "ftf" in q and not any(x in q for x in ("kpi", "tien do", "target", "con thieu")): return "ftf"
    if any(x in q for x in ("nhan su cac hang", "hang doi thu", "nhan su doi thu")): return "brand_shops"
    if any(x in q for x in ("nhan vien doi tac", "nhan su doi tac", "danh sach doi tac")): return "partners"
    if any(x in q for x in ("nhan su sale", "danh sach sale")): return "sales"
    if "shop" in q and not any(x in q for x in ("workshop", "kpi", "tien do")): return "shops"
    if "target" in q and "da luu" in q: return "records"
    if any(has_words(q, x) for x in ("pg", "pgs", "nhan su")): return "employees"
    if "trainer" in q and any(x in q for x in ("danh sach", "phan cong", "khu vuc")) and not any(x in q for x in ("kpi", "tien do")): return "trainers"
    if any(x in q for x in ("kpi", "target", "tien do", "chi so", "con thieu", "doanh so")): return "kpi"
    return "catalog"


def query_plan(text, now, previous=None):
    q = folded(text)
    kind = infer_kind(text)
    follow = bool(previous and re.match(r"^(?:tiep\b|trang\s*\d|chi tiet|con |the |thang\s|thang truoc)", q)
                  and kind in ("catalog", previous["kind"]))
    plan = copy.deepcopy(previous) if follow else {"kind":kind, "operation":"list", "page":1}
    if not follow or re.search(r"\bthang\b|\b\d{1,2}/20\d{2}\b|20\d{2}-\d{2}", q):
        plan["month"] = parse_month(text, now)
        plan.pop("day", None)
    if not follow and plan["kind"]=="sellout" and not re.search(r"thang|20\d{2}-\d{2}|\d{1,2}[/.-]20\d{2}",q):
        current=datetime.fromtimestamp(now,VIETNAM)
        plan["month"]=(current.replace(day=1)-timedelta(days=1)).strftime("%Y-%m")
    day=None
    if "hom nay" in q:day=datetime.fromtimestamp(now,VIETNAM).date().isoformat()
    elif "hom qua" in q:day=(datetime.fromtimestamp(now,VIETNAM)-timedelta(days=1)).date().isoformat()
    else:
        explicit=re.search(r"\b(\d{1,2}/\d{1,2}/20\d{2})\b",q)
        if explicit:
            try:day=datetime.strptime(explicit[1],"%d/%m/%Y").date().isoformat()
            except ValueError:raise ValueError("invalid_date")
    if day:
        plan["day"]=day
        if plan["kind"]!="kpi":plan["month"]=day[:7]
    if re.search(r"\b(?:bao nhieu|tong so|so luong|dem)\b", q): plan["operation"] = "count"
    if re.search(r"\b(?:tong so\.o|tong s\.o|tong so\.o|tong doanh so|tong so luong ban)\b", q): plan["operation"] = "sum"
    if "chi tiet" in q or "cac truong" in q: plan["operation"] = "detail"
    if "thong ke" in q or "tong hop" in q: plan["operation"] = "summary"
    if "top" in q or "cao nhat" in q or "thap nhat" in q: plan["operation"] = "rank"
    if re.match(r"^tiep\b", q): plan["page"] = int(plan.get("page",1)) + 1
    page = re.search(r"\btrang\s*(\d+)\b", q)
    if page: plan["page"] = max(1,min(999,int(page[1])))
    if not follow:
        for brand in ("OPPO", "Samsung", "Vivo", "Xiaomi", "Realme", "Apple", "Honor"):
            if has_words(q, brand.lower()): plan["brand"] = brand
        if re.search(r"\b0\s*[*★]?\s*[/–-]\s*1\s*[*★]?|\b0\s*[*★]\s*1\s*[*★]", q): plan["stars"]=[0,1]
        else:
            star = re.search(r"\b([0-5])\s*(?:sao|[*★])", q)
            if star: plan["stars"]=[int(star[1])]
        for status in ("off", "on", "chua hoan thanh", "hoan thanh", "dang lam", "khong tham gia", "tham gia"):
            if has_words(q,status): plan["status"] = status; break
        if plan["kind"]=="employees" and has_words(q,"moi"): plan["new"] = True
        for channel in ("MWG","K.A","FPT","Viettel","IND"):
            if has_words(q,folded(channel)): plan["channel"] = channel
        code = re.search(r"\b(?:ma pg|ma nv|code|ma shop|ma)\s*[:=]?\s*([a-z0-9_-]{2,40})\b", q)
        if code: plan["code"] = code[1]
        search = re.search(r'[“"\']([^”"\']{1,100})[”"\']',text)
        if search: plan["search"] = search[1]
        field = re.search(r"\b(?:trường|truong|cột|cot|field)\s*[:=]?\s*[`\"“']?([a-zA-Z_][a-zA-Z0-9_]*)", text,re.I)
        if field: plan["field"] = field[1]
        if field and "tong" in q:plan["operation"]="sum"
        top=re.search(r"\btop\s*(\d+)\b",q)
        if top:plan["top"]=max(1,min(100,int(top[1])))
    if "truyen thong" in q:
        plan["group"]="truyenthong"
        if "doi tac" in q:plan["subtype"]="doitac"
        elif "noi bo" in q:plan["subtype"]="noibo"
    elif "noi bo" in q: plan["group"]="noibo"
    elif "doi tac" in q: plan["group"]="doitac"
    code = re.search(r"\b(?:ma pg|ma nv|code|ma shop|ma)\s*[:=]?\s*([a-z0-9_-]{2,40})\b", q)
    if code: plan["code"]=code[1]
    if plan["kind"]=="sellout":
        if any(x in q for x in ("bao nhieu","tong","so luong")) and not re.search(r"bao nhieu\s+(?:pg|pgs|nguoi)",q):plan["operation"]="sum"
        category = "iot" if "iot" in q else "accessories" if "phu kien" in q else "phone" if "dien thoai" in q else None
        if category:
            plan["field"] = category
            plan.pop("product", None)
        elif not follow:
            plan["field"] = "soTotal"
        product=re.search(r"\b(a\d+\s*(?:pro|s|e)?|reno\s*\d+\w*|find\s*\w+|buds\s*\d+\w*|watch\s*\w+)\b",q)
        if product:plan["product"]=product[1];plan["field"]="modelQty"
        plan.pop("brand",None)
    plan["question"] = text[:1500]
    return plan


class DashboardQA:
    def __init__(self, root, state, database, source_factory=None, team_formatter=None, trainer_formatter=None):
        self.root=Path(root); self.state=state; self.db=database
        self.source_factory=source_factory or SupabaseKpiSource
        self.team_formatter=team_formatter or format_team_report
        self.trainer_formatter=trainer_formatter or format_trainer_report
        self.db.execute("""CREATE TABLE IF NOT EXISTS dashboard_queries (
            sender_id TEXT, conversation_id TEXT, plan TEXT, updated_at REAL,
            PRIMARY KEY(sender_id,conversation_id))""")
        self.db.commit()

    def previous(self, incoming, now):
        row=self.db.execute("SELECT plan FROM dashboard_queries WHERE sender_id=? AND conversation_id=? AND updated_at>?",
            (str(incoming.sender_staff_id or ""),str(getattr(incoming,"conversation_id","") or "private"),now-86400)).fetchone()
        return json.loads(row[0]) if row else None

    def handles(self, text, incoming, now=None):
        if is_dashboard_question(text): return True
        return bool(re.match(r"^(?:tiep\b|trang\s*\d|chi tiet|con |the |thang\s|thang truoc)",folded(text)) and self.previous(incoming,time.time() if now is None else now))

    def account(self, incoming, settings):
        sender=str(incoming.sender_staff_id or "")
        if sender and sender==str(self.state.get("leader_staff_id") or ""): return None
        aliases={sender} if sender else set()
        for person in self.state.get("verified_recipients",{}).values():
            if isinstance(person,dict) and str(person.get("staff_id"))==sender:
                aliases.add(str(person.get("open_dingtalk_id") or ""))
        aliases.discard("")
        ids=[str(tid) for tid,route in settings.get("trainer_recipients",{}).items()
             if route.get("channel") in ("dm","dm_open") and str(route.get("target") or "") in aliases]
        if len(ids)!=1: raise PermissionError("Mình chưa đối chiếu được tài khoản với khu vực. Nghĩa cần xác nhận đối chiếu trước khi mình trả dữ liệu dashboard.")
        return ids[0]

    async def answer(self, text, incoming, now=None):
        now=time.time() if now is None else now
        if str(getattr(incoming,"conversation_type","1"))!="1":
            return "Dữ liệu dashboard chỉ trả qua tin nhắn riêng. Bạn nhắn riêng cho Ollie_MT để tra cứu nhé."
        try:
            directory=self.root/"runtime/kpi"
            settings=json.loads((directory/"settings.json").read_text())
            tid=self.account(incoming,settings)
            config=json.loads((directory/"source.json").read_text())
            source=self.source_factory(config)
            meta=await asyncio.to_thread(source.read,["config","campaigns"])
            data={r["key"]:r["value"] for r in meta}
            if not isinstance(data.get("config"),dict) or not isinstance(data.get("campaigns"),list): raise KpiSourceError("metadata_missing")
            access=Access(data["config"],tid)
            plan=query_plan(text,now,self.previous(incoming,now))
            access.apply_request(plan)
            if any(x in folded(text) for x in ("mat khau", "api key", "secret", "auth_users", "access token")):
                return "Phần tra cứu chỉ đọc dữ liệu nghiệp vụ dashboard, không cung cấp mật khẩu hoặc khóa truy cập."
            answer=await self.execute(plan,access,source,data,config,now)
            if len(answer)>1800: answer=paginate_text(answer,1)
            with self.db:
                self.db.execute("INSERT INTO dashboard_queries VALUES (?,?,?,?) ON CONFLICT(sender_id,conversation_id) DO UPDATE SET plan=excluded.plan,updated_at=excluded.updated_at",
                    (str(incoming.sender_staff_id),str(getattr(incoming,"conversation_id","") or "private"),json.dumps(plan,ensure_ascii=False),now))
            return answer
        except PermissionError as error: return str(error)
        except (ValueError,OSError,KeyError,TypeError,KpiSourceError):
            return "Mình chưa đọc hoặc xác định được dữ liệu phù hợp. Bạn ghi rõ mục cần hỏi và tháng, ví dụ ‘Danh sách PGs tháng 10/2026’. Mình không suy đoán số liệu khi thiếu nguồn."

    async def execute(self, plan, access, source, metadata, config, now):
        kind=plan["kind"]; month=plan["month"]
        if kind=="catalog":
            return "Bạn có thể hỏi: KPI/target, PGs, On/Off, shop, nhân sự các hãng/đối tác/Sale, S.O, Coaching, FTF, truyền thông, workshop, CVTV/PGs 3★, Test Online/Tư vấn AI, chiến dịch và đề nghị chờ duyệt.\nPhạm vi: "+access.label()+".\nVí dụ: ‘Tháng 10/2026 có bao nhiêu PGs OPPO 0-1 sao?’"
        if kind=="kpi":
            snapshot=await asyncio.to_thread(source.snapshot,month)
            trainers=[t for t in snapshot.trainers if access.trainer_allowed(t)]
            if not trainers: return "Không có Trainer phù hợp trong phạm vi được phép."
            if access.all and not access.requested_regions and not access.requested_ids:
                reports=await asyncio.to_thread(snapshot.reports)
            else: reports=await asyncio.to_thread(lambda:[snapshot.trainer_report(t) for t in trainers])
            group=plan.get("group")
            if group:
                if group not in ("noibo","doitac","truyenthong"):raise ValueError("invalid_group")
                for report in reports:
                    report["groups"]={k:v if k==group else [] for k,v in report["groups"].items()}
                    report["percentages"]={k:v if k==group else None for k,v in report["percentages"].items()}
            q=folded(plan["question"])
            campaign_ids=campaign_request([c for c in metadata["campaigns"] if c.get("month")==month],plan["question"])
            if any(x in q for x in ("target", "con thieu", "chi tiet", "da lam")) or campaign_ids:
                metric_rows=[]
                for report in reports:
                    for metrics in report["groups"].values():
                        for m in metrics:
                            if not m.get("target",0):continue
                            if campaign_ids and str(m.get("campaign_id","")) not in campaign_ids:continue
                            if plan.get("subtype") and m.get("subtype")!=plan["subtype"]:continue
                            if "pg moi" in q and m.get("key")!="pgMoi":continue
                            if re.search(r"0\s*[*★]?\s*[/–-]?\s*1",q) and m.get("key")!="pg01":continue
                            metric_rows.append({"name":report["name"],"metric":m["label"],"campaign":m.get("campaign_name",""),"actual":m["actual"],"target":m["target"],"pct":m["pct"],"remaining":m["remaining"],"unit":m.get("unit","")})
                metric_plan=dict(plan,operation="detail")
                return render(metric_rows,metric_plan,"KPI theo chỉ số",access.label())
            if plan.get("operation")=="rank":
                ranking=[]
                for r in reports:
                    values=[r["percentages"].get(group)] if group else list(r["percentages"].values())
                    values=[v for v in values if v is not None]
                    if values:ranking.append({"name":r["name"],"region":r.get("region",""),"pct":min(values)})
                return render(ranking,dict(plan,field="pct"),"Xếp hạng tiến độ KPI",access.label())
            content=self.team_formatter(reports,config["dashboard_url"]) if access.all else "\n\n".join(self.trainer_formatter(r,config["dashboard_url"]) for r in reports)
            return paginate_text(content,plan["page"]) if len(content)>1750 or plan["page"]>1 else content
        if kind not in REGISTRY: raise ValueError("unknown_dataset")
        title,mode,prefixes=REGISTRY[kind]
        campaigns=[c for c in metadata["campaigns"] if c.get("month")==month]
        if kind=="campaigns": rows=access.campaigns(campaigns)
        elif kind=="trainers": rows=[access.sanitize(t) for t in access.trainers if access.trainer_allowed(t)]
        else:
            selected=select_campaigns(campaigns,kind,plan)
            prefixes=selected_prefixes(prefixes,kind,plan)
            if mode=="campaign" and not selected: return f"Chưa có chiến dịch phù hợp tháng {month} trong nhóm dữ liệu này."
            keys=list(prefixes) if mode=="global" else [p+":"+month for p in prefixes] if mode=="month" else [p+":"+str(c["id"]) for c in selected for p in prefixes]
            dependencies=["pgs:"+month,"onoffRoster","partnerList","shopTrainerMap","saleRoster"]
            loaded=await asyncio.to_thread(source.read,list(dict.fromkeys(keys+dependencies)))
            values={r["key"]:r["value"] for r in loaded}
            if not any(k in values for k in keys): return f"Nguồn chưa có dữ liệu {title} tháng {month}; mình không quy đổi dữ liệu thiếu thành 0."
            access.build_indexes(values,month)
            rows=[]
            by_campaign={str(c["id"]):c for c in selected}
            for key in keys:
                if key not in values: continue
                family=key.split(":")[0]
                for row in unfold(values[key],family,access):
                    if access.row_allowed(row):
                        item=access.sanitize(row)
                        item["_source"]=family
                        if mode=="campaign":item["_campaign"]=str(by_campaign.get(key.split(":",1)[1],{}).get("name", ""))
                        rows.append(item)
            if kind=="pending": rows=[r for r in rows if not r.get("month") or r["month"]==month]
            if kind=="onoff": rows=onoff_at(rows,month,now,"bien dong" in folded(plan["question"]))
            if kind=="sellout":rows=so_values(rows,plan)
            if plan.get("day") and kind in ("coaching","coaching_new","coaching_reg","workshop","media","courses","sellout"):
                date_fields=("timestamp","registeredAt","training_date","time","createdAt","joinedAt")
                if rows and not any(any(date_vietnam(r.get(f)) for f in date_fields) for r in rows):
                    return f"Nguồn {title} không lưu ngày trong các bản ghi đã đối chiếu; mình chưa thể tách chính xác ngày {plan['day']}. Bạn có thể hỏi kết quả tháng {month}."
                rows=[r for r in rows if any(date_vietnam(r.get(f)) and date_vietnam(r[f]).date().isoformat()==plan["day"] for f in date_fields)]
            rows=filter_rows(rows,plan)
        return render(rows,plan,title,access.label())


class Access:
    def __init__(self, config, trainer_id):
        self.trainers=config.get("trainers",[])
        self.all=trainer_id is None
        by_id={str(t["id"]):t for t in self.trainers}
        if len(by_id)!=len(self.trainers):raise KpiSourceError("trainer_ids_ambiguous")
        if not self.all and (trainer_id not in by_id or not by_id[trainer_id].get("region")):raise PermissionError("Mình chưa xác định được khu vực đã đối chiếu của tài khoản này.")
        self.allowed_regions={norm(by_id[trainer_id]["region"])} if not self.all else set()
        self.allowed_ids={str(t["id"]) for t in self.trainers if self.all or norm(t.get("region")) in self.allowed_regions}
        self.requested_regions=set();self.requested_ids=set();self.entities={};self.shops={}

    def label(self):
        selected=self.requested_regions or self.allowed_regions
        if selected:return ", ".join(dict.fromkeys(str(t["region"]) for t in self.trainers if norm(t.get("region")) in selected))
        if self.requested_ids:return ", ".join(str(t.get("name",t["id"])) for t in self.trainers if str(t["id"]) in self.requested_ids)
        return "Toàn dashboard Miền Trung"

    def apply_request(self, plan):
        q=norm(plan["question"])
        requested={norm(t["region"]) for t in self.trainers if t.get("region") and has_words(q,norm(t["region"]))}
        # Revalidate persisted selectors against current permissions on every turn.
        if not requested:requested=set(plan.get("regions",[]))
        requested_ids=set(plan.get("trainer_ids",[]))
        for t in self.trainers:
            name=norm(t.get("name",""))
            if name and has_words(q,name):requested_ids.add(str(t["id"]))
        if not requested_ids:
            original=unicodedata.normalize("NFC",plan["question"]).casefold()
            candidates=[]
            for t in self.trainers:
                words=str(t.get("name","")).strip().split()
                if not words:continue
                short=unicodedata.normalize("NFC",words[-1]).casefold()
                if re.search(r"(?:trainer|của)\s+"+re.escape(short)+r"\b",original):candidates.append(t)
            if requested:candidates=[t for t in candidates if norm(t.get("region")) in requested]
            if len(candidates)>1:raise PermissionError("Tên Trainer chưa đủ rõ. Bạn ghi đầy đủ tên hoặc thêm khu vực để mình tra đúng người nhé.")
            if candidates:requested_ids={str(candidates[0]["id"])}
        if not self.all and (not requested.issubset(self.allowed_regions) or not requested_ids.issubset(self.allowed_ids)):
            raise PermissionError("Tài khoản của bạn chỉ được tra dữ liệu khu vực mình quản lý. Mình không trả dữ liệu của khu vực khác.")
        self.requested_regions=requested;self.requested_ids=requested_ids
        plan["regions"]=sorted(requested);plan["trainer_ids"]=sorted(requested_ids)

    def trainer_allowed(self,t):
        tid=str(t.get("id",""));region=norm(t.get("region",""))
        return (self.all or (tid in self.allowed_ids and region in self.allowed_regions)) and (not self.requested_ids or tid in self.requested_ids) and (not self.requested_regions or region in self.requested_regions)

    def row_allowed(self,row):
        ids=[str(row[k]) for k in TRAINER_FIELDS if row.get(k)]
        regions=[norm(row[k]) for k in REGION_FIELDS if row.get(k)]
        for key in ("oppo_areas",):
            if isinstance(row.get(key),list):regions.extend(norm(x) for x in row[key] if x)
        if ids:
            valid={str(t["id"]) for t in self.trainers if self.trainer_allowed(t)}
            if any(x not in valid for x in ids): return False
        if regions:
            allowed=self.requested_regions or (self.allowed_regions if not self.all else set())
            if allowed and any(x not in allowed for x in regions):return False
            if self.requested_ids:
                selected={norm(t.get("region")) for t in self.trainers if str(t["id"]) in self.requested_ids}
                if any(x not in selected for x in regions):return False
        known=[]
        for field,index in [(x,self.entities) for x in CODE_FIELDS]+[(x,self.shops) for x in SHOP_FIELDS]:
            key=norm(row.get(field,""))
            if key and key in index:known.append(index[key])
        if known and not all(known):return False
        if ids or regions:return True
        if known:return True
        return self.all and not self.requested_ids and not self.requested_regions

    def build_indexes(self, values,month):
        for key in ("pgs:"+month,"onoffRoster","partnerList"):
            for row in values.get(key,[]) if isinstance(values.get(key),list) else []:
                allowed=self.row_allowed(row)
                for field in CODE_FIELDS:
                    code=norm(row.get(field,""))
                    if code:self.entities[code]=self.entities.get(code,allowed) and allowed
        sale=values.get("saleRoster",{})
        for row in sale.get("list",[]) if isinstance(sale,dict) else []:
            allowed=self.row_allowed(row)
            for field in ("code","key"):
                code=norm(row.get(field,""))
                if code:self.entities[code]=self.entities.get(code,allowed) and allowed
        for row in values.get("shopTrainerMap",[]) if isinstance(values.get("shopTrainerMap"),list) else []:
            allowed=self.row_allowed(row)
            for field in SHOP_FIELDS:
                key=norm(row.get(field,""))
                if key:self.shops[key]=self.shops.get(key,allowed) and allowed

    def sanitize(self,value):
        ownership_fields = (*TRAINER_FIELDS, *REGION_FIELDS, "oppo_areas", *CODE_FIELDS, *SHOP_FIELDS)
        if isinstance(value,dict):
            return {k:self.sanitize(v) for k,v in value.items() if re.sub(r"[^a-z0-9]","",folded(k)) not in SECRET_FIELDS
                    and not (isinstance(v,dict) and any(f in v for f in ownership_fields) and not self.row_allowed(v))}
        if isinstance(value,list):
            return [self.sanitize(v) for v in value if not isinstance(v,dict) or not any(k in v for k in ownership_fields) or self.row_allowed(v)]
        return value

    def campaigns(self,rows):
        keys=("id","name","month","group","subtype","completed","targetLocked","startDate","endDate","frequencyX")
        return [{k:c[k] for k in keys if k in c} for c in rows if self.all or not c.get("region") or norm(c["region"]) in self.allowed_regions]


def select_campaigns(campaigns,kind,plan):
    q=folded(plan["question"])
    def relevant(c):
        group,sub=c.get("group"),c.get("subtype")
        if kind=="media":return group=="truyenthong" and (not plan.get("subtype") or sub==plan["subtype"])
        if kind=="workshop":return sub in ("workshop","hub") and (not plan.get("group") or group==plan["group"])
        if kind=="courses":return sub in ("cvtv","pgs3sao") and ("cvtv" not in q or sub=="cvtv")
        if kind=="frequency":return sub in ("testonline","tuvanai","checkshop","tuvanai_checkshop") and ("test online" not in q or sub=="testonline")
        return True
    rows=[c for c in campaigns if relevant(c) and re.fullmatch(r"[A-Za-z0-9_-]+",str(c.get("id","")))]
    requested=campaign_request(rows,plan["question"])
    return [c for c in rows if str(c["id"]) in requested] if requested else rows


def campaign_request(campaigns,question):
    q=norm(question)
    exact={str(c["id"]) for c in campaigns if c.get("name") and has_words(q,norm(c["name"]))}
    if exact:return exact
    stop=set("KPI TARGET TIEN DO CHI SO CHIEN DICH THANG NAM TRUYEN THONG NOI BO DOI TAC OPPO COACHING PG PGS WORKSHOP WS TEST ONLINE CHI TIET KET QUA TEAM TOAN QUOC".split())
    tokens={x for x in q.split() if x not in stop and not x.isdigit()}
    return {str(c["id"]) for c in campaigns if ({x for x in norm(c.get("name","")).split() if x not in stop and not x.isdigit()} & tokens)}


def selected_prefixes(prefixes,kind,plan):
    q=folded(plan["question"])
    if kind=="media":
        if "ghi chu" in q or "note" in q:return ("mediaNotes",)
        return ("mediaDoitacEmps",) if "doi tac" in q else ("mediaResponses",)
    if kind=="courses":
        if "diem" in q:return ("courseScores",)
        if "khao sat" in q:return ("courseSurveyResponses",)
        return ("courseRegistrations",)
    if kind=="frequency":
        sale=has_words(q,"sale") or has_words(q,"sales")
        if "test online" in q:return ("saleTestOnline",) if sale else ("frequencyProgress",)
        return ("saleAi",) if sale else ("aiCheckProgress",)
    if kind=="workshop":
        actual=any(x in q for x in ("da hoan thanh","hoan thanh","thuc te","da to chuc"))
        target=any(x in q for x in ("ke hoach","du kien"))
        if actual:return ("partnerTrainingActualRows",) if "doi tac" in q else ("workshopActualRows",) if "noi bo" in q else ("workshopActualRows","partnerTrainingActualRows")
        if target:return ("partnerTrainingTargetRows",) if "doi tac" in q else ("workshopTargetRows",) if "noi bo" in q else ("workshopTargetRows","partnerTrainingTargetRows")
    return prefixes


def unfold(value,family,access):
    if isinstance(value,list):return [copy.deepcopy(r) for r in value if isinstance(r,dict)]
    if not isinstance(value,dict):return []
    if family=="saleRoster":return [copy.deepcopy(r) for r in value.get("list",[]) if isinstance(r,dict)]
    if family in ("records","mediaTargets"):
        return [{**(copy.deepcopy(v) if isinstance(v,dict) else {"target":v}),"trainerId":str(k)} for k,v in value.items()]
    if family in ("partnerTrainingTargets","partnerTrainingActuals","partnerTrainingNotes"):
        rows=[]
        for region,channels in value.items():
            if isinstance(channels,dict):
                for channel,fields in channels.items():
                    rows.append({**(copy.deepcopy(fields) if isinstance(fields,dict) else {"value":fields}),"region":region,"channel":channel})
        return rows
    if family in ("saleTestOnline","saleAi"):
        value=value.get("counts",{})
    return [{**(copy.deepcopy(v) if isinstance(v,dict) else {"value":v}),"code":str(k)} for k,v in value.items()]


def filter_rows(rows,plan):
    result=[]
    for row in rows:
        if plan.get("brand") and norm(row.get("brand",""))!=norm(plan["brand"]):continue
        if plan.get("channel") and norm(row.get("channel",""))!=norm(plan["channel"]):continue
        if plan.get("code") and not any(norm(row.get(k,""))==norm(plan["code"]) for k in (*CODE_FIELDS,*SHOP_FIELDS)):continue
        if plan.get("stars"):
            try:star=int(row.get("star",-1))
            except (ValueError,TypeError):continue
            if star not in plan["stars"]:continue
        status=plan.get("status")
        if status:
            actual=folded(str(row.get("status","")))
            complete=row.get("done") is True or actual in ("done","hoan thanh","da hoan thanh","completed","complete")
            if status=="hoan thanh" and not complete:continue
            if status=="chua hoan thanh" and complete:continue
            if status not in ("hoan thanh","chua hoan thanh") and status!=actual:continue
        if plan.get("new") and not str(row.get("joinedAt",""))[:7]==plan["month"]:continue
        if plan.get("search") and norm(plan["search"]) not in norm(json.dumps(row,ensure_ascii=False)):continue
        result.append(row)
    return result


def onoff_at(rows,month,now,changes):
    local=datetime.fromtimestamp(now,VIETNAM)
    year,m=map(int,month.split("-"));end=datetime(year,m,monthrange(year,m)[1],23,59,59,tzinfo=VIETNAM)
    cutoff=min(end,local)
    result=[]
    for row in rows:
        if changes and not any(str(row.get(k,""))[:7]==month for k in ("joinedAt","offDate")):continue
        joined=str(row.get("joinedAt", ""))[:10];off=str(row.get("offDate", ""))[:10]
        if joined and joined>cutoff.strftime("%Y-%m-%d"):continue
        item=dict(row)
        if joined:item["status"]="Off" if off and off<=cutoff.strftime("%Y-%m-%d") else "On"
        result.append(item)
    return result


def so_values(rows,plan):
    result=[]
    product=norm(plan.get("product","")).replace(" ","")
    for row in rows:
        item=dict(row)
        if all(isinstance(row.get(k),(int,float)) and not isinstance(row[k],bool) and math.isfinite(row[k]) for k in ("phone","iot","accessories")):
            item["soTotal"]=row["phone"]+row["iot"]+row["accessories"]
        if product:
            quantities=[]
            models=row.get("models",{})
            if isinstance(models,dict):
                for values in models.values():
                    if isinstance(values,dict):
                        quantities.extend(v for model,v in values.items() if product in norm(model).replace(" ","") and isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v))
            if not quantities:continue
            item["modelQty"]=sum(quantities)
        result.append(item)
    return result


def display(value):
    if value is None:return "—"
    if isinstance(value,bool):return "Có" if value else "Không"
    if isinstance(value,(dict,list)):return json.dumps(value,ensure_ascii=False,separators=(",",":"))
    return str(value)


def render(rows,plan,title,scope):
    header=f"📊 {title} · {plan['month']}\nPhạm vi: {scope}"
    if not rows:return header+"\nKhông có bản ghi phù hợp trong phạm vi được phép."
    op=plan.get("operation","list")
    if op=="count":return header+f"\nCó {len(rows)} bản ghi phù hợp."
    if op=="summary":
        lines=[header,f"Tổng: {len(rows)} bản ghi."]
        for field in ("status","brand","channel","star"):
            counts={}
            for row in rows:
                if row.get(field) is not None:counts[display(row[field])]=counts.get(display(row[field]),0)+1
            if counts and len(counts)<=12:lines.append(LABELS.get(field,field)+": "+" · ".join(f"{k}: {v}" for k,v in sorted(counts.items())))
        return "\n".join(lines)
    field=plan.get("field")
    labels={**LABELS,"phone":"Điện thoại bán","iot":"IoT bán","accessories":"Phụ kiện bán","soTotal":"Tổng S.O","modelQty":"S.O model đã chọn"} if plan["kind"]=="sellout" else LABELS
    if op in ("sum","rank"):
        if not field:
            candidates=("totalSo","totalQty","total","so","qty","quantity","actualStudents","approved","target","count","value")
            field=next((f for f in candidates if any(isinstance(r.get(f),(int,float)) and not isinstance(r.get(f),bool) for r in rows)),None)
        if not field:return header+"\nBạn muốn tính tổng hoặc xếp hạng theo cột nào? Có thể ghi ‘cột tên_trường’."
        numeric=[r for r in rows if isinstance(r.get(field),(int,float)) and not isinstance(r.get(field),bool) and math.isfinite(r[field])]
        if not numeric:return header+f"\nCột {field} chưa có giá trị số phù hợp."
        if op=="sum":return header+f"\nTổng {labels.get(field,field)}: {sum(r[field] for r in numeric):g} · {len(numeric)} bản ghi."
        rows=sorted(numeric,key=lambda r:r[field],reverse="thap nhat" not in folded(plan["question"]))
        if plan.get("top"):rows=rows[:plan["top"]]
    page=max(1,int(plan.get("page",1)))
    lines=[header,f"Có {len(rows)} bản ghi phù hợp."]
    for number,row in enumerate(rows,1):
        if op=="detail":
            fields=[k for k in row if not k.startswith("_")]
        else:
            common=("name","pgName","className","class_name","shopName","storeName","code","region","area","brand","channel","status","star","target","approved","actualStudents","total","count","value")
            fields=[k for k in common if k in row][:7]
            if field and field not in fields and field in row:fields.append(field)
            if not fields:fields=[k for k in row if not k.startswith("_")][:6]
        content=" · ".join(f"{labels.get(k,k)}: {display(row[k])}" for k in fields)
        if row.get("_campaign"):content=row["_campaign"]+" · "+content
        lines.append(f"{number}. {content}")
    lines.append("Có thể hỏi ‘chi tiết mã PG …’ để xem đầy đủ trường.")
    return paginate_text("\n".join(lines),page)


def paginate_text(text,page,limit=1750):
    pages=[];current=""
    for line in text.splitlines():
        if len(line)>limit:
            # Preserve all values; split only long detail lines at field boundaries.
            pieces=line.split(" · ")
        else:pieces=[line]
        for piece in pieces:
            if len(piece)>limit:
                pieces_long=[piece[i:i+limit] for i in range(0,len(piece),limit)]
                if current:pages.append(current);current=""
                pages.extend(pieces_long[:-1]);current=pieces_long[-1];continue
            if current and len(current)+len(piece)+1>limit:pages.append(current);current=""
            current+=("\n" if current else "")+piece
    if current:pages.append(current)
    index=max(0,int(page)-1)
    if index>=len(pages):return "Không có trang chi tiết này; bạn hỏi lại trang 1 nhé."
    return pages[index]+(f"\nChi tiết {index+1}/{len(pages)} · nhắn ‘tiếp’." if len(pages)>1 else "")
