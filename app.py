import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import os
from datetime import datetime, timedelta, timezone

# 데이터 저장 파일명
DB_FILE = "reservations.csv"

# --- [1. 핵심 함수 정의] ---

def get_kst_now():
    """서버 시간(UTC)을 한국 시간(KST)으로 변환합니다."""
    return datetime.now(timezone.utc) + timedelta(hours=9)

def get_latest_df():
    """최신 데이터를 읽어옵니다."""
    if not os.path.isfile(DB_FILE):
        return pd.DataFrame(columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석", "팀원학번"])
    df = pd.read_csv(DB_FILE)
    if "출석" not in df.columns:
        df["출석"] = "미입실"
    if "팀원학번" not in df.columns:
        df["팀원학번"] = ""
    for col in ["이름", "학번", "날짜", "시작", "종료", "방번호", "팀원학번"]:
        df[col] = df[col].astype(str).str.strip()
    return df

def check_team_duplication(member_ids, target_date):
    """대표자 및 팀원 중 한 명이라도 해당 날짜에 이미 예약이 있는지 전수 검사합니다."""
    df = get_latest_df()
    if df.empty: return False, ""
    day_df = df[df["날짜"] == str(target_date)]
    for m_id in member_ids:
        if not m_id: continue
        # 대표자 학번 열 또는 팀원학번 열에서 검색
        is_booked = day_df[(day_df["학번"] == m_id) | (day_df["팀원학번"].str.contains(m_id, na=False))]
        if not is_booked.empty:
            return True, m_id
    return False, ""

def is_already_booked(rep_name, rep_id):
    df = get_latest_df()
    if df.empty: return False
    duplicate = df[(df["이름"] == str(rep_name).strip()) & (df["학번"] == str(rep_id).strip())]
    return not duplicate.empty

def check_overlap(date, start_t, end_t, room):
    df = get_latest_df()
    if df.empty: return False
    same_day_room = df[(df["날짜"] == str(date)) & (df["방번호"] == room)]
    for _, row in same_day_room.iterrows():
        try:
            fmt = "%H:%M"
            e_start = datetime.strptime(row["시작"], fmt).time()
            e_end = datetime.strptime(row["종료"], fmt).time()
            n_start = datetime.strptime(start_t, fmt).time()
            n_end = datetime.strptime(end_t, fmt).time()
            if n_start < e_end and n_end > e_start: return True
        except: continue
    return False

def auto_cleanup_noshow(df):
    now_kst = get_kst_now().replace(tzinfo=None)
    now_date = str(now_kst.date())
    to_delete = []
    for idx, row in df.iterrows():
        if row["날짜"] == now_date and row["출석"] == "미입실":
            try:
                start_dt = datetime.strptime(f"{row['날짜']} {row['시작']}", "%Y-%m-%d %H:%M")
                if now_kst > (start_dt + timedelta(minutes=15)):
                    to_delete.append(idx)
            except: continue
    if to_delete:
        df = df.drop(to_delete)
        df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
    return df

def process_qr_checkin(df):
    q_params = st.query_params
    if "checkin" in q_params:
        room_code = q_params["checkin"]
        target_room = "1번 스터디룸" if room_code == "room1" else "2번 스터디룸"
        now_kst = get_kst_now().replace(tzinfo=None)
        now_date = str(now_kst.date())
        now_time = now_kst.strftime("%H:%M")
        early_limit = (now_kst + timedelta(minutes=10)).strftime("%H:%M")
        mask = (df["방번호"] == target_room) & (df["날짜"] == now_date) & \
               (df["시작"] <= early_limit) & (df["종료"] > now_time) & (df["출석"] == "미입실")
        if any(mask):
            user_name = df.loc[mask, "이름"].values[0]
            df.loc[mask, "출석"] = "입실완료"
            df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.balloons()
            st.success(f"✅ 인증 성공: {user_name}님, 입실 확인되었습니다!")
            st.query_params.clear()
        else:
            st.warning("⚠️ 인증 실패: 예약 시간이 아니거나 이미 인증되었습니다.")
    return df

# --- [2. 페이지 설정 및 디자인] ---
st.set_page_config(page_title="생명과학대학 스터디룸 예약", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
    :root { --point-color: #A7D7C5; --point-dark: #3E7D6B; }
    .stButton>button { background-color: var(--point-color); color: white; border-radius: 10px; font-weight: bold; border: none; width: 100%; height: 3.2rem; }
    .stButton>button:disabled { background-color: #E0E0E0 !important; color: #9E9E9E !important; cursor: not-allowed !important; }
    .schedule-card, .res-card { padding: 15px; border-radius: 12px; border-left: 6px solid var(--point-color); background-color: rgba(167, 215, 197, 0.1); margin-bottom: 12px; }
    .step-header { color: var(--point-dark); font-weight: bold; border-bottom: 2px solid var(--point-color); padding-bottom: 5px; margin-bottom: 15px; font-size: 1.2rem; }
    .success-receipt { border: 2px dashed var(--point-color); padding: 25px; border-radius: 15px; margin-top: 20px; background-color: white; color: black; }
    .receipt-title { color: var(--point-color); font-size: 1.5rem; font-weight: bold; text-align: center; margin-bottom: 20px; }
    .receipt-item { display: flex; justify-content: space-between; margin-bottom: 10px; border-bottom: 1px solid rgba(167, 215, 197, 0.3); padding-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

now_kst = get_kst_now().replace(tzinfo=None)
current_time_str = now_kst.strftime("%H:%M")
time_options_all = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]

df_all = get_latest_df()
df_all = auto_cleanup_noshow(df_all)
df_all = process_qr_checkin(df_all)

# --- [3. 사이드바 실시간 현황] ---
with st.sidebar:
    st.markdown(f"<h2 style='color:var(--point-color);'>📊 실시간 예약 현황</h2>", unsafe_allow_html=True)
    today_res = df_all[df_all["날짜"] == str(now_kst.date())]
    for r in ["1번 스터디룸", "2번 스터디룸"]:
        with st.expander(f"🚪 {r}", expanded=True):
            room_today = today_res[today_res["방번호"] == r].sort_values(by="시작")
            occ = room_today[((room_today["시작"] <= current_time_str) & (room_today["종료"] > current_time_str)) | 
                             ((room_today["출석"] == "입실완료") & (room_today["종료"] > current_time_str))]
            if not occ.empty:
                current_user = occ.iloc[0]
                status_color = "#3E7D6B" if current_user["출석"] == "입실완료" else "#E67E22"
                st.markdown(f'<h3 style="color:{status_color}; margin-bottom: 5px;">{"현재 이용 중" if current_user["출석"] == "입실완료" else "인증 대기 중"}</h3>', unsafe_allow_html=True)
                st.markdown(f"**⏰ 종료 예정: {current_user['종료']}**")
                if current_user["출석"] == "미입실": st.warning("⚠️ 15분 내 QR 인증 필요")
            else: st.success("현재 비어 있음")
            next_res = room_today[room_today["시작"] > current_time_str]
            if not next_res.empty:
                st.markdown("<p style='font-size: 0.8rem; font-weight: bold;'>📅 다음 예약</p>", unsafe_allow_html=True)
                for _, row in next_res.iterrows(): st.caption(f"🕒 {row['시작']}~{row['종료']}")

# --- [4. 메인 화면 구성] ---
st.title("생명과학대학 스터디룸 예약")
tabs = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 예약 일정", "➕ 시간 연장", "♻️ 반납 및 취소"])

with tabs[0]:
    if 'reserve_success' not in st.session_state:
        st.session_state.reserve_success = False
        st.session_state.last_res = {}

    if not st.session_state.reserve_success:
        st.markdown('<div class="step-header">1. 인원 및 날짜 선택 (오늘/내일만 가능)</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        total_count = c1.number_input("이용 인원 (대표자 포함 3~6명)", min_value=3, max_value=6, value=3)
        date_options = [now_kst.date(), (now_kst + timedelta(days=1)).date()]
        sel_date = c2.selectbox("예약 날짜", date_options, format_func=lambda x: x.strftime("%Y-%m-%d"))

        st.markdown('<div class="step-header">2. 팀원 정보 입력 (학번 10자리)</div>', unsafe_allow_html=True)
        st.write("**👤 대표자 정보**")
        rc1, rc2, rc3 = st.columns([2, 2, 1])
        dept = rc1.selectbox("학과", ["스마트팜과학과", "식품생명공학과", "유전생명공학과", "융합바이오·신소재공학과"], key="reg_dept")
        name = rc2.text_input("이름", key="reg_name")
        sid = rc3.text_input("학번", key="reg_sid", max_chars=10)

        st.write(f"**👥 구성원 정보 (대표자 제외 {total_count-1}명)**")
        member_names, member_ids = [], []
        for i in range(total_count - 1):
            mc1, mc2 = st.columns(2)
            m_n = mc1.text_input(f"팀원 {i+1} 이름", key=f"m_n_{i}")
            m_id = mc2.text_input(f"팀원 {i+1} 학번", key=f"m_id_{i}", max_chars=10)
            member_names.append(m_n.strip()); member_ids.append(m_id.strip())

        st.markdown('<div class="step-header">3. 장소 및 시간 선택</div>', unsafe_allow_html=True)
        sc1, sc2, sc3 = st.columns(3)
        room = sc1.selectbox("장소", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
        threshold_time = (now_kst - timedelta(minutes=15)).strftime("%H:%M")
        available_start = [t for t in time_options_all if t >= threshold_time] if str(sel_date) == str(now_kst.date()) else time_options_all
        st_t = sc2.selectbox("시작", available_start, key="reg_start")
        en_t = sc3.selectbox("종료", [t for t in time_options_all if t > st_t], key="reg_end")

        all_ids = [sid.strip()] + member_ids
        is_ready = name and sid and all(member_names) and all(member_ids) and all(len(idx)==10 and idx.isdigit() for idx in all_ids if idx)
        
        if st.button("🚀 예약 신청", disabled=not is_ready):
            duration = datetime.strptime(en_t, "%H:%M") - datetime.strptime(st_t, "%H:%M")
            duplicate_found, culprit_id = check_team_duplication(all_ids, sel_date)
            
            if duration > timedelta(hours=3): st.error("🚫 최대 3시간까지만 이용 가능합니다.")
            elif duplicate_found: st.error(f"❌ 학번 '{culprit_id}'님은 해당 날짜에 이미 예약이 있습니다. (1인 1일 1회)")
            elif check_overlap(sel_date, st_t, en_t, room): st.error("❌ 이미 예약된 시간입니다.")
            else:
                new_data = [dept, name.strip(), sid.strip(), total_count, str(sel_date), st_t, en_t, room, "미입실", ",".join(member_ids)]
                pd.DataFrame([new_data], columns=df_all.columns).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, encoding='utf-8-sig')
                st.session_state.reserve_success = True
                st.session_state.last_res = {"name": name, "sid": sid, "room": room, "date": str(sel_date), "start": st_t, "end": en_t}
                st.rerun()
    else:
        res = st.session_state.last_res
        st.success("🎉 예약 완료!")
        st.markdown(f'<div class="success-receipt"><div class="receipt-title">🌿 예약 확인서</div><div class="receipt-item"><span>신청자</span><b>{res["name"]} ({res["sid"]})</b></div><div class="receipt-item"><span>장소</span><b>{res["room"]}</b></div><div class="receipt-item"><span>시간</span><b>{res["date"]} / {res["start"]}~{res["end"]}</b></div></div>', unsafe_allow_html=True)
        if st.button("처음으로"): st.session_state.reserve_success = False; st.rerun()

with tabs[1]:
    search_id = st.text_input("학번으로 조회", max_chars=10)
    if st.button("내 예약 찾기"):
        df_v = get_latest_df()
        res = df_v[(df_v["학번"] == search_id) | (df_v["팀원학번"].str.contains(search_id, na=False))]
        if not res.empty:
            for _, r in res.iterrows(): st.markdown(f'<div class="res-card">📍 {r["방번호"]} | {r["날짜"]} | ⏰ {r["시작"]}~{r["종료"]} | {r["출석"]}</div>', unsafe_allow_html=True)
        else: st.error("내역이 없습니다.")

with tabs[2]:
    df_v = get_latest_df()
    if not df_v.empty:
        s_date = st.selectbox("날짜", sorted(df_v["날짜"].unique()), key="view_date")
        day_df = df_v[df_v["날짜"] == s_date].sort_values(by=["방번호", "시작"])
        for r_n in ["1번 스터디룸", "2번 스터디룸"]:
            st.markdown(f"#### 🚪 {r_n}")
            room_day = day_df[day_df["방번호"] == r_n]
            if room_day.empty: st.caption("예약 없음")
            else:
                for _, row in room_day.iterrows(): st.markdown(f'<div class="schedule-card"><b>{row["시작"]}~{row["종료"]}</b> | 예약완료</div>', unsafe_allow_html=True)
    else: st.info("현재 예약이 없습니다.")

with tabs[3]:
    st.markdown('<div class="step-header">➕ 이용 시간 연장</div>', unsafe_allow_html=True)
    en_n, en_id = st.text_input("이름 (연장)", key="ext_n"), st.text_input("학번 (연장)", key="ext_id")
    if st.button("연장 가능 여부 확인", key="btn_ext_check"):
        res_e = df_all[(df_all["이름"] == en_n.strip()) & (df_all["학번"] == en_id.strip()) & (df_all["날짜"] == str(now_kst.date()))]
        if not res_e.empty:
            target = res_e.iloc[-1]
            if target["출석"] != "입실완료": st.error("🚫 QR 인증 후에만 연장이 가능합니다.")
            else:
                end_dt = datetime.combine(now_kst.date(), datetime.strptime(target['종료'], "%H:%M").time())
                if (end_dt - timedelta(minutes=30)) <= now_kst < end_dt:
                    st.session_state['ext_target'] = target; st.success(f"✅ 연장 가능 (현재 종료: {target['종료']})")
                else: st.warning("⚠️ 종료 30분 전부터 신청 가능합니다.")
    if 'ext_target' in st.session_state:
        target = st.session_state['ext_target']
        df_full = get_latest_df()
        next_res = df_full[(df_full["방번호"] == target["방번호"]) & (df_full["날짜"] == target["날짜"]) & (df_full["시작"] >= target["종료"])].sort_values(by="시작")
        limit_t = next_res.iloc[0]["시작"] if not next_res.empty else "23:59"
        limit_dt = datetime.strptime(limit_t, "%H:%M")
        curr_en_dt = datetime.strptime(target['종료'], "%H:%M")
        opts = [(curr_en_dt + timedelta(minutes=30*i)).strftime("%H:%M") for i in range(1, 5) if (curr_en_dt + timedelta(minutes=30*i)).time() <= limit_dt.time()]
        if not opts: st.error(f"❌ 다음 예약({limit_t})으로 인해 연장 불가")
        else:
            new_en = st.selectbox("연장 종료 시각", opts)
            if st.button("연장 확정"):
                idx = df_all[(df_all["이름"] == en_n.strip()) & (df_all["학번"] == en_id.strip()) & (df_all["시작"] == target['시작'])].index
                df_all.loc[idx, "종료"] = new_en
                df_all.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
                st.success(f"✨ {new_en}까지 연장 완료!"); del st.session_state['ext_target']; st.rerun()

with tabs[4]:
    can_n, can_id = st.text_input("이름 (취소)", key="can_n"), st.text_input("학번 (취소)", key="can_id")
    if st.button("조회", key="can_btn"):
        res_c = get_latest_df(); res_c = res_c[(res_c["이름"] == can_n.strip()) & (res_c["학번"] == can_id.strip())]
        if not res_c.empty: st.session_state['cancel_list'] = res_c
    if 'cancel_list' in st.session_state:
        opts = [f"{r['날짜']} | {r['방번호']} ({r['시작']}~{r['종료']})" for _, r in st.session_state['cancel_list'].iterrows()]
        target_idx = st.selectbox("취소 대상 선택", range(len(opts)), format_func=lambda x: opts[x])
        if st.button("최종 취소"):
            t = st.session_state['cancel_list'].iloc[target_idx]
            df_del = get_latest_df().drop(get_latest_df()[(get_latest_df()["이름"] == t["이름"]) & (get_latest_df()["학번"] == t["학번"]) & (get_latest_df()["날짜"] == t["날짜"]) & (get_latest_df()["시작"] == t["시작"])].index)
            df_del.to_csv(DB_FILE, index=False, encoding='utf-8-sig'); del st.session_state['cancel_list']; st.rerun()

with st.expander("🛠️ 관리자"):
    pw = st.text_input("PW", type="password")
    if pw == "bio1234":
        df_ad = get_latest_df(); st.dataframe(df_ad)
        if not df_ad.empty:
            sel = st.selectbox("강제 삭제", range(len(df_ad)), format_func=lambda x: f"{df_ad.iloc[x]['이름']} ({df_ad.iloc[x]['학번']})")
            if st.button("삭제 실행"):
                df_ad.drop(df_ad.index[sel]).to_csv(DB_FILE, index=False, encoding='utf-8-sig'); st.rerun()
