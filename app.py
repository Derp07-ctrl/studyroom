import streamlit as st
import pandas as pd
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

# 데이터 저장 파일명
DB_FILE = "reservations.csv"

# --- [1. 핵심 함수 정의] ---

def get_kst_now():
    """서버 시간(UTC)을 한국 시간(KST)으로 변환합니다."""
    return datetime.now(timezone.utc) + timedelta(hours=9)

def get_latest_df():
    if not os.path.isfile(DB_FILE):
        return pd.DataFrame(columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"])
    df = pd.read_csv(DB_FILE)
    if "출석" not in df.columns:
        df["출석"] = "미입실"
    for col in ["이름", "학번", "날짜", "시작", "종료", "방번호"]:
        df[col] = df[col].astype(str).str.strip()
    return df

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
    """URL 파라미터를 통한 QR 즉시 체크인 (조기 입실 로직 포함)"""
    q_params = st.query_params
    if "checkin" in q_params:
        room_code = q_params["checkin"]
        target_room = "1번 스터디룸" if room_code == "room1" else "2번 스터디룸"
        now_kst = get_kst_now().replace(tzinfo=None)
        now_date = str(now_kst.date())
        now_time = now_kst.strftime("%H:%M")
        
        # 10분 전부터 체크인 허용 범위 설정
        early_limit = (now_kst + timedelta(minutes=10)).strftime("%H:%M")
        
        # 조건: (시작 전 10분 내 ~ 종료 전까지) & 미입실
        mask = (df["방번호"] == target_room) & \
               (df["날짜"] == now_date) & \
               (df["시작"] <= early_limit) & \
               (df["종료"] > now_time) & \
               (df["출석"] == "미입실")
        
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

# --- [2. 디자인 및 테마 설정] ---
st.set_page_config(page_title="생과대 스터디룸 예약", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
    :root { --point-color: #A7D7C5; --point-dark: #3E7D6B; }
    .stButton>button { background-color: var(--point-color); color: white; border-radius: 10px; font-weight: bold; border: none; width: 100%; }
    .schedule-card, .res-card { padding: 15px; border-radius: 12px; border-left: 6px solid var(--point-color); background-color: rgba(167, 215, 197, 0.1); margin-bottom: 12px; }
    .step-header { color: var(--point-dark); font-weight: bold; border-bottom: 2px solid var(--point-color); padding-bottom: 5px; margin-bottom: 15px; font-size: 1.2rem; }
    </style>
    """, unsafe_allow_html=True)

now_kst = get_kst_now().replace(tzinfo=None)
current_time_str = now_kst.strftime("%H:%M")
time_options_all = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]
dept_options = ["스마트팜과학과", "식품생명공학과", "유전생명공학과", "융합바이오·신소재공학과"]

df_all = get_latest_df()
df_all = auto_cleanup_noshow(df_all)
df_all = process_qr_checkin(df_all)

# --- [3. 사이드바 실시간 현황 (조기 입실 반영)] ---
with st.sidebar:
    st.markdown(f"<h2 style='color:var(--point-color);'>📊 실시간 현황</h2>", unsafe_allow_html=True)
    st.info(f"🕒 **현재 시각** {current_time_str}")
    
    today_date = str(now_kst.date())
    today_res = df_all[df_all["날짜"] == today_date]
    
    for r in ["1번 스터디룸", "2번 스터디룸"]:
        with st.expander(f"🚪 {r}", expanded=True):
            room_today = today_res[today_res["방번호"] == r].sort_values(by="시작")
            
            # 1. 정규 시간 사용 중이거나, 2. 조기 입실 인증을 완료한 사람 찾기
            occ = room_today[
                ((room_today["시작"] <= current_time_str) & (room_today["종료"] > current_time_str)) | 
                ((room_today["출석"] == "입실완료") & (room_today["종료"] > current_time_str))
            ]
            
            if not occ.empty:
                current_user = occ.iloc[0]
                status_text = "✅ 현재 사용 중" if current_user["출석"] == "입실완료" else "⚠️ 현재 예약 중"
                st.error(status_text)
                st.markdown(f"""
                    <div style="font-size: 0.85rem; font-weight: bold;">
                        👤 {current_user['이름']}님 팀<br>
                        ⏰ {current_user['시작']} ~ {current_user['종료']}
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.success("✨ 현재 이용 가능")
                next_res = room_today[room_today["시작"] > current_time_str]
                if not next_res.empty:
                    next_one = next_res.iloc[0]
                    st.caption(f"📅 다음 예약: {next_one['시작']} ({next_one['이름']}님)")
                else:
                    st.caption("오늘 남은 예약 없음")

# --- [4. 메인 화면 구성] ---
st.title("🌿 스터디룸 예약 시스템")
tabs = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 일정", "➕ 시간 연장", "♻️ 반납 및 취소"])

with tabs[0]:
    st.markdown('<div class="step-header">1. 정보 입력</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    dept = c1.selectbox("🏢 학과", dept_options, key="reg_dept")
    name = c2.text_input("👤 이름", placeholder="성함", key="reg_name")
    sid = c3.text_input("🆔 학번", placeholder="8자리", key="reg_sid")
    count = c4.number_input("👥 인원 (최소 3명)", min_value=3, max_value=20, value=3, key="reg_count")

    sc1, sc2, tc1, tc2 = st.columns([2, 1, 1, 1])
    room = sc1.selectbox("🚪 장소", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
    date = sc2.date_input("📅 날짜", min_value=now_kst.date(), key="reg_date")
    
    available_start = [t for t in time_options_all if t > current_time_str] if str(date) == today_date else time_options_all
    if not available_start: st.error("오늘 예약 종료")
    else:
        st_t = tc1.selectbox("⏰ 시작", available_start, index=0, key="reg_start")
        en_t = tc2.selectbox("⏰ 종료", [t for t in time_options_all if t > st_t], index=0, key="reg_end")
        if st.button("🚀 예약 신청", key="btn_reservation"):
            duration = datetime.strptime(en_t, "%H:%M") - datetime.strptime(st_t, "%H:%M")
            if not (name.strip() and sid.strip()): st.error("정보 입력")
            elif is_already_booked(name, sid): st.error("🚫 이미 예약 내역이 존재합니다.")
            elif duration > timedelta(hours=3): st.error("🚫 최대 3시간")
            elif check_overlap(date, st_t, en_t, room): st.error("❌ 중복 시간")
            else:
                pd.DataFrame([[dept, name.strip(), sid.strip(), count, str(date), st_t, en_t, room, "미입실"]], columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"]).to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, encoding='utf-8-sig')
                st.success("예약 완료!"); st.rerun()

with tabs[1]:
    mc1, mc2 = st.columns(2)
    m_n, m_s = mc1.text_input("조회 이름", key="lookup_n"), mc2.text_input("조회 학번", key="lookup_s")
    if st.button("조회", key="btn_lookup"):
        df_l = get_latest_df()
        res = df_l[(df_l["이름"] == m_n.strip()) & (df_l["학번"] == m_s.strip())]
        if not res.empty:
            for _, r in res.iterrows(): st.markdown(f'<div class="res-card">📍 {r["방번호"]} | {r["날짜"]} | ⏰ {r["시작"]}~{r["종료"]} | 상태: {r["출석"]}</div>', unsafe_allow_html=True)
        else: st.error("내역 없음")

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
                for _, row in room_day.iterrows(): st.markdown(f'<div class="schedule-card"><b>{row["시작"]}~{row["종료"]}</b> | {row["이름"]} ({row["출석"]})</div>', unsafe_allow_html=True)

with tabs[3]:
    en_n, en_id = st.text_input("이름", key="ext_n"), st.text_input("학번", key="ext_id")
    if st.button("연장 확인", key="btn_ext_check"):
        df_e = get_latest_df()
        res_e = df_e[(df_e["이름"] == en_n.strip()) & (df_e["학번"] == en_id.strip()) & (df_e["날짜"] == today_date)]
        if not res_e.empty: st.session_state['ext_target'] = res_e.iloc[-1]; st.success(f"현재 종료: {st.session_state['ext_target']['종료']}. 연장 가능")
    if 'ext_target' in st.session_state:
        new_en = st.selectbox("새 종료 시간", [t for t in time_options_all if t > st.session_state['ext_target']['종료']][:4], key="ext_sel")
        if st.button("확정", key="btn_ext_confirm"):
            df_up = get_latest_df()
            idx = df_up[(df_up["이름"] == en_n.strip()) & (df_up["학번"] == en_id.strip()) & (df_up["시작"] == st.session_state['ext_target']['시작'])].index
            df_up.loc[idx, "종료"] = new_en; df_up.to_csv(DB_FILE, index=False, encoding='utf-8-sig'); st.rerun()

with tabs[4]:
    can_n, can_id = st.text_input("이름", key="can_n"), st.text_input("학번", key="can_id")
    if st.button("조회", key="btn_can_lookup"):
        res_c = get_latest_df()[(get_latest_df()["이름"] == can_n.strip()) & (get_latest_df()["학번"] == can_id.strip())]
        if not res_c.empty: st.session_state['cancel_list'] = res_c
    if 'cancel_list' in st.session_state:
        opts = [f"{r['날짜']} | {r['방번호']} ({r['시작']}~{r['종료']})" for _, r in st.session_state['cancel_list'].iterrows()]
        target_idx = st.selectbox("취소 대상", range(len(opts)), format_func=lambda x: opts[x])
        if st.button("취소 확정", type="primary"):
            df_del = get_latest_df(); t = st.session_state['cancel_list'].iloc[target_idx]
            df_del.drop(df_del[(df_del["이름"] == t["이름"]) & (df_del["학번"] == t["학번"]) & (df_del["날짜"] == t["날짜"]) & (df_del["시작"] == t["시작"])].index).to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            del st.session_state['cancel_list']; st.rerun()

with st.expander("🛠️ 관리자"):
    pw = st.text_input("PW", type="password", key="admin_pw")
    if pw == "bio1234":
        df_ad = get_latest_df()
        st.dataframe(df_ad)
        if st.button("삭제", key="admin_del"): pass
