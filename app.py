import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import os
from datetime import datetime, timedelta, timezone

# 사진 저장 폴더
IMG_DIR = "id_cards"
if not os.path.exists(IMG_DIR):
    os.makedirs(IMG_DIR)

# --- [1. 핵심 함수 정의] ---

def get_kst_now():
    return datetime.now(timezone.utc) + timedelta(hours=9)

def get_latest_df(conn):
    """구글 시트에서 실시간 데이터를 읽어옵니다."""
    try:
        # ttl="0s"로 설정하여 캐시 없이 항상 실시간 데이터를 가져옵니다.
        return conn.read(ttl="0s")
    except Exception as e:
        # 오류 발생 시(시트가 비어있을 때 등) 기본 컬럼 반환
        return pd.DataFrame(columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석", "사진파일명"])

# --- [2. 페이지 설정 및 디자인] ---
st.set_page_config(page_title="생명과학대학 스터디룸 예약", page_icon="🌿", layout="wide")

# 구글 시트 연결 (Secrets 설정 기반)
conn = st.connection("gsheets", type=GSheetsConnection)

st.markdown("""
    <style>
    :root { --point-color: #A7D7C5; --point-dark: #3E7D6B; }
    .stButton>button { background-color: var(--point-color); color: white; border-radius: 10px; font-weight: bold; border: none; width: 100%; height: 3.2rem; font-size: 1.1rem; }
    .stButton>button:disabled { background-color: #E0E0E0 !important; color: #9E9E9E !important; cursor: not-allowed !important; }
    .schedule-card, .res-card { padding: 15px; border-radius: 12px; border-left: 6px solid var(--point-color); background-color: rgba(167, 215, 197, 0.1); margin-bottom: 12px; }
    .step-header { color: var(--point-dark); font-weight: bold; border-bottom: 2px solid var(--point-color); padding-bottom: 5px; margin-bottom: 15px; font-size: 1.2rem; }
    .success-receipt { border: 2px dashed var(--point-color); padding: 25px; border-radius: 15px; margin-top: 20px; background-color: white; color: black; }
    </style>
    """, unsafe_allow_html=True)

now_kst = get_kst_now().replace(tzinfo=None)
current_time_str = now_kst.strftime("%H:%M")
time_options_all = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]

# 데이터 로드
df_all = get_latest_df(conn)

# QR 체크인 로직
q_params = st.query_params
if "checkin" in q_params:
    room_code = q_params["checkin"]
    target_room = "1번 스터디룸" if room_code == "room1" else "2번 스터디룸"
    now_date = str(now_kst.date())
    early_limit = (now_kst + timedelta(minutes=10)).strftime("%H:%M")
    mask = (df_all["방번호"] == target_room) & (df_all["날짜"] == now_date) & \
           (df_all["시작"] <= early_limit) & (df_all["종료"] > current_time_str) & (df_all["출석"] == "미입실")
    if any(mask):
        user_name = df_all.loc[mask, "이름"].values[0]
        df_all.loc[mask, "출석"] = "입실완료"
        conn.update(data=df_all) # 업데이트
        st.balloons()
        st.success(f"✅ 인증 성공: {user_name}님, 입실 완료!")
        st.query_params.clear()
    else:
        st.warning("⚠️ 인증 실패: 예약 시간이 아니거나 이미 인증되었습니다.")

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
                st.markdown(f'### <span style="color:{status_color};">{current_user["출석"]}</span>', unsafe_allow_html=True)
                st.markdown(f"**⏰ 종료 예정: {current_user['종료']}**")
                if current_user["출석"] == "미입실": st.warning("⚠️ 15분 내 QR 인증 필요")
            else: st.success("현재 비어 있음")
            next_res = room_today[room_today["시작"] > current_time_str]
            if not next_res.empty:
                st.markdown("<p style='font-size: 0.85rem; font-weight: bold;'>📅 다음 예약</p>", unsafe_allow_html=True)
                for _, row in next_res.iterrows(): st.caption(f"🕒 {row['시작']} ~ {row['종료']}")

# --- [4. 메인 화면 구성] ---
tabs = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 일정", "➕ 시간 연장", "♻️ 반납 및 취소"])

