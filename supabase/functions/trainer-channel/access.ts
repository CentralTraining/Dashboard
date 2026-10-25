// Server-side access for the dashboard's existing custom accounts.
// Passwords/hashes are never returned. Tokens expire and are invalidated by password/role/region changes.
const enc = new TextEncoder();
const dec = new TextDecoder();
const clean = v => String(v ?? "").trim();
const loginName = v => clean(v).normalize("NFKC").toLowerCase().replace(/[\u200B-\u200D\uFEFF]/g, "");
const regionKey = v => clean(v).normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[Đđ]/g, "d").toLowerCase().replace(/[^a-z0-9]/g, "");
const b64 = bytes => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64 = s => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
const digest = async s => new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(s)));
const hex = bytes => Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
export class AccessError extends Error { constructor(message, status = 401) { super(message); this.status = status; } }
function settings() {
  const url = Deno.env.get("SUPABASE_URL"), secret = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !secret) throw new AccessError("Chưa cấu hình xác thực Xây kênh trên máy chủ.", 503);
  return { url, secret };
}
async function dbRead(keys) {
  const { url, secret } = settings();
  const filter = keys.length === 1 ? "eq." + keys[0] : "in.(" + keys.map(k => '"' + k + '"').join(",") + ")";
  const res = await fetch(url + "/rest/v1/kv_store?key=" + encodeURIComponent(filter) + "&select=key,value", {
    headers: { apikey: secret, Authorization: "Bearer " + secret }, signal: AbortSignal.timeout(12000),
  });
  if (!res.ok) throw new AccessError("Không kiểm tra được quyền Xây kênh. Vui lòng thử lại.", 503);
  const rows = await res.json();
  if (!Array.isArray(rows)) throw new AccessError("Không kiểm tra được quyền Xây kênh.", 503);
  return Object.fromEntries(rows.map(r => [r.key, r.value]));
}
async function accountContext() {
  const data = await dbRead(["auth_users", "config"]);
  if (!Array.isArray(data.auth_users)) throw new AccessError("Không kiểm tra được tài khoản Xây kênh.", 503);
  return { users: data.auth_users, config: data.config || {} };
}
function principal(user, config) {
  if (!user || user.locked || !["admin", "trainer"].includes(user.role) || !user.passHash)
    throw new AccessError("Tài khoản không có quyền truy cập Xây kênh.", 403);
  const trainer = (config.trainers || []).find(t => t.id === user.trainerId);
  const region = trainer?.region || user.region || "";
  if (user.role === "trainer" && !region) throw new AccessError("Tài khoản chưa được gán khu vực.", 403);
  return { userId: String(user.id), role: user.role, region };
}
async function signingKey() {
  return crypto.subtle.importKey("raw", await digest("workshop-session-v1:" + settings().secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}
const binding = (p, user) => JSON.stringify([p.role, p.region, user.passHash]);
export async function authorize(username, password) {
  if (typeof password !== "string" || !password || password.length > 512 || !clean(username) || clean(username).length > 200)
    throw new AccessError("Tên đăng nhập hoặc mật khẩu không đúng.");
  const { users, config } = await accountContext();
  const matches = users.filter(u => loginName(u.username) === loginName(username));
  const user = matches.length === 1 ? matches[0] : null;
  if (!user || user.passHash !== hex(await digest(password))) throw new AccessError("Tên đăng nhập hoặc mật khẩu không đúng.");
  const p = principal(user, config), expires = Date.now() + 8 * 3600000;
  const payload = b64(enc.encode(JSON.stringify({ sub: p.userId, exp: expires, nonce: crypto.randomUUID() })));
  const signature = b64(await crypto.subtle.sign("HMAC", await signingKey(), enc.encode(payload + ":" + binding(p, user))));
  return { token: payload + "." + signature, expires };
}
export async function authenticate(token) {
  let payload, signature, claims;
  try {
    if (typeof token !== "string" || token.length > 1500) throw Error();
    [payload, signature] = token.split(".");
    claims = JSON.parse(dec.decode(unb64(payload)));
    if (!claims.sub || !Number.isFinite(claims.exp) || claims.exp < Date.now() || claims.exp > Date.now() + 8 * 3600000) throw Error();
  } catch { throw new AccessError("Vui lòng xác thực lại để mở dữ liệu Xây kênh."); }
  const { users, config } = await accountContext();
  const matches = users.filter(u => String(u.id) === claims.sub), user = matches.length === 1 ? matches[0] : null;
  const p = principal(user, config);
  let valid = false;
  try { valid = await crypto.subtle.verify("HMAC", await signingKey(), unb64(signature), enc.encode(payload + ":" + binding(p, user))); } catch {}
  if (!valid) throw new AccessError("Vui lòng xác thực lại để mở dữ liệu Xây kênh.");
  return {...p, trainerId:String(user.trainerId||''), trainers:config.trainers||[]};
}


