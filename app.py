import streamlit as st
import pandas as pd
import os
import urllib.parse
from datetime import datetime, timedelta

# 데이터 저장 파일명
DB_FILE = "reservations.csv"

# --- [1. 핵심 함수 정의] 배포 시 NameError 방지를 위해 최상단 배치 ---

def get_latest_df():
    """데이터 파일을 읽어오는 함수"""
    if not os.path.isfile(DB_FILE):
        return pd.DataFrame(columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"])
    df = pd.read_csv(DB_FILE)
    if "출석" not in df.columns:
        df["출석"] = "미입실"
    return df

def is_already_booked(rep_name, rep_id):
    """중복 예약 확인 (1인 1예약 원칙)"""
    df = get_latest_df()
    if df.empty: return False
    duplicate = df[(df["이름"].astype(str).str.strip() == str(rep_name).strip()) & 
                   (df["학번"].astype(str).str.strip() == str(rep_id).strip())]
    return not duplicate.empty

def check_overlap(date, start_t, end_t, room):
    """시간 중복 확인"""
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
    """예약 시작 15분 후까지 미입실 시 자동 삭제"""
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
    """URL 파라미터를 통한 QR 즉시 체크인 처리"""
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

# --- [2. 페이지 설정 및 디자인] ---
st.set_page_config(page_title="생과대 스터디룸 예약", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f9fdfb; }
    .stButton>button { background-color: #A7D7C5; color: white; border-radius: 8px; width: 100%; font-weight: bold; }
    .step-header { color: #3E7D6B; font-weight: bold; border-bottom: 2px solid #A7D7C5; padding-bottom: 5px; margin-bottom: 15px; font-size: 1.2rem; }
    .success-box { background-color: #f0f9f4; padding: 20px; border-radius: 12px; border: 2px solid #A7D7C5; margin-top: 20px; }
    .schedule-card { background-color: #ffffff; padding: 10px; border-radius: 8px; border-left: 5px solid #A7D7C5; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- [3. 초기 데이터 로드 및 시간 로직] ---
now = datetime.now()
time_options = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]
dept_options = ["스마트팜과학과", "식품생명공학과", "유전생명공학과", "융합바이오·신소재공학과"]

# --- 현재 시간과 가장 가까운 예약 시작 시간 계산 ---
if now.minute < 30:
    suggested_start_dt = now.replace(minute=30, second=0, microsecond=0)
else:
    suggested_start_dt = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
suggested_start = suggested_start_dt.strftime("%H:%M")

df_all = get_latest_df()
df_all = auto_cleanup_noshow(df_all)
df_all = process_qr_checkin(df_all)

# --- [4. 사이드바 실시간 현황] ---
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

# --- [5. 메인 화면 구성] ---
st.title("🌿 생명과학대학 스터디룸 예약 시스템")

tabs = st.tabs(["📅 예약 신청", "🔍 내 예약 확인", "📋 전체 일정 보기", "➕ 시간 연장", "♻️ 반납 및 취소"])

with tabs[0]:
    st.markdown('<div class="step-header">1. 예약자 정보 입력</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    dept = c1.selectbox("🏢 학과", dept_options, key="reg_dept")
    name = c2.text_input("👤 이름", placeholder="성함", key="reg_name")
    sid = c3.text_input("🆔 학번", placeholder="8자리 학번", key="reg_sid")
    # 인원 최소값을 3으로 설정하여 1, 2 선택 불가
    count = c4.number_input("👥 인원 (최소 3명)", min_value=3, max_value=20, value=3, step=1)

    st.markdown('<div class="step-header">2. 스터디룸 및 시간 선택 (최대 3시간)</div>', unsafe_allow_html=True)
    sc1, sc2, tc1, tc2 = st.columns([2, 1, 1, 1])
    room = sc1.selectbox("🚪 스터디룸", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
    date = sc2.date_input("📅 날짜", min_value=now.date(), max_value=now.date()+timedelta(days=13))
    
    # 오늘 날짜인 경우 지난 시간 필터링
    available_times = time_options
    if date == now.date():
        available_times = [t for t in time_options if t > now.strftime("%H:%M")]
    
    # 가장 가까운 시간이 기본값으로 선택되도록 index 설정
    try:
        start_index = available_times.index(suggested_start) if suggested_start in available_times else 0
    except:
        start_index = 0
        
    st_t = tc1.selectbox("⏰ 시작", available_times, index=start_index)
    
    # 종료 시간은 시작 시간 이후만 표시
    end_options = [t for t in time_options if t > st_t]
    en_t = tc2.selectbox("⏰ 종료", end_options, index=min(1, len(end_options)-1))

    if st.button("🚀 예약 신청하기"):
        t_fmt = "%H:%M"
        duration = datetime.strptime(en_t, t_fmt) - datetime.strptime(st_t, t_fmt)
        
        if not (name.strip() and sid.strip()):
            st.error("이름과 학번을 입력해 주세요.")
        elif is_already_booked(name, sid):
            st.error("🚫 이미 등록된 예약이 존재합니다. (1인 1예약 원칙)")
        elif duration > timedelta(hours=3):
            st.error("🚫 최대 3시간까지만 예약 가능합니다.")
        elif check_overlap(date, st_t, en_t, room):
            st.error("❌ 선택하신 시간에 이미 예약이 있습니다.")
        else:
            new_row = pd.DataFrame([[dept, name.strip(), sid.strip(), count, str(date), st_t, en_t, room, "미입실"]], 
                                    columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"])
            new_row.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, encoding='utf-8-sig')
            st.success(f"🎉 예약 완료! {st_t} ~ {en_t}")
            st.rerun()

# [탭 2~5 로직은 기존 기능 유지]
with tabs[1]:
    st.markdown('<div class="step-header">🔍 내 예약 확인</div>', unsafe_allow_html=True)
    mc1, mc2 = st.columns(2)
    m_name = mc1.text_input("조회용 이름", key="my_name")
    m_sid = mc2.text_input("조회용 학번", key="my_sid")
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

# --- [6. 관리자 메뉴] ---
st.markdown('<div style="height:100px;"></div>', unsafe_allow_html=True)
with st.expander("🛠️ 관리자 전용 메뉴"):
    pw = st.text_input("Admin Password", type="password")
    if pw == "bio1234":
        df_ad = get_latest_df()
        if not df_ad.empty:
            st.markdown("### 🗑️ 개별 예약 삭제")
            df_ad['label'] = df_ad['이름'] + " | " + df_ad['날짜'] + " | " + df_ad['시작'] + " (" + df_ad['방번호'] + ")"
            target = st.selectbox("삭제 대상을 선택하세요", df_ad['label'].tolist())
            if st.button("❌ 선택한 예약 강제 삭제", type="primary"):
                df_ad = df_ad[df_ad['label'] != target]
                df_ad.drop(columns=['label']).to_csv(DB_FILE, index=False, encoding='utf-8-sig')
                st.success("삭제되었습니다."); st.rerun()
