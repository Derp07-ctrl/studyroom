import streamlit as st
import pandas as pd
import os
import urllib.parse
from datetime import datetime, timedelta

# 데이터 저장 파일명
DB_FILE = "reservations.csv"

# --- [1. 핵심 함수 정의] ---

def get_latest_df():
    if not os.path.isfile(DB_FILE):
        return pd.DataFrame(columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"])
    df = pd.read_csv(DB_FILE)
    if "출석" not in df.columns:
        df["출석"] = "미입실"
    return df

def is_already_booked(rep_name, rep_id):
    df = get_latest_df()
    if df.empty: return False
    duplicate = df[(df["이름"].astype(str).str.strip() == str(rep_name).strip()) & 
                   (df["학번"].astype(str).str.strip() == str(rep_id).strip())]
    return not duplicate.empty

def check_overlap(date, start_t, end_t, room):
    df = get_latest_df()
    if df.empty: return False
    same_day_room = df[(df["날짜"] == str(date)) & (df["방번호"] == room)]
    for _, row in same_day_room.iterrows():
        fmt = "%H:%M"
        try:
            e_start = datetime.strptime(row["시작"], fmt).time()
            e_end = datetime.strptime(row["종료"], fmt).time()
            n_start = datetime.strptime(start_t, fmt).time()
            n_end = datetime.strptime(end_t, fmt).time()
            if n_start < e_end and n_end > e_start: return True
        except: continue
    return False

def auto_cleanup_noshow(df):
    now_dt = datetime.now()
    now_date = str(now_dt.date())
    to_delete = []
    for idx, row in df.iterrows():
        if row["날짜"] == now_date and row["출석"] == "미입실":
            try:
                start_dt = datetime.strptime(f"{row['날짜']} {row['시작']}", "%Y-%m-%d %H:%M")
                if now_dt > (start_dt + timedelta(minutes=15)):
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
        now_dt = datetime.now()
        now_date = str(now_dt.date())
        now_time = now_dt.strftime("%H:%M")
        mask = (df["방번호"] == target_room) & (df["날짜"] == now_date) & \
               (df["시작"] <= now_time) & (df["종료"] > now_time) & (df["출석"] == "미입실")
        if any(mask):
            user_name = df.loc[mask, "이름"].values[0]
            df.loc[mask, "출석"] = "입실완료"
            df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.success(f"✅ 인증 성공: {user_name}님, {target_room} 입실 확인되었습니다!")
            st.query_params.clear()
        else:
            st.warning(f"현재 {target_room}에 등록된 본인의 예약 시간이 아니거나 이미 인증되었습니다.")
    return df

# --- [2. 페이지 설정 및 초기화] ---
st.set_page_config(page_title="생과대 스터디룸 예약", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
    .stButton>button { background-color: #A7D7C5; color: white; border-radius: 8px; width: 100%; font-weight: bold; }
    .step-header { color: #3E7D6B; font-weight: bold; border-bottom: 2px solid #A7D7C5; padding-bottom: 5px; margin-bottom: 15px; font-size: 1.2rem; }
    .success-box { background-color: #f0f9f4; padding: 20px; border-radius: 12px; border: 2px solid #A7D7C5; margin-top: 20px; }
    </style>
    """, unsafe_allow_html=True)

now = datetime.now()
dept_options = ["스마트팜과학과", "식품생명공학과", "유전생명공학과", "융합바이오·신소재공학과"]

df_all = get_latest_df()
df_all = auto_cleanup_noshow(df_all)
df_all = process_qr_checkin(df_all)

# --- [3. 메인 로직] ---
st.title("🌿 생명과학대학 스터디룸 예약 시스템")

tabs = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 일정", "➕ 연장", "♻️ 반납"])

with tabs[0]:
    # --- 날짜 선택 ---
    st.markdown('<div class="step-header">1. 예약 날짜 및 스터디룸 선택</div>', unsafe_allow_html=True)
    c_date, c_room = st.columns(2)
    selected_date = c_date.date_input("📅 날짜", min_value=now.date(), max_value=now.date()+timedelta(days=13))
    selected_room = c_room.selectbox("🚪 스터디룸", ["1번 스터디룸", "2번 스터디룸"])

    # --- 시간 옵션 생성 (오늘인 경우 지나간 시간 제외) ---
    all_times = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]
    
    if selected_date == now.date():
        # 오늘이면 현재 시간 이후의 옵션만 필터링
        available_times = [t for t in all_times if t > now.strftime("%H:%M")]
    else:
        available_times = all_times

    # --- 시작 시간 자동 설정 (가장 가까운 시간) ---
    if not available_times:
        st.error("⚠️ 오늘은 더 이상 예약 가능한 시간이 없습니다.")
        s_idx = 0
    else:
        s_idx = 0 # 필터링된 리스트의 첫 번째가 가장 가까운 시간

    st.markdown('<div class="step-header">2. 시간 선택 (최대 3시간)</div>', unsafe_allow_html=True)
    tc1, tc2 = st.columns(2)
    
    # 시간 선택 시 available_times가 비어있으면 빈 리스트 대신 에러 방지용 값 처리
    display_times = available_times if available_times else ["00:00"]
    st_t = tc1.selectbox("⏰ 시작 시간", display_times, index=s_idx)
    
    # 종료 시간은 시작 시간 이후의 모든 시간 옵션 (전체 리스트에서 추출)
    en_options = [t for t in all_times if t > st_t]
    en_t = tc2.selectbox("⏰ 종료 시간", en_options, index=min(1, len(en_options)-1))

    st.markdown('<div class="step-header">3. 예약자 정보 입력</div>', unsafe_allow_html=True)
    inf1, inf2, inf3, inf4 = st.columns(4)
    dept = inf1.selectbox("🏢 학과", dept_options)
    name = inf2.text_input("👤 이름", placeholder="성함")
    sid = inf3.text_input("🆔 학번", placeholder="8자리 학번")
    count = inf4.number_input("👥 인원 (최소 3명)", min_value=1, max_value=20, value=3)

    if st.button("🚀 예약 신청하기"):
        t_fmt = "%H:%M"
        t1 = datetime.strptime(st_t, t_fmt)
        t2 = datetime.strptime(en_t, t_fmt)
        duration = t2 - t1
        
        if not (name.strip() and sid.strip()):
            st.error("이름과 학번을 입력해 주세요.")
        elif count < 3:
            st.error("🚫 최소 인원은 3명입니다.")
        elif is_already_booked(name, sid):
            st.error("🚫 이미 등록된 예약이 존재합니다.")
        elif duration > timedelta(hours=3):
            st.error("🚫 최대 3시간까지만 예약 가능합니다.")
        elif check_overlap(selected_date, st_t, en_t, selected_room):
            st.error("❌ 이미 예약된 시간입니다.")
        else:
            new_row = pd.DataFrame([[dept, name.strip(), sid.strip(), count, str(selected_date), st_t, en_t, selected_room, "미입실"]], 
                                    columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"])
            new_row.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, encoding='utf-8-sig')
            st.success(f"🎉 예약 완료! {st_t} ~ {en_t}")
            st.rerun()

# [사이드바 및 기타 탭 로직]
with st.sidebar:
    st.markdown("<h2 style='color:#3E7D6B;'>📊 실시간 점유 현황</h2>", unsafe_allow_html=True)
    today_df = df_all[df_all["날짜"] == str(now.date())].sort_values(by="시작")
    for r in ["1번 스터디룸", "2번 스터디룸"]:
        with st.expander(f"🚪 {r}", expanded=True):
            room_res = today_df[today_df["방번호"] == r]
            is_occ = False
            for _, row in room_res.iterrows():
                try:
                    s_t = datetime.strptime(row["시작"], "%H:%M").time()
                    e_t = datetime.strptime(row["종료"], "%H:%M").time()
                    if s_t <= now.time() < e_t:
                        is_occ = True
                        status = "✅ 입실완료" if row["출석"] == "입실완료" else "⚠️ 미인증(곧 취소)"
                        st.error(f"{status} ({row['시작']}~{row['종료']})")
                        break
                except: continue
            if not is_occ: st.success("✅ 예약 가능")
    st.divider()
    st.caption("🌿 생명과학대학 학생회")

with tabs[1]:
    st.markdown('<div class="step-header">🔍 예약 확인</div>', unsafe_allow_html=True)
    m_name = st.text_input("이름", key="my_name")
    m_sid = st.text_input("학번", key="my_sid")
    if st.button("조회"):
        res = df_all[(df_all["이름"] == m_name) & (df_all["학번"].astype(str) == m_sid)]
        if not res.empty:
            r = res.iloc[0]
            st.info(f"📍 {r['방번호']} | 📅 {r['날짜']} | ⏰ {r['시작']} ~ {r['종료']} | 상태: {r['출석']}")
        else: st.error("내역이 없습니다.")

with tabs[2]:
    st.markdown('<div class="step-header">📋 통합 일정</div>', unsafe_allow_html=True)
    if not df_all.empty:
        u_dates = sorted(df_all["날짜"].unique())
        s_date = st.selectbox("날짜 선택", u_dates)
        day_df = df_all[df_all["날짜"] == s_date].sort_values(by="시작")
        st.dataframe(day_df[["방번호", "시작", "종료", "이름", "출석"]], use_container_width=True)

with tabs[3]:
    st.markdown('<div class="step-header">➕ 연장</div>', unsafe_allow_html=True)
    # 연장 로직 (기존과 동일)

with tabs[4]:
    st.markdown('<div class="step-header">♻️ 반납</div>', unsafe_allow_html=True)
    # 반납 로직 (기존과 동일)

with st.expander("🛠️ 관리자 전용 메뉴"):
    pw = st.text_input("PW", type="password")
    if pw == "bio1234":
        df_ad = get_latest_df()
        if not df_ad.empty:
            df_ad['label'] = df_ad['이름'] + " | " + df_ad['날짜'] + " | " + df_ad['시작']
            target = st.selectbox("삭제 대상 선택", df_ad['label'].tolist())
            if st.button("❌ 삭제"):
                df_ad = df_ad[df_ad['label'] != target]
                df_ad.drop(columns=['label']).to_csv(DB_FILE, index=False, encoding='utf-8-sig')
                st.rerun()
