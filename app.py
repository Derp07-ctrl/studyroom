import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta

# 데이터 저장 파일명
DB_FILE = "reservations.csv"

# --- [핵심 함수 정의] 모든 함수는 실행 로직보다 위에 있어야 합니다 ---

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
    now = datetime.now()
    now_date = str(now.date())
    to_delete = []
    for idx, row in df.iterrows():
        if row["날짜"] == now_date and row["출석"] == "미입실":
            start_dt = datetime.strptime(f"{row['날짜']} {row['시작']}", "%Y-%m-%d %H:%M")
            if now > (start_dt + timedelta(minutes=15)):
                to_delete.append(idx)
    if to_delete:
        df = df.drop(to_delete)
        df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
    return df

def process_qr_checkin(df):
    """QR 코드 스캔 시 즉시 체크인 처리"""
    q_params = st.query_params
    if "checkin" in q_params:
        room_code = q_params["checkin"]
        target_room = "1번 스터디룸" if room_code == "room1" else "2번 스터디룸"
        now = datetime.now()
        now_date = str(now.date())
        now_time = now.strftime("%H:%M")

        mask = (df["방번호"] == target_room) & \
               (df["날짜"] == now_date) & \
               (df["시작"] <= now_time) & \
               (df["종료"] > now_time) & \
               (df["출석"] == "미입실")
        
        if any(mask):
            user_name = df.loc[mask, "이름"].values[0]
            df.loc[mask, "출석"] = "입실완료"
            df.to_csv(DB_FILE, index=False, encoding='utf-8-sig')
            st.success(f"✅ 인증 성공: {user_name}님, {target_room} 입실 확인되었습니다!")
            st.query_params.clear()
        else:
            st.warning(f"현재 {target_room}에 등록된 본인의 예약 시간이 아니거나 이미 인증되었습니다.")
    return df

# --- 페이지 설정 및 디자인 ---
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

# --- 초기 설정 및 데이터 처리 ---
time_options = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in (0, 30)]
dept_options = ["스마트팜과학과", "식품생명공학과", "유전생명공학과", "융합바이오·신소재공학과"]
now = datetime.now()

# 데이터 로드 및 자동 관리 실행
df_all = get_latest_df()
df_all = auto_cleanup_noshow(df_all)
df_all = process_qr_checkin(df_all)

# --- 사이드바 ---
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

# --- 메인 화면 ---
st.title("🌿 생명과학대학 스터디룸 예약 시스템")

tabs = st.tabs(["📅 예약 신청", "🔍 예약 확인", "📋 전체 일정", "➕ 연장", "♻️ 반납"])

with tabs[0]:
    st.markdown('<div class="step-header">1. 예약자 정보 입력</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    dept = c1.selectbox("🏢 학과", dept_options, key="reg_dept")
    name = c2.text_input("👤 이름", placeholder="성함", key="reg_name")
    sid = c3.text_input("🆔 학번", placeholder="8자리", key="reg_sid")
    # 최소 인원 3명 설정
    count = c4.number_input("👥 인원 (최소 3명)", min_value=1, max_value=20, value=3)

    st.markdown('<div class="step-header">2. 스터디룸 및 시간 선택</div>', unsafe_allow_html=True)
    sc1, sc2, tc1, tc2 = st.columns([2, 1, 1, 1])
    room = sc1.selectbox("🚪 스터디룸", ["1번 스터디룸", "2번 스터디룸"], key="reg_room")
    date = sc2.date_input("📅 날짜", min_value=now.date(), max_value=now.date()+timedelta(days=13))
    st_t = tc1.selectbox("⏰ 시작", time_options, index=18)
    en_t = tc2.selectbox("⏰ 종료", time_options, index=20)

    if st.button("🚀 예약 신청하기"):
        if not (name.strip() and sid.strip()):
            st.error("이름과 학번을 입력해 주세요.")
        elif count < 3:
            st.error("🚫 스터디룸 이용 최소 인원은 3명입니다.")
        elif is_already_booked(name, sid):
            st.error("🚫 이미 등록된 예약이 존재합니다.")
        elif st_t >= en_t:
            st.error("시간 설정 오류")
        elif check_overlap(date, st_t, en_t, room):
            st.error("❌ 이미 예약된 시간입니다.")
        else:
            new_row = pd.DataFrame([[dept, name.strip(), sid.strip(), count, str(date), st_t, en_t, room, "미입실"]], 
                                    columns=["학과", "이름", "학번", "인원", "날짜", "시작", "종료", "방번호", "출석"])
            new_row.to_csv(DB_FILE, mode='a', header=not os.path.exists(DB_FILE), index=False, encoding='utf-8-sig')
            
            st.markdown(f"""
                <div class="success-box">
                    <h3 style="color: #3E7D6B; margin-top: 0;">예약 완료!</h3>
                    <p>📍 <b>{room}</b> | 📅 <b>{date}</b> | ⏰ <b>{st_t}~{en_t}</b></p>
                    <p style="color: #E74C3C;">⚠️ 시작 15분 내 문 앞 QR을 찍지 않으면 자동 취소됩니다.</p>
                </div>
            """, unsafe_allow_html=True)
            st.rerun()

# [관리자 메뉴] 개별 삭제 기능 포함
st.markdown('<div class="spacer" style="height:100px;"></div>', unsafe_allow_html=True)
with st.expander("🛠️ 관리자 전용 메뉴"):
    pw = st.text_input("PW", type="password")
    if pw == "bio1234":
        df_ad = get_latest_df()
        if not df_ad.empty:
            st.markdown("### 🗑️ 개별 삭제")
            df_ad['label'] = df_ad['이름'] + " | " + df_ad['날짜'] + " | " + df_ad['시작']
            target = st.selectbox("삭제 대상 선택", df_ad['label'].tolist())
            if st.button("❌ 선택 예약 삭제"):
                df_ad = df_ad[df_ad['label'] != target]
                df_ad.drop(columns=['label']).to_csv(DB_FILE, index=False, encoding='utf-8-sig')
                st.rerun()
            st.divider()
            st.dataframe(df_ad.drop(columns=['label']))