with tabs[0]:
    if 'reserve_success' not in st.session_state:
        st.session_state.reserve_success = False
        st.session_state.last_res = {}

    if not st.session_state.reserve_success:
        st.markdown('<div class="step-header">1. 정보 입력</div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        dept = c1.selectbox("🏢 학과", ["스마트팜과학과", "식품생명공학과", "유전생명공학과", "융합바이오·신소재공학과"], key="reg_dept")
        name = c2.text_input("👤 이름", key="reg_name")
        sid = c3.text_input("🆔 학번 (10자리)", key="reg_sid", max_chars=10)
        count = c4.number_input("👥 인원 (최소 3명)", min_value=3, value=3, key="reg_count")
        
        is_sid_valid = sid.isdigit() and len(sid) == 10
        id_file = st.file_uploader("💳 학생증 사진 업로드", type=['png', 'jpg', 'jpeg'])

        st.markdown('<div class="step-header">2. 장소 및 시간 선택</div>', unsafe_allow_html=True)
        sc1, sc2, tc1, tc2 = st.columns([2, 1, 1, 1])
        room = sc1.selectbox("🚪 장소", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
        date = sc2.date_input("📅 날짜", min_value=now_kst.date(), max_value=now_kst.date() + timedelta(days=13), key="reg_date")
        
        threshold_time = (now_kst - timedelta(minutes=15)).strftime("%H:%M")
        available_start = [t for t in time_options_all if t >= threshold_time] if str(date) == str(now_kst.date()) else time_options_all
        
        if not available_start: st.error("⚠️ 오늘은 예약 가능한 시간이 없습니다.")
        else:
            st_t = tc1.selectbox("⏰ 시작", available_start, key="reg_start")
            en_t = tc2.selectbox("⏰ 종료", [t for t in time_options_all if t > st_t], key="reg_end")
            
            submit_disabled = not (name.strip() and is_sid_valid and id_file)
            
            if st.button("🚀 예약 신청", disabled=submit_disabled):
                duration = datetime.strptime(en_t, "%H:%M") - datetime.strptime(st_t, "%H:%M")
                if duration > timedelta(hours=3): st.error("🚫 최대 3시간까지만 가능합니다.")
                else:
                    img_filename = f"{sid}_{datetime.now().strftime('%m%d%H%M%S')}.png"
                    with open(os.path.join(IMG_DIR, img_filename), "wb") as f:
                        f.write(id_file.getbuffer())
                    
                    new_data = [dept, name.strip(), sid.strip(), count, str(date), st_t, en_t, room, "미입실", img_filename]
                    df_new = pd.concat([df_all, pd.DataFrame([new_data], columns=df_all.columns)], ignore_index=True)
                    conn.update(data=df_new)
                    
                    st.session_state.reserve_success = True
                    st.session_state.last_res = {"name": name, "sid": sid, "room": room, "date": str(date), "start": st_t, "end": en_t}
                    st.rerun()
    else:
        res = st.session_state.last_res
        st.success("🎉 예약 완료! 구글 시트에 저장되었습니다.")
        st.markdown(f'<div class="success-receipt"><div class="receipt-item"><span>신청자</span><b>{res["name"]}</b></div><div class="receipt-item"><span>장소</span><b>{res["room"]}</b></div><div class="receipt-item"><span>시간</span><b>{res["date"]} / {res["start"]}~{res["end"]}</b></div></div>', unsafe_allow_html=True)
        if st.button("처음으로"):
            st.session_state.reserve_success = False
            st.rerun()

with tabs[1]:
    mc1, mc2 = st.columns(2)
    m_n, m_s = mc1.text_input("이름", key="lookup_n"), mc2.text_input("학번", key="lookup_s")
    if st.button("조회"):
        res_list = df_all[(df_all["이름"] == m_n.strip()) & (df_all["학번"] == m_s.strip())]
        if not res_list.empty:
            for _, r in res_list.iterrows(): st.markdown(f'<div class="res-card">📍 {r["방번호"]} | {r["날짜"]} | ⏰ {r["시작"]}~{r["종료"]} | {r["출석"]}</div>', unsafe_allow_html=True)
        else: st.error("내역 없음")

with tabs[3]:
    st.markdown('<div class="step-header">➕ 이용 시간 연장</div>', unsafe_allow_html=True)
    en_n, en_id = st.text_input("이름", key="ext_n"), st.text_input("학번", key="ext_id")
    if st.button("연장 확인"):
        res_e = df_all[(df_all["이름"] == en_n.strip()) & (df_all["학번"] == en_id.strip()) & (df_all["날짜"] == str(now_kst.date()))]
        if not res_e.empty:
            target = res_e.iloc[-1]
            if target["출석"] != "입실완료": st.error("🚫 QR 인증 후에만 연장이 가능합니다.")
            else:
                end_dt = datetime.combine(now_kst.date(), datetime.strptime(target['종료'], "%H:%M").time())
                if (end_dt - timedelta(minutes=30)) <= now_kst < end_dt:
                    st.session_state['ext_target'] = target; st.success(f"연장 가능 (현재 종료: {target['종료']})")
                else: st.warning("종료 30분 전부터 가능합니다.")
    if 'ext_target' in st.session_state:
        target = st.session_state['ext_target']
        new_en = st.selectbox("변경 시각", [t for t in time_options_all if t > target['종료']][:4])
        if st.button("확정"):
            idx = df_all[(df_all["이름"] == en_n.strip()) & (df_all["학번"] == en_id.strip()) & (df_all["시작"] == target['시작'])].index
            df_all.loc[idx, "종료"] = new_en
            conn.update(data=df_all)
            st.success("연장 완료!"); del st.session_state['ext_target']; st.rerun()

with st.expander("🛠️ 관리자"):
    pw = st.text_input("PW", type="password")
    if pw == "bio1234":
        st.dataframe(df_all)
        if not df_all.empty:
            sel = st.selectbox("대상 선택", range(len(df_all)), format_func=lambda x: f"{df_all.iloc[x]['이름']} ({df_all.iloc[x]['학번']})")
            img_path = os.path.join(IMG_DIR, str(df_all.iloc[sel]['사진파일명']))
            if os.path.exists(img_path): st.image(img_path, width=300)
            if st.button("삭제"):
                df_del = df_all.drop(df_all.index[sel])
                conn.update(data=df_del); st.rerun()import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import os
from datetime import datetime, timedelta, timezone

# 사진 저장 폴더
IMG_DIR = "id_cards"
if not os.path.exists(IMG_DIR):
    os.makedirs(IMG_DIR)

# --- [1. 핵심 함수 정의] ---

def get_kst_now():
    return datetime.now(timezone.utc) + timedelta(hours=9)

def get_latest_df(conn):
    """구글 시트에서 실시간 데이터를 읽어옵니다."""
    try:
        # ttl="0s"로 설정하여 캐시 없이 항상 실시간 데이터를 가져옵니다.
        return conn.read(ttl="0s")
    except Exception as e:
        # 오류 발생 시(시트가 비어있을 때 등) 기본 컬럼 반환
        return pd.DataFrame(columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석", "사진파일명"])

# --- [2. 페이지 설정 및 디자인] ---
st.set_page_config(page_title="생명과학대학 스터디룸 예약", page_icon="🌿", layout="wide")

# 구글 시트 연결 (Secrets 설정 기반)
conn = st.connection("gsheets", type=GSheetsConnection)

st.markdown("""
    <style>
    :root { --point-color: #A7D7C5; --point-dark: #3E7D6B; }
    .stButton>button { background-color: var(--point-color); color: white; border-radius: 10px; font-weight: bold; border: none; width: 100%; height: 3.2rem; font-size: 1.1rem; }
    .stButton>button:disabled { background-color: #E0E0E0 !important; color: #9E9E9E !important; cursor: not-allowed !important; }
    .schedule-card, .res-card { padding: 15px; border-radius: 12px; border-left: 6px solid var(--point-color); background-color: rgba(167, 215, 197, 0.1); margin-bottom: 12px; }
    .step-header { color: var(--point-dark); font-weight: bold; border-bottom: 2px solid var(--point-color); padding-bottom: 5px; margin-bottom: 15px; font-size: 1.2rem; }
    .success-receipt { border: 2px dashed var(--point-color); padding: 25px; border-radius: 15px; margin-top: 20px; background-color: white; color: black; }
    </style>
    """, unsafe_allow_html=True)

now_kst = get_kst_now().replace(tzinfo=None)
current_time_str = now_kst.strftime("%H:%M")
time_options_all = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]

# 데이터 로드
df_all = get_latest_df(conn)

# QR 체크인 로직
q_params = st.query_params
if "checkin" in q_params:
    room_code = q_params["checkin"]
    target_room = "1번 스터디룸" if room_code == "room1" else "2번 스터디룸"
    now_date = str(now_kst.date())
    early_limit = (now_kst + timedelta(minutes=10)).strftime("%H:%M")
    mask = (df_all["방번호"] == target_room) & (df_all["날짜"] == now_date) & \
           (df_all["시작"] <= early_limit) & (df_all["종료"] > current_time_str) & (df_all["출석"] == "미입실")
    if any(mask):
        user_name = df_all.loc[mask, "이름"].values[0]
        df_all.loc[mask, "출석"] = "입실완료"
        conn.update(data=df_all) # 업데이트
        st.balloons()
        st.success(f"✅ 인증 성공: {user_name}님, 입실 완료!")
        st.query_params.clear()
    else:
        st.warning("⚠️ 인증 실패: 예약 시간이 아니거나 이미 인증되었습니다.")

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
                st.markdown(f'### <span style="color:{status_color};">{current_user["출석"]}</span>', unsafe_allow_html=True)
                st.markdown(f"**⏰ 종료 예정: {current_user['종료']}**")
                if current_user["출석"] == "미입실": st.warning("⚠️ 15분 내 QR 인증 필요")
            else: st.success("현재 비어 있음")
            next_res = room_today[room_today["시작"] > current_time_str]
            if not next_res.empty:
                st.markdown("<p style='font-size: 0.85rem; font-weight: bold;'>📅 다음 예약</p>", unsafe_allow_html=True)
                for _, row in next_res.iterrows(): st.caption(f"🕒 {row['시작']} ~ {row['종료']}")

# --- [4. 메인 화면 구성] ---
tabs = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 일정", "➕ 시간 연장", "♻️ 반납 및 취소"])

with tabs[0]:
    if 'reserve_success' not in st.session_state:
        st.session_state.reserve_success = False
        st.session_state.last_res = {}

    if not st.session_state.reserve_success:
        st.markdown('<div class="step-header">1. 정보 입력</div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        dept = c1.selectbox("🏢 학과", ["스마트팜과학과", "식품생명공학과", "유전생명공학과", "융합바이오·신소재공학과"], key="reg_dept")
        name = c2.text_input("👤 이름", key="reg_name")
        sid = c3.text_input("🆔 학번 (10자리)", key="reg_sid", max_chars=10)
        count = c4.number_input("👥 인원 (최소 3명)", min_value=3, value=3, key="reg_count")
        
        is_sid_valid = sid.isdigit() and len(sid) == 10
        id_file = st.file_uploader("💳 학생증 사진 업로드", type=['png', 'jpg', 'jpeg'])

        st.markdown('<div class="step-header">2. 장소 및 시간 선택</div>', unsafe_allow_html=True)
        sc1, sc2, tc1, tc2 = st.columns([2, 1, 1, 1])
        room = sc1.selectbox("🚪 장소", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
        date = sc2.date_input("📅 날짜", min_value=now_kst.date(), max_value=now_kst.date() + timedelta(days=13), key="reg_date")
        
        threshold_time = (now_kst - timedelta(minutes=15)).strftime("%H:%M")
        available_start = [t for t in time_options_all if t >= threshold_time] if str(date) == str(now_kst.date()) else time_options_all
        
        if not available_start: st.error("⚠️ 오늘은 예약 가능한 시간이 없습니다.")
        else:
            st_t = tc1.selectbox("⏰ 시작", available_start, key="reg_start")
            en_t = tc2.selectbox("⏰ 종료", [t for t in time_options_all if t > st_t], key="reg_end")
            
            submit_disabled = not (name.strip() and is_sid_valid and id_file)
            
            if st.button("🚀 예약 신청", disabled=submit_disabled):
                duration = datetime.strptime(en_t, "%H:%M") - datetime.strptime(st_t, "%H:%M")
                if duration > timedelta(hours=3): st.error("🚫 최대 3시간까지만 가능합니다.")
                else:
                    img_filename = f"{sid}_{datetime.now().strftime('%m%d%H%M%S')}.png"
                    with open(os.path.join(IMG_DIR, img_filename), "wb") as f:
                        f.write(id_file.getbuffer())
                    
                    new_data = [dept, name.strip(), sid.strip(), count, str(date), st_t, en_t, room, "미입실", img_filename]
                    df_new = pd.concat([df_all, pd.DataFrame([new_data], columns=df_all.columns)], ignore_index=True)
                    conn.update(data=df_new)
                    
                    st.session_state.reserve_success = True
                    st.session_state.last_res = {"name": name, "sid": sid, "room": room, "date": str(date), "start": st_t, "end": en_t}
                    st.rerun()
    else:
        res = st.session_state.last_res
        st.success("🎉 예약 완료! 구글 시트에 저장되었습니다.")
        st.markdown(f'<div class="success-receipt"><div class="receipt-item"><span>신청자</span><b>{res["name"]}</b></div><div class="receipt-item"><span>장소</span><b>{res["room"]}</b></div><div class="receipt-item"><span>시간</span><b>{res["date"]} / {res["start"]}~{res["end"]}</b></div></div>', unsafe_allow_html=True)
        if st.button("처음으로"):
            st.session_state.reserve_success = False
            st.rerun()

with tabs[1]:
    mc1, mc2 = st.columns(2)
    m_n, m_s = mc1.text_input("이름", key="lookup_n"), mc2.text_input("학번", key="lookup_s")
    if st.button("조회"):
        res_list = df_all[(df_all["이름"] == m_n.strip()) & (df_all["학번"] == m_s.strip())]
        if not res_list.empty:
            for _, r in res_list.iterrows(): st.markdown(f'<div class="res-card">📍 {r["방번호"]} | {r["날짜"]} | ⏰ {r["시작"]}~{r["종료"]} | {r["출석"]}</div>', unsafe_allow_html=True)
        else: st.error("내역 없음")

with tabs[3]:
    st.markdown('<div class="step-header">➕ 이용 시간 연장</div>', unsafe_allow_html=True)
    en_n, en_id = st.text_input("이름", key="ext_n"), st.text_input("학번", key="ext_id")
    if st.button("연장 확인"):
        res_e = df_all[(df_all["이름"] == en_n.strip()) & (df_all["학번"] == en_id.strip()) & (df_all["날짜"] == str(now_kst.date()))]
        if not res_e.empty:
            target = res_e.iloc[-1]
            if target["출석"] != "입실완료": st.error("🚫 QR 인증 후에만 연장이 가능합니다.")
            else:
                end_dt = datetime.combine(now_kst.date(), datetime.strptime(target['종료'], "%H:%M").time())
                if (end_dt - timedelta(minutes=30)) <= now_kst < end_dt:
                    st.session_state['ext_target'] = target; st.success(f"연장 가능 (현재 종료: {target['종료']})")
                else: st.warning("종료 30분 전부터 가능합니다.")
    if 'ext_target' in st.session_state:
        target = st.session_state['ext_target']
        new_en = st.selectbox("변경 시각", [t for t in time_options_all if t > target['종료']][:4])
        if st.button("확정"):
            idx = df_all[(df_all["이름"] == en_n.strip()) & (df_all["학번"] == en_id.strip()) & (df_all["시작"] == target['시작'])].index
            df_all.loc[idx, "종료"] = new_en
            conn.update(data=df_all)
            st.success("연장 완료!"); del st.session_state['ext_target']; st.rerun()

with st.expander("🛠️ 관리자"):
    pw = st.text_input("PW", type="password")
    if pw == "bio1234":
        st.dataframe(df_all)
        if not df_all.empty:
            sel = st.selectbox("대상 선택", range(len(df_all)), format_func=lambda x: f"{df_all.iloc[x]['이름']} ({df_all.iloc[x]['학번']})")
            img_path = os.path.join(IMG_DIR, str(df_all.iloc[sel]['사진파일명']))
            if os.path.exists(img_path): st.image(img_path, width=300)
            if st.button("삭제"):
                df_del = df_all.drop(df_all.index[sel])
                conn.update(data=df_del); st.rerun()
